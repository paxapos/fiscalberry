# coding=utf-8
"""
Confirmación de impresión: el cliente le avisa al servidor cómo terminó cada
trabajo del spooler (impreso, o error con motivo), identificado por el `jobId`
que el servidor puso en el ticket.

Lo que estos tests fijan:
  - URL, headers y body del POST;
  - sin `jobId` (o sin uuid / sio_host / tenant) no se envía nada;
  - "Impreso con errores": EscPComandos.run() atrapa el error de cada acción y
    el resultado igual se ve "exitoso"; se reporta como fallo SIN relanzar;
  - throttle de fallos no finales (primero sí, luego 1 cada 5 min, final siempre);
  - 4xx no se reintenta; red/timeout/5xx sí, con backoff 2, 4, 8 s;
  - nada de esto puede demorar ni romper la impresión (nunca lanza, cola acotada).

Sin red real ni sleeps: `requests.post`, el reloj y el backoff se inyectan.
"""

import json
import threading
import time

import pytest

pytest.importorskip("requests")

import requests  # noqa: E402

from fiscalberry.common import confirmacion_impresion as ci  # noqa: E402
from fiscalberry.common.confirmacion_impresion import ConfirmadorImpresion  # noqa: E402
from fiscalberry.common.print_spooler import DurablePrintSpooler  # noqa: E402
from fiscalberry.version import VERSION  # noqa: E402


def _wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class ConfigFalso:
    """Misma interfaz que usa el confirmador de Configberry."""

    def __init__(self, uuid="uuid-del-equipo", host="https://server.test", tenant="comercio_demo",
                 verify=True):
        self.valores = {
            ("SERVIDOR", "uuid"): uuid,
            ("SERVIDOR", "sio_host"): host,
            ("Paxaprinter", "tenant"): tenant,
        }
        self.verify = verify

    def get(self, seccion, clave, fallback=None):
        return self.valores.get((seccion, clave), fallback)

    def get_ssl_verify(self):
        return self.verify


class RespuestaFalsa:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""


class PostFalso:
    """Reemplazo de requests.post: guarda las llamadas y responde lo configurado.

    Cada respuesta es un status HTTP (int) o una excepción a lanzar; la última se repite.
    """

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas) or [200]
        self.llamadas = []

    def __call__(self, url, **kwargs):
        self.llamadas.append((url, kwargs))
        r = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(r, Exception):
            raise r
        return RespuestaFalsa(r)

    def bodies(self):
        return [json.loads(kw["data"]) for _, kw in self.llamadas]


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _confirmador(cfg=None, post=None, **kw):
    """Confirmador sin hilo: se vacía a mano con procesar_pendientes()."""
    dormidos = []
    c = ConfirmadorImpresion(
        configberry=cfg or ConfigFalso(),
        post=post or PostFalso(200),
        dormir=dormidos.append,
        arrancar_worker=False,
        **kw)
    c.dormidos = dormidos
    return c


TICKET = {"printerName": "cocina", "jobId": "comanda-77-abc123", "printComanda": {"x": 1}}


# ---------------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------------

def test_url_confirmacion():
    assert ci.url_confirmacion("https://server.test", "comercio_demo") == \
        "https://server.test/comercio_demo/printers/impresiones/confirmar.json"


def test_url_confirmacion_tolera_barra_final_y_escapa_el_tenant():
    assert ci.url_confirmacion("https://server.test/", " mi/tenant ") == \
        "https://server.test/mi%2Ftenant/printers/impresiones/confirmar.json"


def test_payload_de_exito():
    p = ci.armar_payload("u-1", "job-1", True, None, 1, True, ts=1730000000)
    assert p == {
        "uuid": "u-1", "jobId": "job-1", "ok": True, "error": None,
        "intentos": 1, "final": True, "version": VERSION, "ts": 1730000000,
    }


def test_payload_de_error_y_ts_por_defecto():
    antes = int(time.time())
    p = ci.armar_payload("u-1", "job-1", False, "PrintJobError: sin papel", 3, False)
    assert p["ok"] is False
    assert p["error"] == "PrintJobError: sin papel"
    assert p["intentos"] == 3 and p["final"] is False
    assert antes <= p["ts"] <= int(time.time())
    json.dumps(p)  # serializable


