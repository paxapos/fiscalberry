# -*- coding: iso-8859-1 -*-
from DriverInterface import DriverInterface

import serial
import sys
import logging

logger = logging.getLogger('drivers.FiscalPrinterDriver')


def debugEnabled(*args):
    # print >> sys.stderr, " ".join(map(str, args))
    res = " ".join(map(str, args))
    logger.debug(res)


def debugDisabled(*args):
    pass


debug = debugEnabled


class PrinterException(Exception):
    pass


class UnknownServerError(PrinterException):
    errorNumber = 1


class ComunicationError(PrinterException):
    errorNumber = 2


class PrinterStatusError(PrinterException):
    errorNumber = 3


class FiscalStatusError(PrinterException):
    errorNumber = 4


ServerErrors = [UnknownServerError, ComunicationError, PrinterStatusError, FiscalStatusError]


class ProxyError(PrinterException):
    errorNumber = 5


class FiscalPrinterDriver(DriverInterface):
    WAIT_TIME = 10
    RETRIES = 4
    WAIT_CHAR_TIME = 0.1
    NO_REPLY_TRIES = 200

    def __init__(self, path, speed=9600):
        logger.info('Open Serial Port %s' % path)
        self._serialPort = serial.Serial(port=path, timeout=None, baudrate=speed)
        self._initSequenceNumber()

    def start(self):
        pass

    def close(self):
        try:
            self._serialPort.close()
        except:
            pass
        del self._serialPort
        logger.info('Close Serial Port')

    def sendCommand(self, commandNumber, fields, skipStatusErrors=False):
        logger.info('sendCommand\ncommandNumber: 0x%x\nfields: %s\nskipStatusErrors: %s' %
                    (commandNumber, str(fields), skipStatusErrors))
        fields = map(lambda x: x.encode("latin-1", 'ignore'), fields)
        message = chr(0x02) + chr(self._sequenceNumber) + chr(commandNumber)
        if fields:
            message += chr(0x1c)
        message += chr(0x1c).join(fields)
        message += chr(0x03)
        checkSum = sum([ord(x) for x in message])
        checkSumHexa = ("0000" + hex(checkSum)[2:])[-4:].upper()
        message += checkSumHexa
        reply = self._sendMessage(message)
        self._incrementSequenceNumber()
        return self._parseReply(reply, skipStatusErrors)

    def _write(self, s):
        debug("_write", ", ".join(["%x" % ord(c) for c in s]))
        self._serialPort.write(s)

    def _read(self, count):
        ret = self._serialPort.read(count)
        # debug("_read", ", ".join(["%x" % ord(c) for c in ret]))
        return ret

    def __del__(self):
        if hasattr(self, "_serialPort"):
            try:
                self.close()
            except:
                pass

    def _parseReply(self, reply, skipStatusErrors):
        r = reply[4:-1]  # Saco STX <Nro Seq> <Nro Comando> <Sep> ... ETX
        fields = r.split(chr(28))
        printerStatus = fields[0]
        fiscalStatus = fields[1]
        logger.info('Complete Reply info is below\n Reply: {reply} \n printerStatus {printerStatus} fiscalStatus {fiscalStatus}'.format(**locals()))
        if not skipStatusErrors:
            self._parsePrinterStatus(printerStatus)
            self._parseFiscalStatus(fiscalStatus)
        return fields

    def _parsePrinterStatus(self, printerStatus):
        x = int(printerStatus, 16)
        for value, message in self.printerStatusErrors:
            if (value & x) == value:
                logger.warning(message)
                raise PrinterStatusError, message

    def _parseFiscalStatus(self, fiscalStatus):
        x = int(fiscalStatus, 16)
        for value, message in self.fiscalStatusErrors:
            if (value & x) == value:
                logger.warning(message)
                raise FiscalStatusError, message

    def _checkReplyBCC(self, reply, bcc):
        checkSum = sum([ord(x) for x in reply])
        checkSumHexa = ("0000" + hex(checkSum)[2:])[-4:].upper()
        logger.debug('Reply from printer(_checkReplyBCC)\nReply> %s\nReply(ORD)> %s \nCHECKS> checkSum: %s; checkSumHexa: %s; bcc: %s' %
                     (reply, [ord(x) for x in reply], checkSum, checkSumHexa, bcc))
        return checkSumHexa == bcc.upper()
