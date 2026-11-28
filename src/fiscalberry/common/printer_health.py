# coding=utf-8
"""
Estado de salud de cada impresora, en palabras que entiende cualquiera.

Por qué existe:
  Cuando una impresora deja de imprimir, el cajero no tiene que leer códigos ni
  trazas: tiene que saber QUÉ hacer. Este módulo traduce cualquier falla de
  impresión (de la impresora o de la computadora) a un mensaje corto y claro,
  recuerda qué impresora está con problemas y avisa una sola vez por MQTT cuando
  el problema aparece o cambia (no en cada reintento del spooler).

  Distingue el ORIGEN del problema, porque la acción es distinta:
    - "impresora":   papel, tapa, apagada, cable. Lo resuelve el cajero.
    - "computadora": Windows perdió la impresora, cola pausada. Suele hacer
                     falta reiniciar la PC o llamar a soporte.

  La UI (desktop: mismo proceso; Android: vía service_status.json) muestra
  `problemas()`. Nada de este módulo puede romper una impresión: si algo falla
  acá, se loguea y se sigue.
"""

import threading
import time

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger()


ORIGEN_IMPRESORA = "impresora"
ORIGEN_COMPUTADORA = "computadora"

# Tipos de problema -> (origen, mensaje para el cajero).
# Reglas de redacción: frases cortas, qué pasa y qué hacer. Sin códigos, sin
# nombres de puertos ni de Windows internos.
SIN_PAPEL = "SIN_PAPEL"
TAPA_ABIERTA = "TAPA_ABIERTA"
PAPEL_TRABADO = "PAPEL_TRABADO"
NO_RESPONDE = "NO_RESPONDE"
IMPRESORA_CON_FALLA = "IMPRESORA_CON_FALLA"
CONEXION_PERDIDA = "CONEXION_PERDIDA"
NO_ENCONTRADA = "NO_ENCONTRADA"
COLA_PAUSADA = "COLA_PAUSADA"
NO_IMPRIME = "NO_IMPRIME"
DESCONOCIDO = "DESCONOCIDO"

MENSAJES = {
    SIN_PAPEL: (ORIGEN_IMPRESORA,
                "La impresora se quedó sin papel. Poné un rollo nuevo."),
    TAPA_ABIERTA: (ORIGEN_IMPRESORA,
                   "La tapa de la impresora está abierta. Cerrala bien."),
    PAPEL_TRABADO: (ORIGEN_IMPRESORA,
                    "Se trabó el papel. Abrí la tapa, acomodá el rollo y cerrala."),
    NO_RESPONDE: (ORIGEN_IMPRESORA,
                  "La impresora no responde. Fijate que esté prendida "
                  "y que el cable esté bien enchufado."),
    IMPRESORA_CON_FALLA: (ORIGEN_IMPRESORA,
                          "La impresora tiene una falla. Apagala, esperá "
                          "10 segundos y volvé a prenderla."),
    CONEXION_PERDIDA: (ORIGEN_COMPUTADORA,
                       "La computadora perdió la conexión con la impresora. "
                       "Reiniciá la computadora. Si vuelve a pasar, llamá a soporte."),
    NO_ENCONTRADA: (ORIGEN_COMPUTADORA,
                    "La computadora no encuentra la impresora. "
                    "Llamá a soporte."),
    COLA_PAUSADA: (ORIGEN_COMPUTADORA,
                   "La impresora quedó pausada en la computadora. "
                   "Llamá a soporte."),
    NO_IMPRIME: (ORIGEN_IMPRESORA,
                 "La impresora no está imprimiendo. Fijate que esté prendida "
                 "y con el cable bien enchufado. Si sigue igual, reiniciá la computadora."),
    DESCONOCIDO: (ORIGEN_IMPRESORA,
                  "No se pudo imprimir. Apagá y prendé la impresora. "
                  "Si sigue igual, llamá a soporte."),
}

TITULOS = {
    ORIGEN_IMPRESORA: "Problema con la impresora",
    ORIGEN_COMPUTADORA: "Problema en la computadora con la impresora",
}

# Se muestra siempre debajo del problema: el spooler durable reintenta, así que
# es verdad, y evita que el cajero reimprima a mano y salga todo dos veces.
AVISO_REINTENTO = "Los tickets no se pierden: salen solos cuando se arregle."


class PrinterProblem(Exception):
    """
    Falla de impresión ya clasificada.

    `tipo` es una clave de MENSAJES; `detalle` es el texto técnico (para el log
    y para soporte), nunca se muestra al cajero.
    """

    def __init__(self, tipo, detalle=""):
        self.tipo = tipo if tipo in MENSAJES else DESCONOCIDO
        self.detalle = detalle
        super().__init__(f"{self.tipo}: {detalle}" if detalle else self.tipo)

    @property
    def origen(self):
        return MENSAJES[self.tipo][0]

    @property
    def mensaje(self):
        return MENSAJES[self.tipo][1]


