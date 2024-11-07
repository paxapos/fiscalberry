import os
import logging

from common.Configberry import Configberry

configberry = Configberry()

environment = configberry.config.get("SERVIDOR", "environment", fallback="production")


# configuro logger segun ambiente
if environment == 'development':
    print("* * * * * Modo de desarrollo * * * * *")
    logging.basicConfig(level=logging.DEBUG)
else:
    print("@ @ @ @ @ Modo de producción @ @ @ @ @")
    logging.basicConfig(level=logging.WARNING)


logging.getLogger("pika").setLevel(logging.WARNING)


try:
    from kivy.logger import Logger
except ImportError:
    import logging
    Logger = logging.getLogger("** Fiscalberry ** ")
    


def getLogger():
    return Logger