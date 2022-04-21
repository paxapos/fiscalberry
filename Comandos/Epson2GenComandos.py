# -*- coding: iso-8859-1 -*-
import logging
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
        "CUIT": c_int(3).value,
        "CUIL": c_int(2).value,
        "DNI": c_int(1).value,
        "PASAPORTE": c_int(5).value,
        "SIN_CALIFICADOR": c_int(0).value
    }

    ivaTypes = {
        "NINGUNO": c_int(0).value,
        "RESPONSABLE_INSCRIPTO": c_int(1).value,
        "NO_RESPONSABLE": c_int(3).value,
        "RESPONSABLE_MONOTRIBUTO": c_int(4).value,
        "CONSUMIDOR_FINAL": c_int(5).value,
        "EXENTO": c_int(6).value,
        "NO_CATEGORIZADO": c_int(7).value,
        "MONOTRIBUTISTA_SOCIAL": c_int(8).value,
        "CONTRIBUYENTE_EVENTUAL": c_int(9).value,
        "CONTRIBUYENTE_EVENTUAL_SOCIAL": c_int(10).value,
        "MONOTRIBUTO_INDEPENDIENTE_PROMOVIDO": c_int(11).value
    }

    percepcionTypes = {
        "IMPUESTOS_NACIONALES" : c_int(1).value,
        "IMPUESTOS_PROVINCIAL" : c_int(2).value,
        "IMPUESTO_MUNICIPAL" : c_int(3).value,
        "IMPUESTO_INTERNOS" : c_int(4).value,
        "INGRESOS_BRUTOS" : c_int(5).value,
        "PERCEPCION_DE_IVA" : c_int(6).value,
        "PERCEPCION_DE_INGRESOS_BRUTOS" : c_int(7).value,
        "PERCEPCION_POR_IMPUESTOS_MUNICIPALES" : c_int(8).value,
        "OTRAS_PERCEPCIONES" : c_int(9).value,
        "OTROS" : c_int(99).value
    }

    pagoTypes = {
        "CHEQUE" : c_int(3).value,
        "CUENTA_CORRIENTE" : c_int(6).value,
        "DEPOSITO" : c_int(7).value,
        "EFECTIVO" : c_int(8).value,
        "TARJETA_DE_CREDITO" : c_int(20).value,
        "TARJETA_DE_DEBITO" : c_int(21).value,
        "TRANSFERENCIA_BANCARIA" : c_int(23).value,
        "OTROS" : c_int(99).value,
    }

    comprobanteTypes = {
        "T": c_int(1).value,
        "FB": c_int(2).value,
        "FA": c_int(2).value,
        "FC": c_int(2).value,
        "FM": c_int(2).value,
        "NCT": c_int(3).value,
        "NCA": c_int(3).value,
        "NCB": c_int(3).value,
        "NCC": c_int(3).value,
        "NCM": c_int(3).value,
        "NDA": c_int(4).value,
        "NDB": c_int(4).value,
        "NDC": c_int(4).value,
        "NDM": c_int(4).value,
    }

    ivaPercentageIds = {
        'NINGUNO': c_int(0).value,
        '0.00': c_int(1).value,
        '0': c_int(1).value,
        '0.0': c_int(1).value,
        0.0: c_int(1).value,
        0: c_int(1).value,
        '10.50': c_int(4).value,
        '10.5': c_int(4).value,
        10.5: c_int(4).value,
        '21.00': c_int(5).value,
        '21.0': c_int(5).value,
        '21': c_int(5).value,
        21.0: c_int(5).value,
        21: c_int(5).value
    }

    comprobanteNro = 0


    def start(self):
        self.conector.driver.start()

    def close(self):
        self.conector.driver.close()

    def getStatus(self, *args):
        return self.conector.driver.ObtenerEstadoFiscal()

    def setHeader(self, headerlist=[]):
        """Establecer encabezado"""
        print(headerlist)
        line = 1
        while line <= len(headerlist):
            texto = c_char_p(headerlist[line-1]).value
            self.conector.driver.EpsonLibInterface.EstablecerEncabezado(line, texto)
            line += 1
            pass

    def setTrailer(self, trailer=[]):
        """Establecer pie"""
        line = 1
        while line <= len(trailer):
            texto = c_char_p(trailer[line-1]).value
            self.conector.driver.EpsonLibInterface.EstablecerCola(line, texto)
            line += 1

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        self.conector.sendCommand()

    def _setCustomerData(self, name, address, doc, docType, ivaType):   
        name1 = name[0:40]
        name2 = name[40:80]
        address1 = address[0:40]
        address2 = address[40:80]
        address3 = address[80:120]

        return self.conector.driver.EpsonLibInterface.CargarDatosCliente(str(name1), str(name2), str(address1), str(address2), str(address3), docType, str(doc) , ivaType)

    def addItem(self, description, quantity, price, iva, itemNegative=False, discount=0, discountDescription='',
                discountNegative=False, id_ii=0, ii_valor=0, id_codigo=1, codigo="1",
                codigo_unidad_matrix="1",codigo_unidad_medida=0):
        """Agrega un item a la FC.
                * param `description`          Descripción del item. Puede ser un string o una lista.
                        Si es una lista cada valor va en una línea.
                * param `quantity`             Cantidad
                * param `price`                Precio (incluye el iva si la FC es B o C, si es A no lo incluye)
                * param `iva`                  Porcentaje de iva
                * param `itemNegative`         Anulación del ítem.
                * param `discount`             Importe de descuento
                * param `discountDescription`  Descripción del descuento
                * param `discountNegative`     True->Resta de la FC
                * param `id_ii`                ID de Impuesto Interno: 0-Ninguno; 1-Impuesto Fijo; 2-Impuesto Porcentual
                * param `ii_valor`             Valor del impuesto 1=(7,4); 2=(0,8)
        """

        id_item = 200  # Agregar como ítem de venta.
        if itemNegative == True:
            id_item = 201
        if discountNegative == True:
            id_item = 206

        # id tipo de item, descripción, cantidad, porcentaje de IVA,
        # identificador II impuestos internos (0 = Ninguno), valor II, id_codigo (1 = Interno), valor del codigo, codigo_unidad_matrix, unidad de medida Unidad (7)
        ivaid = self.ivaPercentageIds.get(iva, 5)
        qty = str(quantity)
        description = c_char_p(description).value
        precio = str(price)
        iiValor = ""

        if (ii_valor > 0):
            str(ii_valor)

        logging.info("Item:  Mod: %s - Desc: %s Cant: %s - Precio: %s - Iva: %s - IIid: %d - IIvalor: %s" %
              (id_item, description, qty, precio, ivaid, id_ii, iiValor))

        return self.conector.driver.EpsonLibInterface.ImprimirItem(id_item, description, qty, precio, ivaid, id_ii,
                iiValor,id_codigo, codigo, codigo_unidad_matrix, codigo_unidad_medida)

    def openTicket(self, comprobanteType="T"):
        """Abre ticket
        str comprobanteType

        • 1 - Tique.
        • 2 - Tique factura A/B/C/M.
        • 3 - Tique nota de crédito, tique nota crédito A/B/C/M.
        • 4 - Tique nota de débito A/B/C/M.
        • 21 - Documento no fiscal homologado genérico.
        • 22 - Documento no fiscal homologado de uso interno.
        """
        self.conector.driver.EpsonLibInterface.AbrirComprobante(c_int(1).value)
        
        str_doc_number_max_len = 20
        str_doc_number = create_string_buffer(b'\000' * str_doc_number_max_len)
        error = self.conector.driver.EpsonLibInterface.ConsultarNumeroComprobanteActual(str_doc_number, c_int(str_doc_number_max_len).value) 
        self.comprobanteNro = str_doc_number.value   
        logging.info("Abrio comprobante Ticket : %s" % self.comprobanteNro)

        return error

    def openBillTicket(self, comprobanteType, name, address, doc, docType, ivaType):
        """
        Abre un ticket-factura
                @param  type        Tipo de Factura "A", "B", o "C"
                @param  name        Nombre del cliente
                @param  address     Domicilio
                @param  doc         Documento del cliente según docType
                @param  docType     Tipo de documento
                @param  ivaType     Tipo de IVA
        """

        comprobanteType = 'F' + comprobanteType
        comprobanteType = self.comprobanteTypes[comprobanteType]
        self._setCustomerData(name, address, doc, docType, ivaType)
        self.conector.driver.EpsonLibInterface.AbrirComprobante(comprobanteType)
        
        str_doc_number_max_len = 20
        str_doc_number = create_string_buffer(b'\000' * str_doc_number_max_len)
        error = self.conector.driver.EpsonLibInterface.ConsultarNumeroComprobanteActual(str_doc_number, c_int(str_doc_number_max_len).value) 
        self.comprobanteNro = str_doc_number.value   
        logging.info("Abrio comprobante Factura : %s" % self.comprobanteNro)

        return error

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
        comprobanteType = c_int(3).value
        self._setCustomerData(name, address, doc, docType, ivaType)
        self.conector.driver.EpsonLibInterface.AbrirComprobante(comprobanteType)
        
        str_doc_number_max_len = 20
        str_doc_number = create_string_buffer(b'\000' * str_doc_number_max_len)
        error = self.conector.driver.EpsonLibInterface.ConsultarNumeroComprobanteActual(str_doc_number, c_int(str_doc_number_max_len).value) 
        self.comprobanteNro = str_doc_number.value   
        logging.info("Abrio comprobante NC : %s" % self.comprobanteNro)

        return error

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

        comprobanteType = c_int(4).value
        self._setCustomerData(name, address, doc, docType, ivaType)
        self.conector.driver.EpsonLibInterface.AbrirComprobante(comprobanteType)

        str_doc_number_max_len = 20
        str_doc_number = create_string_buffer(b'\000' * str_doc_number_max_len)
        error = self.conector.driver.EpsonLibInterface.ConsultarNumeroComprobanteActual(
        str_doc_number, c_int(str_doc_number_max_len).value) 
        self.comprobanteNro = str_doc_number.value   
        logging.info("Abrio comprobante ND : %s" % self.comprobanteNro)

        return error

    def addAdditional(self, description, amount, iva, negative=False):
        """Agrega un descuento general a la Factura o Ticket.
                @param description  Descripción
                @param amount       Importe (sin iva en FC A, sino con IVA)
                @param iva          Porcentaje de Iva
                @param negative     Si negative = True, se añadira el monto como descuento, sino, sera un recargo
        """
        amount = "%.2f" % float(amount)
        id_modificador = 401
        if negative:
            id_modificador = 400
        ivaid = self.ivaPercentageIds.get(iva,5)
        self.conector.driver.EpsonLibInterface.CargarAjuste(id_modificador, str(description), str(amount), ivaid, " ")
        logging.info(str(id_modificador)+" " + str(description)+" "+ str(amount)+" "+str(ivaid)+ "")

    def addPerception(self, ds, importe, percepcion_tipo=" ", iva="21.00"):
        percepcionType = self.percepcionTypes[percepcion_tipo]
        ivaType = self.ivaPercentageIds[iva]
        importe = str(importe)
        ds = str(ds)
        self.conector.driver.EpsonLibInterface.CargarOtrosTributos(percepcionType,ds,importe,ivaType)

    def addPayment(self, description, payment):
        """Agrega un pago a la FC.
                @param description  Descripción
                @param payment      Importe
        """
        modificador = c_int(200).value
        tipoPago = self.pagoTypes[description]

        error = self.conector.driver.EpsonLibInterface.CargarPago(modificador, tipoPago,c_int(0).value,str(payment), "", "", "", "")
        logging.info(error)

    def getLastNumber(self, letter):
        self.start()
        self.cancelDocument()

        retLenght = 20
        ret = create_string_buffer(b'\000' * retLenght)
        self.conector.driver.EpsonLibInterface.ConsultarNumeroComprobanteUltimo(
            ret, retLenght)

        self.close()
        return ret

    def closeDocument(self, copias=0, email=None):
        subtotal = self.conector.driver.EpsonLibInterface.ImprimirSubTotal()
        logging.info("SUBTOTAL: %s" % subtotal)
        self.conector.driver.EpsonLibInterface.CerrarComprobante()

        return self.comprobanteNro

    def cancelDocument(self):
        self.conector.driver.EpsonLibInterface.Cancelar()

    def cancelAnyDocument(self):
        return self.cancelDocument()
    
    def imprimirAuditoria(self, desde, hasta, modificador=500):
        """ Auditoría desde - hasta
        *param `desde` : numero de Z ('9999') o fecha formato 'ddmmyy'
        *param `hasta` : numero de Z ('9999') o fecha formato 'ddmmyy'
        *param `modificador` : 500- detallada, 501- resumida
        """
        # desde & Hasta = Nros de Zeta o fechas, ambos pueden ser usados como intervalos de tiempo.
        self.conector.driver.EpsonLibInterface.ImprimirAuditoria(modificador, desde, hasta)

    def dailyClose(self, type):
        self.start()

        self.cancelDocument()

        if type == 'Z':
            ret = self.conector.driver.EpsonLibInterface.ImprimirCierreZ()
        else:
            ret = self.conector.driver.EpsonLibInterface.ImprimirCierreX()

        self.close()

        return ret









    ##### NO IMPLEMENTADOS #####

    def __cargarNumReferencia(self, numero):
        pass
    def getWarnings(self):
        return []

    def setCodigoBarras(self, numero, tipoCodigo="CodigoTipoI2OF5", imprimeNumero="ImprimeNumerosCodigo"):
        pass

    def openDrawer(self):
        pass

    def openNonFiscalReceipt(self):
        """Abre documento no fiscal"""
        pass

    def getLastCreditNoteNumber(self, letter):
        """Obtiene el último número de FC"""
        pass

    def getLastRemitNumber(self):
        """Obtiene el último número de Remtio"""
        pass

    def printFiscalText(self, text):
        pass
        #self.conector.sendCommand( jdata )

    def printNonFiscalText(self, text):
        """Imprime texto fiscal. Si supera el límite de la linea se trunca."""
        pass
        #self.conector.sendCommand( jdata )

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
        #self.conector.sendCommand( jdata )
