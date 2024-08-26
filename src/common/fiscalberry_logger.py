import logging

try:
    from kivy.logger import Logger
except ImportError:
    Logger = logging.getLogger("Fiscalberry")


def getLogger():
    return Logger