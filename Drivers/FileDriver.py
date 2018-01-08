# -*- coding: iso-8859-1 -*-

from DriverInterface import DriverInterface
import logging


class FileDriver(DriverInterface):
    def __init__(self, path):
        bufsize = 1  # line buffer
        self.file = open(path, "a", bufsize)

    def sendCommand(self, command, parameters, skipStatusErrors=False):
        import random
        self.file.write("Command: %d, Parameters: %s\n" % (command, parameters))
        print("*** OUTPUT Command: %d, Parameters: %s\n" % (command, parameters))
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

    def set(self, *kwargs):
        pass

    def _raw(self, *kwargs):
        pass

    def text(self, *kwargs):
        for texto in kwargs:
            self.file.write(texto)
        pass

    def cut(self, *kwargs):
        pass