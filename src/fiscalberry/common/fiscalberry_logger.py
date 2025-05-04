import os
import logging
import tempfile
from logging.handlers import RotatingFileHandler
from fiscalberry.common.Configberry import Configberry

# Cargar configuración del ambiente
configberry = Configberry()
environment = configberry.config.get("SERVIDOR", "environment", fallback="production")

# Ruta del archivo de log (rotativo)
LOG_OUTPUT_FILEPATH = os.path.join(tempfile.gettempdir(), "fiscalberry.log")

# Crea el logger base
logger = logging.getLogger("Fiscalberry")
logger.setLevel(logging.DEBUG)  # Capturamos de DEBUG hacia arriba internamente

# Formato de log
log_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# RotatingFileHandler: máximo 5MB por archivo, con 3 backups
file_handler = RotatingFileHandler(LOG_OUTPUT_FILEPATH, maxBytes=5*1024*1024, backupCount=3)
file_handler.setFormatter(log_format)

# En desarrollo mostramos más información en consola
if environment.lower() == "development":
    console_level = logging.DEBUG
    print("* * * * * Modo de desarrollo * * * * *")
else:
    console_level = logging.WARNING
    print("@ @ @ @ @ Modo de producción @ @ @ @ @")

# StreamHandler para la consola
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_format)
console_handler.setLevel(console_level)

# Evitar agregar manejadores duplicados en caso de recarga
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# Reducir el ruido de librerías de terceros, por ejemplo "pika"
logging.getLogger("pika").setLevel(logging.WARNING)

# Intenta usar el logger de Kivy si está disponible

Logger = logger

def getLogFilePath():
    """Devuelve la ruta del archivo de log."""
    # Crea el archivo si no existe
    if not os.path.exists(LOG_OUTPUT_FILEPATH):
        open(LOG_OUTPUT_FILEPATH, "w").close()
    # Verifica permisos de escritura
    if not os.access(LOG_OUTPUT_FILEPATH, os.W_OK):
        Logger.error(f"El archivo de log {LOG_OUTPUT_FILEPATH} no es escribible.")
        exit(1)
    return LOG_OUTPUT_FILEPATH

def getLogger():
    return Logger