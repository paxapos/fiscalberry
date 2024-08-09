# -*- coding: utf-8 -*-
from ComandoInterface import ComandoInterface, ComandoException
from Comandos.EscPConstants import *
import datetime
from math import ceil
import json
import base64

from fiscalberry_logger import getLogger

logger = getLogger()

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
        self.price_cols = 12 #12 espacios permiten hasta 9,999,999.99
        self.cant_cols = 6   #4 no admitiría decimales, 6 sería mejor
        self.desc_cols =  self.total_cols - self.cant_cols - self.price_cols
        self.desc_cols_ext = self.total_cols - self.price_cols
        self.signo = "$" # Agregar el signo $ opcionalmente o espacio.
        

    def _sendCommand(self, comando, skipStatusErrors=False):
        try:
            ret = self.conector.sendCommand(comando, skipStatusErrors)
            return ret
        except PrinterException as e:
            getLogger("EscPComandos").error("PrinterException: %s" % str(e))
            raise ComandoException("Error de la impresora: %s.\nComando enviado: %s" % (str(e),comando))
    def getStatus(self):
        printer = self.conector.driver
        printer.start()
        rta = printer.connected
        printer.end()
        if rta: 
            if hasattr(printer , "host"):
                return f"Conectada en {printer.host}"
        else:
            return False

    def printTexto(self, texto):
        printer = self.conector.driver
        try:
            printer.start()
        except Exception as e:
            return False
        printer.text(texto)
        printer.cut(PARTIAL_CUT) 
        printer.end()
        return True

    def printMuestra(self):
        printer = self.conector.driver 
        try:
            printer.start()
        except Exception as e:
            return False
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
        try:
            printer.start()
        except Exception as e:
            return False
        printer.cashdraw(2)
        printer.end()

    def printPedido(self, **kwargs):
        "imprimir pedido de compras"

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])

        if encabezado is None or len(items) == 0:
            logger.error("No hay datos suficientes para imprimir")
            return False

        printer = self.conector.driver

        try:
            printer.start()
        except Exception as e:
            return False
        
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)

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
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        printer.end()

        return True

    def __printExtras(self, kwargs):
        "Imprimir QRs y Barcodes"
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
            printer.qr(qrcodeml, QR_ECLEVEL_H, 5, QR_MODEL_2 , False)
    
    def printFacturaElectronica(self, **kwargs):
        "Imprimir Factura Electronica"

        # Secciones de la Factura
        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        pagos = kwargs.get("pagos", [])
        addAdditional = kwargs.get("addAdditional", False)
        setTrailer = kwargs.get("setTrailer", False)

        if encabezado is None or len(items) == 0:
            logger.error("No hay datos suficientes para imprimir")
            return False

            
        tiposInscriptoString = ["Factura A", "NOTAS DE CREDITO A", "Factura M", "NOTAS DE CREDITO M", "Factura \"A\"", "NOTAS DE CREDITO \"A\"", "Factura \"M\"", "NOTAS DE CREDITO \"M\""]
        tiposInscriptoCod = ["001","051","003","053"]
        tiposNC = ["NOTAS DE CREDITO A", "NOTAS DE CREDITO B", "NOTAS DE CREDITO C", "NOTAS DE CREDITO M",
                      "NOTAS DE CREDITO \"A\"" "NOTAS DE CREDITO \"B\"", "NOTAS DE CREDITO \"C\"", "NOTAS DE CREDITO \"M\"",
                      "003", "008", "013", "053"]
        
        printer = self.conector.driver
        try:
            printer.start()
        except Exception as e:
            return False
        

        # 1- DATOS DEL COMERCIO
        nombreComercio = encabezado.get('nombre_comercio')
        razonSocial = encabezado.get('razon_social')
        cuitComercio = encabezado.get('cuit_empresa')
        ingresosBrutos = encabezado.get('ingresos_brutos')
        domicilioComercial = encabezado.get('domicilio_comercial')
        inicioActividades = encabezado.get('inicio_actividades')
        tipoResponsabilidad = encabezado.get('tipo_responsable')

        printer.set(CENTER, FONT_A, BOLD, 2, 1)
        printer.text(f"{ nombreComercio }\n\n")

        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        printer.text(f"{ razonSocial }\n")
        printer.text(f"CUIT: { cuitComercio }\n")        

        if ingresosBrutos:
            printer.text(f"Ingresos Brutos: {ingresosBrutos}\n")
        printer.text(f"{ domicilioComercial }\n")
        printer.text(f"Inicio de actividades: {inicioActividades}\n")
        printer.text(f"{ tipoResponsabilidad }\n")        

        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        printer.text("-" * self.total_cols + "\n")

        # 2- IDENTIFICACIÓN DEL COMPROBANTE
        tipoComprobante = encabezado.get('tipo_comprobante')
        tipoCmp = encabezado.get('tipo_comprobante_codigo')
        nroComprobante = encabezado.get('numero_comprobante')
        fechaComprobante = encabezado.get('fecha_comprobante')
        cae = encabezado.get("cae")
        caeVto = encabezado.get("cae_vto")

        printer.set(CENTER, FONT_A, BOLD, 1, 1)
        printer.text(f"{ tipoComprobante } Nro. { nroComprobante }\n")
        printer.text(f"Fecha { fechaComprobante }\n")
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        printer.text("-" * self.total_cols + "\n")

        # 3- DATOS DEL CLIENTE
        if "nombre_cliente" in encabezado:
            nombreCliente = f"A {encabezado.get('nombre_cliente')}"
            tipoRespCliente = encabezado.get('tipo_responsable_cliente', False)
            tipoDocCliente = encabezado.get('nombre_tipo_documento', False)
            documentoCliente = encabezado.get('documento_cliente', False)
            domicilioCliente = encabezado.get("domicilio_cliente", False)
            tipoDocRec = encabezado.get('tipoDocRec')

            printer.text(nombreCliente + "\n")
            if documentoCliente and tipoDocCliente:
                printer.text(f"{tipoDocCliente}: {documentoCliente}\n")
            if domicilioCliente:
                printer.text(domicilioCliente + "\n")
            if tipoRespCliente:
                printer.text( tipoRespCliente + "\n")
        else:
            printer.text("A Consumidor Final \n")

        printer.text("=" * self.total_cols + "\n")
        
        # 4- ITEMS
        # 4.1- ENCABEZADOS ITEMS
        if tipoComprobante in tiposInscriptoString or tipoCmp in tiposInscriptoCod:

            cantHeader = "Cant. x Precio Unit. (%IVA)"
            dsHeader = pad("Descripción", (self.desc_cols_ext), " ", "l")
            precioHeader = pad("Importe", self.price_cols, " ", "r")
            
            printer.set(LEFT, FONT_B, BOLD, 1,1)
            printer.text(f"{cantHeader}\n")
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            printer.text(f"{dsHeader}{precioHeader}\n")
            printer.text("-" * self.total_cols + "\n")
        else:
            cantHeader = pad( "CANT", self.cant_cols, " ", "l")
            dsCentrador = (" " * (self.price_cols - self.cant_cols))
            dsHeader = (dsCentrador + "DESCRIPCIÓN").center(self.desc_cols, " ")
            precioHeader = pad( "PRECIO", self.price_cols, " ", "r")

            printer.set(LEFT, FONT_A, BOLD, 1,1)
            printer.text( f"{cantHeader}{dsHeader}{precioHeader}\n" )
            printer.text("\n")
            
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)

        # 4.2- TABLA ITEMS
        itemIvas = {}
        for item in items:

            if item.get('alic_iva'):
                alicIva = float(item.get('alic_iva'))
            else:
                alicIva = 21.00

            qty = float(item.get('qty'))
            importe = float(item.get('importe'))
            ds = item.get('ds')[0:self.desc_cols-2]

            itemIvasTot = float(itemIvas.get(alicIva, 0) )
            importeiva = (importe * (alicIva/100))/(1+alicIva/100)
            itemIvas[alicIva] = itemIvasTot + ( importeiva * qty )
           
            itemCant = floatToString( qty )
            importeUnitario = floatToString( importe )
            totalProducto = f"{round( qty * importe , 2 ):,.2f}"

            if tipoComprobante in tiposInscriptoString or tipoCmp in tiposInscriptoCod:
                printer.set(LEFT, FONT_B, BOLD, 1,1)
                printer.text(f"{itemCant} x {importeUnitario} ({floatToString(alicIva)})\n")
                printer.set(LEFT, FONT_A, NORMAL, 1, 1)
                printer.text(f'{pad(ds, self.desc_cols_ext, " ", "l")}{pad( totalProducto, self.price_cols , " ", "r")}\n' )
            else:
                printer.set(LEFT, FONT_A, NORMAL, 1, 1)
                cantTxt = pad(itemCant, self.cant_cols, " ", "l")
                dsTxt = pad(ds, self.desc_cols, " ", "l")
                totalTxt = pad(totalProducto, self.price_cols, " ", "r")

                printer.text(f'{cantTxt}{dsTxt}{totalTxt}\n')

        printer.text("-" * self.total_cols + "\n")

        totalNeto = float( encabezado.get("importe_neto") )
        tot_iva  = float( encabezado.get("importe_iva") ) # Descontinuado en favor de detalle por c/alícuota
        total    = float( encabezado.get("importe_total") )

        # 5- DESCUENTOS / RECARGOS
        descuentoRatio = 1
        if addAdditional:
            sAmount = float(addAdditional.get('amount', 0))
            descuentoDesc = addAdditional.get('description')[0:20]
            desporcentaje = float(addAdditional.get('descuento_porcentaje'))
            sAmount = -sAmount
            descuentoRatio = (1 - (desporcentaje/100)) if desporcentaje != 0 else 1

            # 5.1- SUBTOTAL
            dsSubtotal = pad("SUBTOTAL:", self.desc_cols_ext - 1, " ", "l")
            importeSubtotal = pad(f"{round(total - sAmount,2):,.2f}",self.price_cols, " ", "r")
            dsDescuento = pad(descuentoDesc, self.desc_cols_ext - 1, " ", "l")
            importeDescuento = pad(f"{round(sAmount, 2):,.2f}",self.price_cols, " ", "r")

            printer.set(LEFT, FONT_A, BOLD, 1, 1)
            printer.text(f'{dsSubtotal}{self.signo}{importeSubtotal}\n')
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            printer.text(f'{dsDescuento}{self.signo}{importeDescuento}\n\n')

        # 6- DETALLE IVAS (INSCRIPTO)
        if tipoComprobante in tiposInscriptoString or tipoCmp in tiposInscriptoCod:
            dsSinIva = pad("Total sin IVA:", self.desc_cols_ext - 1, " ", "l")
            importeSinIva = pad(f"{round(totalNeto, 2):,.2f}",self.price_cols, " ", "r")
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)

            printer.text(f'{dsSinIva}{self.signo}{importeSinIva}\n')

            for nameiva, importeiva in itemIvas.items():
                dsIva = pad(f"IVA {str(nameiva)}%:", self.desc_cols_ext - 1, " ", "l")
                importeIva = pad(f"{round(importeiva * descuentoRatio, 2):,.2f}",self.price_cols, " ", "r")
                printer.set(LEFT, FONT_A, NORMAL, 1, 1)

                printer.text(f'{dsIva}{self.signo}{importeIva}\n')

        # 7- TOTAL
        printer.set(LEFT, FONT_A, BOLD, 1, 2)
        dsTotal =  pad("TOTAL:", self.desc_cols_ext - 1, " ", "l")
        importeTotal =  pad(f"{round(total,2):,.2f}",self.price_cols, " ", "r")

        printer.text(f'{dsTotal}{self.signo}{importeTotal}\n\n')

        printer.set(LEFT, FONT_B, NORMAL, 1, 1)

        if tipoComprobante in tiposNC or tipoCmp in tiposNC:
            printer.text(u"Firma.......................................\n\n")
            printer.text(u"Aclaración..................................\n")
        else:
            self._printPagoDetallado(pagos)

        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        printer.text("-" * self.total_cols + "\n\n")

        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)

        # 8- AFIP
        # 8.1- Json Datos AFIP
        felist = fechaComprobante.split("/")
        fecha = felist[2]+"-"+felist[1]+"-"+felist[0]

        fullnumero = nroComprobante
        numlist = fullnumero.split("-")
        pdv = int(numlist[0])
        numticket = int(numlist[1])

        qrcode = {
            "ver":1,
            "fecha":fecha,
            "cuit": int(cuitComercio),
            "ptoVta":pdv,
            "tipoCmp":int(tipoCmp),
            "nroCmp":numticket,
            "importe":total,
            "moneda":"PES", #pesos argentinos
            "ctz":1,
            #tipoDocRec OPCIONAL,
            #nroDocRec OPCIONAL,
            #tipoCodAut,
            #codAut
        }

        # Opcionales si vienen en el JSON
        if ( encabezado.get('documento_cliente') ) :
            qrcode["tipoDocRec"] = int(tipoDocRec)
            qrcode["nroDocRec"]  = int(documentoCliente)

        qrcode["tipoCodAut"] = "E"
        qrcode["codAut"] = int(cae)  

        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        printer.text("Comprobante Autorizado por AFIP")
        printer.text("\n")

        # 8.2- QR nueva disposicion de la AFIP
        jsonqr = json.dumps(qrcode)
        qrcode = base64.encodebytes( jsonqr.encode() )
        
        if qrcode:
            data = "https://www.afip.gob.ar/fe/qr/?p=" + qrcode.decode().replace("\n", "")
            printer.qr(data, QR_ECLEVEL_H, 3, QR_MODEL_2 , False)

        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        caeTxt = f"CAE: {cae}"
        caeVtoTxt = f" CAE VTO: {caeVto}"
        printer.text("\n")
        printer.text(f"{caeTxt}    {caeVtoTxt}")
        printer.text("\n")
        
 
        printer.set(CENTER, FONT_B, BOLD, 1, 1)
        printer.text("Software PAXAPOS - Hecho por y para gastronómicos")
        
        printer.cut(PARTIAL_CUT)

        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        printer.end()

        return True

    def printRemitoCorto(self, **kwargs):
        "Imprimir remito corto"

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)     

        if encabezado is None or len(items) == 0:
            logger.error("No hay datos suficientes para imprimir")
            return False

        printer = self.conector.driver          

        try:
            printer.start()
        except Exception as e:
            return False

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

        tot_importe = 0.0
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        for item in items:
            ds = item.get('ds')[0:self.desc_cols-2]
            item_cant = float(item.get('qty'))
            total_producto = item_cant * float(item.get('importe'))
            tot_importe += total_producto
         
            itemcanttxt = pad(floatToString(item_cant), self.cant_cols, " ", "l")
            dstxt = pad(ds, self.desc_cols, " ", "l")
            preciotxt = pad(f"{self.signo}{round(total_producto,2):,.2f}" , self.price_cols, " ", "r")
            printer.text(itemcanttxt + dstxt + preciotxt + "\n")

        printer.text("\n")

        if addAdditional:
            # imprimir subtotal
            printer.set(RIGHT, FONT_A, NORMAL, 1, 1)
            printer.text(f"SUBTOTAL: {self.signo}%.2f\n" % tot_importe)

            # imprimir descuento
            sAmount = float(addAdditional.get('amount', 0))
            tot_importe = tot_importe - sAmount
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            descText = pad(addAdditional.get('description'), self.desc_cols_ext, " ", "r") + pad(f"{self.signo}{sAmount:.2f}", self.price_cols ," ", "r")
            printer.text(descText + "\n")

        # imprimir total
        printer.set(RIGHT, FONT_A, NORMAL, 1, 2)
        printer.text(f"TOTAL: {self.signo}{tot_importe:.2f}\n")

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

        return True

    def printRemito(self, **kwargs):
        "Imprimir remito"

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        pagos = kwargs.get("pagos", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)

        if encabezado is None or len(items) == 0:
            logger.error("No hay datos suficientes para imprimir")
            return False

        printer = self.conector.driver
        try:
            printer.start()
        except Exception as e:
            return False
        
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)

        if encabezado and "imprimir_fecha_remito" in encabezado:
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

        cantHeader = pad( "CANT", self.cant_cols, " ", "l")
        dsCentrador = (" " * (self.price_cols - self.cant_cols))
        dsHeader = (dsCentrador + "DESCRIPCIÓN").center(self.desc_cols, " ")
        precioHeader = pad( "PRECIO", self.price_cols, " ", "r")
        
        printer.text( f"{cantHeader}{dsHeader}{precioHeader}\n" )
        printer.text("\n")

        printer.set(LEFT, FONT_A, NORMAL, 1, 1)

        importeSubTotal = 0.0

        for item in items:
            qty = float(item.get('qty', 1))
            importe = float(item.get('importe'))
            ds = item.get('ds')[0:self.desc_cols-2]
            total = importe * qty
         
            itemCant = floatToString( qty )
            totalProducto = f"{round( qty * importe , 2 ):,.2f}"

            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            cantTxt = pad(itemCant, self.cant_cols, " ", "l")
            dsTxt = pad(ds, self.desc_cols, " ", "l")
            totalTxt = pad(totalProducto, self.price_cols, " ", "r")

            printer.text(f'{cantTxt}{dsTxt}{totalTxt}\n')            
            
            importeSubTotal += total

        printer.text("\n")

        importeTotal = importeSubTotal

        if addAdditional:
            sAmount = float(addAdditional.get('amount', 0))
            descuentoDesc = addAdditional.get('description')[0:self.desc_cols_ext - 2]
            negative = addAdditional.get('negative', True)
            sAmount = -sAmount
            importeTotal += sAmount

            dsSubtotal = pad("SUBTOTAL:", self.desc_cols_ext - 1, " ", "l")
            importeSubTotal = pad(f"{round(importeSubTotal,2):,.2f}",self.price_cols, " ", "r")
            dsDescuento = pad(descuentoDesc, self.desc_cols_ext - 1, " ", "l")
            importeDescuento = pad(f"{round(sAmount, 2):,.2f}",self.price_cols, " ", "r")

            printer.set(LEFT, FONT_A, BOLD, 1, 1)
            printer.text(f'{dsSubtotal}{self.signo}{importeSubTotal}\n')
            printer.set(LEFT, FONT_A, NORMAL, 1, 1)
            printer.text(f'{dsDescuento}{self.signo}{importeDescuento}\n\n')

        # Imprimir total
        printer.set(LEFT, FONT_A, BOLD, 1, 2)
        dsTotal = pad("TOTAL:", self.desc_cols_ext - 1, " ", "l")
        importeTotal = pad(f"{round(importeTotal,2):,.2f}",self.price_cols, " ", "r")

        printer.text(f'{dsTotal}{self.signo}{importeTotal}\n\n')

        # Imprimir pagos "Simple"
        self._printPagoSimple(pagos)

        # Imprimir pagos "Detallado" (uncomment)
        #self._printPagoDetallado(pagos)

        printer.text("\n")

        self.__printExtras(kwargs)

        printer.set(CENTER, FONT_A, BOLD, 2, 2)
        
        if self.__preFillTrailer:
            self._setTrailer(self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(setTrailer)   


        printer.cut(PARTIAL_CUT)
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        printer.end()

        return True

    def _printPagoSimple(self, pagos):
        printer = self.conector.driver

        if len(pagos) > 0:
            printer.set(RIGHT, FONT_A, NORMAL, 1, 2)
        else:
            return False

        for pago in pagos:
            desc = pago.get('ds', "Pago")[0:20]
            importe = float(pago.get('importe'))

            dsTxt = pad(desc, self.desc_cols_ext - 1," ","l")
            importeTxt = pad(f"{importe:,.2f}",self.price_cols," ","r")
            
            printer.text(f"{dsTxt}{self.signo}{importeTxt}\n")
        
        return True

    def _printPagoDetallado(self, pagos):
        printer = self.conector.driver
        if len(pagos) > 0:
            printer.set(LEFT, FONT_A, BOLD, 1, 1)
            printer.text("Recibimos:\n")
        else: 
            return False

        vuelto = 0
        totalPagos = 0
        cantPagos = 0
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        for pago in pagos:
            importe = float(pago.get('importe'))
            if importe > 0:
                totalPagos += importe
                desc = str(pago.get('ds')[0:20]).upper()
                printer.text(f'{pad(desc, self.desc_cols_ext, " ", "l")}{pad(f"{importe:,.2f}",self.price_cols," ", "r")}\n')
                cantPagos += 1
            else:
                vuelto += importe
        if totalPagos > 0 and cantPagos > 1:
            printer.set(LEFT, FONT_A, BOLD, 1, 1)
            printer.text(f'{pad("La suma de sus pagos:", self.desc_cols_ext, " ", "l")}{pad(f"{totalPagos:,.2f}", self.price_cols, " ", "r")}\n')
        if vuelto < 0: 
            printer.set(LEFT, FONT_A, BOLD, 1, 1)
            printer.text(f'{pad("Su vuelto:", self.desc_cols_ext, " ", "l")}{pad(f"{abs(vuelto):,.2f}", self.price_cols, " ", "r")}\n')
        
        return True

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
        try:
            printer.start()
        except Exception as e:
            return False
        
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)

        if setHeader:
            for headerLine in setHeader:
                printer.text(headerLine)
                printer.text("\n\n")

        if "id" in comanda:
            if "nuevaComanda" in comanda:
                printer.text("Nueva Comanda\n")
            else:
                printer.text("- REIMPRESION -\n")
            printer.text(f"Comanda #{comanda['id']}\n")
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

            printer.text(f"{plato['cant']}) {plato['nombre']}")

            if 'sabores' in plato:
                printer.text(f"({', '.join(plato['sabores'])})")

            printer.text("\n")

            if 'observacion' in plato:
                printer.text(f"   OBS: {plato['observacion']}\n")

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

        return True
    
    def printArqueo(self, **kwargs):
        
        encabezado: dict = kwargs.get('encabezado', None)

        if encabezado is None:
            logger.error("No hay datos suficientes para imprimir")
            return False


        printer = self.conector.driver 
        
        try:
            printer.start()
        except Exception as e:
            return False

        
        totalIngresosPorVenta = 0
        ingresosEfectivo = 0
        otrosIngresos = 0

        totalEgresosPorPagos = 0
        egresosEfectivo = 0
        otrosEgresos = 0

        totalRetiros  = 0
        totalIngresos = 0

        fechaDesde = datetime.datetime.strptime(encabezado['fechaDesde'], '%d-%m-%Y %H:%M').strftime('%d/%m %H:%M',)
        fechaHasta = datetime.datetime.strptime(encabezado['fechaHasta'], '%d-%m-%Y %H:%M').strftime('%d/%m %H:%M',)
        fechaArqueo = datetime.datetime.strptime(encabezado['ArqueoDateTime'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%y %H:%M',)


        def imprimirEncabezado():            
            printer.set(CENTER, FONT_B, BOLD, 2, 2)
            printer.text("ARQUEO DE CAJA")
            printer.text("\n\n")
            printer.set(CENTER, FONT_A, NORMAL, 2, 1)
            printer.text(f"{encabezado.get('nombreComercio', '')}")
            printer.text("\n")
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
                    printer.text(pad("    Otros Cobros",(self.desc_cols_ext)," ", "l") 
                                + "$" + pad(f"{float(ingresosPorVentas['otros']):,.2f}", self.price_cols - 1," ","r") + "\n\n")
                    totalIngresosPorVenta += float(ingresosPorVentas['otros'])
                    otrosIngresos += float(ingresosPorVentas['otros'])

                printer.set(LEFT, FONT_A, BOLD, 1, 1)
                printer.text(pad("    TOTAL",self.desc_cols_ext, " ", "l")
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
                    printer.text(pad("    Otros Pagos",(self.desc_cols_ext)," ", "l") 
                                + "$" + pad(f"{float(egresosPorPagos['otros']):,.2f}", self.price_cols - 1," ","r") + "\n\n")                    
                    totalEgresosPorPagos += float(egresosPorPagos['otros'])
                    otrosEgresos += float(egresosPorPagos['otros'])

                printer.set(LEFT, FONT_A, BOLD, 1, 1)
                printer.text(pad("    TOTAL",self.desc_cols_ext, " ", "l")
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
                    printer.text(pad(fechaRetiro,self.desc_cols_ext, " ","l")
                                + "$" + pad(f"{retiro['monto']:,.2f}",self.price_cols - 1," ","r") + "\n")
                    totalRetiros += retiro['monto']
                    #TODO traer las observaciones del retiro
                    # if retiro['observacion']:
                    #     printer.set(CENTER, "A", "A", 1, 1)
                    #     printer.text(retiro['observacion'])        

                printer.text("\n")
                printer.set(LEFT, FONT_A, BOLD, 1, 1)
                printer.text(pad("    TOTAL",self.desc_cols_ext, " ", "l")
                            + "$" +  pad(f"{totalRetiros:,.2f}", self.price_cols - 1, " ","r") + "\n\n")

        ######### INGRESOS TRASPASOS

        if ('ingresos' in kwargs):
            ingresos = kwargs.get("ingresos", None)
            if(len(ingresos) > 0):            
                #Solo imprime cuando hay traspasos        

                imprimirTitulo(u"INGRESOS DE CAJA")

                printer.set(LEFT, FONT_A, NORMAL, 1, 1)

                for ingreso in ingresos:
                    fechaIngreso = datetime.datetime.strptime(ingreso['fechaTraspaso'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M',)
                    printer.text(pad(fechaIngreso,self.desc_cols_ext, " ","l")
                                + "$" + pad(f"{ingreso['monto']:,.2f}",self.price_cols - 1," ","r") + "\n")
                    totalIngresos += ingreso['monto']
                    #TODO traer observaciones de ingresos
                    # if ingreso['observacion']:
                    #     printer.set(CENTER, "A", "A", 1, 1)
                    #     printer.text(ingreso['observacion'])

                printer.text("\n")
                printer.set(LEFT, FONT_A, BOLD, 1, 1)
                printer.text(pad("    TOTAL",self.desc_cols_ext, " ", "l")
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
            printer.text(pad("+",self.cant_cols," ","l") + pad(key,self.desc_cols," ","l") + "$" 
                        + pad(ingresosDict[key],self.price_cols - 1 ," ","r") + "\n")
        
        printer.set(LEFT, FONT_A, BOLD, 1, 1)

        sumaIngresos = (ingresosEfectivo + totalIngresos + float(encabezado['importeInicial']))
        printer.text(" " * (self.desc_cols_ext) + "$" 
                    + pad(f"{sumaIngresos:,.2f}",self.price_cols - 1, " ","r") + "\n\n")
        
        printer.set(LEFT, FONT_A, NORMAL, 1, 1)

        egresosDict = {"Retiros de Caja:"   :   f"{totalRetiros:,.2f}",
                       "Egresos por Pagos"  :   f"{egresosEfectivo:,.2f}",
                       "Otros Egresos"      :   f"{otrosEgresos:,.2f}",
                       "Importe Final:"     :   f"{importeFinal:,.2f}"}

        for key in egresosDict:
            printer.text(pad("-",self.cant_cols," ","l") + pad(key,self.desc_cols," ","l") + "$" 
                        + pad(egresosDict[key],self.price_cols - 1 ," ","r") + "\n")

        printer.set(LEFT, FONT_A, BOLD, 1, 1) 

        sumaEgresos = (egresosEfectivo + totalRetiros + importeFinal)
        printer.text(" " * (self.desc_cols_ext) + "$" 
                    + pad(f"{sumaEgresos:,.2f}",self.price_cols - 1, " ","r") + "\n\n")
        
        printer.set(LEFT, FONT_A, BOLD, 1, 2, invert=True)

        montoSaldo = float(encabezado['diferencia'])
        if (montoSaldo < 0):
            saldo = "SOBRANTE"
        elif (montoSaldo > 0):
            saldo = "FALTANTE"
        else:
            saldo = ""

        printer.text(pad(f"    Saldo {saldo}", self.desc_cols_ext , " ", "l") 
                    + "$" + pad(f"{abs(montoSaldo):,.2f}",self.price_cols - 1, " ", "r"))

        ##########   FIRMA

        printer.text("\n" * 7)
        printer.set(CENTER, FONT_A, NORMAL, 1, 1)
        printer.text("_" * self.desc_cols + "\n")
        printer.text("Firma Responsable")
        printer.text("\n\n")
        printer.set(CENTER, FONT_B, NORMAL, 1, 1)
        printer.text("Reporte de Cierre de Caja\n")
        printer.text(datetime.datetime.strftime(datetime.datetime.now(), '%d/%m/%y %H:%M'))


        printer.set(LEFT, FONT_A, NORMAL, 1, 1)
        printer.cut(PARTIAL_CUT)
        printer.end()

        return True
