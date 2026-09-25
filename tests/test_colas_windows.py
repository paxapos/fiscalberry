# coding=utf-8
"""
Colas de Windows (#174, escenario 4).

EnumPrinters se simula con la salida de win32print (dicts de nivel 2). El
subproceso es real: se lanza un Python que se cuelga como lo haría una cola
compartida caída, y se comprueba que se lo mata y que se reintenta solo con
las locales, sin congelar a quien espera.
"""

import json
import subprocess
import sys
import threading
import time

import pytest

from fiscalberry.common import windows_queues as wq
from fiscalberry.common.printer_setup import PrinterSetupService


def cola(nombre, puerto, driver, atributos=0x40, estado=0, servidor=None, **extra):
    return dict(pPrinterName=nombre, pPortName=puerto, pDriverName=driver,
                Attributes=atributos, Status=estado, pServerName=servidor,
                pShareName=extra.get("share"), pLocation="", pComment="")


SALIDA_ENUMPRINTERS = [
    cola("Microsoft Print to PDF", "PORTPROMPT:", "Microsoft Print To PDF"),
    cola("Microsoft XPS Document Writer", "PORTPROMPT:", "Microsoft XPS Document Writer v4"),
    cola("OneNote (Desktop)", "nul:", "Send to Microsoft OneNote 16 Driver"),
    cola("Fax", "SHRFAX:", "Microsoft Shared Fax Driver", atributos=0x40 | 0x4000),
    cola("EPSON TM-T20II Receipt", "USB001", "EPSON TM-T20II Receipt5"),
    cola("Cocina", "IP_192.168.1.50", "Generic / Text Only"),
    cola("POS-80", "USB002", "POS-80C", atributos=0x40 | 0x400),         # "usar sin conexión"
    cola("Barra", "COM3:", "Generic / Text Only", estado=0x80),           # fuera de línea
    cola("\\\\CAJA-PC\\EPSON", "USB001", "EPSON TM-T88V Receipt", atributos=0x10,
         servidor="\\\\CAJA-PC"),
    cola("epson tm-t20ii receipt", "USB001", "EPSON TM-T20II Receipt5"),  # duplicada
    cola("Térmica Wi-Fi", "WSD-3c1e1c0a-0b2d-4f3e-9f23-1234567890ab", "XP-80", estado=0x10),
]


def colas():
    return wq.normalize(SALIDA_ENUMPRINTERS, default_name="Cocina")


def por_nombre():
    return {c.name: c for c in colas()}


# ---------------------------------------------------------------------------
# Resultado normalizado
# ---------------------------------------------------------------------------

def test_virtuales_fax_y_offline_quedan_ocultas():
    c = por_nombre()
    for nombre in ("Microsoft Print to PDF", "Microsoft XPS Document Writer",
                   "OneNote (Desktop)", "Fax"):
        assert c[nombre].virtual and c[nombre].hidden, nombre
    assert c["POS-80"].offline and c["POS-80"].hidden
    assert c["Barra"].offline and c["Barra"].hidden
    assert not c["EPSON TM-T20II Receipt"].hidden
    assert not c["Cocina"].hidden


def test_tipos_de_conexion_por_puerto():
    c = por_nombre()
    assert c["EPSON TM-T20II Receipt"].kind == wq.KIND_USB
    assert c["Cocina"].kind == wq.KIND_NETWORK
    assert c["Barra"].kind == wq.KIND_SERIAL
    assert c["\\\\CAJA-PC\\EPSON"].kind == wq.KIND_SHARED
    assert c["Térmica Wi-Fi"].kind == wq.KIND_NETWORK
    assert c["Microsoft Print to PDF"].kind == wq.KIND_VIRTUAL
    assert c["EPSON TM-T20II Receipt"].usb_ports == {"USB001"}
    assert c["Barra"].com_ports == {"COM3"}


def test_duplicadas_sin_distinguir_mayusculas():
    nombres = [x.name.casefold() for x in colas()]
    assert nombres.count("epson tm-t20ii receipt") == 1


