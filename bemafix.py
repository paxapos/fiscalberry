# -*- coding: utf-8 -*-

#from hasarPrinter import HasarPrinter
# Drivers:

from Drivers.EpsonDriver import EpsonDriver
from Drivers.FileDriver import FileDriver
from Drivers.HasarDriver import HasarDriver
from Drivers.DummyDriver import DummyDriver

from Comandos.EpsonComandos import EpsonComandos
from Comandos.HasarComandos import HasarComandos
from math import ceil

from Traductor import Traductor
from escpos import printer


barra = printer.File("/tmp/asas.txt")
texto = u"ñandú imprimiendo caracteres raros\nÑasasas\n"

# colocar en modo ESC P
barra._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"1")

#1D F9 37 n CP850
#barra._raw(chr(0x1D) + chr(0xF9) + chr(0x37) + "2")
barra.charcode("WEST_EUROPE")
barra._raw(chr(0x1D) + chr(0xF9) + chr(0x37) + "2")
barra.text(texto)


barra.cut()

barra._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")

