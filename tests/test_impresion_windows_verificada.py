# coding=utf-8
"""
Windows le cambia el puerto USB a la impresora y Fiscalberry daba el ticket
por impreso.

Visto en un comercio con Windows 11 e impresora Hasar USB: cada tanto Windows
vuelve a enumerar la impresora y le asigna otro puerto (USB001 -> USB002), pero
la cola sigue en el viejo. Win32Raw escribía en la cola sin error, el trabajo
quedaba trabado en Windows, el spooler lo daba por "impreso OK" y lo borraba.

Estos tests simulan el spooler y el registro de Windows para cubrir:
  - la cola se corrige sola cuando la impresora apareció en otro puerto;
  - si no hay permiso, se imprime por la "Copia 1" que ya está en el puerto vivo;
  - un trabajo trabado se cancela (no sale duplicado) y es un FALLO, no un OK;
  - el error llega a la pantalla como un mensaje simple, sin códigos.
"""

import base64
import gzip
import types

import pytest

import escpos.printer.win32raw as escpos_win32raw

from fiscalberry.common import ComandosHandler as CH
from fiscalberry.common import win32_printer as w32
from fiscalberry.common import printer_health as ph
from fiscalberry.common.printer_health import PrinterProblem


# ---------------------------------------------------------------------------
# Windows simulado
# ---------------------------------------------------------------------------

class FakePywintypesError(Exception):
    pass


class FakeWindows:
    """win32print + winreg mínimos, con un modelo de colas, puertos y trabajos."""

    PRINTER_ENUM_NAME = 8
    HKEY_LOCAL_MACHINE = "HKLM"

    def __init__(self):
        self.colas = {}       # nombre -> PRINTER_INFO_2 (dict)
        self.puertos = {}     # "USB001" -> {"vivo": bool, "descripcion": str}
        self.trabajos = {}    # job_id -> {"cola": str, "Status": int, "datos": bytes}
        self.impreso = {}     # puerto -> bytes que llegaron a la impresora
        self.cancelados = []
        self.admin = True     # permiso para mover la cola de puerto
        self.status_trabado = 0  # Status que toma un trabajo que no puede salir
        self._job = 0
        self._handles = {}

    # -- configuración ---------------------------------------------------
    def agregar_cola(self, nombre, puerto, driver="HASAR Thermal"):
        self.colas[nombre] = {"pPrinterName": nombre, "pPortName": puerto,
                              "pDriverName": driver, "Status": 0, "Attributes": 0}

    def agregar_puerto(self, puerto, vivo, descripcion="HASAR PT-1000"):
        self.puertos[puerto] = {"vivo": vivo, "descripcion": descripcion}

    # -- win32print ------------------------------------------------------
    def OpenPrinter(self, nombre, defaults=None):
        if nombre not in self.colas:
            raise FakePywintypesError(1801, "OpenPrinter", "nombre inválido")
        h = object()
        self._handles[id(h)] = {"cola": nombre, "doc": None,
                                "admin": bool(defaults)}
        return h

    def ClosePrinter(self, h):
        self._handles.pop(id(h), None)

    def GetPrinter(self, h, nivel):
        assert nivel == 2
        return dict(self.colas[self._handles[id(h)]["cola"]])

    def SetPrinter(self, h, nivel, info, comando):
        if not (self.admin and self._handles[id(h)]["admin"]):
            raise FakePywintypesError(5, "SetPrinter", "Acceso denegado")
        self.colas[self._handles[id(h)]["cola"]]["pPortName"] = info["pPortName"]
        self._despachar()

    def EnumPrinters(self, *args):
        nivel = args[-1] if len(args) > 1 else args[0]
        return [dict(c) for c in self.colas.values()] if nivel in (2, 4) else []

    def GetDefaultPrinter(self):
        return next(iter(self.colas))

    def StartDocPrinter(self, h, nivel, doc):
        self._job += 1
        self._handles[id(h)]["doc"] = {"id": self._job, "datos": b""}
        return self._job

    def StartPagePrinter(self, h):
        pass

    def WritePrinter(self, h, datos):
        self._handles[id(h)]["doc"]["datos"] += datos
        return len(datos)

    def EndPagePrinter(self, h):
        pass

    def EndDocPrinter(self, h):
        doc = self._handles[id(h)]["doc"]
        self.trabajos[doc["id"]] = {"cola": self._handles[id(h)]["cola"],
                                    "Status": 0, "datos": doc["datos"]}
        self._despachar()

    def GetJob(self, h, job_id, nivel):
        if job_id not in self.trabajos:
            raise FakePywintypesError(87, "GetJob", "parámetro incorrecto")
        t = self.trabajos[job_id]
        return {"JobId": job_id, "Status": t["Status"], "pStatus": None}

    def SetJob(self, h, job_id, nivel, info, comando):
        assert comando == w32.JOB_CONTROL_DELETE
        self.trabajos.pop(job_id, None)
        self.cancelados.append(job_id)

    def _despachar(self):
        """Los trabajos en una cola con puerto vivo salen; el resto se traba."""
        for job_id, t in list(self.trabajos.items()):
            puerto = self.colas[t["cola"]]["pPortName"]
            if self.puertos.get(puerto, {}).get("vivo"):
                self.impreso[puerto] = self.impreso.get(puerto, b"") + t["datos"]
                del self.trabajos[job_id]
            else:
                t["Status"] = self.status_trabado

    # -- winreg ----------------------------------------------------------
    class _Key:
        def __init__(self, ruta):
            self.ruta = ruta

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, base, sub):
        ruta = sub if base == self.HKEY_LOCAL_MACHINE else f"{base.ruta}\\{sub}"
        if ruta == w32.USBPRINT_CLASS_KEY:
            return self._Key(ruta)
        for i, (puerto, d) in enumerate(sorted(self.puertos.items())):
            inst = f"{w32.USBPRINT_CLASS_KEY}\\dev{i}"
            if ruta == inst + r"\#\Device Parameters":
                return self._Key(ruta)
            if ruta == inst + r"\#\Control" and d["vivo"]:
                return self._Key(ruta)
        raise OSError("no existe")

    def EnumKey(self, key, i):
        if i >= len(self.puertos):
            raise OSError("fin")
        return f"dev{i}"

    def QueryValueEx(self, key, nombre):
        i = int(key.ruta.split("\\dev")[1].split("\\")[0])
        puerto, d = sorted(self.puertos.items())[i]
        if nombre == "Port Number":
            return int(puerto[3:]), 4
        if nombre == "Base Name":
            return "USB", 1
        if nombre == "Port Description":
            return d["descripcion"], 1
        if nombre == "Linked":
            return 1, 4
        raise OSError(nombre)

    def CloseKey(self, key):
        pass


