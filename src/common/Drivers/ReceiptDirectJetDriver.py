# -*- coding: utf-8 -*-
from escpos import printer, escpos
from common.fiscalberry_logger import getLogger
from common.DriverInterface import DriverInterface


class ReceiptDirectJetDriver(printer.Network, DriverInterface):
    connected = False

    def __init__(self, host, port=9100, timeout=10, codepage="cp858", mac="", vendor="", cols = 42, *args, **kwargs):
        """ escrito aqui solo para tener bien en claro las variables iniciales"""
        """
        :param host : Printer's hostname or IP address
        :param port : Port to write to
        :param timeout : timeout in seconds for the socket-library
        :param codepage : codepage default to cp858
        :param cols : Defaults to 42 columns for the Sam4s Giant
        """
        escpos.Escpos.__init__(self, *args, **kwargs)
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.codepage = codepage
        self.cols = int(cols)
        self.logger = getLogger()

    def start(self):
        """ iniciar """
        try:
            self.open()
            self.connected = True
        except Exception as e:
            self.logger.error(f"Error de la impresora: {str(e)}")
            self.logger.info(f"Cerrando Socket: {self.device}")
            self.device.close()
            self.logger.info(f"Socket Cerrado: {self.device}")
            raise


    def end(self):
        try:
            self.close()
            self.connected = False
        except Exception as e:
            self.logger.error("Error de la impresora: " + str(e))
            self.logger.info(f"Cerrando Socket: {self.device}")
            self.device.close()
            self.logger.info(f"Socket Cerrado: {self.device}")
            


    def reconnect(self):
        try:
            self.open()
            self.connected = True
        except Exception as e:
            self.logger.error(f"Error de la impresora: {str(e)}")
            self.logger.info(f"Cerrando Socket: {self.device}")
            self.device.close()
            self.logger.info(f"Socket Cerrado: {self.device}")
