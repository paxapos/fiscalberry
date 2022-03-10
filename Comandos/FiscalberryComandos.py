# -*- coding: UTF-8 -*-

import requests
import logging
from ComandoInterface import ComandoInterface, ComandoException


class PrinterException(Exception):
    pass


class FiscalberryComandos(ComandoInterface):
    # el traductor puede ser: TraductorFiscal o TraductorReceipt
    # path al modulo de traductor que este comando necesita
    traductorModule = "Traductores.TraductorFiscalberry"

    DEFAULT_DRIVER = "Fiscalberry"


    def _sendCommand(self, comando, skipStatusErrors=False):
        try:
            ret = self.conector.sendCommand(comando, skipStatusErrors)
            return ret
        except PrinterException as e:
            logging.getLogger("ProxyComandos").error("PrinterException: %s" % str(e))
            raise ComandoException("Error de la impresora: %s.\nComando enviado: %s" % \
                                   (str(e), comando))

