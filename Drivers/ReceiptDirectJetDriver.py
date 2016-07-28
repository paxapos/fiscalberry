# -*- coding: utf-8 -*-

import socket
from escpos import printer

TCP_IP = '127.0.0.1'
TCP_PORT = 9100


from DriverInterface import DriverInterface

class ReceiptDirectJetDriver( printer.Network ):
