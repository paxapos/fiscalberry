# -*- coding: iso-8859-1 -*-
import string
import types
import logging
from Comandos.ComandoFiscalInterface import ComandoFiscalInterface
from ComandoInterface import formatText, ComandoException

from Drivers.FiscalPrinterDriver import PrinterException


class FiscalPrinterError(Exception):
    pass


class EpsonComandos(ComandoFiscalInterface):
    # el traductor puede ser: TraductorFiscal o TraductorReceipt
    # path al modulo de traductor que este comando necesita
    traductorModule = "Traductores.TraductorFiscal"

    _currentDocument = None
    _currentDocumentType = None

    # por ahora el mismo Driver Epson cumple igual para RD, si falla se crea uno pro pais asi: Epson_es_RD o Epson_es_AR
    DEFAULT_DRIVER = "Epson"

    DEBUG = True
# ini TODO definir todos lso comandos del kit loq ue estan son de argentina aun
    CMD_OPEN_FISCAL_RECEIPT = 0x40
    CMD_OPEN_BILL_TICKET = 0x60
    ## CMD_PRINT_TEXT_IN_FISCAL = (0x41, 0x61)
    CMD_PRINT_TEXT_IN_FISCAL = 0x41
    CMD_PRINT_LINE_ITEM = (0x42, 0x62)
    CMD_PRINT_SUBTOTAL = (0x43, 0x63)
    CMD_ADD_PAYMENT = (0x44, 0x64)
    CMD_CLOSE_FISCAL_RECEIPT = (0x45, 0x65)
    CMD_DAILY_CLOSE = 0x39
    CMD_STATUS_REQUEST = 0x2a

    CMD_OPEN_DRAWER = 0x7b

    CMD_SET_HEADER_TRAILER = 0x5d

    CMD_OPEN_NON_FISCAL_RECEIPT = 0x48
    CMD_PRINT_NON_FISCAL_TEXT = 0x49
    CMD_CLOSE_NON_FISCAL_RECEIPT = 0x4a

    CURRENT_DOC_TICKET = 1
    CURRENT_DOC_BILL_TICKET = 2
    CURRENT_DOC_CREDIT_TICKET = 4
    CURRENT_DOC_NON_FISCAL = 3