def test_orden_primero_las_locales_listas_y_la_predeterminada():
    orden = [x.name for x in colas()]
    assert orden[:2] == ["Cocina", "EPSON TM-T20II Receipt"]  # listas; Cocina es la predeterminada
    assert orden.index("Térmica Wi-Fi") < orden.index("\\\\CAJA-PC\\EPSON")  # local antes que compartida
    assert all(x.hidden for x in colas()[-6:])  # ocultas al final


def test_el_resultado_es_estable():
    assert colas() == wq.normalize(list(reversed(SALIDA_ENUMPRINTERS)), default_name="Cocina")


def test_el_estado_de_windows_es_solo_informativo():
    c = por_nombre()
    assert c["Cocina"].status_text == "Windows la muestra lista"
    assert c["Barra"].status_text == "Windows la marca fuera de línea"
    assert c["Térmica Wi-Fi"].status_text == "Windows dice que no tiene papel"
    # "Sin papel" según el spooler no la oculta: la prueba en papel decide.
    assert not c["Térmica Wi-Fi"].hidden


def test_la_seleccion_se_mapea_a_win32raw():
    candidato = por_nombre()["EPSON TM-T20II Receipt"].candidate()
    assert candidato.driver_config == {"driver": "Win32Raw", "printer_name": "EPSON TM-T20II Receipt"}
    assert candidato.detail == "USB001"


def test_una_cola_ya_configurada_se_reconoce_sin_mayusculas():
    class Config:
        def get_actual_config(self):
            return {"Caja": {"driver": "Win32Raw", "printer_name": "epson tm-t20ii receipt"}}

    candidato = por_nombre()["EPSON TM-T20II Receipt"].candidate()
    assert PrinterSetupService(Config()).find_duplicate(candidato) == "Caja"


def test_enumeracion_en_proceso_usa_nivel_2_locales_y_conexiones():
    llamadas = []

    class Win32Print:
        def EnumPrinters(self, flags, nombre, nivel):
            llamadas.append((flags, nombre, nivel))
            return SALIDA_ENUMPRINTERS

        def GetDefaultPrinter(self):
            return "EPSON TM-T20II Receipt"

    resultado = wq.enumerate_in_process(Win32Print())
    assert llamadas == [(wq.PRINTER_ENUM_LOCAL | wq.PRINTER_ENUM_CONNECTIONS, None, 2)]
    assert resultado[0].name == "EPSON TM-T20II Receipt" and resultado[0].is_default

    wq.enumerate_in_process(Win32Print(), local_only=True)
    assert llamadas[-1][0] == wq.PRINTER_ENUM_LOCAL


def test_modo_list_printers_escribe_json(tmp_path):
    class Win32Print:
        def EnumPrinters(self, flags, nombre, nivel):
            return SALIDA_ENUMPRINTERS[:5]

        def GetDefaultPrinter(self):
            raise RuntimeError("sin predeterminada")

    ruta = tmp_path / "colas.json"
    assert wq.run_list_printers(str(ruta), win32print=Win32Print()) == 0
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["error"] is None
    assert {c["name"] for c in datos["colas"]} >= {"EPSON TM-T20II Receipt", "Fax"}


def test_modo_list_printers_con_error_de_spooler(tmp_path):
    class SpoolerCaido:
        def EnumPrinters(self, *a):
            raise OSError(1722, "El servidor RPC no está disponible")

    ruta = tmp_path / "colas.json"
    assert wq.run_list_printers(str(ruta), win32print=SpoolerCaido()) == 1
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["colas"] == [] and "RPC" in datos["error"]


# ---------------------------------------------------------------------------
# El subproceso que se puede matar
# ---------------------------------------------------------------------------

def comando_python(codigo_por_modo):
    """Comando que, según solo-locales o no, corre un Python distinto."""
    def comando(ruta, local_only):
        codigo = codigo_por_modo[local_only].replace("RUTA", repr(ruta))
        return [sys.executable, "-c", codigo]
    return comando


ESCRIBE_COLAS = ("import json; json.dump({'colas': [{'name': 'EPSON', 'port': 'USB001'}, "
                 "{'name': 'Cocina', 'port': 'IP_192.168.1.50', 'bogus': 1}], 'error': None}, "
                 "open(RUTA, 'w'))")