def test_payload_ok_nunca_lleva_error():
    assert ci.armar_payload("u", "j", True, "algo", 1, True)["error"] is None


@pytest.mark.parametrize("ticket,esperado", [
    ({"jobId": "abc"}, "abc"),
    ({"jobId": ""}, None),
    ({"jobId": "   "}, None),
    ({"jobId": 55}, None),
    ({"jobId": None}, None),
    ({"printerName": "x"}, None),
    (None, None),
    ("jobId", None),
])
def test_job_id_del_ticket(ticket, esperado):
    assert ci.job_id_del_ticket(ticket) == esperado


def test_errores_en_resultado_detecta_acciones_con_error():
    result = {"message": "Impresión exitosa", "result": [
        {"action": "printComanda", "rta": "Error: Device not found"},
        {"action": "openDrawer", "rta": True},
    ]}
    assert ci.errores_en_resultado(result) == ["printComanda: Error: Device not found"]


def test_errores_en_resultado_junta_varios():
    result = {"result": [
        {"action": "printComanda", "rta": "Error: sin papel"},
        {"action": "openDrawer", "rta": "Error: no responde"},
    ]}
    assert ci.errores_en_resultado(result) == [
        "printComanda: Error: sin papel", "openDrawer: Error: no responde"]


def test_errores_en_resultado_acepta_la_lista_directa():
    assert ci.errores_en_resultado([{"action": "a", "rta": "Error: x"}]) == ["a: Error: x"]


def test_function_not_found_no_es_error():
    result = {"result": [{"action": "jobId", "rta": "Function not found"}]}
    assert ci.errores_en_resultado(result) == []


@pytest.mark.parametrize("result", [
    None,
    "ok",
    {"message": "Impresion RAW exitosa", "result": "ok", "bytes": 10},
    {"result": []},
    {"result": [{"action": "a", "rta": None}, "basura", {"sin": "rta"}]},
    {"result": [{"action": "a", "rta": {"Error:": "no es string"}}]},
])
def test_errores_en_resultado_sin_errores(result):
    assert ci.errores_en_resultado(result) == []


def test_motivo_de_excepcion():
    assert ci.motivo_de_excepcion(ValueError("sin papel")) == "ValueError: sin papel"
    assert ci.motivo_de_excepcion(RuntimeError()) == "RuntimeError"


def test_motivo_se_recorta_a_500_y_queda_en_una_linea():
    motivo = ci.motivo_de_excepcion(RuntimeError("linea uno\nlinea dos\t" + "x" * 2000))
    assert len(motivo) == 500
    assert motivo.endswith("...")
    assert "\n" not in motivo and "\t" not in motivo


@pytest.mark.parametrize("mensaje,secreto", [
    ("no conecta a amqp://fiscalberry:S3cr3t@broker.test:5672/", "S3cr3t"),
    ("fallo con password=Hunter2 y listo", "Hunter2"),
    ("config invalida: token: abc123xyz", "abc123xyz"),
    ("Authorization: Bearer eyJhbGciOi", "eyJhbGciOi"),
])
def test_motivo_no_filtra_credenciales(mensaje, secreto):
    assert secreto not in ci.motivo_de_excepcion(RuntimeError(mensaje))


def test_motivo_impreso_con_errores():
    m = ci.motivo_impreso_con_errores(["printComanda: Error: sin papel", "openDrawer: Error: x"])
    assert m == "Impreso con errores: printComanda: Error: sin papel | openDrawer: Error: x"
    assert len(ci.motivo_impreso_con_errores(["a: Error: " + "x" * 1000])) == 500


# ---------------------------------------------------------------------------
# Qué se envía y cuándo
# ---------------------------------------------------------------------------

def test_exito_envia_el_post_del_contrato():
    post = PostFalso(200)
    c = _confirmador(post=post)

    assert c.reportar_exito("comanda-77-abc123", TICKET, {"result": []}, 1) is True
    c.procesar_pendientes()

    assert len(post.llamadas) == 1
    url, kw = post.llamadas[0]
    assert url == "https://server.test/comercio_demo/printers/impresiones/confirmar.json"
    assert kw["headers"] == {"Content-Type": "application/json", "Accept": "application/json"}
    assert kw["timeout"] == 15
    assert kw["verify"] is True
    body = post.bodies()[0]
    assert body.pop("ts") > 0
    assert body == {
        "uuid": "uuid-del-equipo", "jobId": "comanda-77-abc123", "ok": True, "error": None,
        "intentos": 1, "final": True, "version": VERSION,
    }


