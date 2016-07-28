# -*- coding: utf-8 -*-

#from hasarPrinter import HasarPrinter
# Drivers:

from Drivers.EpsonDriver import EpsonDriver
from Drivers.FileDriver import FileDriver
from Drivers.HasarDriver import HasarDriver
from Drivers.DummyDriver import DummyDriver

from Comandos.EpsonComandos import EpsonComandos
from Comandos.HasarComandos import HasarComandos

from Traductor import Traductor
from escpos import printer


printer = printer.Network("192.168.1.124")

printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")

