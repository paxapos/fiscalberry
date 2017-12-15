# -*- coding: utf-8 -*-

from escpos import printer, escpos
import threading
import serial
import time
from DriverInterface import DriverInterface


# TCP_PORT = 9100


class ReceiptUSBDriver(printer.Usb, DriverInterface):

    def __init__(self, usb_vendor, usb_product, timeout=0, in_ep=0x82, out_ep=0x01, codepage="cp858", *args, **kwargs):  # noqa: N803
        """
        :param idVendor: Vendor ID
        :param idProduct: Product ID
        :param timeout: Is the time limit of the USB operation. Default without timeout.
        :param in_ep: Input end point
        :param out_ep: Output end point
        """
        escpos.Escpos.__init__(self, *args, **kwargs)
        self.idVendor = usb_vendor
        self.idProduct = usb_product
        self.timeout = timeout
        self.in_ep = in_ep
        self.out_ep = out_ep
        self.codepage = codepage
   

    def start(self):
    	self.open()

    def end(self):
    	self.close()

    def reconnect(self):
		pass