def test_usa_el_verify_del_config():
    post = PostFalso(200)
    c = _confirmador(cfg=ConfigFalso(verify="/ruta/ca.pem"), post=post)
    c.reportar_exito("j", TICKET, None, 1)
    c.procesar_pendientes()
    assert post.llamadas[0][1]["verify"] == "/ruta/ca.pem"


@pytest.mark.parametrize("ticket", [
    {"printerName": "cocina", "printComanda": {}},
    {"printerName": "cocina", "jobId": ""},
    {"printerName": "cocina", "jobId": 123},
    None,
])
def test_sin_job_id_no_se_envia_nada(ticket):
    """El job_id del spooler sale del sha1 de respaldo: el servidor no lo conoce."""
    post = PostFalso(200)
    c = _confirmador(post=post)

    assert c.reportar_exito("sha1-de-respaldo", ticket, {"result": []}, 1) is False
    assert c.reportar_fallo("sha1-de-respaldo", ticket, RuntimeError("x"), 1, True) is False
    c.procesar_pendientes()

    assert post.llamadas == []


@pytest.mark.parametrize("faltante", [
    {"uuid": ""}, {"host": ""}, {"tenant": ""}, {"uuid": None}, {"tenant": "   "},
])
def test_sin_uuid_sio_host_o_tenant_no_se_envia(faltante):
    post = PostFalso(200)
    c = _confirmador(cfg=ConfigFalso(**faltante), post=post)

    c.reportar_exito("j", TICKET, None, 1)
    c.procesar_pendientes()

    assert post.llamadas == []


def test_el_config_se_lee_en_cada_envio_y_no_se_cachea():
    """El tenant puede reasignarse desde la plataforma (test_cambio_de_tenant.py)."""
    cfg = ConfigFalso(tenant="comercio_viejo")
    post = PostFalso(200)
    c = _confirmador(cfg=cfg, post=post)

    c.reportar_exito("j1", dict(TICKET, jobId="j1"), None, 1)
    c.procesar_pendientes()
    cfg.valores[("Paxaprinter", "tenant")] = "comercio_nuevo"
    cfg.valores[("SERVIDOR", "sio_host")] = "https://otro.test"
    c.reportar_exito("j2", dict(TICKET, jobId="j2"), None, 1)
    c.procesar_pendientes()

    assert post.llamadas[0][0] == \
        "https://server.test/comercio_viejo/printers/impresiones/confirmar.json"
    assert post.llamadas[1][0] == \
        "https://otro.test/comercio_nuevo/printers/impresiones/confirmar.json"


def test_impreso_con_errores_se_reporta_como_fallo_final():
    post = PostFalso(200)
    c = _confirmador(post=post)
    result = {"message": "Impresión exitosa", "result": [
        {"action": "printComanda", "rta": "Error: Device not found"},
        {"action": "jobId", "rta": "Function not found"},
    ]}

    c.reportar_exito("comanda-77-abc123", TICKET, result, 2)
    c.procesar_pendientes()

    body = post.bodies()[0]
    assert body["ok"] is False
    assert body["final"] is True
    assert body["intentos"] == 2
    assert body["error"] == "Impreso con errores: printComanda: Error: Device not found"


def test_fallo_no_final_lleva_motivo_e_intentos():
    post = PostFalso(200)
    c = _confirmador(post=post)

    c.reportar_fallo("j", TICKET, OSError("Impresora sin papel"), 2, False)
    c.procesar_pendientes()

    body = post.bodies()[0]
    assert body["ok"] is False and body["final"] is False and body["intentos"] == 2
    assert body["error"] == "OSError: Impresora sin papel"


# ---------------------------------------------------------------------------
# Throttle de fallos no finales
# ---------------------------------------------------------------------------

