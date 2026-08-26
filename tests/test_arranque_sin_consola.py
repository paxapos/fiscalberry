# coding=utf-8
"""
Arrancar cuando no hay consola a la que escribir.

El .exe de la GUI se compila con `console=False`, y en esa modalidad
PyInstaller deja `sys.stdout` y `sys.stderr` valiendo None. La 3.6.4 no
arrancaba en Windows por eso: `logging.basicConfig()` armaba un StreamHandler
sobre ese None, Kivy redirigía después `sys.stderr` a un stream que reinyecta
lo escrito como `Logger.warning`, y el handler roto se realimentaba a sí mismo
por `handleError` hasta matar el proceso con un RecursionError.

Estos tests van más allá de "no se cae":

- comprueban la propiedad de fondo (ningún handler apuntando a un stream que no
  se puede escribir), no el síntoma puntual;
- comprueban que lo que se deja de escribir en consola termina en el archivo de
  log, porque un arreglo que consista en tragarse los errores no es un arreglo;
- y el primero de todos comprueba que el escenario simulado ACÁ todavía mata a
  un proceso sin el arreglo. Sin esa guardia, el resto podría seguir en verde
  mientras deja de probar nada.
"""

import os

import pytest

from soporte_consola import (
    HOOK,
    KIVY_TOMA_STDERR,
    SIN_CONSOLA,
    VOLVER_A_LA_CONSOLA,
    en_proceso_aparte,
    veredicto,
)


# --------------------------------------------------------------------------
# La guardia: el escenario tiene que seguir siendo capaz de reproducir el bug
# --------------------------------------------------------------------------

def test_el_escenario_simulado_todavia_mata_a_un_proceso_sin_arreglo():
    """
    Sin el arreglo, este escenario tiene que matar al intérprete.

    Es la prueba de que los tests de abajo prueban algo. Si este test falla, no
    hay que "arreglarlo": significa que la simulación dejó de reproducir el bug
    original (por ejemplo porque cambió el logging de la stdlib) y entonces
    todos los demás pasaron a ser tests vacíos que hay que rehacer.
    """
    resultado = en_proceso_aparte(f"""
{SIN_CONSOLA}
logging.basicConfig(level=logging.INFO)   # <- exactamente lo que hacía la 3.6.4
registro = logging.getLogger("GUI")
registro.info("primer log")
{KIVY_TOMA_STDERR}
registro.info("segundo log")
{VOLVER_A_LA_CONSOLA}
print("SOBREVIVIO")
""", comprobar=False)

    assert resultado.returncode != 0 and "SOBREVIVIO" not in resultado.stdout, (
        "el escenario ya no reproduce el fallo original, así que los tests de "
        "regresión de este archivo dejaron de probar el bug. Hay que rehacer "
        "la simulación, no relajar este test."
    )


# --------------------------------------------------------------------------
# El arreglo
# --------------------------------------------------------------------------

def test_sin_consola_el_arranque_sobrevive_a_que_kivy_tome_stderr():
    """El mismo escenario, pero pasando por el logger de Fiscalberry."""
    resultado = en_proceso_aparte(f"""
{SIN_CONSOLA}
from fiscalberry.common.fiscalberry_logger import getLogger

registro = getLogger("GUI")
registro.info("lo que loguea el arranque temprano de la GUI")
{KIVY_TOMA_STDERR}

# Muchos, y desde dentro de un except: así es como se encadenaban los
# "During handling of the above exception" del traceback que reportó el usuario.
for i in range(200):
    try:
        raise RuntimeError("algo falló adentro")
    except RuntimeError:
        registro.error("error numero %s", i, exc_info=True)

{VOLVER_A_LA_CONSOLA}
print(json.dumps({{"vivo": True}}))
""")

    assert veredicto(resultado)["vivo"]


def test_ningun_handler_queda_apuntando_a_un_stream_que_no_se_puede_escribir():
    """
    La propiedad de fondo, no el síntoma.

    Da igual cómo se configure el logging: si algún handler queda con un stream
    que no se puede escribir, el fallo vuelve. Este test lo prohíbe en general,
    así que también atrapa un `basicConfig()` que alguien reintroduzca mañana.
    """
    resultado = en_proceso_aparte(f"""
{SIN_CONSOLA}
from fiscalberry.common.fiscalberry_logger import getLogger, setup_file_logging
setup_file_logging(role="test")
getLogger("GUI").info("algo")

rotos = []
for h in logging.getLogger().handlers:
    stream = getattr(h, "stream", "no-aplica")
    if stream != "no-aplica" and not hasattr(stream, "write"):
        rotos.append(type(h).__name__)

{VOLVER_A_LA_CONSOLA}
print(json.dumps({{
    "rotos": rotos,
    "handlers": [type(h).__name__ for h in logging.getLogger().handlers],
}}))
""")

    datos = veredicto(resultado)
    assert datos["rotos"] == [], (
        f"handlers escribiendo a un stream inválido: {datos['rotos']}")
    assert "StreamHandler" not in datos["handlers"], (
        "sin consola no puede haber StreamHandler: es el handler que reventaba")


