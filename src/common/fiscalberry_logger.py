import os

try:
    from kivy.logger import Logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.DEBUG)
    environment = os.getenv('ENVIRONMENT', 'development')
    if environment != 'development':
        logging.basicConfig(level=logging.WARNING)
    else:  # development
        logging.basicConfig(level=logging.DEBUG)
    Logger = logging.getLogger("** Fiscalberry ** ")


def getLogger():
    return Logger