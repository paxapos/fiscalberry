import os

try:
    from kivy.logger import Logger
except ImportError:
    import logging
    Logger = logging.getLogger("** Fiscalberry ** ")


def getLogger():
    return Logger