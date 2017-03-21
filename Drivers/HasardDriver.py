# -*- coding: iso-8859-1 -*-

from Drivers.FiscalPrinterdDriver import FiscalPrinterdDriver, ComunicationError
import random
import time

__name__="HasardDriver"

class HasardDriver( FiscalPrinterdDriver ):
    ACK = chr(0x06)
    NAK = chr(0x15)
    STATPRN = chr(0xa1)

    
    fiscalStatusErrors = [(1<<0 + 1<<7, "Memoria Fiscal llena"),
                          (1<<0, "Error en memoria fiscal"),
                          (1<<1, "Error de comprobación en memoria de trabajo"),
                          (1<<2, "Poca batería"),
                          (1<<3, "Comando no reconocido"),
                          (1<<4, "Campo de datos no válido"),
                          (1<<5, "Comando no válido para el estado fiscal"),
                          (1<<6, "Desbordamiento de totales"),
                          (1<<7, "Memoria Fiscal llena"),
                          (1<<8, "Memoria Fiscal casi llena"),
                          (1<<11, "Es necesario hacer un cierre de la jornada fiscal o se superó la cantidad máxima de tickets en una factura."),
                          ]

    printerStatusErrors = [(1<<2, "Error y/o falla de la impresora"),
                          (1<<3, "Impresora fuera de linea"),
##                          (1<<4, "Poco papel para la cinta de auditoría"),
##                          (1<<5, "Poco papel para comprobantes o tickets"),
                          (1<<6, "Buffer de impresora lleno"),
                          (1<<8, "Tapa de impresora abierta"),
                          ]

    

    def _initSequenceNumber( self ):
        self._sequenceNumber = random.randint( 0x20, 0x7f )
        if self._sequenceNumber % 2:
            self._sequenceNumber -= 1

    def _incrementSequenceNumber( self ):
        # Avanzo el número de sequencia, volviendolo a 0x20 si pasó el limite
        self._sequenceNumber += 2
        if self._sequenceNumber > 0x7f:
            self._sequenceNumber = 0x20

    def _sendAndWaitAck( self, message, count = 0 ):
        if count > 10:
            raise ComunicationError, "Demasiados NAK desde la impresora. Revise la conexión."
        self._write( message )
        timeout = time.time() + self.WAIT_TIME
        while 1:
            if time.time() > timeout:
                raise ComunicationError, "Expiró el tiempo de espera para una respuesta de la impresora. Revise la conexión."
            c = self._read(1)
            if len(c) == 0:
                continue
            if c == self.ACK:
                return True
            if c == self.NAK:
                return self._sendAndWaitAck( message, count + 1 )

    def _sendMessage( self, message ):
        # Envía el mensaje
        # @return reply Respuesta (sin el checksum)
        print( message )
        timeout = 0
        retries = 0
        return chr(0x02)+chr(0x20)+chr(0x02)+chr(28)+"0"+chr(28)+chr(28)+"0"+chr(0x03)


