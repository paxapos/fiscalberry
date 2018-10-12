# -*- coding: utf-8 -*-

from DriverInterface import DriverInterface


class TxtDriver(DriverInterface):
    def __init__(self, path):
        self.filename = path
        bufsize = 1  # line buffer
        self.file = open(self.filename, "w", bufsize)

    def sendCommand(self, command=0, fields=None, skipStatusErrors=False):
        import random

        if isinstance(command,dict):
            st=""
            for key,val in command.iteritems():
                st = st + key + str(val)
            command = st
            self.file.write(command + "\n")
            message = command

        else:
            message = chr(0x02) + chr(98) + chr(command)
            if fields:
                message += chr(0x1c)
            message += chr(0x1c).join(fields)
            message += chr(0x03)
            checkSum = sum([ord(x) for x in message])
            checkSumHexa = ("0000" + hex(checkSum)[2:])[-4:].upper()
            message += checkSumHexa
            self.file.write(message + "\n")


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