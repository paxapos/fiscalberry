# coding=utf-8
"""
Colas de impresión de Windows que ya existen (#174, escenario 4).

- Clasificación con fixtures de lo que devuelve EnumPrinters nivel 2 en PCs
  reales: impresoras físicas, virtuales (PDF, XPS, OneNote, fax), compartidas
  de otra PC, duplicadas y fuera de línea.
- La enumeración corre en un subproceso: si el spooler se cuelga (una cola
  compartida de una PC apagada), se lo mata al vencer el tiempo o al cancelar,
  y la interfaz nunca se congela.
"""

import json
import os
import subprocess
import sys
import threading
import time

import pytest

from fiscalberry.common import windows_queues as wq

LOCAL = wq.PRINTER_ATTRIBUTE_LOCAL
NETWORK = wq.PRINTER_ATTRIBUTE_NETWORK


def cruda(nombre, driver="", puerto="", servidor="", atributos=LOCAL, estado=0):
    return {"nombre": nombre, "driver": driver, "puerto": puerto,
            "servidor": servidor, "atributos": atributos, "estado": estado}


# Lo que devuelve EnumPrinters en una PC de un local típico.
PC_DEL_LOCAL = [
    cruda("Microsoft Print to PDF", "Microsoft Print To PDF", "PORTPROMPT:"),
    cruda("Microsoft XPS Document Writer", "Microsoft XPS Document Writer v4", "PORTPROMPT:"),
    cruda("OneNote (Desktop)", "Send to Microsoft OneNote 16 Driver", "nul:"),
    cruda("OneNote for Windows 10", "Microsoft Software Printer Driver",
          "Microsoft.Office.OneNote_16001.14326.21802.0_x64__8wekyb3d8bbwe_microsoft.onenoteim_S-1-5-21"),
    cruda("Fax", "Microsoft Shared Fax Driver", "SHRFAX:",
          atributos=LOCAL | wq.PRINTER_ATTRIBUTE_FAX),
    cruda("POS-80", "Generic / Text Only", "USB002"),
    cruda("EPSON TM-T20II Receipt", "EPSON TM-T20II Receipt5", "USB001"),
    cruda("Comandera vieja", "Generic / Text Only", "USB003",
          atributos=LOCAL | wq.PRINTER_ATTRIBUTE_WORK_OFFLINE),
    cruda("\\\\CAJA\\Cocina", "EPSON TM-T88V Receipt", "", servidor="\\\\CAJA",
          atributos=NETWORK),
    cruda("\\\\SERVIDOR\\Barra", "Generic / Text Only", "", servidor="\\\\SERVIDOR",
          atributos=NETWORK, estado=wq.PRINTER_STATUS_SERVER_UNKNOWN),
    cruda("Etiquetas", "ZDesigner GK420t", "USB004", estado=wq.PRINTER_STATUS_PAUSED),
    # Windows a veces lista la misma cola dos veces.
    cruda("epson tm-t20ii receipt", "EPSON TM-T20II Receipt5", "USB001"),
]


@pytest.fixture
def colas():
    return [wq.clasificar(c) for c in PC_DEL_LOCAL]


def _por_nombre(colas, nombre):
    return next(c for c in colas if c.nombre == nombre)


# --------------------------------------------------------------------------
# Clasificación
# --------------------------------------------------------------------------

@pytest.mark.parametrize("nombre", [
    "Microsoft Print to PDF", "Microsoft XPS Document Writer", "OneNote (Desktop)",
    "OneNote for Windows 10", "Fax",
])
def test_las_virtuales_no_son_impresoras(colas, nombre):
    assert _por_nombre(colas, nombre).virtual


@pytest.mark.parametrize("nombre", ["POS-80", "EPSON TM-T20II Receipt", "Etiquetas"])
def test_las_fisicas_locales(colas, nombre):
    cola = _por_nombre(colas, nombre)
    assert not cola.virtual and cola.local and not cola.compartida


def test_generic_text_only_es_una_impresora_de_verdad(colas):
    """Muchas térmicas POS se instalan con el driver genérico de texto."""
    assert not _por_nombre(colas, "POS-80").virtual


def test_compartida_de_otra_pc(colas):
    cola = _por_nombre(colas, "\\\\CAJA\\Cocina")
    assert cola.compartida and not cola.local and not cola.fuera_de_linea


@pytest.mark.parametrize("nombre", ["Comandera vieja", "\\\\SERVIDOR\\Barra"])
def test_fuera_de_linea(colas, nombre):
    assert _por_nombre(colas, nombre).fuera_de_linea


def test_pausada_no_esta_lista_pero_se_ofrece(colas):
    cola = _por_nombre(colas, "Etiquetas")
    assert not cola.lista and not cola.fuera_de_linea
    assert cola in wq.ordenar(colas)


def test_orden_y_filtro_por_defecto(colas):
    nombres = [c.nombre for c in wq.ordenar(colas)]

    # Locales listas primero, después locales con problemas, después compartidas.
    assert nombres == ["EPSON TM-T20II Receipt", "POS-80", "Etiquetas", "\\\\CAJA\\Cocina"]


