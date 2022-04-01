# -*- coding: iso-8859-1 -*-
import string
import types
import logging
import ctypes
import unicodedata
from ctypes import byref, c_int, c_char, c_char_p, c_long, c_short, c_float, create_string_buffer
from Comandos.ComandoFiscalInterface import ComandoFiscalInterface
from Drivers.FiscalPrinterDriver import PrinterException
from ComandoInterface import formatText


class Epson2GenComandos(ComandoFiscalInterface):
    # el traductor puede ser: TraductorFiscal o TraductorReceipt
    # path al modulo de traductor que este comando necesita
    traductorModule = "Traductores.TraductorFiscal"

    DEFAULT_DRIVER = "Epson2Gen"

    AVAILABLE_MODELS = ["TM-T900"]

    docTypes = {
        "CUIT": 3,
        "CUIL": 2,
        "LIBRETA_ENROLAMIENTO": 7,
        "LIBRETA_CIVICA": 6,
        "DNI": 1,
        "PASAPORTE": 5,
        "CEDULA": 4,
        "SIN_CALIFICADOR": 0,
    }

    ivaTypes = {
        "RESPONSABLE_INSCRIPTO": 1,
        "EXENTO": 6,
        "NO_RESPONSABLE": 3,
        "CONSUMIDOR_FINAL": 5,
        "NO_CATEGORIZADO": 7,
        "RESPONSABLE_MONOTRIBUTO": 4,
        "MONOTRIBUTISTA_SOCIAL": 8,
    }

    comprobanteTypes = {
        "T": 1,
        "FB": 2,
        "FA": 2,
        "FC": 2,
        "FM": 2,
        "NCT": 3,
        "NCA": 3,
        "NCB": 3,
        "NCC": 3,
        "NCM": 3,
        "NDA": 4,
        "NDB": 4,
        "NDC": 4,
        "NDM": 4,
    }

    ivaPercentageIds = {
        '0.00': 0,
        '10.50': 4,
        '21.00': 5,
        '21.0': 5,
        '21': 5,
        21.: 5,
        21: 5
    }

    def getStatus(self, *args):
        return {self.conector.driver.ObtenerEstadoFiscal()}

    def setHeader(self, headerlist=[]):
        """Establecer encabezado"""
        print(headerlist)
        line = 1
        while line <= len(headerlist):
            texto = c_char_p(headerlist[line-1]).value
            self.conector.driver.EpsonLibInterface.EstablecerEncabezado(
                line, texto)
            line += 1
            pass
    #line = 0
    # for text in headerlist:
         #   self.conector.driver.EstablecerEncabezado(line, text)
          #  line += 1

    def setTrailer(self, trailer=[]):
        """Establecer pie"""
        line = 1
        while line <= len(trailer):
            texto = c_char_p(trailer[line-1]).value
            self.conector.driver.EpsonLibInterface.EstablecerCola(line, texto)
            line += 1
            pass
        #line = 0
    # for text in trailer:
         #   self.conector.driver.EstablecerCola(line, text)
          #  line += 1

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        self.conector.sendCommand()

    def _setCustomerData(self, name=" ", address=" ", doc=" ", docType=" ", ivaType="T"):
        # nombre, segunda línea nombre, primer segunda y tercera línea dirección, tipo de documento, número de documento y tipo de responsabilidad ante el IVA
        self.conector.driver.EpsonLibInterface.CargarDatosCliente(
            name, None, address, None, None, self.docTypes.get(docType), doc, self.ivaTypes.get(ivaType))

    # Documentos no fiscales

    def openNonFiscalReceipt(self):
        """Abre documento no fiscal"""
        pass

    def printFiscalText(self, text):
        pass
        #self.conector.sendCommand( jdata )

    def printNonFiscalText(self, text):
        """Imprime texto fiscal. Si supera el límite de la linea se trunca."""
        pass
        #self.conector.sendCommand( jdata )

    def closeDocument(self, copias=0, email=None):
        """Cierra el documento que esté abierto"""
        self.conector.driver.EpsonLibInterface.CerrarComprobante()

    def cancelDocument(self):
        """Cancela el documento que esté abierto"""
        self.conector.driver.EpsonLibInterface.Cancelar()

    def imprimirAuditoria(self, desde, hasta):
        # desde & Hasta = Nros de Zeta o fechas, ambos pueden ser usados como intervalos de tiempo.
        self.conector.driver.ImprimirAuditoria(desde, hasta)

    def addItem(self, description, quantity, price, iva, itemNegative=False, discount=0, discountDescription='', discountNegative=False, id_ii=0, ii_valor=""):
        """Agrega un item a la FC.
                @param description          Descripción del item. Puede ser un string o una lista.
                        Si es una lista cada valor va en una línea.
                @param quantity             Cantidad
                @param price                Precio (incluye el iva si la FC es B o C, si es A no lo incluye)
                @param iva                  Porcentaje de iva
                @param itemNegative         Anulación del ítem.
                @param discount             Importe de descuento
                @param discountDescription  Descripción del descuento
                @param discountNegative     True->Resta de la FC
                @param 
        """

        id_item = 200  # Agregar como ítem de venta.
        if itemNegative == True:
            id_item = 201
        if discountNegative == True:
            id_item = 206

        # id tipo de item, descripción, cantidad, porcentaje de IVA,
        # identificador II impuestos internos (0 = Ninguno), valor II, id_codigo (1 = Interno), valor del codigo, codigo_unidad_matrix, unidad de medida Unidad (7)
        ivaid = self.ivaPercentageIds.get("iva", 5)
        qty = str(quantity)
        ret = self.conector.driver.ImprimirItem(
            id_item, description, qty, price, ivaid, id_ii, ii_valor)
        print("Imprimiendo item       : %s", ret)

    def addPayment(self, description, payment):
        """Agrega un pago a la FC.
                @param description  Descripción
                @param payment      Importe
        """
        pass

        #self.conector.sendCommand( jdata )

    # Ticket fiscal (siempre es a consumidor final, no permite datos del cliente)

    def openTicket(self, comprobanteType="T"):
        """Abre documento fiscal
        str comprobanteType

        • 1 - Tique.
        • 2 - Tique factura A/B/C/M.
        • 3 - Tique nota de crédito, tique nota crédito A/B/C/M.
        • 4 - Tique nota de débito A/B/C/M.
        • 21 - Documento no fiscal homologado genérico.
        • 22 - Documento no fiscal homologado de uso interno.
        """
        numcomp = self.comprobanteTypes[comprobanteType]
        err = self.conector.driver.EpsonLibInterface.AbrirComprobante(numcomp)
        print(err)
        logging.getLogger().info("Abrio comprobante  : %s" % (err))

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
        type = 'F' + type
        comprobanteType = self.comprobanteTypes[type]
        self.conector.driver.EpsonLibInterface.AbrirComprobante(
            comprobanteType)

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
        comprobanteType = 3  # Tique Nota de crédito A/B/C/M

        self.conector.driver.EpsonLibInterface.AbrirComprobante(
            comprobanteType)

    def __cargarNumReferencia(self, numero):
        pass

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

        comprobanteType = 4  # Tique Nota de débito A/B/C/M

        self.conector.driver.EpsonLibInterface.AbrirComprobante(
            comprobanteType)

    def openRemit(self, name, address, doc, docType, ivaType):
        """
        Abre un remito
                @param  name        Nombre del cliente
                @param  address     Domicilio
                @param  doc         Documento del cliente según docType
                @param  docType     Tipo de documento
                @param  ivaType     Tipo de IVA
        """
        pass

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
        pass

    def addRemitItem(self, description, quantity):
        """Agrega un item al remito
                @param description  Descripción
                @param quantity     Cantidad
        """
        pass

    def addReceiptDetail(self, descriptions, amount):
        """Agrega el detalle del recibo
                @param descriptions Lista de descripciones (lineas)
                @param amount       Importe total del recibo
        """
        pass

    def ImprimirAnticipoBonificacionEnvases(self, description, amount, iva, negative=False):
        """Agrega un descuento general a la Factura o Ticket.
                @param description  Descripción
                @param amount       Importe (sin iva en FC A, sino con IVA)
                @param iva          Porcentaje de Iva
                @param negative     Si negative = True, se añadira el monto como descuento, sino, sera un recargo
        """
        pass

    def addAdditional(self, description, amount, iva, negative=False):
        """Agrega un descuento general a la Factura o Ticket.
                @param description  Descripción
                @param amount       Importe (sin iva en FC A, sino con IVA)
                @param iva          Porcentaje de Iva
                @param negative     Si negative = True, se añadira el monto como descuento, sino, sera un recargo
        """
        ivaid = self.ivaPercentageIds.get(iva)
        self.conector.driver.cargarAjuste(description, amount, ivaid, negative)

    def setCodigoBarras(self, numero, tipoCodigo="CodigoTipoI2OF5", imprimeNumero="ImprimeNumerosCodigo"):
        pass

    def start(self):
        self.conector.driver.start()

    def close(self):
        self.conector.driver.close()

    def getLastNumber(self, letter):
        """Obtiene el último número de FC"""
        self.start()
        self.cancelDocument()

        retLenght = 28
        ret = create_string_buffer(b'\000' * retLenght)
        self.conector.driver.EpsonLibInterface.ConsultarNumeroComprobanteUltimo(
            ret, retLenght)

        self.close()
        return ret

    def getLastCreditNoteNumber(self, letter):
        """Obtiene el último número de FC"""
        pass

    def getLastRemitNumber(self):
        """Obtiene el último número de Remtio"""
        pass

    def cancelAnyDocument(self):
        """Este comando no esta disponible en la 2da generación de impresoras, es necesaria su declaración por el uso del TraductorFiscal """
        return self.cancelDocument()

    def dailyClose(self, type):
        self.start()

        self.cancelDocument()

        if type == 'Z':
            ret = self.conector.driver.EpsonLibInterface.ImprimirCierreZ()
        else:
            ret = self.conector.driver.EpsonLibInterface.ImprimirCierreX()

        self.close()

        return ret

    def getWarnings(self):
        return []

    def openDrawer(self):
        pass
