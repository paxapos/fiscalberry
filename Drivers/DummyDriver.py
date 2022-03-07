# -*- coding: iso-8859-1 -*-
import random

from DriverInterface import DriverInterface


class DummyDriver(DriverInterface):
    
    
    def __init__(self,*args,**kwargs):
        self.cols = 48
        print("\n\n")
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
    def text(self, text:bytes):
        text = text.replace("\x1bE\x01\x1b-\x01", "").replace("\x1b-\x00\x1bE\x00", "")
        print("\033[1m"+text+"\033[0m")

    def cut(self, text):
        print("\n\n")
        print(f"<--------------     CORTE    --------------->")
        print("\n\n\n")

    def end(self):
        pass

    def reconnect(self):
        pass

    def set(self, *args, **kwargs): pass

    def qr(*args):
        print("OOO   OOO   OO")
        print("O OO OO OOOOOO")
        print("  O OO O  O   ")
        print("O  O O OOOOOO ")
        print(" OOO O  O O   ")
        print(" O OO OO  O OO")
        print("OO  O  OOO  OO")
