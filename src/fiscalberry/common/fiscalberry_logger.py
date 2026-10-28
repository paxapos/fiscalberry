import os
import sys
import logging


def _escribible(stream):
    """
    ¿Se puede escribir en este stream?

    Vale None cuando no hay consola: el ejecutable GUI de Windows (PyInstaller
    con `console=False`) y cualquier arranque bajo `pythonw`.
    """
    return stream is not None and hasattr(stream, "write")


# Se decide una sola vez, al importar, porque es lo único que hace falta: los
# handlers se arman acá abajo y de ahí en más nadie más lo consulta. Kivy
# reemplaza sys.stderr al importarse, así que este valor no sirve para
# preguntar más tarde.
_HAY_CONSOLA = _escribible(getattr(sys, "stderr", None))


def _a_consola(mensaje):
    """print() que no depende de que exista una consola."""
    if _escribible(getattr(sys, "stdout", None)):
        print(mensaje)


# Evitar referencia circular en la importación
def get_configberry():
    from fiscalberry.common.Configberry import Configberry
    return Configberry()

# Determinar ambiente
try:
    configberry = get_configberry()
    environment = configberry.config.get("SERVIDOR", "environment", fallback="production").lower()
except Exception:
    environment = "production"

# Anunciar el modo de ejecución (estilo v1.0.26)
if environment == 'development':
    _a_consola("* * * * * Modo de desarrollo * * * * *")
    _nivel = logging.DEBUG
    sioLogger = True
else:
    _a_consola("@ @ @ @ @ Modo de producción @ @ @ @ @")
    _nivel = logging.INFO  # Cambiado de WARNING a INFO
    sioLogger = False

if _HAY_CONSOLA:
    logging.basicConfig(level=_nivel)
else:
    # Sin consola, basicConfig() instalaría un StreamHandler sobre None y cada
    # emit reventaría con "'NoneType' object has no attribute 'write'". Peor
    # todavía: al importarse, Kivy redirige sys.stderr a un stream que reinyecta
    # lo escrito como Logger.warning, con lo que el handler roto se realimenta a
    # sí mismo a través de handleError hasta matar al proceso con un
    # RecursionError. Eso era lo que impedía arrancar a la GUI 3.6.4 en Windows.
    # El NullHandler ocupa el lugar para que basicConfig no ponga el suyo; los
    # logs de verdad los toma setup_file_logging().
    #
    # En los ejecutables esto además está cubierto por el runtime hook
    # `build_tools/pyi_rth_consola.py`, que les da un stream de descarte. Esta
    # rama es la que cubre lo que el hook no alcanza: `pythonw`, servicios de
    # Windows y cualquier arranque no empaquetado.
    logging.basicConfig(level=_nivel, handlers=[logging.NullHandler()])

# Silenciar logs de librerías externas
logging.getLogger("paho").setLevel(logging.WARNING)
logging.getLogger("pika").setLevel(logging.WARNING)
logging.getLogger("socketio").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Logger global
Logger = logging.getLogger()

def getLogger(name=None):
    """Obtiene el logger global o uno específico por nombre."""
    if name:
        return logging.getLogger(name)
    return Logger

LOG_FILE_NAME = "fiscalberry.log"
_file_handler = None

# Por qué no hay log en archivo, si es que no lo hay. Sin consola —el .exe de
# Windows— este error no tenía a dónde ir: el usuario se quedaba sin ningún
# rastro de lo que pasó Y sin manera de enterarse de que no lo había.
_motivo_sin_archivo = None


def _log_dir():
    from fiscalberry.common.Configberry import Configberry

    return os.path.join(os.path.dirname(Configberry().getConfigFIle()), "logs")


def getServiceLogFilePath():
    """Ruta del log en archivo (la escriben tanto la UI como el servicio)."""
    try:
        return os.path.join(_log_dir(), LOG_FILE_NAME)
    except Exception:
        return None


