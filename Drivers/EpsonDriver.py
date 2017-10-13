# -*- coding: iso-8859-1 -*-

from Drivers.FiscalPrinterDriver import FiscalPrinterDriver
import random
import time
import serial


class EpsonDriver(FiscalPrinterDriver):
    fiscalStatusErrors = [  # (1<<0 + 1<<7, "Memoria Fiscal llena"),
        (1 << 0, "Error en memoria fiscal"),
        (1 << 1, "Error de comprobación en memoria de trabajo"),
        (1 << 2, "Poca batería"),
        (1 << 3, "Comando no reconocido"),
        (1 << 4, "Campo de datos no válido"),
        (1 << 5, "Comando no válido para el estado fiscal"),
        (1 << 6, "Desbordamiento de totales"),
        (1 << 7, "Memoria Fiscal llena"),
        (1 << 8, "Memoria Fiscal casi llena"),
        (1 << 11,
         "Es necesario hacer un cierre de la jornada fiscal o se superó la cantidad máxima de tickets en una factura."),
    ]

    printerStatusErrors = [(1 << 2, "Error y/o falla de la impresora"),
                           (1 << 3, "Impresora fuera de linea"),
                           ##                          (1<<4, "Poco papel para la cinta de auditoría"),
                           ##                          (1<<5, "Poco papel para comprobantes o tickets"),
                           (1 << 6, "Buffer de impresora lleno"),
                           (1 << 14, "Impresora sin papel"),
                           ]

    def _initSequenceNumber(self):
        self._sequenceNumber = random.randint(0x20, 0x7f)

    def _incrementSequenceNumber(self):
        # Avanzo el número de sequencia, volviendolo a 0x20 si pasó el limite
        self._sequenceNumber += 1
        if self._sequenceNumber > 0x7f:
            self._sequenceNumber = 0x20

    def _sendMessage(self, message):
        # Envía el mensaje
        # @return reply Respuesta (sin el checksum)
        self._write(message)
        timeout = time.time() + self.WAIT_TIME
        retries = 0
        while 1:
            if time.time() > timeout:
                raise ComunicationError, "Expiró el tiempo de espera para una respuesta de la impresora. Revise la conexión."
            c = self._read(1)
            if len(c) == 0:
                continue
            if ord(c) in (0x12, 0x14):  # DC2 o DC4
                # incrementar timeout
                timeout += self.WAIT_TIME
                continue
            if ord(c) == 0x15:  # NAK
                if retries > self.RETRIES:
                    raise ComunicationError, "Falló el envío del comando a la impresora luego de varios reintentos"
                # Reenvío el mensaje
                self._write(message)
                timeout = time.time() + self.WAIT_TIME
                retries += 1
                continue
            if c == chr(0x02):  # STX - Comienzo de la respuesta
                reply = c
                noreplyCounter = 0
                while c != chr(0x03):  # ETX (Fin de texto)
                    c = self._read(1)
                    if not c:
                        noreplyCounter += 1
                        time.sleep(self.WAIT_CHAR_TIME)
                        if noreplyCounter > self.NO_REPLY_TRIES:
                            raise ComunicationError, "Fallo de comunicación mientras se recibía la respuesta de la impresora."
                    else:
                        noreplyCounter = 0
                        reply += c
                bcc = self._read(4)  # Leo BCC
                if not self._checkReplyBCC(reply, bcc):
                    # Mando un NAK y espero la respuesta de nuevo.
                    self._write(chr(0x15))
                    timeout = time.time() + self.WAIT_TIME
                    retries += 1
                    if retries > self.RETRIES:
                        raise ComunicationError, "Fallo de comunicación, demasiados paquetes inválidos (bad bcc)."
                    continue
                elif reply[1] != chr(self._sequenceNumber):  # Los número de seq no coinciden
                    # Reenvío el mensaje
                    self._write(message)
                    timeout = time.time() + self.WAIT_TIME
                    retries += 1
                    if retries > self.RETRIES:
                        raise ComunicationError, "Fallo de comunicación, demasiados paquetes inválidos (mal sequence_number)."
                    continue
                else:
                    # Respuesta OK
                    break
        return reply
