# -*- coding: utf-8 -*-

import socket
from escpos import printer, escpos
import threading
import time
import logging
from DriverInterface import DriverInterface


# TCP_PORT = 9100


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

    def start(self):
        """ iniciar """
        try:
            self.open()
            self.connected = True
        except Exception as e:
            logging.error("Error de la impresora: " + str(e))
            return True


    def end(self):
        try:
            self.close()
            self.connected = False
        except Exception as e:
            logging.error("Error de la impresora: "+str(e))

    def reconnect(self):
        try:
            self.open()
            self.connected = True
        except Exception as e:
            self.connected = False
