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
    Devuelve la ruta del archivo de log.
    Nota: En esta versión simplificada no hay archivo de log,
    pero mantenemos la función para compatibilidad con la GUI.
    """
    return None
