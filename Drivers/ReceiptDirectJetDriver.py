# -*- coding: utf-8 -*-

import socket
from escpos import printer, escpos
import threading
import time
from DriverInterface import DriverInterface


# TCP_PORT = 9100


class ReceiptDirectJetDriver(printer.Network, DriverInterface):
    connected = False

    def __init__(self, host, port=9100, timeout=10, codepage="cp858", mac="", vendor="", *args, **kwargs):
        """ escrito aqui solo para tener bien en claro las variables iniciales"""
        """
        :param host : Printer's hostname or IP address
        :param port : Port to write to
        :param timeout : timeout in seconds for the socket-library
        :param codepage : codepage default to cp858
        """
        escpos.Escpos.__init__(self, *args, **kwargs)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.codepage = codepage

    def start(self):
        """ iniciar """
        self.open()
        self.connected = True

    def end(self):
        self.close()
        self.connected = False

    def reconnect(self):
        try:
            self.open()
            self.connected = True
        except Exception as e:
            self.connected = False
