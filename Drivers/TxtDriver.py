# -*- coding: utf-8 -*-

from DriverInterface import DriverInterface
import logging

logger = logging.getLogger('drivers.FiscalPrinterDriver')

class TxtDriver(DriverInterface):
    def __init__(self, path):
        self.filename = path
        bufsize = 1  # line buffer
        self.file = open(self.filename, "w", bufsize)

    def sendCommand(self, command=0, fields=None, skipStatusErrors=False):
        import random

        message = chr(command)

        if fields:
            message += chr(0x1c)

        fields = map(lambda x: x.encode("latin-1", 'ignore'), fields)
        message += chr(0x1c).join(fields)
        #message += chr(0x03)
        self.file.write(message + "\n")
        logger.debug("-> sendCommand: %s" % message)
        number = random.randint(2, 12432)
        return [str(number)] * 10
    def close(self):
        self.file.close()

    def start(self):
        """ iniciar """
        pass

    def end(self):
        pass

    def reconnect(self):
        pass

    def set(self, *args):
        pass

    def _raw(self, *args):
        pass

    def text(self, *args):
        pass

    def cut(self, *args):
        pass

    def qr(self, *args):
        pass