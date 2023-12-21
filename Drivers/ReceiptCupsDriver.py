# -*- coding: utf-8 -*-
from escpos import printer, escpos
import threading
import time
import logging
from DriverInterface import DriverInterface


class ReceiptCupsDriver(printer.Cups, DriverInterface):

    def __init__(self, printer_name, *args, **kwargs):  # noqa: N803
        """
        :param printer_name: Nombre de la impresora
        """
        escpos.Escpos.__init__(self, *args, **kwargs)
        self.printer_name = printer_name
        self.logger = logging.getLogger("CUPSDriver")

    def start(self):
        try:
            self.open()
        except Exception as e:
            self.logger.error("Error de la impresora: "+str(e))

    def end(self):
        try:
            self.close()
        except Exception as e:
            self.logger.error("Error de la impresora: "+str(e))

    def reconnect(self):
        pass