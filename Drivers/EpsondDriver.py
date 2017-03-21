# -*- coding: iso-8859-1 -*-

from Drivers.FiscalPrinterDriver import FiscalPrinterDriver
import random
import time

class EpsondDriver( FiscalPrinterDriver ):


    fiscalStatusErrors = [#(1<<0 + 1<<7, "Memoria Fiscal llena"),
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
                          (1<<14, "Impresora sin papel"),
                          ]

    def __init__( self ):
        bufsize = 1 # line buffer
        self.file = open("epsond.txt", "a", bufsize)
        self._initSequenceNumber()

    def _initSequenceNumber( self ):
        self._sequenceNumber = random.randint( 0x20, 0x7f )

    def _incrementSequenceNumber( self ):
        # Avanzo el número de sequencia, volviendolo a 0x20 si pasó el limite
        self._sequenceNumber += 1
        if self._sequenceNumber > 0x7f:
            self._sequenceNumber = 0x20


    def _sendMessage( self, message ):
        # Envía el mensaje
        # @return reply Respuesta (sin el checksum)
        print( message )
        self.file.write(message+"\n")
        timeout = 0
        return chr(0x02)+chr(0x20)+chr(0x02)+chr(28)+"0"+chr(28)+chr(28)+"0"+chr(0x03)

    def close(self):
        self.file.close()