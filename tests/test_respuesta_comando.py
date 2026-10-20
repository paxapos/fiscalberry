# coding=utf-8
"""
Respuesta de comandos a la consola de Paxapos.

Los mensajes que salen de la consola (Paxaprinteres > Consola) traen `cmdId`.
Solo esos se reportan al backend (POST {sio_host}/paxaprinter_respuesta.json);
un trabajo de impresión normal no genera tráfico extra. El reporte nunca lleva
credenciales y nunca rompe el procesamiento del comando.
"""

import json

import pytest

from fiscalberry.common import respuesta_comando as rc
from fiscalberry.common import ComandosHandler as ch
from fiscalberry.common.rabbitmq.consumer import RabbitMQConsumer


class ConfigFalsa:
    def __init__(self, uuid="uuid-123", host="https://beta.paxapos.com/"):
        self.valores = {("SERVIDOR", "uuid"): uuid, ("SERVIDOR", "sio_host"): host}

    def get(self, seccion, clave, fallback=None):
        return self.valores.get((seccion, clave), fallback)

    def get_ssl_verify(self):
        return True


@pytest.fixture
def posts(monkeypatch):
    """Captura los POST en vez de mandarlos."""
    enviados = []

    class Respuesta:
        status_code = 200

    def post_falso(url, headers=None, data=None, timeout=None, verify=None):
        enviados.append((url, json.loads(data)))
        return Respuesta()

    monkeypatch.setattr(rc.requests, "post", post_falso)
    return enviados


def test_sin_cmd_id_no_se_reporta(posts):
    assert rc.reportar({"getStatus": True}, {"rta": {}}, configberry=ConfigFalsa(), sincronico=True) is False
    assert rc.reportar("texto plano", {}, configberry=ConfigFalsa(), sincronico=True) is False
    assert posts == []


def test_cmd_id_invalido_no_se_reporta(posts):
    for cmd_id in ("", 123, "x" * 65, None):
        assert rc.reportar({"cmdId": cmd_id, "getStatus": True}, {}, configberry=ConfigFalsa(), sincronico=True) is False
    assert posts == []


def test_reporta_al_servidor_del_discover(posts):
    comando = {"cmdId": "abc", "getAvailablePrinters": True}
    assert rc.reportar(comando, {"rta": ["cocina"]}, configberry=ConfigFalsa(), sincronico=True) is True

    url, payload = posts[0]
    assert url == "https://beta.paxapos.com/paxaprinter_respuesta.json"
    assert payload["uuid"] == "uuid-123"
    assert payload["cmdId"] == "abc"
    assert payload["acciones"] == ["getAvailablePrinters"]
    assert payload["ok"] is True
    assert payload["resultado"] == {"rta": ["cocina"]}
    assert "version" in payload


def test_sin_sio_host_no_reporta(posts):
    assert rc.reportar({"cmdId": "abc"}, {}, configberry=ConfigFalsa(host=""), sincronico=True) is False
    assert posts == []


def test_error_de_red_no_se_propaga(monkeypatch):
    def explota(*a, **k):
        raise ConnectionError("sin red")

    monkeypatch.setattr(rc.requests, "post", explota)
    assert rc.reportar({"cmdId": "abc"}, {}, configberry=ConfigFalsa(), sincronico=True) is True


def test_no_salen_credenciales():
    resultado = {"rta": {"SERVIDOR": {"uuid": "u", "sio_password": "secreta"},
                         "RabbitMq": {"host": "h", "password": "otra", "user": "fb"}}}
    limpio = rc.sanitizar(resultado)
    assert limpio["rta"]["SERVIDOR"]["sio_password"] == "***"
    assert limpio["rta"]["RabbitMq"]["password"] == "***"
    assert limpio["rta"]["RabbitMq"]["user"] == "fb"
    assert "secreta" not in json.dumps(limpio)


def test_sin_metadatos_saca_solo_cmd_id():
    original = {"cmdId": "abc", "printerName": "cocina", "printTexto": {"texto": "hola"}}
    limpio = rc.sin_metadatos(original)
    assert limpio == {"printerName": "cocina", "printTexto": {"texto": "hola"}}
    assert "cmdId" in original, "no debe mutar el mensaje original"


