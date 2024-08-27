# -*- coding: UTF-8 -*-

import requests
from common.fiscalberry_logger import getLogger
from common.ComandoInterface import ComandoInterface, ComandoException


class PrinterException(Exception):
    pass


class FiscalberryComandos(ComandoInterface):
    # el traductor puede ser: TraductorFiscal o TraductorReceipt
    # path al modulo de traductor que este comando necesita
    traductorModule = "common.Traductores.TraductorFiscalberry"

    DEFAULT_DRIVER = "Fiscalberry"


    def _sendCommand(self, comando, skipStatusErrors=False):
        try:
            ret = self.conector.sendCommand(comando, skipStatusErrors)
            return ret
        except PrinterException as e:
            getLogger().error("PrinterException: %s" % str(e))
            raise ComandoException("Error de la impresora: %s.\nComando enviado: %s" % \
                                   (str(e), comando))