def _cadena(exc):
    """La excepción y todas sus causas (EscPComandos re-envuelve el error)."""
    vistos = set()
    while exc is not None and id(exc) not in vistos:
        vistos.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def clasificar(exc):
    """Devuelve el tipo de problema (clave de MENSAJES) para una excepción."""
    for e in _cadena(exc):
        if isinstance(e, PrinterProblem):
            return e.tipo

    nombres = {type(e).__name__ for e in _cadena(exc)}
    # DeviceNotFoundError: escpos no pudo abrir la impresora.
    # PrintJobError/DriverError: impresora sin configurar o mal configurada;
    # apagar y prender la impresora no lo arregla, hace falta soporte.
    if nombres & {"DeviceNotFoundError", "PrintJobError", "DriverError"}:
        return NO_ENCONTRADA

    from fiscalberry.common.printer_error_detector import (
        PrinterErrorDetector, PrinterErrorType)

    texto = " | ".join(str(e) for e in _cadena(exc))
    tipo_detectado, _ = PrinterErrorDetector.detect_error_type(texto, exc)
    return {
        PrinterErrorType.PAPER_OUT: SIN_PAPEL,
        PrinterErrorType.COVER_OPEN: TAPA_ABIERTA,
        PrinterErrorType.PAPER_JAM: PAPEL_TRABADO,
        PrinterErrorType.COMMUNICATION_ERROR: NO_RESPONDE,
        PrinterErrorType.OFFLINE: NO_RESPONDE,
        PrinterErrorType.CUTTER_ERROR: IMPRESORA_CON_FALLA,
        PrinterErrorType.TEMPERATURE_ERROR: IMPRESORA_CON_FALLA,
        PrinterErrorType.HARDWARE_ERROR: IMPRESORA_CON_FALLA,
    }.get(tipo_detectado, DESCONOCIDO)


class PrinterHealth:
    """Registro en memoria de qué impresora tiene problemas (thread-safe)."""

    def __init__(self, publicar=None):
        self._lock = threading.Lock()
        self._problemas = {}  # printer_name -> dict
        self._publicar = publicar

    def reportar_ok(self, printer_name):
        if not printer_name:
            return
        with self._lock:
            previo = self._problemas.pop(printer_name, None)
        if previo:
            logger.info("Impresora '%s' volvió a imprimir (estaba: %s)",
                        printer_name, previo["tipo"])

    def reportar_falla(self, printer_name, exc):
        """Registra la falla y devuelve el tipo. Avisa solo si es nueva o cambió."""
        tipo = clasificar(exc)
        origen, mensaje = MENSAJES[tipo]
        if not printer_name:
            return tipo
        with self._lock:
            previo = self._problemas.get(printer_name)
            nuevo = previo is None or previo["tipo"] != tipo
            self._problemas[printer_name] = {
                "impresora": printer_name,
                "tipo": tipo,
                "origen": origen,
                "titulo": TITULOS[origen],
                "mensaje": mensaje,
                "desde": previo["desde"] if previo and not nuevo else time.time(),
            }
        if nuevo:
            logger.error("Impresora '%s': %s (%s) | detalle técnico: %s",
                         printer_name, mensaje, tipo, exc)
            self._avisar(printer_name, tipo, origen, mensaje, exc)
        return tipo

    def _avisar(self, printer_name, tipo, origen, mensaje, exc):
        try:
            publicar = self._publicar
            if publicar is None:
                from fiscalberry.common.rabbitmq.error_publisher import publish_error
                publicar = publish_error
            publicar(
                error_type="PRINTER_PROBLEM",
                error_message=mensaje,
                context={
                    "printer_name": printer_name,
                    "problema": tipo,
                    "origen": origen,
                    "titulo": TITULOS[origen],
                    # Texto listo para mostrar en pantalla (sin códigos).
                    "mensaje_usuario": mensaje,
                    "detalle_tecnico": str(exc)[:500],
                },
            )
        except Exception as e:
            logger.debug("No se pudo publicar el problema de impresora: %s", e)

    def problemas(self):
        """Lista de problemas activos, el más viejo primero."""
        with self._lock:
            return sorted((dict(p) for p in self._problemas.values()),
                          key=lambda p: p["desde"])

    def limpiar(self):
        with self._lock:
            self._problemas.clear()


def resumen_para_pantalla(problemas, pendientes=0):
    """
    (titulo, mensaje, aviso) para mostrar en grande, o None si todo anda.
    Si hay varias impresoras con problemas se muestra la más vieja y se avisa
    que hay más.
    """
    if not problemas:
        return None
    p = problemas[0]
    titulo = f"{p['titulo']} «{p['impresora']}»"
    mensaje = p["mensaje"]
    if len(problemas) > 1:
        otras = len(problemas) - 1
        mensaje += (" También hay otra impresora con problemas." if otras == 1
                    else f" También hay otras {otras} impresoras con problemas.")
    aviso = AVISO_REINTENTO
    if pendientes:
        aviso += (" Hay 1 ticket esperando." if pendientes == 1
                  else f" Hay {pendientes} tickets esperando.")
    return titulo, mensaje, aviso


_health = PrinterHealth()


def get_printer_health():
    return _health
