# -*- coding: utf-8 -*-

from escpos import printer, escpos
import threading
import logging
import serial
import time
from DriverInterface import DriverInterface


# TCP_PORT = 9100


class ReceiptSerialDriver(printer.Serial, DriverInterface):
    connected = False

    def __init__(self, devfile="/dev/ttyS0", baudrate=9600, bytesize=8, timeout=1,
                 parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                 xonxoff=False, dsrdtr=True, codepage="cp858", *args, **kwargs):
        """
        @param devfile  : Device file under dev filesystem
        @param baudrate : Baud rate for serial transmission
        @param bytesize : Serial buffer size
        @param timeout  : Read/Write timeout
        """
        escpos.Escpos.__init__(self, *args, **kwargs)
        self.devfile = devfile
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.timeout = timeout
        self.parity = parity
        self.stopbits = stopbits
        self.xonxoff = xonxoff
        self.dsrdtr = dsrdtr
        self.codepage = codepage
       

    def start(self):
        try:
            self.open()
        except Exception as e:
            logging.error("Error de la impresora: "+str(e))

    def end(self):
        try:
            self.close()
        except Exception as e:
            logging.error("Error de la impresora: "+str(e))

    def reconnect(self):
		pass