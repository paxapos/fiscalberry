# -*- coding: iso-8859-1 -*-
import ConectorDriverComando
import unicodedata
import importlib

class ValidationError(Exception):
    pass


class FiscalPrinterError(Exception):
    pass


class ComandoException(RuntimeError):
    pass


def formatText(text):
    asciiText = unicodedata.normalize('NFKD', unicode(text)).encode('ASCII', 'ignore')
    asciiText = asciiText.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return asciiText


class ComandoInterface:
    """Interfaz que deben cumplir las impresoras fiscales."""
    
    DEFAULT_DRIVER=None

    def __init__(self, *args, **kwargs):
        print (kwargs)
        self.model = kwargs.pop("modelo", None)
        driver = kwargs.pop("driver", self.DEFAULT_DRIVER)
        print ConectorDriverComando
        if driver:
            self.conector = ConectorDriverComando.ConectorDriverComando(self, driver, **kwargs)

        print "COSOROTO %s\n" %self.traductorModule
        traductorModule = importlib.import_module(self.traductorModule)
        print traductorModule
        traductorClass = getattr(traductorModule, self.traductorModule[12:])
        self.traductor = traductorClass(self, *args)

       

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        print "_sendCommand", commandNumber, parameters
        try:
            logging.getLogger().info("sendCommand: SEND|0x%x|%s|%s" % (commandNumber,
                skipStatusErrors and "T" or "F",
                                                                     str(parameters)))
            return self.conector.sendCommand(commandNumber, parameters, skipStatusErrors)
        except epsonFiscalDriver.ComandoException, e:
            logging.getLogger().error("epsonFiscalDriver.ComandoException: %s" % str(e))
            raise ComandoException("Error de la impresora fiscal: " + str(e))



    def close(self):
        """Cierra la impresora"""
        self.conector.close()


    # Documentos no fiscales

    def openNonFiscalReceipt(self):
        """Abre documento no fiscal"""
        raise NotImplementedError

    def printNonFiscalText(self, text):
        """Imprime texto fiscal. Si supera el límite de la linea se trunca."""
        raise NotImplementedError

    NON_FISCAL_TEXT_MAX_LENGTH = 40 # Redefinir

    def closeDocument(self):
        """Cierra el documento que esté abierto"""
        raise NotImplementedError

    def cancelDocument(self):
        """Cancela el documento que esté abierto"""
        raise NotImplementedError

    def addItem(self, description, quantity, price, iva, discount, discountDescription, negative=False):
        """Agrega un item a la FC.
            @param description          Descripción del item. Puede ser un string o una lista.
                Si es una lista cada valor va en una línea.
            @param quantity             Cantidad
            @param price                Precio (incluye el iva si la FC es B o C, si es A no lo incluye)
            @param iva                  Porcentaje de iva
            @param negative             True->Resta de la FC
            @param discount             Importe de descuento
            @param discountDescription  Descripción del descuento
        """
        raise NotImplementedError

    def addPayment(self, description, payment):
        """Agrega un pago a la FC.
            @param description  Descripción
            @param payment      Importe
        """
        raise NotImplementedError


    

    docTypeNames = {
        "DOC_TYPE_CUIT": "CUIT",
        "DOC_TYPE_LIBRETA_ENROLAMIENTO": 'L.E.',
        "DOC_TYPE_LIBRETA_CIVICA": 'L.C.',
        "DOC_TYPE_DNI": 'DNI',
        "DOC_TYPE_PASAPORTE": 'PASAP',
        "DOC_TYPE_CEDULA": 'CED',
        "DOC_TYPE_SIN_CALIFICADOR": 'S/C'
    }

    docTypes = {
        "CUIT": 'C',
        "LIBRETA_ENROLAMIENTO": '0',
        "LIBRETA_CIVICA": '1',
        "DNI": '2',
        "PASAPORTE": '3',
        "CEDULA": '4',
        "SIN_CALIFICADOR": ' ',
    }

    ivaTypes = {
        "RESPONSABLE_INSCRIPTO": 'I',
        "RESPONSABLE_NO_INSCRIPTO": 'N',
        "EXENTO": 'E',
        "NO_RESPONSABLE": 'A',
        "CONSUMIDOR_FINAL": 'C',
        "RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO": 'B',
        "RESPONSABLE_MONOTRIBUTO": 'M',
        "MONOTRIBUTISTA_SOCIAL": 'S',
        "PEQUENIO_CONTRIBUYENTE_EVENTUAL": 'V',
        "PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL": 'W',
        "NO_CATEGORIZADO": 'T',
    }
   

    # Ticket fiscal (siempre es a consumidor final, no permite datos del cliente)

    def openTicket(self):
        """Abre documento fiscal"""
        raise NotImplementedError

    def openBillTicket(self, type, name, address, doc, docType, ivaType):
        """
        Abre un ticket-factura
            @param  type        Tipo de Factura "A", "B", o "C"
            @param  name        Nombre del cliente
            @param  address     Domicilio
            @param  doc         Documento del cliente según docType
            @param  docType     Tipo de documento
            @param  ivaType     Tipo de IVA
        """
        raise NotImplementedError

    def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference="NC"):
        """
        Abre un ticket-NC
            @param  type        Tipo de Factura "A", "B", o "C"
            @param  name        Nombre del cliente
            @param  address     Domicilio
            @param  doc         Documento del cliente según docType
            @param  docType     Tipo de documento
            @param  ivaType     Tipo de IVA
            @param  reference
        """
        raise NotImplementedError

    def openDebitNoteTicket(self, type, name, address, doc, docType, ivaType):
        """
        Abre una Nota de Débito
            @param  type        Tipo de Factura "A", "B", o "C"
            @param  name        Nombre del cliente
            @param  address     Domicilio
            @param  doc         Documento del cliente según docType
            @param  docType     Tipo de documento
            @param  ivaType     Tipo de IVA
            @param  reference
        """
        raise NotImplementedError

    def openRemit(self, name, address, doc, docType, ivaType):
        """
        Abre un remito
            @param  name        Nombre del cliente
            @param  address     Domicilio
            @param  doc         Documento del cliente según docType
            @param  docType     Tipo de documento
            @param  ivaType     Tipo de IVA
        """
        raise NotImplementedError

    def openReceipt(self, name, address, doc, docType, ivaType, number):
        """
        Abre un recibo
            @param  name        Nombre del cliente
            @param  address     Domicilio
            @param  doc         Documento del cliente según docType
            @param  docType     Tipo de documento
            @param  ivaType     Tipo de IVA
            @param  number      Número de identificación del recibo (arbitrario)
        """
        raise NotImplementedError

    def addRemitItem(self, description, quantity):
        """Agrega un item al remito
            @param description  Descripción
            @param quantity     Cantidad
        """
        raise NotImplementedError

    def addReceiptDetail(self, descriptions, amount):
        """Agrega el detalle del recibo
            @param descriptions Lista de descripciones (lineas)
            @param amount       Importe total del recibo
        """
        raise NotImplementedError

    def addAdditional(self, description, amount, iva, negative=False):
        """Agrega un adicional a la FC.
            @param description  Descripción
            @param amount       Importe (sin iva en FC A, sino con IVA)
            @param iva          Porcentaje de Iva
            @param negative True->Descuento, False->Recargo"""
        raise NotImplementedError

    def getLastNumber(self, letter):
        """Obtiene el último número de FC"""
        raise NotImplementedError

    def getLastCreditNoteNumber(self, letter):
        """Obtiene el último número de FC"""
        raise NotImplementedError

    def getLastRemitNumber(self):
        """Obtiene el último número de Remtio"""
        raise NotImplementedError

    def cancelAnyDocument(self):
        """Cancela cualquier documento abierto, sea del tipo que sea.
           No requiere que previamente se haya abierto el documento por este objeto.
           Se usa para destrabar la impresora."""
        raise NotImplementedError

    def dailyClose(self, type):
        """Cierre Z (diario) o X (parcial)
            @param type     Z (diario), X (parcial)
        """
        raise NotImplementedError


    def getWarnings(self):
        return []

    def openDrawer(self):
        """Abrir cajón del dinero - No es mandatory implementarlo"""
        pass