@pytest.fixture
def win(monkeypatch):
    fake = FakeWindows()
    monkeypatch.setattr(escpos_win32raw, "_DEP_WIN32PRINT", True)
    monkeypatch.setattr(escpos_win32raw, "win32print", fake, raising=False)
    monkeypatch.setattr(escpos_win32raw, "pywintypes",
                        types.SimpleNamespace(error=FakePywintypesError), raising=False)
    monkeypatch.setattr(w32, "_win32print", lambda: fake)
    monkeypatch.setattr(w32, "_winreg", lambda: fake)
    # Esperas cortas: los tests no pueden tardar lo que tarda Windows.
    monkeypatch.setattr(w32, "SEGUNDOS_SIN_AVANCE", 0.2)
    monkeypatch.setattr(w32, "SEGUNDOS_MAX_IMPRIMIENDO", 0.4)
    monkeypatch.setattr(w32, "SEGUNDOS_EN_ERROR", 0.05)
    monkeypatch.setattr(w32, "INTERVALO_SONDEO", 0.01)

    class FakeConfigberry:
        def get_config_for_printer(self, nombre):
            return {"driver": "Win32Raw", "printer_name": nombre}

        def get(self, *a, fallback=None, **k):
            return fallback

    monkeypatch.setattr(CH, "configberry", FakeConfigberry())
    monkeypatch.setattr(CH, "publish_error", lambda *a, **k: None)
    monkeypatch.setattr(
        "fiscalberry.common.printer_error_detector.publish_error", lambda *a, **k: None)
    return fake


def _raw(datos=b"TICKET"):
    return {"printRaw": {"data": base64.b64encode(gzip.compress(datos)).decode(),
                         "encoding": "gzip+base64"}}


def _imprimir(nombre, **ticket):
    return CH.runTraductor({"printerName": nombre, **ticket}, None)


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------

def test_impresora_sana_imprime_igual_que_antes(win):
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=True)

    res = _imprimir("Hasar", **_raw(b"HOLA"))

    assert res["result"] == "ok"
    assert win.impreso["USB001"] == b"HOLA"


def test_puerto_cambiado_se_corrige_solo(win):
    """El caso del comercio: la cola quedó en USB001, la impresora está en USB002."""
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=False)
    win.agregar_puerto("USB002", vivo=True)

    res = _imprimir("Hasar", **_raw(b"HOLA"))

    assert res["result"] == "ok"
    assert win.colas["Hasar"]["pPortName"] == "USB002"
    assert win.impreso["USB002"] == b"HOLA"