def test_throttle_primer_fallo_si_segundo_dentro_de_5_min_no_final_si():
    reloj = Reloj()
    post = PostFalso(200)
    c = _confirmador(post=post, reloj=reloj)
    exc = RuntimeError("sin papel")

    assert c.reportar_fallo("j", TICKET, exc, 1, False) is True       # el primero
    reloj.t += 60
    assert c.reportar_fallo("j", TICKET, exc, 2, False) is False      # dentro de 5 min
    reloj.t += 239
    assert c.reportar_fallo("j", TICKET, exc, 3, False) is False      # 299 s: todavía no
    reloj.t += 1
    assert c.reportar_fallo("j", TICKET, exc, 4, False) is True       # 300 s: ya
    reloj.t += 1
    assert c.reportar_fallo("j", TICKET, exc, 5, True) is True        # el final siempre

    c.procesar_pendientes()
    assert [b["intentos"] for b in post.bodies()] == [1, 4, 5]
    assert [b["final"] for b in post.bodies()] == [False, False, True]


def test_throttle_es_por_trabajo():
    c = _confirmador(reloj=Reloj())
    exc = RuntimeError("x")
    assert c.reportar_fallo("a", dict(TICKET, jobId="a"), exc, 1, False) is True
    assert c.reportar_fallo("b", dict(TICKET, jobId="b"), exc, 1, False) is True
    assert c.reportar_fallo("a", dict(TICKET, jobId="a"), exc, 2, False) is False


def test_el_exito_siempre_se_envia_y_reinicia_el_throttle():
    reloj = Reloj()
    c = _confirmador(reloj=reloj)
    exc = RuntimeError("x")
    c.reportar_fallo("j", TICKET, exc, 1, False)
    assert c.reportar_exito("j", TICKET, {"result": []}, 2) is True
    assert c.reportar_exito("j", TICKET, {"result": []}, 3) is True   # los éxitos no se limitan
    assert "j" not in c._ultimo_fallo


def test_el_fallo_final_siempre_se_envia_aunque_haya_uno_reciente():
    c = _confirmador(reloj=Reloj())
    exc = RuntimeError("x")
    c.reportar_fallo("j", TICKET, exc, 1, False)
    assert c.reportar_fallo("j", TICKET, exc, 2, True) is True
    assert "j" not in c._ultimo_fallo


def test_el_registro_del_throttle_esta_acotado(monkeypatch):
    monkeypatch.setattr(ci, "MAX_TRABAJOS_THROTTLE", 150)
    reloj = Reloj()
    c = _confirmador(reloj=reloj, max_cola=10)
    exc = RuntimeError("x")

    for i in range(400):
        c.reportar_fallo("j%d" % i, dict(TICKET, jobId="j%d" % i), exc, 1, False)

    assert len(c._ultimo_fallo) <= 150
    # Lo vencido se poda sin cambiar ninguna decisión: pasado el intervalo se vuelve a avisar.
    reloj.t += ci.INTERVALO_FALLO_NO_FINAL + 1
    assert c.reportar_fallo("j399", dict(TICKET, jobId="j399"), exc, 2, False) is True


# ---------------------------------------------------------------------------
# Reintentos y respuestas del servidor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [400, 403, 404, 422])
def test_4xx_no_se_reintenta(status):
    post = PostFalso(status)
    c = _confirmador(post=post)

    c.reportar_exito("j", TICKET, None, 1)
    c.procesar_pendientes()

    assert len(post.llamadas) == 1
    assert c.dormidos == []


@pytest.mark.parametrize("status", [400, 422])
def test_otros_4xx_descartan_solo_ese_envio_y_no_suspenden(status):
    post = PostFalso(status, 200)
    c = _confirmador(post=post)

    c.reportar_exito("j1", dict(TICKET, jobId="j1"), None, 1)
    c.reportar_exito("j2", dict(TICKET, jobId="j2"), None, 1)
    c.procesar_pendientes()

    assert [b["jobId"] for b in post.bodies()] == ["j1", "j2"]