def test_run_traductor_no_toma_cmd_id_como_accion(monkeypatch):
    """cmdId no es una acción: si llegara a EscPComandos.run() sería 'Function not found'."""
    vistos = {}

    def config_falla(nombre):
        vistos["ticket"] = dict(ticket)
        raise KeyError(nombre)

    ticket = {"printerName": "cocina", "cmdId": "abc", "jobId": "j1", "printTexto": {"texto": "hola"}}
    monkeypatch.setattr(ch.configberry, "get_config_for_printer", config_falla)
    ch.runTraductor(ticket, None)
    assert "cmdId" not in vistos["ticket"]
    assert "jobId" not in vistos["ticket"]


def test_spooler_reporta_exito_y_fallo(monkeypatch):
    class BreakerPermisivo:
        def allow(self, _n):
            return True

        def record_failure(self, _n):
            pass

        def record_success(self, _n):
            pass

    monkeypatch.setattr("fiscalberry.common.printer_circuit_breaker.get_circuit_breaker", lambda: BreakerPermisivo())
    reportes = []
    monkeypatch.setattr(ch.respuesta_comando, "reportar",
                        lambda comando, resultado, ok=True, **k: reportes.append((comando.get("cmdId"), ok, resultado)))

    monkeypatch.setattr(ch, "runTraductor", lambda *a, **k: {"message": "ok"})
    ch._spooler_print_fn({"printerName": "cocina", "cmdId": "c1"})

    monkeypatch.setattr(ch, "runTraductor", lambda *a, **k: {"error": "Impresora no encontrada"})
    with pytest.raises(ch.PrintJobError):
        ch._spooler_print_fn({"printerName": "cocina", "cmdId": "c2"})

    assert reportes[0][0] == "c1" and reportes[0][1] is True and reportes[0][2]["impreso"] is True
    assert reportes[1][0] == "c2" and reportes[1][1] is False and "no encontrada" in reportes[1][2]["err"]


class MensajeMqtt:
    def __init__(self, data):
        self.payload = json.dumps(data).encode("utf-8")


def _consumer():
    c = RabbitMQConsumer.__new__(RabbitMQConsumer)
    import logging
    c.logger = logging.getLogger("test")
    c.topic = "uuid-123"
    c._comandos_handler = None
    return c


def test_consumer_reporta_comando_de_control(monkeypatch):
    reportes = []
    monkeypatch.setattr("fiscalberry.common.rabbitmq.consumer.respuesta_comando.reportar",
                        lambda comando, resultado, ok=True, **k: reportes.append((comando, resultado, ok)))
    recibidos = []

    class HandlerFalso:
        def send_command(self, comando):
            recibidos.append(comando)
            return {"rta": {"action": "getAvailablePrinters", "rta": ["cocina"]}}

    c = _consumer()
    c._comandos_handler = HandlerFalso()
    c._on_message(None, None, MensajeMqtt({"cmdId": "abc", "getAvailablePrinters": True}))

    assert recibidos == [{"getAvailablePrinters": True}], "el handler no recibe el cmdId"
    assert reportes[0][0]["cmdId"] == "abc"
    assert reportes[0][2] is True


def test_consumer_reporta_trabajo_encolado(monkeypatch):
    reportes = []
    monkeypatch.setattr("fiscalberry.common.rabbitmq.consumer.respuesta_comando.reportar",
                        lambda comando, resultado, ok=True, **k: reportes.append((comando, resultado, ok)))
    encolados = []

    class SpoolerFalso:
        def enqueue(self, job_id, ticket, printer):
            encolados.append(ticket)
            return True

    monkeypatch.setattr(ch, "get_print_spooler", lambda: SpoolerFalso())
    c = _consumer()
    c._on_message(None, None, MensajeMqtt({"cmdId": "abc", "printerName": "cocina", "printTexto": {"texto": "hola"}}))

    assert encolados[0]["cmdId"] == "abc", "el cmdId viaja con el ticket para reportar la impresión"
    assert reportes[0][1]["encolado"] is True
    assert reportes[0][1]["printerName"] == "cocina"


def test_get_available_printers_no_lista_secciones_del_sistema(monkeypatch):
    monkeypatch.setattr(ch.configberry, "sections",
                        lambda: ["SERVIDOR", "RabbitMq", "Paxaprinter", "Heartbeat", "cocina", "caja"])
    rta = ch.ComandosHandler()._getAvailablePrinters()
    assert rta["rta"] == ["cocina", "caja"]