def test_con_consola_el_logging_sigue_funcionando_igual():
    """El arreglo no puede cambiar nada en el arranque normal."""
    resultado = en_proceso_aparte("""
from fiscalberry.common.fiscalberry_logger import getLogger
getLogger("GUI").info("visible")
print(json.dumps({
    "handlers": [type(h).__name__ for h in logging.getLogger().handlers],
    "raise_exceptions": logging.raiseExceptions,
}))
""")

    datos = veredicto(resultado)
    assert "StreamHandler" in datos["handlers"]
    assert "INFO:GUI:visible" in resultado.stderr
    # Apagar raiseExceptions taparía también los fallos del log en archivo.
    assert datos["raise_exceptions"] is True, (
        "no se puede apagar el reporte de errores de logging para todo el proceso")


# --------------------------------------------------------------------------
# Que el error no se silencie
# --------------------------------------------------------------------------

def test_sin_consola_los_errores_terminan_completos_en_el_archivo(tmp_path):
    """
    Lo que ya no va a la consola tiene que ir al archivo, traceback incluido.

    Si no, el arreglo sería sacarle la voz al programa en vez de darle una.
    """
    carpeta = tmp_path / "logs"
    resultado = en_proceso_aparte(f"""
{SIN_CONSOLA}
from fiscalberry.common import fiscalberry_logger as registro_mod
registro_mod._log_dir = lambda: {str(carpeta)!r}
registro_mod.setup_file_logging(role="test")

registro = registro_mod.getLogger("GUI")
{KIVY_TOMA_STDERR}
try:
    raise ValueError("la causa real del problema")
except ValueError:
    registro.error("Error crítico en GUI", exc_info=True)

{VOLVER_A_LA_CONSOLA}
print(json.dumps({{"ok": True}}))
""")
    assert veredicto(resultado)["ok"]

    archivo = carpeta / "fiscalberry.log"
    assert archivo.exists(), "sin consola, el log en archivo es la única salida"
    contenido = archivo.read_text(encoding="utf-8")
    assert "Error crítico en GUI" in contenido
    assert "ValueError: la causa real del problema" in contenido
    assert "Traceback" in contenido, "el traceback no se puede perder"


def test_si_el_log_en_archivo_no_se_puede_abrir_el_motivo_queda_a_la_vista():
    """
    Sin consola y sin archivo, el usuario no tiene nada. Que al menos sepa por
    qué: la pantalla de registro muestra el motivo en vez de aparecer vacía.
    """
    resultado = en_proceso_aparte(f"""
{SIN_CONSOLA}
from fiscalberry.common import fiscalberry_logger as registro_mod

def _explota():
    raise OSError("disco de solo lectura")
registro_mod._log_dir = _explota

handler = registro_mod.setup_file_logging(role="test")

{VOLVER_A_LA_CONSOLA}
print(json.dumps({{
    "handler": handler,
    "motivo": registro_mod.motivo_sin_log_en_archivo(),
    "pantalla": registro_mod.readLogTail(path="/no/existe/tampoco"),
}}))
""")

    datos = veredicto(resultado)
    assert datos["handler"] is None, "no puede decir que configuró lo que no pudo"
    assert "disco de solo lectura" in (datos["motivo"] or "")
    assert "disco de solo lectura" in datos["pantalla"], (
        "la pantalla de registro no puede quedar en blanco escondiendo el motivo")


def test_una_excepcion_del_arranque_no_se_traga(tmp_path):
    """
    Si la GUI no puede levantar, el proceso tiene que morir con la excepción
    a la vista —es lo que hace que PyInstaller muestre el cartel de error— y
    además dejarla escrita en el archivo.
    """
    carpeta = tmp_path / "logs"
    resultado = en_proceso_aparte(f"""
{SIN_CONSOLA}
import types
from fiscalberry.common import fiscalberry_logger as registro_mod
registro_mod._log_dir = lambda: {str(carpeta)!r}

falso = types.ModuleType("fiscalberry.ui.fiscalberry_app")
class FiscalberryApp:
    def __init__(self): raise RuntimeError("no hay display")
falso.FiscalberryApp = FiscalberryApp
sys.modules["fiscalberry.ui.fiscalberry_app"] = falso

from fiscalberry.desktop.main import main
sys.argv = ["fiscalberry-gui"]
main()
""", comprobar=False)

    assert resultado.returncode != 0, "una GUI que no levanta no puede salir con 0"
    archivo = carpeta / "fiscalberry.log"
    assert archivo.exists()
    contenido = archivo.read_text(encoding="utf-8")
    assert "RuntimeError: no hay display" in contenido
    assert "=== Finalizando Fiscalberry GUI ===" in contenido