def test_sin_permiso_usa_la_copia_que_ya_esta_en_el_puerto_nuevo(win):
    win.admin = False
    win.agregar_cola("Hasar", "USB001")
    win.agregar_cola("Hasar (Copia 1)", "USB002")
    win.agregar_puerto("USB001", vivo=False)
    win.agregar_puerto("USB002", vivo=True)

    res = _imprimir("Hasar", **_raw(b"HOLA"))

    assert res["result"] == "ok"
    assert win.impreso["USB002"] == b"HOLA"


def test_sin_permiso_ni_copia_es_un_fallo_claro_y_no_deja_trabajo_trabado(win):
    win.admin = False
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=False)
    win.agregar_puerto("USB002", vivo=True)

    with pytest.raises(PrinterProblem) as exc:
        _imprimir("Hasar", **_raw())

    assert exc.value.tipo == ph.CONEXION_PERDIDA
    assert exc.value.origen == ph.ORIGEN_COMPUTADORA
    assert win.trabajos == {}, "no se mandó nada que pueda salir duplicado después"


def test_impresora_desenchufada_es_problema_de_la_impresora(win):
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=False)

    with pytest.raises(PrinterProblem) as exc:
        _imprimir("Hasar", **_raw())

    assert exc.value.tipo == ph.NO_RESPONDE
    assert exc.value.origen == ph.ORIGEN_IMPRESORA


def test_trabajo_trabado_se_cancela_y_no_se_da_por_impreso(win, monkeypatch):
    """Puerto no USB (no se puede chequear antes): se detecta después."""
    win.agregar_cola("Hasar", "COM3")
    win.status_trabado = w32.JOB_STATUS_ERROR | w32.JOB_STATUS_OFFLINE

    with pytest.raises(PrinterProblem) as exc:
        _imprimir("Hasar", **_raw())

    assert exc.value.tipo == ph.NO_RESPONDE
    assert win.cancelados, "el trabajo trabado tiene que cancelarse"
    assert win.trabajos == {}


def test_trabajo_sin_papel(win):
    win.agregar_cola("Hasar", "COM3")
    win.status_trabado = w32.JOB_STATUS_PAPEROUT

    with pytest.raises(PrinterProblem) as exc:
        _imprimir("Hasar", **_raw())

    assert exc.value.tipo == ph.SIN_PAPEL


def test_trabajo_que_no_avanza_vence(win):
    win.agregar_cola("Hasar", "COM3")
    win.status_trabado = 0  # ni error ni nada: simplemente no sale

    with pytest.raises(PrinterProblem) as exc:
        _imprimir("Hasar", **_raw())

    assert exc.value.tipo == ph.NO_IMPRIME
    assert win.cancelados


def test_cola_pausada(win):
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=True)
    win.colas["Hasar"]["Attributes"] = w32.PRINTER_ATTRIBUTE_WORK_OFFLINE

    with pytest.raises(PrinterProblem) as exc:
        _imprimir("Hasar", **_raw())

    assert exc.value.tipo == ph.COLA_PAUSADA
    assert exc.value.origen == ph.ORIGEN_COMPUTADORA


def test_ticket_normal_con_puerto_muerto_no_se_da_por_impreso(win):
    """
    Camino EscPComandos: antes la impresora se abría dentro de la acción, el
    error se tragaba ahí y el ticket quedaba "OK" sin haber salido.
    """
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=False)

    with pytest.raises(PrinterProblem):
        _imprimir("Hasar", printTexto={"texto": "hola"})


def test_ticket_normal_con_trabajo_trabado_es_fallo(win):
    win.agregar_cola("Hasar", "COM3")
    win.status_trabado = w32.JOB_STATUS_ERROR

    with pytest.raises(Exception) as exc:
        _imprimir("Hasar", printTexto={"texto": "hola"})

    assert ph.clasificar(exc.value) == ph.IMPRESORA_CON_FALLA
    assert win.cancelados


def test_ticket_normal_sano(win):
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=True)

    res = _imprimir("Hasar", printTexto={"texto": "hola"})

    assert "result" in res
    assert b"hola" in win.impreso["USB001"]


def test_cola_inexistente(win):
    with pytest.raises(PrinterProblem) as exc:
        _imprimir("NoExiste", **_raw())
    assert exc.value.tipo == ph.NO_ENCONTRADA


def test_dos_impresoras_iguales_no_adivina(win):
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=False)
    win.agregar_puerto("USB002", vivo=True)
    win.agregar_puerto("USB003", vivo=True)

    with pytest.raises(PrinterProblem) as exc:
        _imprimir("Hasar", **_raw())

    assert exc.value.tipo == ph.CONEXION_PERDIDA
    assert win.colas["Hasar"]["pPortName"] == "USB001"