# fin TODO definir todos lso comandos del kit loq ue estan son de argentina aun
    models = ["tickeadoras", "epsonlx300+", "tm-220-af"] # la , "tm-t900fa" no la pude probar y no me aparece en RD

    ivaTypes = {
        "CREDITO_FISCAL": 'C',
        "CONSUMIDOR_FINAL": 'F',
        "GUBERNAMENTAL": 'G',
        "NO_CATEGORIZADO": 'N',
    }

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        print "_sendCommand", commandNumber, parameters
        try:
            logging.getLogger().info("sendCommand: SEND|0x%x0x%x|%s|%s" % (commandNumber, # por confirmar, send command aqui en rd recibe dos exa en vez uno
                                                                       skipStatusErrors and "T" or "F",
                                                                       str(parameters)))
            return self.conector.sendCommand(commandNumber, parameters, skipStatusErrors)
        except PrinterException, e:
            logging.getLogger().error("PrinterException: %s" % str(e))
            raise ComandoException("Error de la impresora fiscal: " + str(e))

    def openNonFiscalReceipt(self):
        status = self._sendCommand(self.CMD_OPEN_NON_FISCAL_RECEIPT, [])
        self._currentDocument = self.CURRENT_DOC_NON_FISCAL
        self._currentDocumentType = None
        return status

    def printNonFiscalText(self, text):
        return self._sendCommand(self.CMD_PRINT_NON_FISCAL_TEXT, [formatText(text[:40] or " ")])

    ADDRESS_SIZE = 30

    def _setHeaderTrailer(self, line, text):
        self._sendCommand(self.CMD_SET_HEADER_TRAILER, (str(line), text))

    def setHeader(self, header=None):
        "Establecer encabezados"
        if not header:
            header = []
        line = 3
        for text in (header + [chr(0x7f)] * 3)[:3]:  # Agrego chr(0x7f) (DEL) al final para limpiar las
            # líneas no utilizadas
            self._setHeaderTrailer(line, text)
            line += 1

    def setTrailer(self, trailer=None):
        "Establecer pie"
        if not trailer:
            trailer = []
        line = 11
        for text in (trailer + [chr(0x7f)] * 9)[:9]:
            self._setHeaderTrailer(line, text)
            line += 1

    def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference="NC"):
        return self._openBillCreditTicket(type, name, address, doc, docType, ivaType, isCreditNote=True)

    def openBillTicket(self, type, name, address, doc, docType, ivaType):
        return self._openBillCreditTicket(type, name, address, doc, docType, ivaType, isCreditNote=False)

    def _openBillCreditTicket(self, type, name, address, doc, docType, ivaType, isCreditNote,
                              reference=None):

        if not doc or not docType in self.docTypeNames:
            doc, docType = "", ""
        else:
            doc = doc.replace("-", "").replace(".", "")
            docType = self.docTypeNames[docType]

        self._type = type
        if self.model == "epsonlx300+":
            parameters = [isCreditNote and "N" or "F",  # Por ahora no soporto ND, que sería "D"
                          "C",
                          type,  # Tipo de FC (A/B/C)
                          "1",  # Copias - Ignorado
                          "P",  # "P" la impresora imprime la lineas(hoja en blanco) o "F" preimpreso
                          "17",  # Tamaño Carac - Ignorado
                          "I",  # Responsabilidad en el modo entrenamiento - Ignorado
                          self.ivaTypes.get(ivaType, "F"),  # Iva Comprador
                          formatText(name[:40]),  # Nombre
                          formatText(name[40:80]),  # Segunda parte del nombre - Ignorado
                          formatText(docType) or (isCreditNote and "-" or ""),
                          # Tipo de Doc. - Si es NC obligado pongo algo
                          doc or (isCreditNote and "-" or ""),  # Nro Doc - Si es NC obligado pongo algo
                          "N",  # No imprime leyenda de BIENES DE USO
                          formatText(address[:self.ADDRESS_SIZE] or "-"),  # Domicilio
                          formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]),  # Domicilio 2da linea
                          formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]),  # Domicilio 3ra linea
                          (isCreditNote or self.ivaTypes.get(ivaType, "F") != "F") and "-" or "",
                          # Remito primera linea - Es obligatorio si el cliente no es consumidor final
                          "",  # Remito segunda linea
                          "C",  # No somos una farmacia
                          ]
        else:
            parameters = [isCreditNote and "M" or "T",  # Ticket NC o Factura
                          "C",  # Tipo de Salida - Ignorado
                          type,  # Tipo de FC (A/B/C)
                          "1",  # Copias - Ignorado
                          "P",  # Tipo de Hoja - Ignorado
                          "17",  # Tamaño Carac - Ignorado
                          "E",  # Responsabilidad en el modo entrenamiento - Ignorado
                          self.ivaTypes.get(ivaType, "F"),  # Iva Comprador
                          formatText(name[:40]),  # Nombre
                          formatText(name[40:80]),  # Segunda parte del nombre - Ignorado
                          formatText(docType) or (isCreditNote and "-" or ""),
                          # Tipo de Doc. - Si es NC obligado pongo algo
                          doc or (isCreditNote and "-" or ""),  # Nro Doc - Si es NC obligado pongo algo
                          "N",  # No imprime leyenda de BIENES DE USO
                          formatText(address[:self.ADDRESS_SIZE] or "-"),  # Domicilio
                          formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]),  # Domicilio 2da linea
                          formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]),  # Domicilio 3ra linea
                          (isCreditNote or self.ivaTypes.get(ivaType, "F") != "F") and "-" or "",
                          # Remito primera linea - Es obligatorio si el cliente no es consumidor final
                          "",  # Remito segunda linea
                          "C",  # No somos una farmacia
                          ]
        if isCreditNote:
            self._currentDocument = self.CURRENT_DOC_CREDIT_TICKET
        else:
            self._currentDocument = self.CURRENT_DOC_BILL_TICKET
        # guardo el tipo de FC (A/B/C)
        self._currentDocumentType = type
        return self._sendCommand(self.CMD_OPEN_BILL_TICKET, parameters)

    def _getCommandIndex(self):
        if self._currentDocument == self.CURRENT_DOC_TICKET:
            return 0
        elif self._currentDocument in (self.CURRENT_DOC_BILL_TICKET, self.CURRENT_DOC_CREDIT_TICKET):
            return 1
        elif self._currentDocument == self.CURRENT_DOC_NON_FISCAL:
            return 2
        raise "Invalid currentDocument"

    def openTicket(self, defaultLetter='B'):
        if self.model == "epsonlx300+":
            print self.ivaTypes
            print self.ivaTypes.get("CONSUMIDOR_FINAL")
            return self.openBillTicket(defaultLetter, "CONSUMIDOR FINAL", "", None, None,
                                       self.ivaTypes.get("CONSUMIDOR_FINAL"))
        else:
            self._sendCommand(self.CMD_OPEN_FISCAL_RECEIPT, ["C"])
            self._currentDocument = self.CURRENT_DOC_TICKET

    def openDrawer(self):
        self._sendCommand(self.CMD_OPEN_DRAWER, [])

    def closeDocument(self):
        if self._currentDocument == self.CURRENT_DOC_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()], ["T"])
            return reply[2]
        if self._currentDocument == self.CURRENT_DOC_BILL_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()],
                                      [self.model == "epsonlx300+" and "F" or "T", self._type, "FINAL"])
            del self._type
            return reply[2]
        if self._currentDocument == self.CURRENT_DOC_CREDIT_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()],
                                      [self.model == "epsonlx300+" and "N" or "M", self._type, "FINAL"])
            del self._type
            return reply[2]
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL,):
            return self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT, ["T"])
        raise NotImplementedError

    def cancelDocument(self):
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET,
                                     self.CURRENT_DOC_CREDIT_TICKET):
            status = self._sendCommand(self.CMD_ADD_PAYMENT[self._getCommandIndex()], ["Cancelar", "0", 'C'])
            return status
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL,):
            self.printNonFiscalText("CANCELADO")
            return self.closeDocument()
        raise NotImplementedError

    def addItem(self, description, quantity, price, iva, itemNegative=False, discount=0, discountDescription='',
                discountNegative=True):
        if type(description) in types.StringTypes:
            description = [description]
        if itemNegative:
            sign = 'R'
        else:
            sign = 'M'
        quantityStr = str(int(quantity * 1000))
        if self.model == "epsonlx300+":
            bultosStr = str(int(quantity))
        else:
            bultosStr = "0" * 5  # No se usa en TM220AF ni TM300AF ni TMU220AF
        if self._currentDocumentType != 'A':
            # enviar con el iva incluido
            priceUnitStr = str(int(round(price * 100, 0)))
        else:
            if self.model == "tm-220-af": # la impresona , "tm-t900fa" aun no me aparece en RD
                # enviar sin el iva (factura A)
                priceUnitStr = "%0.4f" % (price / ((100.0 + iva) / 100.0))
            else:
                # enviar sin el iva (factura A)
                priceUnitStr = str(int(round((price / ((100 + iva) / 100)) * 100, 0)))
        ivaStr = str(int(iva * 100))
        extraparams = self._currentDocument in (self.CURRENT_DOC_BILL_TICKET,
                                                self.CURRENT_DOC_CREDIT_TICKET) and ["", "", ""] or []
        if self._getCommandIndex() == 0:
            for d in description[:-1]:
                self._sendCommand(self.CMD_PRINT_TEXT_IN_FISCAL,
                                  [formatText(d)[:20]])
        reply = self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                                  [formatText(description[-1][:20]),
                                   quantityStr, priceUnitStr, ivaStr, sign, bultosStr, "0" * 8] + extraparams)
        if discount:
            discountStr = str(int(discount * 100))
            self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                              [formatText(discountDescription[:20]), "1000",
                               discountStr, ivaStr, 'R', "0", "0"] + extraparams)
        return reply

    def addPayment(self, description, payment):
        paymentStr = str(int(payment * 100))
        status = self._sendCommand(self.CMD_ADD_PAYMENT[self._getCommandIndex()],
                                   [formatText(description)[:20], paymentStr, 'T'])
        return status

    def addAdditional(self, description, amount, iva, negative=False):
        """Agrega un adicional a la FC.
            @param description  Descripción
            @param amount       Importe (sin iva en FC A, sino con IVA)
            @param iva          Porcentaje de Iva
            @param negative True->Descuento, False->Recargo"""
        if negative:
            if not description:
                description = "Descuento"
            sign = 'R'
        else:
            if not description:
                description = "Recargo"
            sign = 'M'

        quantityStr = "1000"
        bultosStr = "0"
        priceUnit = amount
        if self._currentDocumentType != 'A':
            # enviar con el iva incluido
            priceUnitStr = str(int(round(priceUnit * 100, 0)))
        else:
            # enviar sin el iva (factura A)
            priceUnitStr = str(int(round((priceUnit / ((100 + iva) / 100)) * 100, 0)))
        ivaStr = str(int(iva * 100))
        extraparams = self._currentDocument in (self.CURRENT_DOC_BILL_TICKET,
                                                self.CURRENT_DOC_CREDIT_TICKET) and ["", "", ""] or []
        reply = self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                                  [formatText(description[:20]),
                                   quantityStr, priceUnitStr, ivaStr, sign, bultosStr, "0"] + extraparams)
        return reply

    def dailyClose(self, type):
        reply = self._sendCommand(self.CMD_DAILY_CLOSE, [type, "P"])
        return reply[2:]

    def getLastNumber(self, letter):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], True)
        if len(reply) < 3:
            # La respuesta no es válida. Vuelvo a hacer el pedido y si hay algún error que se reporte como excepción
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], False)
        if letter == "A":
            return int(reply[6])
        else:
            return int(reply[4])

    def getLastCreditNoteNumber(self, letter):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], True)
        if len(reply) < 3:
            # La respuesta no es válida. Vuelvo a hacer el pedido y si hay algún error que se reporte como excepción
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], False)
        if letter == "A":
            return int(reply[10])
        else:
            return int(reply[11])

    def cancelAnyDocument(self):
        try:
            self._sendCommand(self.CMD_ADD_PAYMENT[0], ["Cancelar", "0", 'C'])
            return True
        except:
            pass
        try:
            self._sendCommand(self.CMD_ADD_PAYMENT[1], ["Cancelar", "0", 'C'])
            return True
        except:
            pass
        try:
            self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT, ["T"])
            return True
        except:
            pass
        return False

    def getWarnings(self):
        ret = []
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["N"], True)
        printerStatus = reply[0]
        x = int(printerStatus, 16)
        if ((1 << 4) & x) == (1 << 4):
            ret.append("Poco papel para la cinta de auditoria")
        if ((1 << 5) & x) == (1 << 5):
            ret.append("Poco papel para comprobantes o tickets")
        return ret

    def __del__(self):
        try:
            self.close()
        except:
            pass
