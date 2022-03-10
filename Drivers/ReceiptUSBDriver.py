# -*- coding: utf-8 -*-
from escpos import printer, escpos
import threading
import time
import logging
from DriverInterface import DriverInterface


class ReceiptUSBDriver(printer.Usb, DriverInterface):

    def __init__(self, usb_vendor, usb_product, timeout=0, interface=0, in_ep=0x82, out_ep=0x01, codepage="cp858", cols = 42, *args, **kwargs):  # noqa: N803
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
        self.cols = int(cols)
        self.logger = logging.getLogger("USBDriver")

    def start(self):
        try:
            self.open()
        except Exception as e:
            self.logger.error("Error de la impresora: "+str(e))

    def end(self):
        try:
            self.close()
        except Exception as e:
            self.logger.error("Error de la impresora: "+str(e))

    def reconnect(self):
        pass