# -*- coding: utf-8 -*-

from escpos import printer, escpos
import threading
import time
from DriverInterface import DriverInterface


# TCP_PORT = 9100


class UsbAndSerialDriver(printer.Serial, DriverInterface):
    connected = False

    def __init__(self, devfile="/dev/ttyACM0", baudrate=9600, bytesize=8, timeout=1, parity='N', stopbits=1, xonxoff=False, dsrdtr=True, codepage="cp858", mac="", *args, **kwargs):
        """ escrito aqui solo para tener bien en claro las variables iniciales"""
        """
        :param path : The path of the printer's file in the system. (Example: ttyACM0 in linux, or COM1 in Windows).
        :param port : Port to write to
        :param codepage : codepage default to cp858
        """
        escpos.Escpos.__init__(self, *args, **kwargs)
        self.devfile = devfile
        self.baudrate = 9600
        self.codepage = codepage

    def start(self):
    	self.open()

    def end(self):
    	self.close()

    def reconnect(self):
		pass