@pytest.mark.parametrize("status", [403, 404])
def test_403_y_404_suspenden_las_confirmaciones_30_minutos(status):
    """Una ráfaga de 403/404 desde la IP del local la hace banear por el firewall del servidor."""
    reloj = Reloj()
    post = PostFalso(status, 200)
    c = _confirmador(post=post, reloj=reloj)
    assert ci.SUSPENSION_POR_RECHAZO == 30 * 60

    c.reportar_exito("j1", dict(TICKET, jobId="j1"), None, 1)
    # Ya encoladas cuando llega el rechazo: se descartan sin llamar a post.
    c.reportar_exito("j2", dict(TICKET, jobId="j2"), None, 1)
    c.reportar_exito("j3", dict(TICKET, jobId="j3"), None, 1)
    c.procesar_pendientes()
    assert len(post.llamadas) == 1

    # Mientras dura la suspensión no se encola ni se envía nada (éxitos, fallos y finales).
    reloj.t += 30 * 60 - 1
    assert c.reportar_exito("j4", dict(TICKET, jobId="j4"), None, 1) is False
    assert c.reportar_fallo("j5", dict(TICKET, jobId="j5"), RuntimeError("x"), 1, False) is False
    assert c.reportar_fallo("j6", dict(TICKET, jobId="j6"), RuntimeError("x"), 9, True) is False
    c.procesar_pendientes()
    assert len(post.llamadas) == 1

    # Vencida la suspensión, vuelve a enviar.
    reloj.t += 1
    assert c.reportar_exito("j7", dict(TICKET, jobId="j7"), None, 1) is True
    c.procesar_pendientes()
    assert [b["jobId"] for b in post.bodies()] == ["j1", "j7"]


def test_la_duracion_de_la_suspension_es_inyectable():
    reloj = Reloj()
    post = PostFalso(404, 200)
    c = _confirmador(post=post, reloj=reloj, suspension=10)

    c.reportar_exito("j1", dict(TICKET, jobId="j1"), None, 1)
    c.procesar_pendientes()
    reloj.t += 9
    assert c.reportar_exito("j2", dict(TICKET, jobId="j2"), None, 1) is False
    reloj.t += 1
    assert c.reportar_exito("j3", dict(TICKET, jobId="j3"), None, 1) is True
    c.procesar_pendientes()

    assert [b["jobId"] for b in post.bodies()] == ["j1", "j3"]


def test_una_rafaga_de_comandas_con_servidor_viejo_hace_un_solo_post():
    """Una comanda con varias copias/impresoras dispara varias confirmaciones seguidas."""
    post = PostFalso(404)
    c = _confirmador(post=post, reloj=Reloj())

    for i in range(12):
        c.reportar_exito("j%d" % i, dict(TICKET, jobId="j%d" % i), None, 1)
    c.procesar_pendientes()

    assert len(post.llamadas) == 1


def test_si_vuelve_a_dar_404_tras_la_suspension_se_suspende_otra_vez():
    reloj = Reloj()
    post = PostFalso(404)
    c = _confirmador(post=post, reloj=reloj)

    c.reportar_exito("j1", dict(TICKET, jobId="j1"), None, 1)
    c.procesar_pendientes()
    reloj.t += ci.SUSPENSION_POR_RECHAZO
    c.reportar_exito("j2", dict(TICKET, jobId="j2"), None, 1)
    c.procesar_pendientes()
    assert len(post.llamadas) == 2
    assert c.reportar_exito("j3", dict(TICKET, jobId="j3"), None, 1) is False


def test_un_error_de_red_no_suspende():
    post = PostFalso(requests.exceptions.ConnectionError("sin red"), 500, 500, 500, 200)
    c = _confirmador(post=post)

    c.reportar_exito("j1", dict(TICKET, jobId="j1"), None, 1)
    c.reportar_exito("j2", dict(TICKET, jobId="j2"), None, 1)
    c.procesar_pendientes()

    assert [b["jobId"] for b in post.bodies()] == ["j1"] * 4 + ["j2"]


def test_error_de_red_reintenta_con_backoff_y_despues_descarta():
    post = PostFalso(requests.exceptions.ConnectionError("sin red"))
    c = _confirmador(post=post)

    c.reportar_exito("j", TICKET, None, 1)
    c.procesar_pendientes()   # no lanza

    assert len(post.llamadas) == 4            # el primero + 3 reintentos
    assert c.dormidos == [2, 4, 8]


def test_timeout_reintenta():
    post = PostFalso(requests.exceptions.Timeout("lento"), 200)
    c = _confirmador(post=post)

    c.reportar_exito("j", TICKET, None, 1)
    c.procesar_pendientes()

    assert len(post.llamadas) == 2
    assert c.dormidos == [2]


