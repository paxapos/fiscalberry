# -*- coding: utf-8 -*-

from DriverInterface import DriverInterface
import logging


class FileDriver(DriverInterface):
    def __init__(self, path):
        bufsize = 1  # line buffer
        self.file = open(path, "a", bufsize)

    def sendCommand(self, command=0, parameters=None, skipStatusErrors=False):
        import random

        if isinstance(command,dict):
            dt={'d': 2, 'f': 2, 'g': 2, 'q': 5, 'w': 3}
            st=""
            for key,val in dt.iteritems():
                st = st + key + str(val)
            command = st

        if command:
            self.file.write("Command: %s\n" % command)
            print("*** OUTPUT Command: %s\n" % command)
        if parameters:
            self.file.write("Parameters: %s\n" % command)
            print("*** OUTPUT Parameters: %s\n" % parameters)

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