# --------------------------------------------------------------------------
# El entrypoint completo
# --------------------------------------------------------------------------

def test_el_entrypoint_de_la_gui_arranca_entero_sin_consola(tmp_path):
    """
    De punta a punta: `main()` con los streams en None, como en el .exe.

    Cubre el orden real —modos especiales, log en archivo, updater, Kivy— que
    es donde el fallo aparecía: el primer logger.info() ocurría antes de que
    nadie hubiera configurado una salida válida.
    """
    carpeta = tmp_path / "logs"
    resultado = en_proceso_aparte(f"""
{SIN_CONSOLA}
import types
from fiscalberry.common import fiscalberry_logger as registro_mod
registro_mod._log_dir = lambda: {str(carpeta)!r}

falso = types.ModuleType("fiscalberry.ui.fiscalberry_app")
class FiscalberryApp:
    def run(self):
        {KIVY_TOMA_STDERR.replace(chr(10), chr(10) + "        ")}
        logging.getLogger("APP").info("la app corrió")
falso.FiscalberryApp = FiscalberryApp
sys.modules["fiscalberry.ui.fiscalberry_app"] = falso

from fiscalberry.desktop.main import main
sys.argv = ["fiscalberry-gui"]
main()

{VOLVER_A_LA_CONSOLA}
print(json.dumps({{"ok": True}}))
""")

    assert veredicto(resultado)["ok"]
    contenido = (carpeta / "fiscalberry.log").read_text(encoding="utf-8")
    assert "=== Iniciando Fiscalberry GUI ===" in contenido
    assert "la app corrió" in contenido
    assert "=== Finalizando Fiscalberry GUI ===" in contenido
    # El rol tiene que ser el mismo que usa ui/fiscalberry_app.py: es el mismo
    # proceso, y setup_file_logging es idempotente, así que gana el primero.
    assert "[app:" in contenido


# --------------------------------------------------------------------------
# El runtime hook de PyInstaller
# --------------------------------------------------------------------------

def test_el_runtime_hook_deja_los_streams_usables():
    """
    En el ejecutable el hook corre antes que nada, y evita que reviente
    cualquier escritura a consola: la propia, la de Kivy y la de terceros.
    """
    resultado = en_proceso_aparte(f"""
import traceback
{SIN_CONSOLA}
exec(open({HOOK!r}, encoding="utf-8").read())

try:
    raise ValueError("como el traceback.print_exc() de los entry points")
except ValueError:
    traceback.print_exc()

print("un print cualquiera")
print("y uno a stderr", file=sys.stderr)
sys.stdout.flush()
datos = {{"encoding": sys.stdout.encoding, "escribible": sys.stdout.writable()}}

{VOLVER_A_LA_CONSOLA}
print(json.dumps(datos))
""")

    datos = veredicto(resultado)
    # Hay librerías que consultan sys.stdout.encoding antes de escribir.
    assert datos["encoding"] == "utf-8"
    assert datos["escribible"] is True


def test_el_runtime_hook_no_pisa_una_consola_que_si_existe():
    """En el binario de consola no tiene que cambiar nada."""
    resultado = en_proceso_aparte(f"""
originales = (sys.stdout, sys.stderr)
exec(open({HOOK!r}, encoding="utf-8").read())
print(json.dumps({{"intactos": (sys.stdout, sys.stderr) == originales}}))
""")

    assert veredicto(resultado)["intactos"]


def test_con_el_hook_los_logs_siguen_yendo_al_archivo(tmp_path):
    """
    El hook descarta lo que va a consola. Que no se lleve puesto el log de
    verdad: es la única salida que le queda al ejecutable de Windows.
    """
    carpeta = tmp_path / "logs"
    resultado = en_proceso_aparte(f"""
{SIN_CONSOLA}
exec(open({HOOK!r}, encoding="utf-8").read())

from fiscalberry.common import fiscalberry_logger as registro_mod
registro_mod._log_dir = lambda: {str(carpeta)!r}
registro_mod.setup_file_logging(role="test")
{KIVY_TOMA_STDERR}
registro_mod.getLogger("GUI").error("esto tiene que quedar registrado")

{VOLVER_A_LA_CONSOLA}
print(json.dumps({{"ok": True}}))
""")

    assert veredicto(resultado)["ok"]
    contenido = (carpeta / "fiscalberry.log").read_text(encoding="utf-8")
    assert "esto tiene que quedar registrado" in contenido
