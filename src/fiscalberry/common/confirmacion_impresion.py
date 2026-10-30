# coding=utf-8
"""
Confirmación de impresión: avisarle al servidor cómo terminó cada trabajo.

Por qué existe:
  El servidor encola la comanda (MQTT) y se queda sin saber si salió o no: el
  spooler durable imprime con reintentos, pero nada de eso se informaba. Si la
  impresora está sin papel o apagada, el comercio se entera cuando el cliente
  reclama la comida.

Qué hace:
  Al terminar cada trabajo del spooler (impreso, o error con motivo) hace un
  POST a `{sio_host}/{tenant}/printers/impresiones/confirmar.json`, identificado
  por el `jobId` que el servidor puso en el ticket. Es el mismo servidor y el mismo
  mecanismo HTTP que el discover. NO usa MQTT: el broker solo deja publicar al
  usuario del cliente en `fiscalberry.(errors|heartbeat).*`, y un topic nuevo le
  cerraría la conexión. Tampoco usa `publish_error()`: su rate-limit de 5 s por
  tipo de error descartaría confirmaciones legítimas.

Garantías:
  - Solo se confirma si el ticket trae `jobId` (string no vacío). El job_id del
    spooler que sale del sha1 de respaldo no lo conoce nadie más: no se envía nada.
  - Es best-effort: el envío corre en un hilo daemon propio con cola acotada, los
    `reportar_*` nunca lanzan y nunca demoran ni rompen la impresión.
  - Éxitos: siempre. Fallos que el spooler va a reintentar: el primero de cada
    trabajo y, después, como máximo uno cada 5 minutos por trabajo (una impresora
    caída se reintenta cada pocos minutos durante días: sin límite se inundaría al
    servidor). El fallo final (dead-letter) siempre.
  - 403/404 (el uuid no corresponde, o servidor viejo sin esta función) = no se
    reintenta y se SUSPENDEN todas las confirmaciones durante 30 minutos (en
    memoria): una ráfaga de 403/404 desde la IP del local puede hacer que el
    firewall del servidor banee la IP del comercio entero, y una comanda
    con varias copias o impresoras dispara varias confirmaciones seguidas. Otros
    4xx (400 inválido) = se descarta solo ese envío. Red/timeout/5xx = hasta 3
    reintentos con backoff 2, 4, 8 s y después se descarta con un warning.
  - Un solo worker serializa los envíos, uno detrás de otro y sin pausas artificiales.

Las funciones puras (`job_id_del_ticket`, `errores_en_resultado`, `armar_payload`,
`url_confirmacion`, ...) no tocan la red ni el config: se testean sin mocks.
"""

import json
import queue
import re
import threading
import time
from urllib.parse import quote

import requests

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.version import VERSION

logger = getLogger()

RUTA_CONFIRMACION = "printers/impresiones/confirmar.json"
MAX_LARGO_ERROR = 500
TIMEOUT_ENVIO = 15
# Esperas entre reintentos: 3 reintentos tras el primer intento (4 intentos en total).
ESPERAS_REINTENTO = (2, 4, 8)
MAX_COLA = 500
# Tras un 403/404 se deja de confirmar este tiempo (ver el docstring del módulo).
SUSPENSION_POR_RECHAZO = 30 * 60.0
# Mínimo entre dos avisos de FALLO no final del mismo trabajo.
INTERVALO_FALLO_NO_FINAL = 300.0
# Tope de trabajos recordados para el throttle (ver _debe_enviar_fallo).
MAX_TRABAJOS_THROTTLE = 1000
_UMBRAL_PODA_THROTTLE = 100

PREFIJO_IMPRESO_CON_ERRORES = "Impreso con errores: "

