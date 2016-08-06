'''Para testing y desarrollo'''


# -*- coding: utf-8 -*-

import socket
from escpos import printer

TCP_PORT = 9100


from DriverInterface import DriverInterface



class ReceiptFileDriver( printer.File ):
	""" Generic file printer
    This class is used for parallel port printer or other printers that are directly attached to the filesystem.
    Note that you should stay away from using USB-to-Parallel-Adapter since they are unreliable
    and produce arbitrary errors.
    inheritance:
    .. inheritance-diagram:: escpos.printer.File
        :parts: 1
    """

	def __init__(self, devfile="/dev/usb/lp0", auto_flush=True, *args, **kwargs):
		printer.File.__init__(self, devfile, auto_flush, *args, **kwargs)