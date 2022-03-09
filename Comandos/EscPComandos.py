# -*- coding: utf-8 -*-
import logging
from ComandoInterface import ComandoInterface, ComandoException
from Comandos.EscPConstants import *
import datetime
from math import ceil
import json
import base64


def floatToString(inputValue):
    if ( not isinstance(inputValue, float) ):
        inputValue = float(inputValue)
    return ('%.2f' % inputValue).rstrip('0').rstrip('.')

def pad(texto, size, relleno, float = 'l'):
    text = str(texto)
    if float.lower() == 'l':
        return text[0:size].ljust(size, relleno)
    else:
        return text[0:size].rjust(size,relleno)


class PrinterException(Exception):
    pass


class EscPComandos(ComandoInterface):
    # el traductor puede ser: TraductorFiscal o TraductorReceipt
    # path al modulo de traductor que este comando necesita
    traductorModule = "Traductores.TraductorReceipt"

    DEFAULT_DRIVER = "ReceipDirectJet"

    __preFillTrailer = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)        
        self.total_cols = self.conector.driver.cols
        self.price_cols = 12
        self.cant_cols = 4
        self.desc_cols =  self.total_cols - self.cant_cols - self.price_cols

    def _sendCommand(self, comando, skipStatusErrors=False):
        try:
            ret = self.conector.sendCommand(comando, skipStatusErrors)
            return ret
        except PrinterException as e:
            logging.getLogger().error("PrinterException: %s" % str(e))
            raise ComandoException("Error de la impresora: %s.\nComando enviado: %s" % \
                                   (str(e),comando))


    def printTexto(self, texto):
        printer = self.conector.driver
        printer.start()
        printer.text(texto)
        printer.cut(PARTIAL_CUT) 
        printer.end()

    def printMuestra(self):
        printer = self.conector.driver 
        printer.start()
        firstLetter = [FONT_B,FONT_A]
        secondLetter = [NORMAL, BOLD]
        iteration = 0
        for j in range(1,3):
            for i in range(1,3):
                for second in secondLetter:
                    for first in firstLetter:
                        printer.set(CENTER, first, second, i, j)
                        printer.text("\n")
                        printer.text(f"{iteration} CENTER, {first}, {second}, {i}, {j}")
                        printer.text("\n")
                        iteration +=1
        printer.cut(PARTIAL_CUT) 
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
        
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        
        # colocar en modo ESC P
        #printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "1")

        if "es_pedido" in encabezado:
            printer.text(u"Nuevo Pedido \n")
        else:
            printer.text(u"Nueva OC \n")
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        fecha = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M %x')
        if encabezado:
            if "nombre_proveedor" in encabezado:
                printer.text(u"Proveedor: " + encabezado.get("nombre_proveedor") )
                printer.text("\n")
            if "cuit" in encabezado and len(encabezado.get("cuit")) > 1: 
                printer.text(u"CUIT: "+encabezado.get("cuit") )
                printer.text("\n")
            if "telefono" in encabezado and len(encabezado.get("telefono")) > 1:
                printer.text(u"Telefono: "+encabezado.get("telefono") )
                printer.text("\n")
            if "email" in encabezado and len(encabezado.get("email")) > 1:
                printer.text(u"E-mail: "+encabezado.get("email") )
            printer.text("\n")
            if "pedido_recepcionado" in encabezado:
                if encabezado.get("pedido_recepcionado") == 1:
                    printer.text(u"Esta orden de compra ya ha sido recepcionada\n")
        printer.text(u"Fecha: %s \n\n\n" % fecha)

        printer.text(u"CANT\tDESCRIPCIÓN\n")
        printer.text("\n")
        self.total_cols = 40
        
        for item in items:
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            desc = item.get('ds')[0:24]
            cant = float(item.get('qty'))
            unidad_de_medida = item.get('unidad_de_medida')
            observacion = item.get('observacion')
            cant_tabs = 3
            can_tabs_final = cant_tabs - ceil(len(desc) / 8)
            strTabs = desc.ljust(int(len(desc) + can_tabs_final), '\t')

            printer.text(u"%.2f%s%s\t%s\n" % (cant," ",unidad_de_medida, strTabs))

            if observacion:
                printer.set(LEFT, FONT_B, BOLD, 1, 1)
                printer.text(u"OBS: %s\n" % observacion)

        printer.text("\n")

        barcode = kwargs.get("barcode", None)
        if barcode:            
            printer.barcode(str(barcode).rjust(8, "0"), 'EAN13')

        printer.set(CENTER, FONT_A, BOLD, 2, 2)  

        printer.cut(PARTIAL_CUT)

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set("LEFT", "A", "B", 1, 2)
        printer.end()

    def __printExtras(self, kwargs):
        "imprimir qr y barcodes"
        printer = self.conector.driver
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        
        barcode = kwargs.get("barcode", None)
        if barcode:            
            printer.barcode(str(barcode).rjust(8, "0"), 'EAN13')

        qrcode = kwargs.get("qr", None)
        if qrcode:
            printer.set(CENTER, FONT_A, NORMAL, 1, 1)
            printer.qr(qrcode, QR_ECLEVEL_H, 6, QR_MODEL_2 , False)

        qrcodeml = kwargs.get("qr-mercadopago", None)
        if qrcodeml:
            printer.set(CENTER, FONT_A, NORMAL, 1, 1)
            printer.text(u'QR de Pago rápido con Mercado Pago\n')
            printer.set(CENTER, FONT_A, NORMAL, 1, 1)
            printer.qr(qrcodeml, QR_ECLEVEL_H, 5, QR_MODEL_2 , False)
    
    def printFacturaElectronica(self, **kwargs):
        "Imprimir Factura Electronica"

        encabezado = kwargs.get("encabezado", None)

        # antes de comenzar descargo la imagen del barcode
        #barcodeImage = requests.get(encabezado.get("barcode_url"), stream=True).raw

        items = kwargs.get("items", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)
        
        printer = self.conector.driver
        
        printer.start()
        
        printer.set(CENTER, FONT_A, BOLD, 2, 1)
        printer.text(encabezado.get("nombre_comercio")+"\n")
        printer.text("\n")
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        printer.text(encabezado.get("razon_social")+"\n")
        printer.text("CUIT: "+encabezado.get("cuit_empresa")+"\n")
        

        if encabezado.get('ingresos_brutos'):
            printer.text("Ingresos Brutos: "+encabezado.get("ingresos_brutos")+"\n")
        printer.text(encabezado.get("domicilio_comercial")+"\n")
        printer.text("Inicio de actividades: "+encabezado.get("inicio_actividades")+"\n")
        printer.text(encabezado.get("tipo_responsable")+"\n")
        

        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        printer.text("-" * self.total_cols + "\n")
        printer.set(CENTER, FONT_A, BOLD, 1, 1)
        printer.text(encabezado.get("tipo_comprobante")+" Nro. "+encabezado.get("numero_comprobante")+"\n")
        printer.text("Fecha "+encabezado.get("fecha_comprobante")+"\n")
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        printer.text("-" * self.total_cols + "\n")
        # print(" * * * ** *  A * * * ** * *")

        if "nombre_cliente" in encabezado:
            nombre_cliente = "A " + encabezado.get("nombre_cliente")
            tipo_responsable_cliente = encabezado.get("tipo_responsable_cliente")
            documento_cliente = encabezado.get("nombre_tipo_documento")+": "+encabezado.get("documento_cliente")
            domicilio_cliente = encabezado.get("domicilio_cliente")
            printer.text(nombre_cliente+"\n")
            if documento_cliente:
                printer.text(documento_cliente+"\n")
            if domicilio_cliente:
                printer.text(domicilio_cliente+"\n")
            if tipo_responsable_cliente:
                printer.text(tipo_responsable_cliente+"\n")
        else:
            printer.text("A Consumidor Final \n")

        printer.text("_" * self.total_cols + "\n")        
        
        if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
            printer.set(LEFT, FONT_B, BOLD, 1,1)
            printer.text("Cant. x Precio Unit. (%IVA)\n")
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            printer.text(f'{pad("Descripción", (self.total_cols - self.price_cols), " ", "l")}{pad("Importe", self.price_cols, " ", "r")}\n')
            printer.text("-" * self.total_cols + "\n")
        else:
            printer.set(LEFT, FONT_A, BOLD, 1,1)
            printer.text(f'CANT{"        DESCRIPCION".center(self.desc_cols," ")}{pad("IMPORTE", self.price_cols, " ", "r")}\n\n')
            
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)

        # print("antes de items")
        itemIvas = {}
        
        for item in items:

            if item.get('alic_iva'):
                porcentaje_iva = float(item.get('alic_iva'))
            else:
                porcentaje_iva = 21.00

            qty      = float(item.get('qty'))
            importe  = float(item.get('importe'))
            ds       = item.get('ds')[0:20]

            itemIvasTot = float(itemIvas.get(porcentaje_iva, 0) )

            importeiva = (importe * (porcentaje_iva/100))/(1+porcentaje_iva/100)
            
            itemIvas[porcentaje_iva] = itemIvasTot + ( importeiva * qty )

           
            item_cant = floatToString( qty )
            importe_unitario = floatToString( importe )

            total_producto = f"{round( qty * importe , 2 ):,.2f}"
            
            if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
                printer.set(LEFT, FONT_B, BOLD, 1,1)
                printer.text(f"{item_cant} x {importe_unitario} ({floatToString(porcentaje_iva)})\n")
                dstxt = pad(ds, self.desc_cols + self.cant_cols, " ", "l")
                preciotxt = pad( total_producto, self.price_cols - 1 , " ", "r")
                printer.set(LEFT, FONT_A, NORMAL, 1, 1)
                printer.text(  dstxt + "$" + preciotxt + "\n" )
            else:
                printer.set(LEFT, FONT_A, NORMAL, 1, 1)
                itemcanttxt = pad(item_cant, self.cant_cols, " ", "l")
                dstxt = pad(ds, self.desc_cols, " ", "l")
                preciotxt = pad( total_producto, self.price_cols - 1, " ", "r")
                printer.text(  itemcanttxt + dstxt + "$" + preciotxt + "\n" )
            # print("Item Impreso")


        tot_neto = float( encabezado.get("importe_neto") )
        tot_iva  = float( encabezado.get("importe_iva") ) 
        total    = float( encabezado.get("importe_total") )
        printer.set(RIGHT, FONT_A, NORMAL, 1, 1)
        printer.text("\n")


        descuentoRatio = 1
        if addAdditional:
            # imprimir descuento
            sAmount = float(addAdditional.get('amount', 0))
            descuentoDesc = addAdditional.get('description')
            desporcentaje = float(addAdditional.get('descuento_porcentaje'))
            descuentoRatio = (1 - (desporcentaje/100)) if desporcentaje != 0 else 1
            printer.set(RIGHT, FONT_A, BOLD, 1, 1)
            printer.text("SUBTOTAL: $%.2f\n" % round(total + sAmount,2))
            printer.set(RIGHT, FONT_A, NORMAL, 1, 1)
            printer.text(u"%s -$%.2f\n" % (descuentoDesc[0:20], round(sAmount, 2)))

        if encabezado.get("tipo_comprobante") == "Factura A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "Factura M" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO M":
            # imprimir subtotal
            # print(" * * * ** *  B * * * ** * *")
            printer.text("Total Sin IVA: $%.2f\n" % round(tot_neto, 2))

            # print(" * * * ** *  C * * * ** * *")
            for nameiva, importeiva in itemIvas.items():
                printer.text("IVA %s: $%.2f\n" % (str(nameiva)+"%", round(importeiva * descuentoRatio, 2)))



        # imprimir total
        printer.set(RIGHT, FONT_A, NORMAL, 2, 2)
        printer.text(u"TOTAL: $%.2f\n" % round(total,2))
        printer.text("\n")

        printer.set(LEFT, FONT_B, NORMAL, 1, 1)

        if encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO A" or encabezado.get("tipo_comprobante") == "NOTAS DE CREDITO B" or encabezado.get("tipo_comprobante") == 'NOTAS DE CREDITO M':
            printer.text(u"Firma.......................................\n\n")
            printer.text(u"Aclaración..................................\n")


        printer.set(CENTER, FONT_A, NORMAL, 1, 1)

        
        #printer.text(u"----------------------------------------\n\n") #40 guíones
        printer.text("-" * self.total_cols + "\n\n")
        
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)  

        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
      

        fecha_comprobante = encabezado.get("fecha_comprobante")

        felist = fecha_comprobante.split("/")
        fecha = felist[2]+"-"+felist[1]+"-"+felist[0]

        fullnumero = encabezado.get("numero_comprobante")
        numlist = fullnumero.split("-")
        pdv = int(numlist[0])
        numticket = int(numlist[1])

        qrcode = {
            "ver":1,
            "fecha":fecha,
            "cuit": encabezado.get("cuit_empresa"),
            "ptoVta":pdv,
            "tipoCmp":encabezado.get("tipo_comprobante"),
            "nroCmp":numticket,
            "importe":encabezado.get("importe_total"),
            "moneda":"PES", #pesos argentinoa
            "ctz":1,
           
            "tipoCodAut":"E",
            "codAut":encabezado.get("cae"),
        }

        if ( encabezado.get("documento_cliente") ) :
            qrcode["tipoDocRec"] = encabezado.get("tipoDocRec")
            qrcode["nroDocRec"]  = encabezado.get("documento_cliente")
        

        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        printer.text("Comprobante Autorizado por AFIP\n")
        # QR nueva disposicion de la AFIP
        jsonqr = json.dumps(qrcode)
        qrcode = base64.encodebytes( jsonqr.encode() )
        
        if qrcode:
            data = "https://www.afip.gob.ar/fe/qr/?p=" + qrcode.decode()
            printer.qr(data, QR_ECLEVEL_H, 3, QR_MODEL_2 , False)

        #printer.image( barcodeImage )
        cae = encabezado.get("cae")
        caeVto = encabezado.get("cae_vto")
        printer.set(CENTER, "A", "A", 1, 1)
        printer.text(u"\nCAE: " + cae + "    CAE VTO: " + caeVto +"\n\n")
        
 
        printer.set(CENTER, FONT_B, BOLD, 1, 1)
        printer.text(u"Software PAXAPOS - Hecho por y para gastronómicos")
        
        printer.cut(PARTIAL_CUT)

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set(LEFT, FONT_A, BOLD, 1, 2)
        printer.end()


    def printRemitoCorto(self, **kwargs):
        "imprimir remito"
        printer = self.conector.driver

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)
        

        printer.start()

        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        if "imprimir_fecha_remito" in encabezado:
            fecha = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M %x')
            printer.text(u"Fecha: %s" % fecha)
        printer.text(u"\nNO VALIDO COMO FACTURA\n")

        if encabezado:
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            if "nombre_cliente" in encabezado:
                printer.text(u'\nNombre Cliente: %s\n' % encabezado.get("nombre_cliente"))
                if "telefono" in encabezado:
                    printer.text(u'\nTelefono: %s\n' % encabezado.get("telefono"))
                if "domicilio_cliente" in encabezado:
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

            printer.text("%.2f\t%s$%.2f\n" % (cant, strTabs, precio))

        printer.text("\n")

        if addAdditional:
            # imprimir subtotal
            printer.set(RIGHT, FONT_A, NORMAL, 1, 1)
            printer.text("SUBTOTAL: $%.2f\n" % tot_importe)

            # imprimir descuento
            sAmount = float(addAdditional.get('amount', 0))
            tot_importe = tot_importe - sAmount
            printer.set(RIGHT, FONT_A, NORMAL, 1, 1)
            printer.text("%s $%.2f\n" % (addAdditional.get('description'), sAmount))

        # imprimir total
        printer.set(RIGHT, FONT_A, NORMAL, 2, 2)
        printer.text(u"TOTAL: $%.2f\n" % tot_importe)

        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)   

        self.__printExtras(kwargs)

        printer.cut(PARTIAL_CUT)

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set(BOLD, FONT_A, BOLD, 1, 2)
        printer.end()

    def printRemito(self, **kwargs):
        "imprimir remito"
        printer = self.conector.driver

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        pagos = kwargs.get("pagos", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)
        

        printer.start()
        
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)

        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        if "imprimir_fecha_remito" in encabezado:
            fecha = datetime.datetime.strftime(datetime.datetime.now(), "%d/%m/%Y %H:%M")
            printer.text(f"Fecha: {fecha} \n\n\n")
        printer.text(u"Verifique su cuenta por favor\n")
        printer.text(u"NO VÁLIDO COMO FACTURA\n\n")

        if encabezado:
            printer.set(CENTER, FONT_A, NORMAL, 1, 2)
            if "nombre_cliente" in encabezado:
                printer.text(f'\n{encabezado.get("nombre_cliente")}\n')
                if "telefono" in encabezado:
                    printer.text(f'\n{encabezado.get("telefono")}\n')
                if "domicilio_cliente" in encabezado:
                    printer.text(f'\n{encabezado.get("domicilio_cliente")}\n')
                printer.text(u"\n")

        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        itemcanttxt = pad( "CANT", self.cant_cols, " ", "l")
        #dstxt = pad("DESCRIPCION", 36, " ", "l")
        dstxt = "DESCRIPCIÓN".center(self.desc_cols, " ")
        preciotxt = pad( "PRECIO", self.price_cols, " ", "r")
        printer.text(  itemcanttxt + dstxt + preciotxt + "\n" )
        printer.text("\n")

        tot_importe = 0.0
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        for item in items:
            ds = item.get('ds')[0:30]
            item_cant = float(item.get('qty'))
            total_producto = item_cant * float(item.get('importe'))
            tot_importe += total_producto
         
            itemcanttxt = pad(floatToString(item_cant), self.cant_cols, " ", "l")
            dstxt = pad(ds, self.desc_cols, " ", "l")
            preciotxt = pad(f"${round(total_producto,2):.2f}" , self.price_cols, " ", "r")
            printer.text(  itemcanttxt + dstxt + preciotxt + "\n" )

        printer.text("\n")

        if addAdditional:
            #imprimir subtotal
            #printer.set("RIGHT", "A", "A", 1, 1)
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            subtotText = pad("SUBTOTAL:", self.total_cols - self.price_cols, " ", "r") + pad(f"${tot_importe:6.2f}",self.price_cols," ", "r")
            printer.text(subtotText + "\n")

            # imprimir descuento
            sAmount = float(addAdditional.get('amount', 0))
            tot_importe = tot_importe - sAmount
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            descText = pad(addAdditional.get('description'), self.total_cols - self.price_cols, " ", "r") + pad(f"${sAmount:.2f}", self.price_cols ," ", "r")
            printer.text(descText + "\n")

        # imprimir total
        printer.set(RIGHT, FONT_A, NORMAL, 2, 2)
        printer.text("\n")
        printer.text(f"TOTAL: ${tot_importe:.2f}\n")
        printer.text("\n\n\n")

        printer.set(RIGHT, FONT_A, BOLD, 1, 2)
        for pago in pagos:
            desc = pago.get('ds')[0:20]
            importe =float(pago.get('importe'))
            printer.text("%s\t$%.2f\n" % (desc, importe))

        printer.text("\n")

        self.__printExtras(kwargs)

        printer.set(CENTER, FONT_A, BOLD, 2, 2)
        
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)   


        printer.cut(PARTIAL_CUT)

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set(LEFT, FONT_A, BOLD, 1, 2)
        printer.end()

    def setTrailer(self, setTrailer):
        self.__preFillTrailer = setTrailer

    def _setTrailer(self, setTrailer):
        #print(self.conector.driver)
        printer = self.conector.driver

        for trailerLine in setTrailer:
            if trailerLine:
                printer.text(trailerLine)

            printer.text("\n")

    def printComanda(self, comanda, setHeader=None, setTrailer=None):
        "observacion, entradas{observacion, cant, nombre, sabores}, platos{observacion, cant, nombre, sabores}"
        printer = self.conector.driver
        printer.start()
        
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)

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
            
        printer.text(fecha + "\n\n")

        def print_plato(plato):
            "Imprimir platos"
            printer.set(LEFT, FONT_A, BOLD, 1, 2)

            printer.text("%s) %s" % (plato['cant'], plato['nombre']))

            if 'sabores' in plato:
                printer.text(f"({', '.join(plato['sabores'])})")

            printer.text("\n")

            if 'observacion' in plato:
                printer.text(u"   OBS: %s\n" % plato['observacion'])

        if 'observacion' in comanda:
            printer.set(CENTER, FONT_B, BOLD, 2, 2)
            printer.text(u"OBSERVACIÓN\n")
            printer.text(comanda['observacion'])
            printer.text("\n\n")

        if 'entradas' in comanda:
            printer.set(CENTER, FONT_A, BOLD, 1, 1)
            printer.text(u"** ENTRADA **\n")
            for entrada in comanda['entradas']:
                print_plato(entrada)
            printer.text("\n\n")

        if 'platos' in comanda:
            printer.set(CENTER, FONT_A, BOLD, 1, 1)
            printer.text(u"----- PRINCIPAL -----\n")
            for plato in comanda['platos']:
                print_plato(plato)
            printer.text("\n\n")

        printer.set(CENTER, FONT_A, BOLD, 2, 2)
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)   

        printer.cut(PARTIAL_CUT)
        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")

        # dejar letra chica alineada izquierda
        printer.set(LEFT, FONT_A, NORMAL, 1, 2)
        printer.end()
    
    def printArqueo(self, **kwargs):
        
        printer = self.conector.driver 
        printer.start()

        
        totalIngresosPorVenta = 0
        ingresosEfectivo = 0
        otrosIngresos = 0

        totalEgresosPorPagos = 0
        egresosEfectivo = 0
        otrosEgresos = 0

        totalRetiros  = 0
        totalIngresos = 0

        encabezado = kwargs.get('encabezado')

        fechaDesde  = datetime.datetime.strptime(encabezado['fechaDesde'], '%d-%m-%Y %H:%M').strftime('%d/%m %H:%M',)
        fechaHasta  = datetime.datetime.strptime(encabezado['fechaHasta'], '%d-%m-%Y %H:%M').strftime('%d/%m %H:%M',)
        fechaArqueo = datetime.datetime.strptime(encabezado['ArqueoDateTime'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%y %H:%M',)


        def imprimirEncabezado():            
            printer.set(CENTER, FONT_B, BOLD, 2, 2)
            printer.text("ARQUEO DE CAJA\n\n")
            printer.set(CENTER, FONT_A, NORMAL, 2, 1)
            printer.text(f"{encabezado['nombreComercio']}\n")
            printer.set(CENTER, FONT_A, NORMAL, 1, 1)
            printer.text("-" * self.total_cols + "\n")
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            printer.text(f"{BOLD_ON}{UNDERLINED_ON}'Fecha de Cierre'{UNDERLINED_OFF}{BOLD_OFF} : {fechaArqueo}\n")
            printer.text(f"{BOLD_ON}{UNDERLINED_ON}'Fecha de Turno'{UNDERLINED_OFF}{BOLD_OFF}  : {fechaDesde} al {fechaHasta}\n")
            printer.text(f"{BOLD_ON}{UNDERLINED_ON}'Reporte de Caja'{UNDERLINED_OFF}{BOLD_OFF} : {encabezado['nombreCaja']}\n")
            printer.text(f"{BOLD_ON}{UNDERLINED_ON}'Usuario'{UNDERLINED_OFF}{BOLD_OFF}         : {encabezado['aliasUsuario']}\n")
            printer.text(f"{BOLD_ON}{UNDERLINED_ON}'Observación'{UNDERLINED_OFF}{BOLD_OFF}     : {encabezado['observacion']}\n\n")

        def imprimirTitulo(titulo, ancho=1, alto=1):
            printer.set(CENTER, FONT_A, BOLD, 1, 1)
            printer.text("-" * self.total_cols + "\n")
            printer.set(CENTER, FONT_A, BOLD, ancho, alto)
            printer.text(f"{titulo}\n")
            printer.set(CENTER, FONT_A, BOLD, 1, 1)
            printer.text("-" * self.total_cols + "\n")

        #########   ENCABEZADO
        
        imprimirEncabezado()

        ######### INGRESOS POR VENTA

        if 'ingresosPorVentas' in kwargs:
            ingresosPorVentas = kwargs.get("ingresosPorVentas", [])
            if (len(ingresosPorVentas['detalle']) > 0) or ingresosPorVentas['otros']:
                imprimirTitulo(u"INGRESOS POR COBROS")

                printer.set(LEFT, FONT_A, NORMAL, 1, 1)
                for cobro in ingresosPorVentas['detalle']:
                    printer.text(pad(cobro['cant'],self.cant_cols," ","l") 
                                + pad(cobro['tipoPago'][:self.desc_cols-1],self.desc_cols," ","l")
                                + "$" + pad(f"{cobro['importe']:,.2f}",self.price_cols - 1," ", "r") + "\n")
                    totalIngresosPorVenta += cobro['importe']
                    if (cobro['tipoPago'] == 'Efectivo'):
                        ingresosEfectivo = cobro['importe'] 

                if (ingresosPorVentas['otros']):
                    printer.text(pad("    Otros Cobros",(self.total_cols - self.price_cols)," ", "l") 
                                + "$" + pad(f"{float(ingresosPorVentas['otros']):,.2f}", self.price_cols - 1," ","r") + "\n\n")
                    totalIngresosPorVenta += float(ingresosPorVentas['otros'])
                    otrosIngresos += float(ingresosPorVentas['otros'])

                printer.set(LEFT, FONT_A, BOLD, 1, 1)
                printer.text(pad("    TOTAL",self.total_cols - self.price_cols, " ", "l")
                            + "$" +  pad(f"{totalIngresosPorVenta:,.2f}", self.price_cols - 1, " ","r") + "\n\n")

        ######### EGRESOS POR PAGOS

        if 'egresosPorPagos' in kwargs:
            egresosPorPagos = kwargs.get("egresosPorPagos", []) 
            if (len(egresosPorPagos['detalle']) > 0) or egresosPorPagos['otros']:
                imprimirTitulo(u"EGRESOS POR PAGOS")

                printer.set(LEFT, FONT_A, NORMAL, 1, 1)
                for pago in egresosPorPagos['detalle']:
                    printer.text(pad(pago['cant'],self.cant_cols," ","l") 
                                + pad(pago['tipoPago'][:self.desc_cols-1],self.desc_cols," ","l")
                                + "$" + pad(f"{pago['importe']:,.2f}",self.price_cols - 1," ", "r") + "\n")
                    totalEgresosPorPagos += pago['importe']
                    if (pago['tipoPago'] == 'Efectivo'):
                        egresosEfectivo = pago['importe']

                if (egresosPorPagos['otros']):
                    printer.text(pad("    Otros Pagos",(self.total_cols - self.price_cols)," ", "l") 
                                + "$" + pad(f"{float(egresosPorPagos['otros']):,.2f}", self.price_cols - 1," ","r") + "\n\n")                    
                    totalEgresosPorPagos += float(egresosPorPagos['otros'])
                    otrosEgresos += float(egresosPorPagos['otros'])

                printer.set(LEFT, FONT_A, BOLD, 1, 1)
                printer.text(pad("    TOTAL",self.total_cols - self.price_cols, " ", "l")
                            + "$" +  pad(f"{totalEgresosPorPagos:,.2f}", self.price_cols - 1, " ","r") + "\n\n")



        ######### RETIROS TRASPASOS

        if ('retiros' in kwargs):
            retiros = kwargs.get("retiros", [])            
            if (len(retiros) > 0):
                #Solo imprime cuando llega retiros en el JSON

                imprimirTitulo(u"RETIROS DE CAJA")

                printer.set(LEFT, FONT_A, NORMAL, 1, 1)

                for retiro in retiros:
                    fechaRetiro = datetime.datetime.strptime(retiro['fechaTraspaso'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M',)
                    printer.text(pad(fechaRetiro,self.total_cols - self.price_cols, " ","l")
                                + "$" + pad(f"{retiro['monto']:,.2f}",self.price_cols - 1," ","r") + "\n")
                    totalRetiros += retiro['monto']
                    #TODO traer las observaciones del retiro
                    # if retiro['observacion']:
                    #     printer.set(CENTER, "A", "A", 1, 1)
                    #     printer.text(retiro['observacion'])        

                printer.text("\n")
                printer.set(LEFT, FONT_A, BOLD, 1, 1)
                printer.text(pad("    TOTAL",self.total_cols - self.price_cols, " ", "l")
                            + "$" +  pad(f"{totalRetiros:,.2f}", self.price_cols - 1, " ","r") + "\n\n")

        ######### INGRESOS TRASPASOS

        if ('ingresos' in kwargs):
            ingresos = kwargs.get("ingresos", None)
            if(len(ingresos) > 0):            
                #Solo imprime cuando hay traspasos        

                imprimirTitulo(u"INGRESOS DE CAJA")

                printer.set("LEFT", "A", "A", 1, 1)

                for ingreso in ingresos:
                    fechaIngreso = datetime.datetime.strptime(ingreso['fechaTraspaso'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M',)
                    printer.text(pad(fechaIngreso,self.total_cols - self.price_cols, " ","l")
                                + "$" + pad(f"{ingreso['monto']:,.2f}",self.price_cols - 1," ","r") + "\n")
                    totalIngresos += ingreso['monto']
                    #TODO traer observaciones de ingresos
                    # if ingreso['observacion']:
                    #     printer.set(CENTER, "A", "A", 1, 1)
                    #     printer.text(ingreso['observacion'])

                printer.text("\n")
                printer.set(LEFT, FONT_A, BOLD, 1, 1)
                printer.text(pad("    TOTAL",self.total_cols - self.price_cols, " ", "l")
                            + "$" +  pad(f"{totalIngresos:,.2f}", self.price_cols - 1, " ","r") + "\n\n")
        
        ######### RESULTADO
        if encabezado['importeFinal']:
            importeFinal = float(encabezado['importeFinal'])
        else:
            importeFinal = 0

        imprimirTitulo(u"RESÚMEN (Efectivo)", 1, 2)

        printer.set(LEFT, FONT_A, NORMAL, 1, 1)

        ingresosDict = {"Importe Inicial:"    : f"{float(encabezado['importeInicial']):,.2f}",
                        "Ingresos por Cobros:": f"{ingresosEfectivo:,.2f}",
                        "Ingresos de Caja:"   : f"{totalIngresos:,.2f}",
                        "Otros Ingresos:"     : f"{otrosIngresos:,.2f}"}

        for key in ingresosDict:
            printer.text(pad("+",self.cant_cols," ","l") + pad(key,self.desc_cols," ","l") + "$" + 
                         pad(ingresosDict[key],self.price_cols - 1 ," ","r") + "\n")
        
        printer.set(LEFT, FONT_A, BOLD, 1, 1)

        sumaIngresos = (ingresosEfectivo + totalIngresos + float(encabezado['importeInicial']))
        printer.text(" " * (self.total_cols - self.price_cols) + "$" + pad(f"{sumaIngresos:,.2f}",self.price_cols - 1, " ","r") + "\n\n")
        
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)

        egresosDict = {"Retiros de Caja:"   :   f"{totalRetiros:,.2f}",
                       "Egresos por Pagos"  :   f"{egresosEfectivo:,.2f}",
                       "Otros Egresos"      :   f"{otrosEgresos:,.2f}",
                       "Importe Final:"     :   f"{importeFinal:,.2f}"}

        for key in egresosDict:
            printer.text(pad("-",self.cant_cols," ","l") + pad(key,self.desc_cols," ","l") + "$" + 
                         pad(egresosDict[key],self.price_cols - 1 ," ","r") + "\n")

        printer.set(LEFT, FONT_A, BOLD, 1, 1) 

        sumaEgresos = (egresosEfectivo + totalRetiros + importeFinal)
        printer.text(" " * (self.total_cols - self.price_cols)+ "$" + pad(f"{sumaEgresos:,.2f}",self.price_cols - 1, " ","r") + "\n\n")
        
        printer.set(LEFT, FONT_A, BOLD, 1, 2, density=1,invert=True)

        montoSaldo = float(encabezado['diferencia'])
        if (montoSaldo < 0):
            saldo = "SOBRANTE"
        elif (montoSaldo > 0):
            saldo = "FALTANTE"
        else:
            saldo = ""

        printer.text(pad(f"    Saldo {saldo}", self.total_cols - self.price_cols , " ", "l") 
                    + "$" + pad(f"{abs(montoSaldo):,.2f}",self.price_cols - 1, " ", "r"))

        ##########   FIRMA

        printer.text("\n" * 7)
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        printer.text("_" * self.desc_cols + "\n")
        printer.text("Firma Responsable\n\n")
        printer.set(CENTER, FONT_B, NORMAL, 1, 1)
        printer.text("Reporte de Cierre de Caja\n")
        printer.text(datetime.datetime.strftime(datetime.datetime.now(), '%d/%m/%y %H:%M'))


        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        printer.cut(PARTIAL_CUT)
        printer.end()