def setup_file_logging(role="app", level=logging.INFO):
    """
    Manda los logs a un archivo rotativo, además de la consola.

    Sin esto, en Android todo va solo a logcat: el servicio corre en otro
    proceso y sus logs —los que importan para diagnosticar por qué no imprime—
    no quedan en ningún lado que el usuario pueda ver desde la app.

    Ambos procesos escriben el mismo archivo; por eso cada línea lleva el rol y
    el PID. Es idempotente: llamarla dos veces no duplica handlers.
    """
    global _file_handler, _motivo_sin_archivo

    if _file_handler is not None:
        return _file_handler

    try:
        from logging.handlers import RotatingFileHandler

        directorio = _log_dir()
        os.makedirs(directorio, exist_ok=True)
        ruta = os.path.join(directorio, LOG_FILE_NAME)

        handler = RotatingFileHandler(
            ruta, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                f"%(asctime)s [{role}:%(process)d] %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

        root = logging.getLogger()
        root.addHandler(handler)
        if root.level > level:
            root.setLevel(level)

        _file_handler = handler
        _motivo_sin_archivo = None
        root.info(f"Log en archivo: {ruta} (rol={role})")
        return handler
    except Exception as e:
        # Nunca romper el arranque por no poder loguear a archivo, pero que no
        # se pierda: sin consola, este print no lo lee nadie. Queda anotado
        # para que la pantalla de registro lo muestre en vez de aparecer vacía.
        _motivo_sin_archivo = f"No se pudo configurar el log en archivo: {e}"
        _a_consola(_motivo_sin_archivo)
        return None


def motivo_sin_log_en_archivo():
    """El error que dejó al proceso sin log en archivo, o None si hay log."""
    return _motivo_sin_archivo


def readLogTail(max_bytes=16384, path=None):
    """
    Devuelve el FINAL del log (por defecto 16 KB).

    Nunca el archivo entero: la UI refresca cada segundo y el archivo rota
    recién al llegar a 1 MB. Volcar todo eso en un Label de Kivy genera una
    textura enorme en cada refresco y tumba la app.
    """
    ruta = path or getLogFilePath()
    if not ruta or not os.path.exists(ruta):
        # Una pantalla de registro vacía no distingue "todavía no pasó nada" de
        # "el log nunca se pudo abrir". Si fue lo segundo, decirlo.
        return _motivo_sin_archivo or ""

    try:
        tamanio = os.path.getsize(ruta)
        with open(ruta, "rb") as fh:
            if tamanio > max_bytes:
                fh.seek(tamanio - max_bytes)
                # Descartar la primera línea, casi seguro cortada al medio.
                fh.readline()
            datos = fh.read()
        return datos.decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error al leer log: {e}"


def getLogFilePath():
    """
    Devuelve la ruta del archivo de log a mostrar en la UI.

    Prioriza el log propio de Fiscalberry (que incluye los del proceso del
    servicio); si todavía no existe, cae al log de Kivy.
    """
    propio = getServiceLogFilePath()
    if propio and os.path.exists(propio):
        return propio

    try:
        # Intentar obtener la ruta del log desde Kivy Logger
        # Importamos aquí para evitar dependencia dura si no se usa GUI
        from kivy.logger import Logger as KivyLogger
        
        # Kivy guarda la ruta del log actual en Logger.logfile
        if hasattr(KivyLogger, 'logfile') and KivyLogger.logfile:
            return KivyLogger.logfile
            
        # Fallback: buscar el archivo más reciente en ~/.kivy/logs/
        # Esto sirve si Kivy aún no inicializó completamente el Logger
        # OJO: no re-importar `os` acá. Un `import os` local convierte a `os` en
        # variable local de TODA la función, y el uso de arriba (antes de esta
        # línea) revienta con UnboundLocalError. Ya está importado arriba.
        import glob

        kivy_log_dir = os.path.expanduser("~/.kivy/logs")
        
        if not os.path.exists(kivy_log_dir):
            return None
        
        log_files = glob.glob(os.path.join(kivy_log_dir, "kivy_*.txt"))
        if not log_files:
            return None
        
        # Retornar el archivo más reciente
        latest_log = max(log_files, key=os.path.getmtime)
        return latest_log
        
    except Exception as e:
        # Si falla (ej: no instalado kivy), retornamos None
        # El caller (GUI) debe manejar el None
        return None
