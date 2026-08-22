import os
import logging

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
    print("* * * * * Modo de desarrollo * * * * *")
    logging.basicConfig(level=logging.DEBUG)
    sioLogger = True
else:
    print("@ @ @ @ @ Modo de producción @ @ @ @ @")
    logging.basicConfig(level=logging.INFO)  # Cambiado de WARNING a INFO
    sioLogger = False

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
    global _file_handler

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
        root.info(f"Log en archivo: {ruta} (rol={role})")
        return handler
    except Exception as e:
        # Nunca romper el arranque por no poder loguear a archivo.
        print(f"No se pudo configurar el log en archivo: {e}")
        return None


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
        import glob
        import os
        
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
