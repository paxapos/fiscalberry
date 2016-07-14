# -*- coding: iso-8859-1 -*-

from DriverInterface import DriverInterface

class FileDriver(DriverInterface):

    def __init__(self, filename):
        self.filename = filename
        self.file = open(filename, "a")

    def sendCommand(self, command, parameters, skipStatusErrors=False):
        import random
        self.file.write("Command: %d, Parameters: %s\n" % (command, parameters))
        number = random.randint(2, 12432)
        return [str(number)] * 10

    def close(self):
        self.file.close()