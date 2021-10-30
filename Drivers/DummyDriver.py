# -*- coding: iso-8859-1 -*-
import random

from DriverInterface import DriverInterface


class DummyDriver(DriverInterface):
    def close(self):
        pass

    def sendCommand(self, commandNumber=None, parameters=None, skipStatusErrors=None):
        print("Enviando Comando DUMMY")
        print(commandNumber, parameters, skipStatusErrors)
        number = random.randint(0, 99999999)
        return ["00", "00"] + [str(number)] * 11

    def start(self):
        """ iniciar """
        pass

    def end(self):
        pass

    def reconnect(self):
        pass

    def set(self):
        pass