SE_CUELGA = "import time; time.sleep(60)"
FALLA = "import json; json.dump({'colas': [], 'error': 'OSError: 1722'}, open(RUTA, 'w'))"


def test_listado_normal_por_subproceso():
    r = wq.list_queues(platform="win32", command=comando_python({False: ESCRIBE_COLAS,
                                                                  True: SE_CUELGA}))
    assert [c.name for c in r.queues] == ["EPSON", "Cocina"]
    assert not r.timed_out and not r.local_only and r.message == ""
    assert r.seconds < 5


def test_si_se_cuelga_se_mata_y_se_reintenta_solo_con_las_locales():
    procesos = []

    def popen(*a, **k):
        p = subprocess.Popen(*a, **k)
        procesos.append(p)
        return p

    inicio = time.monotonic()
    r = wq.list_queues(timeout=1.0, local_timeout=5, platform="win32", popen=popen,
                       command=comando_python({False: SE_CUELGA, True: ESCRIBE_COLAS}))
    assert time.monotonic() - inicio < 5
    assert r.timed_out and r.local_only
    assert [c.name for c in r.queues] == ["EPSON", "Cocina"]
    assert "compartida" in r.message
    assert procesos[0].poll() is not None  # el colgado quedó muerto


def test_si_se_cuelgan_los_dos_intentos_se_explica():
    r = wq.list_queues(timeout=0.5, local_timeout=0.5, platform="win32",
                       command=comando_python({False: SE_CUELGA, True: SE_CUELGA}))
    assert r.timed_out and r.queues == []
    assert "tardó demasiado" in r.message


def test_error_del_spooler_se_explica():
    r = wq.list_queues(platform="win32", command=comando_python({False: FALLA, True: FALLA}))
    assert r.queues == [] and "1722" in r.error
    assert r.message == "No se pudieron leer las impresoras instaladas en Windows."


def test_se_cancela_al_salir_del_asistente():
    cancelar = threading.Event()
    threading.Timer(0.3, cancelar.set).start()
    inicio = time.monotonic()
    r = wq.list_queues(timeout=30, platform="win32", cancel=cancelar,
                       command=comando_python({False: SE_CUELGA, True: SE_CUELGA}))
    assert r.cancelled and time.monotonic() - inicio < 3


def test_fuera_de_windows_no_hay_colas():
    r = wq.list_queues(platform="linux")
    assert r.skipped and r.queues == [] and r.message == ""


def test_comando_del_exe_y_de_desarrollo():
    assert wq.list_printers_command("x.json", frozen=True, executable="C:\\F\\fiscalberry-gui.exe") \
        == ["C:\\F\\fiscalberry-gui.exe", "--list-printers", "--report", "x.json"]
    dev = wq.list_printers_command("x.json", local_only=True, frozen=False, executable="python")
    assert dev == ["python", "-m", "fiscalberry.common.windows_queues", "--list-printers",
                   "--report", "x.json", "--local-only"]


def test_el_modulo_se_puede_correr_como_subproceso_de_desarrollo():
    """python -m ... --list-printers: fuera de Windows responde con un error, sin colgarse."""
    r = wq.list_queues(platform="win32")  # el comando de verdad: python -m ...
    # En Linux no hay win32print: el subproceso arranca, contesta con el error
    # y no se cuelga.
    assert not r.timed_out
    assert r.error == "ModuleNotFoundError: No module named 'win32print'"


def test_el_arranque_temprano_atiende_list_printers(tmp_path, monkeypatch):
    from fiscalberry.common.updater import cli_modes

    llamado = {}

    def falso(ruta, local_only=False):
        llamado.update(ruta=ruta, local_only=local_only)
        return 0

    monkeypatch.setattr(wq, "run_list_printers", falso)
    with pytest.raises(SystemExit) as salida:
        cli_modes.handle_early_modes(["fiscalberry-gui.exe", "--list-printers", "--report",
                                      "c.json", "--local-only"])
    assert salida.value.code == 0
    assert llamado == {"ruta": "c.json", "local_only": True}
    assert "--list-printers" in cli_modes.MODES
