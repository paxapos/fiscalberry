'''Para testing y desarrollo'''

# -*- coding: utf-8 -*-

from escpos import printer
from common.DriverInterface import DriverInterface


TCP_PORT = 9100


class ReceiptFileDriver(printer.File, DriverInterface):
    """ Generic file printer
    This class is used for parallel port printer or other printers that are directly attached to the filesystem.
    Note that you should stay away from using USB-to-Parallel-Adapter since they are unreliable
    and produce arbitrary errors.
    inheritance:
    .. inheritance-diagram:: escpos.printer.File
        :parts: 1
    """

    def __init__(self, devfile="/dev/usb/lp0", auto_flush=True, codepage="cp858", *args, **kwargs):
        self.cols = 48
        printer.File.__init__(self, devfile, auto_flush, codepage, *args, **kwargs)
        self.codepage = codepage
    
    def start(self):
        pass
