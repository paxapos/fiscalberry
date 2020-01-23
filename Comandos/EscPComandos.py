# -*- coding: UTF-8 -*-

import string
import types
import requests
import logging
import unicodedata
import escpos
from ComandoInterface import ComandoInterface, ComandoException, ValidationError, FiscalPrinterError, formatText
import time
import datetime
from math import ceil


class PrinterException(Exception):
    pass


class EscPComandos(ComandoInterface):
    # el traductor puede ser: TraductorFiscal o TraductorReceipt
    # path al modulo de traductor que este comando necesita
    traductorModule = "Traductores.TraductorReceipt"

    DEFAULT_DRIVER = "ReceipDirectJet"

    __preFillTrailer = None

    def _sendCommand(self, comando, skipStatusErrors=False):
        try:
            ret = self.conector.sendCommand(comando, skipStatusErrors)
            return ret
        except PrinterException, e:
            logging.getLogger().error("PrinterException: %s" % str(e))
            raise ComandoException("Error de la impresora: %s.\nComando enviado: %s" % \
                                   (str(e), commandString))


    def printTexto(self, texto):
       printer = self.conector.driver
 
       printer.start()
       printer.text(texto)
 
       printer.cut("PART")
 
       printer.end()

    def print_mesa_mozo(self, setTrailer):
        for key in setTrailer:
            self.doble_alto_x_linea(key)

    def openDrawer(self):
        printer = self.conector.driver
        printer.start()
        printer.cashdraw(2)
        printer.end()

    def printPedido(self, **kwargs):
        "imprimir pedido de compras"
        printer = self.conector.driver

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])

        printer.start()
        
        printer.set("CENTER", "A", "A", 1, 1)
        
        # colocar en modo ESC P
        printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "1")

        if encabezado.has_key("es_pedido"):
            printer.text(u"Nuevo Pedido \n")
        else:
            printer.text(u"Nueva OC \n")
        printer.set("LEFT", "A", "A", 1, 1)
        fecha = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M %x')
        if encabezado:
            if encabezado.has_key("nombre_proveedor"):
                printer.text(u"Proveedor: "+encabezado.get("nombre_proveedor") )
                printer.text("\n")
            if encabezado.has_key("cuit") and len(encabezado.get("cuit")) > 1: 
                printer.text(u"CUIT: "+encabezado.get("cuit") )
                printer.text("\n")
            if encabezado.has_key("telefono") and len(encabezado.get("telefono")) > 1:
                printer.text(u"Telefono: "+encabezado.get("telefono") )
                printer.text("\n")
            if encabezado.has_key("email") and len(encabezado.get("email")) > 1:
                printer.text(u"E-mail: "+encabezado.get("email") )
            printer.text("\n")
            if encabezado.has_key("pedido_recepcionado"):
                if encabezado.get("pedido_recepcionado") == 1:
                    printer.text(u"Esta orden de compra ya ha sido recepcionada\n")
        printer.text(u"Fecha: %s \n\n\n" % fecha)

        printer.text(u"CANT\tDESCRIPCIÓN\n")
        printer.text("\n")
        tot_chars = 40
        for item in items:
            printer.set("LEFT", "A", "A", 1, 1)
            desc = item.get('ds')[0:24]
            cant = float(item.get('qty'))
            unidad_de_medida = item.get('unidad_de_medida')
            observacion = item.get('observacion')
            cant_tabs = 3
            can_tabs_final = cant_tabs - ceil(len(desc) / 8)
            strTabs = desc.ljust(int(len(desc) + can_tabs_final), '\t')

            printer.text(u"%g%s%s\t%s\n" % (cant," ",unidad_de_medida, strTabs))

            if observacion:
                printer.set("LEFT", "B", "B", 1, 1)
                printer.text(u"OBS: %s\n" % observacion)

        printer.text("\n")

        barcode = kwargs.get("barcode", None)
        if barcode:            
            printer.barcode(str(barcode).rjust(8, "0"), 'EAN13')

        printer.set("CENTER", "A", "B", 2, 2)  

        printer.cut("PART")

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set("LEFT", "A", "B", 1, 2)
        printer.end()

    def __printExtras(self, kwargs):
        "imprimir qr y barcodes"
        printer = self.conector.driver
        printer.set("CENTER", "A", "A", 1, 1)
        
        barcode = kwargs.get("barcode", None)
        if barcode:            
            printer.barcode(str(barcode).rjust(8, "0"), 'EAN13')

        qrcode = kwargs.get("qr", None)
        if qrcode:
            printer.qr(qrcode)

        qrcodeml = kwargs.get("qr-mercadopago", None)
        if qrcodeml:
            printer.text(u'Pagá rápido con Mercado Pago\n')
            printer.text(u"1- Escaneá el código QR\n2- Ingresá el monto\n3- Seleccioná tipo de pago\n4- Listo!, ni hace falta que nos avises.\n")
            printer.qr(qrcodeml)
    
    def printFacturaElectronica(self, **kwargs):
        "imprimir Factura Electronica"

        encabezado = kwargs.get("encabezado", None)

        # antes de comenzar descargo la imagen del barcode
        barcodeImage = requests.get(encabezado.get("barcode_url"), stream=True).raw

        items = kwargs.get("items", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)
        printer = self.conector.driver
        printer.start()
        printer.set("LEFT", "A", "B", 2, 1)
        printer.text(encabezado.get("nombre_comercio")+"\n")
        printer.set("LEFT", "A", "A", 1, 1)
        printer.text(encabezado.get("razon_social")+"\n")
        printer.text("CUIT: "+encabezado.get("cuit_empresa")+"\n")
        if encabezado.get('ingresos_brutos'):
            printer.text("Ingresos Brutos: "+encabezado.get("ingresos_brutos")+"\n")
        printer.text("Inicio de actividades: "+encabezado.get("inicio_actividades")+"\n")
        printer.text(encabezado.get("domicilio_comercial")+"\n")
        printer.text(encabezado.get("tipo_responsable")+"\n")
        printer.set("CENTER", "A", "A", 1, 1)
        printer.text("----------------------------------------\n") #40 guíones
        printer.set("LEFT", "A", "B", 1, 1)
        printer.text(encabezado.get("tipo_comprobante")+" Nro. "+encabezado.get("numero_comprobante")+"\n")
        printer.text("Fecha "+encabezado.get("fecha_comprobante")+"\n")
        printer.set("CENTER", "A", "A", 1, 1)
        printer.text("----------------------------------------\n") #40 guíones
        printer.set("LEFT", "A", "A", 1, 1)
        if encabezado.has_key("nombre_cliente"):
            nombre_cliente = "A "+encabezado.get("nombre_cliente")
            tipo_responsable_cliente = encabezado.get("tipo_responsable_cliente")
            documento_cliente = encabezado.get("nombre_tipo_documento")+": "+encabezado.get("documento_cliente")
            domicilio_cliente = encabezado.get("domicilio_cliente")
            printer.text(nombre_cliente+"\n")
            if documento_cliente:
                printer.text(documento_cliente+"\n")
            if tipo_responsable_cliente:
                printer.text(tipo_responsable_cliente+"\n")
            if domicilio_cliente:
                printer.text(domicilio_cliente+"\n")
        else:
            printer.text("A Consumidor Final \n")
        printer.set("CENTER", "A", "A", 1, 1)
        printer.text("----------------------------------------\n\n") #40 guíones
        printer.set("LEFT", "A", "A", 1, 1)
        tot_neto = 0.0
        tot_iva = 0.0
        total = 0.0
        if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
            printer.text(u"DESCRIPCIÓN\t\t(IVA) PRECIO NETO\n")
            printer.text("\n")
        for item in items:
            desc = item.get('ds')[0:20]
            cant = float(item.get('qty'))
            precio_unitario = float(item.get('importe'))
            precio_total = cant * precio_unitario 
            if item.get('alic_iva'):
                porcentaje_iva = float(item.get('alic_iva'))
            else:
                porcentaje_iva = 21.00
            if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
                #es Factura A, enviamos neto e IVA separados.
                precio_unitario_neto = precio_unitario / ((porcentaje_iva + 100.0) / 100)
                precio_unitario_iva = precio_unitario - precio_unitario_neto
                precio_total_neto = cant * precio_unitario_neto
                precio_total_iva = cant * precio_unitario_iva
                tot_neto += precio_total_neto
                tot_iva += precio_total_iva
            else:
                #Usamos estas variables para no tener que agregar ifs abajo
                precio_unitario_neto = precio_unitario
                precio_total_neto = precio_total

            total += precio_total

            cant_tabs = 3
            desc = desc.ljust(20, " ")
            can_tabs_final = cant_tabs - ceil(len(desc) / 8)
            strTabs = desc.ljust(int(len(desc) + can_tabs_final), '\t')

            if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
                printer.text("  %g x $%g\n" % (cant, round(precio_unitario_neto, 4)))
                printer.text(strTabs+"(%g)\t$%g\n" % (round(porcentaje_iva, 2), round(precio_total_neto, 2)))
            else:
                printer.text("%g " % (cant))
                printer.text("%s(%g)\t$%g\n" % (strTabs, round(porcentaje_iva, 2), round(precio_total_neto, 2)))

        printer.set("RIGHT", "A", "A", 1, 1)
        printer.text("\n")

        if addAdditional:
            if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
                # imprimir subtotal
                printer.text("Subtotal: $%g\n" % round(total, 2))

            # imprimir descuento
            sAmount = float(addAdditional.get('amount', 0))
            total = total - sAmount
            printer.set("RIGHT", "A", "A", 1, 1)
            printer.text("%s $%g\n" % (addAdditional.get('description')[0:20], round(sAmount, 2)))
            if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
                #recalculamos el neto e iva
                tot_neto = total / ((porcentaje_iva + 100.0) / 100)
                tot_iva = total - tot_neto
            
        if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
            printer.text("Subtotal Neto: $%g\n" % (round(tot_neto, 2)))
            printer.text("Subtotal IVA: $%g\n" % (round(tot_iva, 2)))
            printer.text("\n")


        # imprimir total
        printer.set("RIGHT", "A", "A", 2, 2)
        printer.text(u"TOTAL: $%g\n" % round(total, 2))
        printer.text("\n")

        printer.set("LEFT", "B", "A", 1, 1)

        if encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO B" or encabezado.get("tipo_comprobante") == 'NOTAS DE CREDITO M':
            printer.text(u"Firma...................................................\n\n")
            printer.text(u"Aclaración..............................................\n")
        
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)  

        printer.set("LEFT", "A", "A", 1, 1)
        #imagen BARCODE bajada de la URL


        printer.image( barcodeImage )
        cae = encabezado.get("cae")
        caeVto = encabezado.get("cae_vto")
        printer.text(u"CAE: " + cae + "    CAE VTO: " + caeVto +"\n\n")

        printer.image('afip.bmp');
        printer.text("Comprobante Autorizado \n")
 
        printer.set("CENTER", "B", "B", 1, 1)
        printer.text(u"Comprobante electrónico impreso por www.paxapos.com")
        
        printer.cut("PART")

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set("LEFT", "A", "B", 1, 2)
        printer.end()

    def printRemitoCorto(self, **kwargs):
        "imprimir remito"
        printer = self.conector.driver

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)
        

        printer.start()

        printer.set("CENTER", "A", "A", 1, 1)
        if encabezado.has_key("imprimir_fecha_remito"):
            fecha = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M %x')
            printer.text(u"Fecha: %s" % fecha)
        printer.text(u"\nNO VALIDO COMO FACTURA\n")

        if encabezado:
            printer.set("LEFT", "A", "A", 1, 1)
            if encabezado.has_key("nombre_cliente"):
                printer.text(u'\nNombre Cliente: %s\n' % encabezado.get("nombre_cliente"))
                if encabezado.has_key("telefono"):
                    printer.text(u'\nTelefono: %s\n' % encabezado.get("telefono"))
                if encabezado.has_key("domicilio_cliente"):
                    printer.text(u'\nDomicilio: %s\n' % encabezado.get("domicilio_cliente"))
                printer.text(u"\n")

        tot_importe = 0.0
        for item in items:
            desc = item.get('ds')[0:20]
            cant = float(item.get('qty'))
            precio = cant * float(item.get('importe'))
            tot_importe += precio
            cant_tabs = 3
            can_tabs_final = cant_tabs - ceil(len(desc) / 8)
            strTabs = desc.ljust(int(len(desc) + can_tabs_final), '\t')

            printer.text("%g\t%s$%g\n" % (cant, strTabs, precio))

        printer.text("\n")

        if addAdditional:
            # imprimir subtotal
            printer.set("RIGHT", "A", "A", 1, 1)
            printer.text("SUBTOTAL: $%g\n" % tot_importe)

            # imprimir descuento
            sAmount = float(addAdditional.get('amount', 0))
            tot_importe = tot_importe - sAmount
            printer.set("RIGHT", "A", "A", 1, 1)
            printer.text("%s $%g\n" % (addAdditional.get('description'), sAmount))

        # imprimir total
        printer.set("RIGHT", "A", "A", 2, 2)
        printer.text(u"TOTAL: $%g\n" % tot_importe)

        printer.set("LEFT", "A", "A", 1, 1)
        
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)   

        self.__printExtras(kwargs)



        printer.cut("PART")

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set("LEFT", "A", "B", 1, 2)
        printer.end()

    def printRemito(self, **kwargs):
        "imprimir remito"
        printer = self.conector.driver

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)
        

        printer.start()
        
        printer.set("CENTER", "A", "A", 1, 1)

        printer.set("CENTER", "A", "A", 1, 1)
        if encabezado.has_key("imprimir_fecha_remito"):
            fecha = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M %x')
            printer.text(u"Fecha: %s \n\n\n" % fecha)
        printer.text(u"Verifique su cuenta por favor\n")
        printer.text(u"NO VALIDO COMO FACTURA\n\n")

        if encabezado:
            printer.set("CENTER", "A", "A", 1, 2)
            if encabezado.has_key("nombre_cliente"):
                printer.text(u'\n%s\n' % encabezado.get("nombre_cliente"))
                if encabezado.has_key("telefono"):
                    printer.text(u'\n%s\n' % encabezado.get("telefono"))
                if encabezado.has_key("domicilio_cliente"):
                    printer.text(u'\n%s\n' % encabezado.get("domicilio_cliente"))
                printer.text(u"\n")

        printer.set("LEFT", "A", "A", 1, 1)
        printer.text(u"CANT\tDESCRIPCIÓN\t\tPRECIO\n")
        printer.text("\n")
        tot_importe = 0.0
        for item in items:
            desc = item.get('ds')[0:20]
            cant = float(item.get('qty'))
            precio = cant * float(item.get('importe'))
            tot_importe += precio
            cant_tabs = 3
            can_tabs_final = cant_tabs - ceil(len(desc) / 8)
            strTabs = desc.ljust(int(len(desc) + can_tabs_final), '\t')

            printer.text("%g\t%s$%g\n" % (cant, strTabs, precio))

        printer.text("\n")

        if addAdditional:
            # imprimir subtotal
            printer.set("RIGHT", "A", "A", 1, 1)
            printer.text("SUBTOTAL: $%g\n" % tot_importe)

            # imprimir descuento
            sAmount = float(addAdditional.get('amount', 0))
            tot_importe = tot_importe - sAmount
            printer.set("RIGHT", "A", "A", 1, 1)
            printer.text("%s $%g\n" % (addAdditional.get('description'), sAmount))

        # imprimir total
        printer.set("RIGHT", "A", "A", 2, 2)
        printer.text(u"TOTAL: $%g\n" % tot_importe)
        printer.text("\n\n\n")

        self.__printExtras(kwargs)

        printer.set("CENTER", "A", "B", 2, 2)
        
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)   


        printer.cut("PART")

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set("LEFT", "A", "B", 1, 2)
        printer.end()

    def setTrailer(self, setTrailer):
        self.__preFillTrailer = setTrailer

    def _setTrailer(self, setTrailer):
        print self.conector.driver
        printer = self.conector.driver

        for trailerLine in setTrailer:
            if trailerLine:
                printer.text(trailerLine)

            printer.text("\n")

    def printComanda(self, comanda, setHeader=None, setTrailer=None):
        "observacion, entradas{observacion, cant, nombre, sabores}, platos{observacion, cant, nombre, sabores}"
        printer = self.conector.driver
        printer.start()
        
        printer.set("CENTER", "A", "A", 1, 1)

        if setHeader:
            for headerLine in setHeader:
                printer.text(headerLine)
                printer.text("\n\n")

        if "id" in comanda:
            if "nuevaComanda" in comanda:
                printer.text(u"Nueva Comanda\n")
            else:
                printer.text(u"- REIMPRESION -\n")
            printer.text(u"Comanda #%s\n" % comanda['id'])
        else:
            printer.text(u"Nueva Comanda\n")

        if "created" in comanda:
            fecha = datetime.datetime.strptime(comanda['created'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M',)
        else:
            fecha = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M')
            
        printer.text(fecha + "\n")

        def print_plato(plato):
            "Imprimir platos"
            printer.set("LEFT", "A", "B", 1, 2)

            printer.text("%s) %s" % (plato['cant'], plato['nombre']))

            if 'sabores' in plato:
                printer.set("LEFT", "A", "B", 1, 1)
                text = "(%s)" % ", ".join(plato['sabores'])
                printer.text(text)

            printer.text("\n")

            if 'observacion' in plato:
                printer.set("LEFT", "A", "B", 1, 2)
                printer.text(u"   OBS: %s\n" % plato['observacion'])

        printer.text("\n")

        if 'observacion' in comanda:
            printer.set("CENTER", "B", "B", 2, 2)
            printer.text(u"OBSERVACIÓN\n")
            printer.text(comanda['observacion'])
            printer.text("\n")
            printer.text("\n")

        if 'entradas' in comanda:
            printer.set("CENTER", "A", "B", 1, 1)
            printer.text(u"** ENTRADA **\n")

            for entrada in comanda['entradas']:
                print_plato(entrada)

            printer.text("\n\n")

        if 'platos' in comanda:
            printer.set("CENTER", "A", "B", 1, 1)
            printer.text(u"----- PRINCIPAL -----\n")

            for plato in comanda['platos']:
                print_plato(plato)
            printer.text("\n\n")

        printer.set("CENTER", "A", "B", 2, 2)
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)   

        printer.cut("PART")
        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")

        # dejar letra chica alineada izquierda
        printer.set("LEFT", "A", "B", 1, 2)
        printer.end()