def test_5xx_reintenta_hasta_que_anda():
    post = PostFalso(503, 502, 200)
    c = _confirmador(post=post)

    c.reportar_exito("j", TICKET, None, 1)
    c.procesar_pendientes()

    assert len(post.llamadas) == 3
    assert c.dormidos == [2, 4]


def test_5xx_persistente_se_descarta_tras_3_reintentos():
    post = PostFalso(500)
    c = _confirmador(post=post)

    c.reportar_exito("j", TICKET, None, 1)
    c.procesar_pendientes()

    assert len(post.llamadas) == 4
    assert c.dormidos == [2, 4, 8]


def test_los_reintentos_reenvian_el_mismo_body():
    post = PostFalso(500, 200)
    c = _confirmador(post=post)

    c.reportar_exito("j", TICKET, None, 1)
    c.procesar_pendientes()

    a, b = post.bodies()
    assert a == b


def test_un_error_del_servidor_en_un_envio_no_frena_los_siguientes():
    post = PostFalso(400, 200)
    c = _confirmador(post=post)

    c.reportar_exito("j1", dict(TICKET, jobId="j1"), None, 1)
    c.reportar_exito("j2", dict(TICKET, jobId="j2"), None, 1)
    c.procesar_pendientes()

    assert [b["jobId"] for b in post.bodies()] == ["j1", "j2"]


# ---------------------------------------------------------------------------
# Nunca demorar ni romper la impresión
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("llamada", [
    lambda c: c.reportar_exito("j", TICKET, object(), "no-es-un-numero"),
    lambda c: c.reportar_fallo("j", TICKET, None, "no-es-un-numero", False),
    lambda c: c.reportar_fallo("j", object(), RuntimeError("x"), 1, True),
    lambda c: c.reportar_exito(None, {"jobId": "j"}, {"result": object()}, None),
])
def test_reportar_nunca_lanza(llamada):
    c = _confirmador()
    llamada(c)   # si lanzara, el test falla


def test_cola_acotada_descarta_la_mas_vieja(monkeypatch):
    avisos = []
    monkeypatch.setattr(ci, "logger", type("L", (), {
        "warning": staticmethod(lambda *a, **k: avisos.append(a)),
        "debug": staticmethod(lambda *a, **k: None),
        "info": staticmethod(lambda *a, **k: None),
    }))
    post = PostFalso(200)
    c = _confirmador(post=post, max_cola=2)

    for jid in ("j1", "j2", "j3"):
        assert c.reportar_exito(jid, dict(TICKET, jobId=jid), None, 1) is True
    assert c._cola.qsize() == 2
    assert avisos, "tiene que dejar un warning al descartar"

    c.procesar_pendientes()
    assert [b["jobId"] for b in post.bodies()] == ["j2", "j3"]


def test_el_worker_envia_en_segundo_plano():
    post = PostFalso(200)
    c = ConfirmadorImpresion(configberry=ConfigFalso(), post=post, dormir=lambda s: None)
    try:
        c.reportar_exito("j", TICKET, None, 1)
        assert _wait_until(lambda: len(post.llamadas) == 1)
        assert c._worker.daemon is True
    finally:
        c.detener()


def test_un_servidor_lento_no_demora_a_quien_reporta():
    """El POST corre en el hilo del confirmador: reportar_* vuelve de inmediato."""
    liberar = threading.Event()
    entro = threading.Event()

    def post_colgado(url, **kwargs):
        entro.set()
        liberar.wait(timeout=5)
        return RespuestaFalsa(200)

    c = ConfirmadorImpresion(configberry=ConfigFalso(), post=post_colgado, dormir=lambda s: None)
    try:
        t0 = time.time()
        for i in range(5):
            c.reportar_exito("j%d" % i, dict(TICKET, jobId="j%d" % i), None, 1)
        assert time.time() - t0 < 1.0
        assert entro.wait(timeout=2)
    finally:
        liberar.set()
        c.detener()


# ---------------------------------------------------------------------------
# Integración con el spooler real
# ---------------------------------------------------------------------------