def test_con_mostrar_todas_aparecen_virtuales_y_fuera_de_linea_al_final(colas):
    nombres = [c.nombre for c in wq.ordenar(colas, mostrar_todas=True)]

    assert nombres[:4] == ["EPSON TM-T20II Receipt", "POS-80", "Etiquetas", "\\\\CAJA\\Cocina"]
    assert set(nombres[4:]) == {
        "Comandera vieja", "\\\\SERVIDOR\\Barra", "Microsoft Print to PDF",
        "Microsoft XPS Document Writer", "OneNote (Desktop)",
        "OneNote for Windows 10", "Fax"}
    # Una sola vez aunque Windows la liste dos veces.
    assert sum(1 for n in nombres if n.casefold() == "epson tm-t20ii receipt") == 1


def test_el_resultado_es_estable(colas):
    assert wq.ordenar(colas) == wq.ordenar(list(reversed(colas)))


def test_elegir_una_cola_la_configura_por_win32raw(colas):
    candidato = _por_nombre(colas, "EPSON TM-T20II Receipt").candidato()

    assert candidato.driver_config == {"driver": "Win32Raw",
                                       "printer_name": "EPSON TM-T20II Receipt"}
    assert candidato.detail == "USB001"
    assert candidato.status_readable is False


# --------------------------------------------------------------------------
# El subproceso
# --------------------------------------------------------------------------

class Win32PrintFalso:
    def __init__(self, colas=None, error=None, predeterminada=None):
        self.colas = colas or []
        self.error = error
        self.pedidos = []
        self.predeterminada = predeterminada

    def GetDefaultPrinter(self):
        if self.predeterminada is None:
            raise RuntimeError("(2, 'GetDefaultPrinter', 'No hay impresora predeterminada')")
        return self.predeterminada

    def EnumPrinters(self, flags, name=None, level=1):
        self.pedidos.append((flags, name, level))
        if self.error:
            raise self.error
        return [{
            "pPrinterName": c["nombre"], "pDriverName": c["driver"],
            "pPortName": c["puerto"], "pServerName": c["servidor"] or None,
            "Attributes": c["atributos"], "Status": c["estado"],
            "pDevMode": object(), "pSecurityDescriptor": object(),
        } for c in self.colas]


def test_el_modo_listado_pide_locales_y_conexiones_nivel_2(tmp_path):
    w32 = Win32PrintFalso(PC_DEL_LOCAL[:2])
    reporte = tmp_path / "colas.json"

    assert wq.run_list_printers(str(reporte), win32print=w32) == 0

    assert w32.pedidos == [(wq.PRINTER_ENUM_LOCAL | wq.PRINTER_ENUM_CONNECTIONS, None, 2)]
    datos = json.loads(reporte.read_text(encoding="utf-8"))
    assert datos["ok"] is True
    assert [c["nombre"] for c in datos["colas"]] == ["Microsoft Print to PDF",
                                                    "Microsoft XPS Document Writer"]


def test_la_predeterminada_va_primero_entre_las_locales_listas(tmp_path):
    caja = dict(PC_DEL_LOCAL[0], nombre="Caja", puerto="USB002", driver="Generic / Text Only",
                atributos=wq.PRINTER_ATTRIBUTE_LOCAL, estado=0)
    barra = dict(caja, nombre="Barra", puerto="USB001")
    w32 = Win32PrintFalso([barra, caja], predeterminada="CAJA")
    reporte = tmp_path / "colas.json"
    wq.run_list_printers(str(reporte), win32print=w32)

    colas = [wq.clasificar(c) for c in json.loads(reporte.read_text(encoding="utf-8"))["colas"]]
    assert [(c.nombre, c.predeterminada) for c in wq.ordenar(colas)] == [
        ("Caja", True), ("Barra", False)]


def test_sin_predeterminada_el_listado_sigue():
    w32 = Win32PrintFalso(PC_DEL_LOCAL[:1])
    assert [c["predeterminada"] for c in wq.enumerar_crudas(w32)] == [False]


@pytest.mark.parametrize("puerto,puertos", [
    ("USB001", ("USB001",)),
    ("COM3:", ("COM3",)),
    ("usb001,USB002", ("USB001", "USB002")),
    ("IP_192.168.1.50", ("IP_192.168.1.50",)),
    ("", ()),
])
def test_puertos_de_una_cola(puerto, puertos):
    assert wq.ColaWindows("X", puerto=puerto).puertos == puertos


def test_el_modo_listado_reporta_el_error_del_spooler(tmp_path):
    w32 = Win32PrintFalso(error=RuntimeError("(1722, 'EnumPrinters', 'El servidor RPC no está disponible.')"))
    reporte = tmp_path / "colas.json"

    assert wq.run_list_printers(str(reporte), win32print=w32) == 1
    datos = json.loads(reporte.read_text(encoding="utf-8"))
    assert datos == {"ok": False, "error": wq.ERROR_SPOOLER,
                     "detalle": "(1722, 'EnumPrinters', 'El servidor RPC no está disponible.')"}