# Credenciales que no pueden salir del dispositivo aunque estén en el texto de una
# excepción (una URL de broker con usuario:clave, un "password=..." en un mensaje).
_RE_CLAVE_EN_URL = re.compile(r"(\b[a-z][a-z0-9+.\-]*://)[^/\s@]*:[^/\s@]*@", re.IGNORECASE)
_RE_CLAVE_ASIGNADA = re.compile(
    r"(\b(?:password|passwd|pwd|secret|token|authorization|api[_-]?key|credential)s?\b"
    r"\s*[=:]\s*)(?:(?:bearer|basic)\s+)?\S+",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------------

def job_id_del_ticket(ticket):
    """El `jobId` que puso el servidor en el ticket, o None si no hay uno válido.

    Solo vale un string no vacío: es el id que el servidor generó. Un ticket sin
    `jobId` (o con uno que no es string) no se confirma: el job_id del spooler en
    ese caso es un sha1 de respaldo que el servidor no conoce.
    """
    if not isinstance(ticket, dict):
        return None
    jid = ticket.get("jobId")
    if isinstance(jid, str) and jid.strip():
        return jid
    return None


def sanear_texto(texto, max_largo=MAX_LARGO_ERROR):
    """Texto de una sola línea, sin credenciales y recortado a `max_largo`."""
    texto = " ".join(str(texto).split())
    texto = _RE_CLAVE_EN_URL.sub(r"\1***@", texto)
    texto = _RE_CLAVE_ASIGNADA.sub(r"\1***", texto)
    if len(texto) > max_largo:
        texto = texto[:max_largo - 3] + "..."
    return texto


def motivo_de_excepcion(exc):
    """`"<TipoExcepcion>: <mensaje>"` saneado y recortado."""
    tipo = type(exc).__name__
    mensaje = str(exc).strip()
    return sanear_texto("%s: %s" % (tipo, mensaje) if mensaje else tipo)


def errores_en_resultado(result):
    """Acciones que fallaron dentro de un resultado de impresión "exitoso".

    `EscPComandos.run()` atrapa la excepción de cada acción y la agrega como
    `{"action": X, "rta": "Error: ..."}` sin relanzar; `runTraductor` devuelve
    `{"message": "Impresión exitosa", "result": [...]}` y el spooler lo toma como
    éxito aunque el ticket haya salido a medias. Devuelve la lista de
    `"<action>: <rta>"` de los items con error (vacía si no hay). Que una acción no
    exista ("Function not found") no cuenta como error de impresión.
    """
    items = result
    if isinstance(result, dict):
        items = result.get("result")
    if not isinstance(items, (list, tuple)):
        return []
    errores = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rta = item.get("rta")
        if isinstance(rta, str) and rta.lstrip().startswith("Error:"):
            errores.append("%s: %s" % (item.get("action"), rta))
    return errores


def motivo_impreso_con_errores(errores):
    """Motivo para un trabajo que salió pero con acciones fallidas."""
    return sanear_texto(PREFIJO_IMPRESO_CON_ERRORES + " | ".join(errores))


def armar_payload(uuid, job_id, ok, error, intentos, final, ts=None):
    """Body del POST de confirmación (función pura, testeable sin red)."""
    return {
        "uuid": uuid,
        "jobId": job_id,
        "ok": bool(ok),
        "error": None if ok else (error or "Error desconocido"),
        "intentos": int(intentos),
        "final": bool(final),
        "version": VERSION,
        "ts": ts if ts is not None else int(time.time()),
    }


def url_confirmacion(host, tenant):
    """`{sio_host}/{tenant}/printers/impresiones/confirmar.json`."""
    return "%s/%s/%s" % (str(host).strip().rstrip("/"), quote(str(tenant).strip(), safe=""),
                        RUTA_CONFIRMACION)


# ---------------------------------------------------------------------------
# Envío en segundo plano
# ---------------------------------------------------------------------------

class ConfirmadorImpresion:
    """Cola acotada + hilo daemon que envía las confirmaciones al servidor.

    El hilo no arranca hasta la primera confirmación (import-safe). `uuid`,
    `sio_host`, `tenant` y la verificación TLS se leen del Configberry en CADA
    envío, sin cachear: el comercio puede reasignarse desde la plataforma
    (ver tests/test_cambio_de_tenant.py).

    Los parámetros inyectables (`configberry`, `post`, `dormir`, `reloj`,
    `esperas`, `suspension`, `arrancar_worker`) existen para testear sin red ni
    sleeps.
    """

    def __init__(self, configberry=None, post=None, dormir=None, reloj=None,
                 esperas=ESPERAS_REINTENTO, max_cola=MAX_COLA, arrancar_worker=True,
                 suspension=SUSPENSION_POR_RECHAZO):
        self._configberry = configberry
        self._post = post
        self._detenido = threading.Event()
        self._dormir = dormir or self._detenido.wait
        self._reloj = reloj or time.monotonic
        self._esperas = tuple(esperas)
        self._suspension = suspension
        # Instante (según `reloj`) hasta el cual no se confirma nada; 0 = no suspendido.
        self._suspendido_hasta = 0.0
        self._arrancar_worker = arrancar_worker
        self._cola = queue.Queue(maxsize=max_cola)
        self._lock = threading.Lock()
        self._worker = None
        # job_id -> instante del último aviso de fallo no final (orden = recencia).
        self._ultimo_fallo = {}

    # -- API para el spooler -------------------------------------------------

    def reportar_exito(self, job_id, ticket, result, intentos=1):
        """Callback `on_success` del spooler. Nunca lanza.

        Si el resultado trae acciones con error ("Impreso con errores") se reporta
        como fallo final, sin relanzar: relanzar reimprimiría el ticket parcial.
        """
        try:
            jid = job_id_del_ticket(ticket)
            if not jid or self._suspendida(jid):
                return False
            self._olvidar_fallos(jid)
            errores = errores_en_resultado(result)
            if errores:
                motivo = motivo_impreso_con_errores(errores)
                logger.warning("CONFIRMACION:: job %s impreso con errores: %s", jid, motivo)
                return self._encolar(armar_payload(None, jid, False, motivo, intentos, True))
            return self._encolar(armar_payload(None, jid, True, None, intentos, True))
        except Exception as e:
            logger.warning("CONFIRMACION:: error armando la confirmación de %s: %s", job_id, e)
            return False

    def reportar_fallo(self, job_id, ticket, exc, intentos, final):
        """Callback `on_failure` del spooler. Nunca lanza.

        `final` = el spooler no lo va a reintentar (dead-letter). Un fallo no final
        se avisa la primera vez y, después, a lo sumo cada 5 minutos por trabajo.
        """
        try:
            jid = job_id_del_ticket(ticket)
            if not jid or self._suspendida(jid):
                return False
            if final:
                self._olvidar_fallos(jid)
            elif not self._debe_enviar_fallo(jid):
                return False
            return self._encolar(
                armar_payload(None, jid, False, motivo_de_excepcion(exc), intentos, final))
        except Exception as e:
            logger.warning("CONFIRMACION:: error armando la confirmación de %s: %s", job_id, e)
            return False

    # -- Suspensión tras un 403/404 --------------------------------------------

    def _suspendida(self, jid):
        """True si las confirmaciones están suspendidas (y deja un log debug)."""
        with self._lock:
            hasta = self._suspendido_hasta
            if not hasta:
                return False
            if self._reloj() >= hasta:
                self._suspendido_hasta = 0.0
                return False
        logger.debug("CONFIRMACION:: confirmaciones suspendidas: se descarta la del job %s", jid)
        return True

    def _suspender(self, status):
        with self._lock:
            self._suspendido_hasta = self._reloj() + self._suspension
        logger.warning(
            "CONFIRMACION:: el servidor contestó %s: se suspenden las confirmaciones de "
            "impresión por %d min (servidor sin esta función, o el uuid no corresponde)",
            status, int(self._suspension // 60))

    # -- Throttle de fallos no finales ----------------------------------------

    def _debe_enviar_fallo(self, jid):
        ahora = self._reloj()
        with self._lock:
            ultimo = self._ultimo_fallo.get(jid)
            if ultimo is not None and ahora - ultimo < INTERVALO_FALLO_NO_FINAL:
                return False
            # Se reinserta para que el orden del dict sea el de recencia.
            self._ultimo_fallo.pop(jid, None)
            self._ultimo_fallo[jid] = ahora
            self._podar_fallos(ahora)
            return True

    def _podar_fallos(self, ahora):
        """Mantiene acotado el dict del throttle (llamar con el lock tomado).

        Un registro vencido equivale a no tenerlo (el próximo fallo se envía igual),
        así que podar lo vencido no cambia ninguna decisión. El tope duro solo
        actúa si hay más de MAX_TRABAJOS_THROTTLE trabajos fallando a la vez.
        """
        if len(self._ultimo_fallo) <= _UMBRAL_PODA_THROTTLE:
            return
        vencidos = [j for j, t in self._ultimo_fallo.items()
                    if ahora - t >= INTERVALO_FALLO_NO_FINAL]
        for j in vencidos:
            del self._ultimo_fallo[j]
        while len(self._ultimo_fallo) > MAX_TRABAJOS_THROTTLE:
            del self._ultimo_fallo[next(iter(self._ultimo_fallo))]

    def _olvidar_fallos(self, jid):
        with self._lock:
            self._ultimo_fallo.pop(jid, None)

    # -- Cola y worker --------------------------------------------------------

    def _encolar(self, payload):
        """Pone el payload en la cola acotada (descarta el más viejo si está llena)."""
        try:
            self._cola.put_nowait(payload)
        except queue.Full:
            try:
                viejo = self._cola.get_nowait()
                self._cola.task_done()
                logger.warning(
                    "CONFIRMACION:: cola llena (%d): se descarta la confirmación más vieja (job %s)",
                    self._cola.maxsize, viejo.get("jobId"))
            except queue.Empty:
                pass
            try:
                self._cola.put_nowait(payload)
            except queue.Full:
                logger.warning("CONFIRMACION:: cola llena: se descarta la confirmación del job %s",
                               payload.get("jobId"))
                return False
        self._asegurar_worker()
        return True

    def _asegurar_worker(self):
        if not self._arrancar_worker:
            return
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._run, name="confirmacion-impresion", daemon=True)
            self._worker.start()

    def _run(self):
        while not self._detenido.is_set():
            try:
                payload = self._cola.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                self._enviar(payload)
            except Exception as e:  # el worker nunca puede morir
                logger.warning("CONFIRMACION:: error inesperado enviando: %s", e)
            finally:
                self._cola.task_done()

    def procesar_pendientes(self):
        """Envía en el hilo actual todo lo encolado (para tests sin worker)."""
        while True:
            try:
                payload = self._cola.get_nowait()
            except queue.Empty:
                return
            try:
                self._enviar(payload)
            finally:
                self._cola.task_done()

    def detener(self):
        """Detiene el worker (no espera lo pendiente: es best-effort)."""
        self._detenido.set()

    # -- HTTP -----------------------------------------------------------------

    def _cfg(self):
        if self._configberry is None:
            from fiscalberry.common.Configberry import Configberry
            self._configberry = Configberry()
        return self._configberry

    def _enviar(self, payload):
        """Resuelve destino y envía con reintentos. Devuelve True si el servidor lo registró."""
        jid = payload.get("jobId")
        if self._suspendida(jid):      # ya estaba en la cola cuando se suspendió
            return False
        cfg = self._cfg()
        uuid = (cfg.get("SERVIDOR", "uuid", fallback="") or "").strip()
        host = (cfg.get("SERVIDOR", "sio_host", fallback="") or "").strip()
        tenant = (cfg.get("Paxaprinter", "tenant", fallback="") or "").strip()
        if not uuid or not host or not tenant:
            logger.debug("CONFIRMACION:: falta uuid, sio_host o tenant: no se confirma el job %s", jid)
            return False

        # El uuid se resuelve acá, no al encolar: es el del config vigente al enviar.
        payload = dict(payload, uuid=uuid)
        url = url_confirmacion(host, tenant)
        verify = cfg.get_ssl_verify()
        if verify is False:
            # Mismo criterio que el discover: warning de urllib3 silenciado solo cuando
            # la verificación se desactivó a propósito (entornos de desarrollo).
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        cuerpo = json.dumps(payload, default=str)
        post = self._post or requests.post

        intentos_max = len(self._esperas) + 1
        for n in range(1, intentos_max + 1):
            motivo = None
            try:
                ret = post(url, headers=headers, data=cuerpo, timeout=TIMEOUT_ENVIO, verify=verify)
                status = ret.status_code
                if 200 <= status < 300:
                    logger.debug("CONFIRMACION:: job %s registrado en el servidor (ok=%s)",
                                 jid, payload.get("ok"))
                    return True
                if status in (403, 404):
                    # El uuid no corresponde, o servidor viejo sin esta función: reintentar
                    # no lo arregla y la ráfaga puede hacer banear la IP del local.
                    self._suspender(status)
                    return False
                if status < 500:
                    # 400 inválido (o cualquier otro 4xx): se descarta solo este envío.
                    logger.info("CONFIRMACION:: el servidor contestó %s a la confirmación del "
                                "job %s; se descarta (no se reintenta)", status, jid)
                    return False
                motivo = "el servidor contestó %s" % status
            except Exception as e:
                motivo = sanear_texto("%s: %s" % (type(e).__name__, e), 200)
            if n < intentos_max:
                logger.debug("CONFIRMACION:: job %s intento %d/%d falló (%s); reintenta en %ss",
                             jid, n, intentos_max, motivo, self._esperas[n - 1])
                self._dormir(self._esperas[n - 1])
                if self._detenido.is_set():
                    return False
            else:
                logger.warning("CONFIRMACION:: no se pudo confirmar el job %s tras %d intentos (%s); "
                               "se descarta", jid, intentos_max, motivo)
        return False


# ---------------------------------------------------------------------------
# Singleton para el spooler del proceso
# ---------------------------------------------------------------------------
_confirmador = None
_confirmador_lock = threading.Lock()


def get_confirmador():
    """Confirmador compartido del proceso (lazy)."""
    global _confirmador
    if _confirmador is None:
        with _confirmador_lock:
            if _confirmador is None:
                _confirmador = ConfirmadorImpresion()
    return _confirmador
