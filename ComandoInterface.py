# -*- coding: iso-8859-1 -*-
from ConectorDriverComando import ConectorDriverComando
import unicodedata
import importlib
import logging
import string
import types
from array import array


class ValidationError(Exception):
    pass

class FiscalPrinterError(Exception):
    pass

class ComandoException(RuntimeError):
    pass

class ComandoInterface:
    """Interfaz que deben cumplir las impresoras."""

    DEFAULT_DRIVER = None   

    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop("modelo", None)
        driver = kwargs.pop("driver", self.DEFAULT_DRIVER)

        # inicializo el driver
        self.conector = ConectorDriverComando(self, driver, **kwargs)

        # inicializo el traductor
        traductorModule = importlib.import_module(self.traductorModule)
        traductorClass = getattr(traductorModule, self.traductorModule[12:])
        self.traductor = traductorClass(self, *args)

        # seteo anchos de columnas
        self.total_cols = self.conector.driver.cols
        self.price_cols = 12
        self.cant_cols = 4
        self.desc_cols =  self.total_cols - self.cant_cols - self.price_cols

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        raise Exception("NotImplementedException")

    def close(self):
        """Cierra la impresora"""
        self.conector.close()