def _entorno_con_src():
    entorno = dict(os.environ)
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    entorno["PYTHONPATH"] = src + os.pathsep + entorno.get("PYTHONPATH", "")
    return entorno


def _popen_con_src(args, **kwargs):
    return subprocess.Popen(args, env=_entorno_con_src(), **kwargs)


def test_proceso_real_fuera_de_windows_lo_explica():
    """El subproceso de verdad: en Linux no hay win32print."""
    resultado = wq.listar_colas(timeout=30, popen=_popen_con_src)
    assert resultado.error == wq.ERROR_NO_WINDOWS
    assert resultado.colas == []


def test_proceso_real_que_devuelve_colas(tmp_path):
    """Un listado que sí encuentra colas, con el mismo protocolo de archivo."""
    script = tmp_path / "listar.py"
    script.write_text(
        "import json, sys\n"
        "ruta = sys.argv[sys.argv.index('--report') + 1]\n"
        f"json.dump({{'ok': True, 'colas': {json.dumps(PC_DEL_LOCAL)}}}, open(ruta, 'w'))\n",
        encoding="utf-8")

    resultado = wq.listar_colas(
        timeout=30, comando=lambda reporte: [sys.executable, str(script), "--report", reporte])

    assert resultado.error is None
    assert [c.nombre for c in wq.ordenar(resultado.colas)][0] == "EPSON TM-T20II Receipt"


def test_spooler_colgado_se_mata_al_vencer_el_tiempo():
    colgado = []

    def popen(args, **kwargs):
        proceso = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        colgado.append(proceso)
        return proceso

    t0 = time.monotonic()
    resultado = wq.listar_colas(timeout=0.5, popen=popen)

    assert resultado.error == wq.ERROR_TIMEOUT
    assert "impresora compartida" in resultado.explicacion
    assert time.monotonic() - t0 < 5
    # El proceso colgado quedó terminado, no huérfano.
    assert colgado[0].poll() is not None


def test_cancelar_mata_el_proceso_al_instante():
    colgado = []
    cancelar = threading.Event()

    def popen(args, **kwargs):
        proceso = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
        colgado.append(proceso)
        threading.Timer(0.3, cancelar.set).start()
        return proceso

    t0 = time.monotonic()
    resultado = wq.listar_colas(timeout=30, cancelar=cancelar, popen=popen)

    assert resultado.error == wq.ERROR_CANCELADO
    assert time.monotonic() - t0 < 5
    assert colgado[0].poll() is not None


def test_un_proceso_que_muere_sin_reporte_no_rompe_nada():
    def popen(args, **kwargs):
        return subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"], **kwargs)

    resultado = wq.listar_colas(timeout=10, popen=popen)
    assert resultado.error == wq.ERROR_SPOOLER
    assert "código 3" in resultado.detalle


def test_la_busqueda_no_bloquea_y_no_avisa_si_se_cancelo():
    llegadas = []
    inicio = threading.Event()

    def listar_lento(timeout, cancelar):
        inicio.set()
        cancelar.wait(5)
        return wq.ResultadoListado(error=wq.ERROR_CANCELADO)

    busqueda = wq.BusquedaDeColas(llegadas.append, listar=listar_lento).iniciar()
    assert inicio.wait(2)          # iniciar() volvió sin esperar el listado
    busqueda.cancelar()
    busqueda.esperar(5)
    assert llegadas == []


def test_la_busqueda_entrega_el_resultado():
    llegadas = []
    esperado = wq.ResultadoListado(colas=[wq.clasificar(PC_DEL_LOCAL[6])])

    busqueda = wq.BusquedaDeColas(llegadas.append,
                                  listar=lambda timeout, cancelar: esperado).iniciar()
    busqueda.esperar(5)
    assert llegadas == [esperado]


def test_el_ejecutable_empaquetado_se_llama_a_si_mismo_en_modo_listado(monkeypatch):
    monkeypatch.setattr(wq.sys, "frozen", True, raising=False)
    monkeypatch.setattr(wq.sys, "executable", r"C:\Programs\Fiscalberry\fiscalberry-gui.exe")
    assert wq.comando_listado(r"C:\tmp\colas.json") == [
        r"C:\Programs\Fiscalberry\fiscalberry-gui.exe", "--list-printers",
        "--report", r"C:\tmp\colas.json"]


def test_el_modo_temprano_atiende_list_printers(monkeypatch, tmp_path):
    from fiscalberry.common.updater import cli_modes

    llamados = []
    monkeypatch.setattr(wq, "run_list_printers",
                        lambda ruta_reporte=None: llamados.append(ruta_reporte) or 0)
    with pytest.raises(SystemExit) as salida:
        cli_modes.handle_early_modes(["fiscalberry-gui.exe", "--list-printers",
                                      "--report", str(tmp_path / "c.json")])
    assert salida.value.code == 0
    assert llamados == [str(tmp_path / "c.json")]