def test_otra_impresora_distinta_no_se_toma_por_la_nuestra(win):
    """Una etiquetadora en USB002 no es la Hasar desenchufada de USB001."""
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=False, descripcion="HASAR PT-1000")
    win.agregar_puerto("USB002", vivo=True, descripcion="ZEBRA ZD220")

    with pytest.raises(PrinterProblem) as exc:
        _imprimir("Hasar", **_raw())

    assert exc.value.tipo == ph.NO_RESPONDE
    assert win.colas["Hasar"]["pPortName"] == "USB001"


def test_registro_ilegible_no_bloquea_la_impresion(win, monkeypatch):
    """Fail-open: si no se puede leer el registro, se imprime como siempre."""
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=True)

    def roto(*a, **k):
        raise PermissionError("registro")

    monkeypatch.setattr(win, "OpenKey", roto)

    res = _imprimir("Hasar", **_raw(b"HOLA"))
    assert res["result"] == "ok"


def test_verificacion_se_puede_apagar(win, monkeypatch):
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=False)
    monkeypatch.setattr(CH, "_verificar_impresion_windows", lambda: False)

    # Comportamiento anterior: el trabajo queda en Windows y no se avisa.
    res = _imprimir("Hasar", **_raw())
    assert res["result"] == "ok"
    assert win.trabajos


# ---------------------------------------------------------------------------
# Del spooler a la pantalla
# ---------------------------------------------------------------------------

@pytest.fixture
def health(monkeypatch):
    avisos = []
    h = ph.PrinterHealth(publicar=lambda **k: avisos.append(k))
    monkeypatch.setattr(CH, "get_printer_health", lambda: h)
    h.avisos = avisos
    return h


@pytest.fixture
def sin_breaker(monkeypatch):
    class Permisivo:
        def allow(self, _):
            return True

        def record_failure(self, _):
            pass

        def record_success(self, _):
            pass

    monkeypatch.setattr(
        "fiscalberry.common.printer_circuit_breaker.get_circuit_breaker", lambda: Permisivo())


def test_falla_llega_a_la_pantalla_y_se_limpia_al_volver(win, health, sin_breaker):
    win.agregar_cola("Hasar", "USB001")
    win.agregar_puerto("USB001", vivo=False)

    for _ in range(3):  # reintentos del spooler
        with pytest.raises(PrinterProblem):
            CH._spooler_print_fn({"printerName": "Hasar", **_raw()})

    problemas = health.problemas()
    assert len(problemas) == 1
    assert problemas[0]["origen"] == ph.ORIGEN_IMPRESORA
    assert len(health.avisos) == 1, "se avisa una vez, no en cada reintento"
    assert health.avisos[0]["context"]["mensaje_usuario"] == problemas[0]["mensaje"]

    titulo, mensaje, aviso = ph.resumen_para_pantalla(problemas, pendientes=2)
    assert "Hasar" in titulo
    assert "prendida" in mensaje
    assert "2 tickets" in aviso

    win.puertos["USB001"]["vivo"] = True  # el cajero enchufó la impresora
    CH._spooler_print_fn({"printerName": "Hasar", **_raw()})
    assert health.problemas() == []


@pytest.mark.parametrize("tipo", list(ph.MENSAJES))
def test_mensajes_aptos_para_cualquiera(tipo):
    origen, mensaje = ph.MENSAJES[tipo]
    assert origen in ph.TITULOS
    prohibido = ["USB0", "0x", "error", "Error", "spooler", "driver", "cola", "Exception"]
    assert not any(p in mensaje for p in prohibido), mensaje
    assert len(mensaje) < 140


def test_clasifica_errores_de_otros_drivers():
    assert ph.clasificar(Exception("Paper out")) == ph.SIN_PAPEL
    assert ph.clasificar(Exception("cover open")) == ph.TAPA_ABIERTA
    assert ph.clasificar(TimeoutError("timed out")) == ph.NO_RESPONDE
    assert ph.clasificar(ValueError("cualquier cosa")) == ph.DESCONOCIDO
    assert ph.clasificar(CH.PrintJobError("Impresora no encontrada: caja")) == ph.NO_ENCONTRADA
    assert ph.clasificar(CH.DriverError("Driver Win32Raw no disponible")) == ph.NO_ENCONTRADA

    try:
        try:
            raise PrinterProblem(ph.SIN_PAPEL, "x")
        except PrinterProblem as e:
            raise RuntimeError("Error ejecutando comandos: x") from e
    except RuntimeError as envuelto:
        assert ph.clasificar(envuelto) == ph.SIN_PAPEL


def test_snapshot_para_android_es_serializable(health):
    import json

    health.reportar_falla("Hasar", PrinterProblem(ph.SIN_PAPEL, "x"))
    snap = CH.print_status_snapshot()
    json.dumps(snap)
    assert snap["printer_problems"][0]["tipo"] == ph.SIN_PAPEL
