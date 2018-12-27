# -*- coding: utf-8 -*-

from escpos import printer, escpos
import threading
import time
from DriverInterface import DriverInterface


# TCP_PORT = 9100


class ReceiptUSBDriver(printer.Usb, DriverInterface):

    def __init__(self, usb_vendor, usb_product, timeout=0, interface=0, in_ep=0x82, out_ep=0x01, codepage="cp858", *args, **kwargs):  # noqa: N803
        """
        :param idVendor: Vendor ID
        :param idProduct: Product ID
        :param timeout: Is the time limit of the USB operation. Default without timeout.
        :param interface: Interface of the device - by default is 0.
        :param in_ep: Input end point
        :param out_ep: Output end point
        """
        escpos.Escpos.__init__(self, *args, **kwargs)
        self.idVendor = int(usb_vendor, 16)
        self.idProduct = int(usb_product, 16)
        self.timeout = timeout
        self.interface = interface
        self.in_ep = int(in_ep, 16)
        self.out_ep = int(out_ep, 16)
        self.codepage = codepage
   

    def start(self):
    	self.open()

    def end(self):
    	self.close()

    def reconnect(self):
		pass