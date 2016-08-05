# -*- coding: iso-8859-1 -*-

from DriverInterface import DriverInterface
import logging

class FileDriver(DriverInterface):

    def __init__(self, filename):
        self.filename = filename
        bufsize = 1 # line buffer
        self.file = open(filename, "a", bufsize)

    def sendCommand(self, command, parameters, skipStatusErrors=False):
        import random
        self.file.write("Command: %d, Parameters: %s\n" % (command, parameters))
        number = random.randint(2, 12432)
        return [str(number)] * 10

    def close(self):
        self.file.close()