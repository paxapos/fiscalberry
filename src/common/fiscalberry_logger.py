import os
import logging
import tempfile

from common.Configberry import Configberry

configberry = Configberry()

environment = configberry.config.get("SERVIDOR", "environment", fallback="production")

# Define la ruta del archivo de log en la carpeta temporal multiplataforma
LOG_OUTPUT_FILEPATH = os.path.join(tempfile.gettempdir(), "cli.log")


# configuro logger segun ambiente
if environment == 'development':
    print("* * * * * Modo de desarrollo * * * * *")
    logging.basicConfig(
        level=logging.DEBUG,
        filename=LOG_OUTPUT_FILEPATH,
        format="%(asctime)s - %(levelname)s - %(message)s",
        )
else:
    print("@ @ @ @ @ Modo de producción @ @ @ @ @")
    logging.basicConfig(
        level=logging.WARNING,
        filename=LOG_OUTPUT_FILEPATH,
        format="%(asctime)s - %(levelname)s - %(message)s"
        )


logging.getLogger("pika").setLevel(logging.WARNING)


try:
    from kivy.logger import Logger
except ImportError:
    import logging
    Logger = logging.getLogger("** Fiscalberry ** ")
    

def getLogFilePath():
    """Devuelve la ruta del archivo de log."""
    
    # Verifica si el archivo de log existe, si no lo crea
    if not os.path.exists(LOG_OUTPUT_FILEPATH):
        with open(LOG_OUTPUT_FILEPATH, "w") as f:
            pass

    # Verifica si el archivo de log es escribible
    if not os.access(LOG_OUTPUT_FILEPATH, os.W_OK):
        Logger.error(f"El archivo de log {LOG_OUTPUT_FILEPATH} no es escribible.")
        exit(1)

    return LOG_OUTPUT_FILEPATH



def getLogger():
    
    return Logger