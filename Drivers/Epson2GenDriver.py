# -*- coding: utf-8 -*-
from DriverInterface import DriverInterface
import logging
import ctypes
from ctypes import byref, c_int, c_char, c_char_p, c_long, c_short, create_string_buffer
import platform
import os


archbits = platform.architecture()[0]
newpath = os.path.dirname(os.path.realpath(__file__))
if archbits[0:2] == "64":
    fullpath = "/lib64/libEpsonFiscalInterface.so"
else:
    fullpath = "/lib/libEpsonFiscalInterface.so"

EpsonLibInterface = ctypes.cdll.LoadLibrary(fullpath)


class Epson2GenDriver(DriverInterface):

    __name__ = "Epson2GenDriver"

    fiscalStatusErrors = []

    printerStatusErrors = []

    #
    #	path disponibles
    #	default serial: /dev/usb/lp0
    #	“0” – USB.
    #	“1” – COM1 o ttyS0.
    #	“2” – COM2 o ttyS1.
    #	“ x ” – COM x o ttyS( x -1).
    #	“serial:COM x ” – COM x
    #	“serial: /dev/ttyS x ” – ttyS x
    #	“lan:192.168.1.1” – Http ip 192.168.1.1
    #	“lan:192.168.1.1:443” – Http ip 192.168.1.1 puerto 443
    #

    def __init__(self, path='serial: /dev/usb/lp0', baudrate=9600):
        print("-" * 26)
        print("*" * 26)
        print("EPSON FISCAL".center(26," "))
        print("*" * 26)
        print("-" * 26)

        self.port = path
        self.baudrate = baudrate
        self.EpsonLibInterface = EpsonLibInterface

    def start(self):
        """Inicia recurso de conexion con impresora"""
        self.EpsonLibInterface.ConfigurarVelocidad(c_int(self.baudrate).value)
        self.EpsonLibInterface.ConfigurarPuerto(self.port)
        error = self.EpsonLibInterface.Conectar()
        logging.info(error)

        str_version_max_len = 500
        str_version = create_string_buffer(b'\000' * str_version_max_len)
        int_major = c_int()
        int_minor = c_int()

        error = self.EpsonLibInterface.ConsultarVersionEquipo(str_version, c_int(
            str_version_max_len).value, byref(int_major), byref(int_minor))
        print("Machine Version         : %s" %  error)
        print("String Machine Version  : %s" %  str_version.value)
        print("Major Machine Version   : %s" %  int_major.value)
        print("Minor Machine Version   : %s" %  int_minor.value)

        # status
        error = self.EpsonLibInterface.ConsultarEstadoDeConexion()
        print("Conexion Status         : %s" %  error)

        error = self.EpsonLibInterface.ComenzarLog()
        print("Log iniciado Status     : %s" % error)

        logging.getLogger().info("Conectada la Epson 2Gen al puerto  : %s" % (self.port))

    def close(self):
        """Cierra recurso de conexion con impresora"""

        # get last error
        error = self.EpsonLibInterface.ConsultarUltimoError()
        print("Last Error              : %s" % str(error))

        self.EpsonLibInterface.Desconectar()
        logging.getLogger().info("Desconectada la Epson 2Gen al puerto: %s" % (self.port))

    def sendCommand(self, commandNumber, fields, skipStatusErrors=False):
        pass
