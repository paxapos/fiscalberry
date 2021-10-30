# -*- coding: utf-8 -*-

from DriverInterface import DriverInterface
import logging
import time
import random


class FileDriver(DriverInterface):
    def __init__(self, path, codepage="utf8"):
        bufsize = 1  # line buffer
        self.file = open(path, "a", bufsize)
        self.codepage = codepage

    def sendCommand(self, command=0, parameters=None, skipStatusErrors=False):

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
            self.file.write("Parameters: %s\n" % parameters)
            print("*** OUTPUT Parameters: %s\n" % parameters)

        number = random.randint(2, 12432)
        return [str(number)] * 10

    def close(self):
        self.file.close()

    def start(self):
        """ iniciar """
        print("imprimiendo.... 5 segundos")
        time.sleep(5)
        
        pass

    def end(self):
        print("despues de sleep")
        print("ENNNNNDDD")
        print("-"*15)
        pass

    def reconnect(self):
        pass

    def set(self, *kwargs):
        pass

    def _raw(self, *kwargs):
        pass

    def text(self, *kwargs):
        print(kwargs)
        for texto in kwargs:
            texto = texto.encode(self.codepage)
            self.file.write(texto)
        pass

    def qr(self, *kwargs):
        print(kwargs)
        for texto in kwargs:
            texto = texto.encode(self.codepage)
            self.file.write(texto)
        pass

    def cut(self, *kwargs):
        pass

    def image(self, *kwargs):
        pass

    def cashdraw(self, *args):
        pass