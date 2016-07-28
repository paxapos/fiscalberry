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


printer = printer.Network("192.168.1.124")

# colocar en modo ESC P
printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"1")


printer.text("P\ta\tb\tc\td\te\tf\tg\th\ti\ta\tb\tc")


desc = desc[0:23]
cant_tabs = 3
can_tabs_final = int( ceil( len(desc)/8 * 100) / 100 )
strTabs = desc.ljust(cant_tabs-can_tabs_final, '\t')

#printer.cut()

printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")