def test_spooler_confirma_impreso_y_impreso_con_errores(tmp_path):
    post = PostFalso(200)
    c = ConfirmadorImpresion(configberry=ConfigFalso(), post=post, dormir=lambda s: None)

    def print_fn(ticket):
        if ticket.get("jobId") == "con-errores":
            return {"message": "Impresión exitosa",
                    "result": [{"action": "printComanda", "rta": "Error: sin papel"}]}
        return {"message": "Impresión exitosa", "result": [{"action": "printComanda", "rta": True}]}

    sp = DurablePrintSpooler(print_fn, db_path=str(tmp_path / "s.db"), base_delay=0.05,
                             idle_wait=0.1, on_success=c.reportar_exito,
                             on_failure=c.reportar_fallo)
    try:
        sp.enqueue("bien", {"printerName": "p", "jobId": "bien"}, "p")
        sp.enqueue("con-errores", {"printerName": "p", "jobId": "con-errores"}, "p")
        sp.enqueue("sin-job-id-del-servidor", {"printerName": "p"}, "p")
        assert _wait_until(lambda: len(post.llamadas) == 2)
        assert _wait_until(lambda: sp.pending_count() == 0)
        fallidos = sp.failed_count()
    finally:
        sp.stop()
        c.detener()

    por_job = {b["jobId"]: b for b in post.bodies()}
    assert set(por_job) == {"bien", "con-errores"}     # el ticket sin jobId no se confirma
    assert por_job["bien"]["ok"] is True and por_job["bien"]["error"] is None
    assert por_job["con-errores"]["ok"] is False and por_job["con-errores"]["final"] is True
    assert por_job["con-errores"]["error"].startswith("Impreso con errores: printComanda")
    assert fallidos == 0     # no se reimprimió: relanzar duplicaría un ticket parcial


def test_spooler_confirma_fallos_con_throttle_y_el_dead_letter(tmp_path):
    post = PostFalso(200)
    c = ConfirmadorImpresion(configberry=ConfigFalso(), post=post, dormir=lambda s: None)

    def print_fn(ticket):
        raise IOError("Impresora apagada")

    sp = DurablePrintSpooler(print_fn, db_path=str(tmp_path / "s.db"), base_delay=0.01,
                             max_delay=0.05, idle_wait=0.05, max_attempts=4,
                             on_success=c.reportar_exito, on_failure=c.reportar_fallo)
    try:
        sp.enqueue("j", {"printerName": "p", "jobId": "j"}, "p")
        assert _wait_until(lambda: sp.failed_count() == 1)
        assert _wait_until(lambda: len(post.llamadas) >= 2)
    finally:
        sp.stop()
        c.detener()

    bodies = post.bodies()
    # 4 intentos fallidos en milisegundos: avisa el primero y el final; los del medio, throttle.
    assert [(b["intentos"], b["final"]) for b in bodies] == [(1, False), (4, True)]
    assert all(b["ok"] is False and b["error"] == "OSError: Impresora apagada" for b in bodies)


def test_get_print_spooler_conecta_el_confirmador(monkeypatch):
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    monkeypatch.setattr(CH, "_print_spooler", None)
    try:
        sp = CH.get_print_spooler()
        confirmador = ci.get_confirmador()
        assert sp._on_success == confirmador.reportar_exito
        assert sp._on_failure == confirmador.reportar_fallo
    finally:
        CH.shutdown_print_spooler()


def test_spooler_print_fn_no_le_saca_el_job_id_al_ticket_original(monkeypatch):
    """runTraductor hace pop de printerName/jobId: tiene que recibir una copia, o el
    spooler se quedaría sin jobId para confirmar."""
    pytest.importorskip("paho")
    pytest.importorskip("escpos")
    import fiscalberry.common.ComandosHandler as CH

    def run_traductor_que_muta(ticket, _queue):
        ticket.pop("printerName")
        ticket.pop("jobId", None)
        return {"message": "Impresión exitosa", "result": []}

    monkeypatch.setattr(CH, "runTraductor", run_traductor_que_muta)
    ticket = {"printerName": "impresora-sin-breaker", "jobId": "comanda-1", "printComanda": {}}

    CH._spooler_print_fn(ticket)

    assert ci.job_id_del_ticket(ticket) == "comanda-1"
