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

def getLogFilePath():
    """
    Devuelve la ruta del archivo de log actual de Kivy.
    
    Kivy genera automáticamente logs en ~/.kivy/logs/kivy_*.txt
    Esta función retorna el archivo de log más reciente.
    """
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
