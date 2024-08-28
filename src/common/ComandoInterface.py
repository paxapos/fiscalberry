# -*- coding: iso-8859-1 -*-
from common.ConectorDriverComando import ConectorDriverComando
import unicodedata
import logging
import string
import types
from array import array
from common.Traductores.TraductorFiscalberry import  TraductorFiscalberry
from common.Traductores.TraductorReceipt import TraductorReceipt


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
        traductorClass = self.traductorModule

        # inicializo el traductor
        if traductorClass == "TraductorFiscalberry":
            self.traductor = TraductorFiscalberry(self, *args)
        elif traductorClass == "TraductorReceipt":
            self.traductor = TraductorReceipt(self, *args)
        else:
            raise ValueError("Invalid traductorClass value")

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        raise Exception("NotImplementedException")

    def close(self):
        """Cierra la impresora"""
        self.conector.close()
