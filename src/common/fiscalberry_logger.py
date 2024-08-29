import os

try:
    from kivy.logger import Logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.DEBUG)
    environment = os.getenv('ENVIRONMENT', 'production')
    if environment == 'development':
        logging.basicConfig(level=logging.DEBUG)
    else:  
        logging.basicConfig(level=logging.WARNING)
    Logger = logging.getLogger("** Fiscalberry ** ")


def getLogger():
    return Logger