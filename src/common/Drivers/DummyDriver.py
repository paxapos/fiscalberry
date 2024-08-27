# -*- coding: iso-8859-1 -*-
import random
from common.DriverInterface import DriverInterface


class DummyDriver(DriverInterface):
    
    
    def __init__(self,*args,**kwargs):
        self.cols = 48
        self.align = "LEFT"
        self.font = "NORMAL"
        self.connected = True
        print("\n\n")

    def start(self): pass
    def close(self): pass
    def end(self):   pass
    def reconnect(self): pass
    
    def sendCommand(self, commandNumber=None, parameters=None, skipStatusErrors=None):
        print("Enviando Comando DUMMY")
        print(commandNumber, parameters, skipStatusErrors)
        number = random.randint(0, 99999999)
        return ["00", "00"] + [str(number)] * 11

    def set(self, *args, **kwargs):
        self.align = args[0]
        self.font = args[2]
    
    def text(self, text:bytes):
        text = text.replace("\x1bE\x01\x1b-\x01'", "").replace("'\x1b-\x00\x1bE\x00", "")
        if self.align =="LEFT":
            text = text.ljust(self.cols, " ")
        elif self.align =="CENTER":
            text = text.center(self.cols, " ")
        elif self.align == "RIGHT":
            text = text.rjust(self.cols, " ")
        if self.font == "B": 
            text = text
        else:
            text = "\033[2m"+text+"\033[0m"

        print(text)

    def cut(self, text):
        print("\n\n")
        print(f"<------------     CORTE    ------------->".center(self.cols, " "))
        print("\n\n\n")

    def qr(self,*args):
        print("OOO   OOO   OO".center(self.cols, " "))
        print("O OO OO OOOOOO".center(self.cols, " "))
        print("  O OO O  O   ".center(self.cols, " "))
        print("O  O O OOOOOO ".center(self.cols, " "))
        print(" OOO O  O O   ".center(self.cols, " "))
        print(" O OO OO  O OO".center(self.cols, " "))
        print("OO  O  OOO  OO".center(self.cols, " "))
    

