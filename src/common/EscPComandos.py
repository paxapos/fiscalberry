# -*- coding: utf-8 -*-
import datetime
from math import ceil
import json
import base64
from common.fiscalberry_logger import getLogger
from escpos.escpos import EscposIO
from escpos.constants import QR_ECLEVEL_H,CD_KICK_2

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


class EscPComandos():

    __preFillTrailer = None
    
    printer = None

    def __init__(self, printer):
        self.printer = printer
        
        # Obtener el número de columnas desde el perfil
        if printer.profile:
            print("--  - -- - - - - - - -")
            print(printer.profile.profile_data)
            line_width = printer.profile.profile_data['columns']
            print(f"Número de caracteres por línea: {line_width}")
        else:
            print("El perfil no tiene definida la cantidad de columnas por línea.")
            
            
        self.total_cols = 40
        self.price_cols = 12 #12 espacios permiten hasta 9,999,999.99
        self.cant_cols = 6   #4 no admitiría decimales, 6 sería mejor
        self.desc_cols =  self.total_cols - self.cant_cols - self.price_cols
        self.desc_cols_ext = self.total_cols - self.price_cols
        self.signo = "$" # Agregar el signo $ opcionalmente o espacio.

    def run(self, jsonTicket):
        with EscposIO(self.printer, autocut=True,autoclose=True) as escpos:
            actions = jsonTicket.keys()
            rta = []
            for action in actions:
                fnAction = getattr(self, action)

                if isinstance(jsonTicket[action], list):
                    res = fnAction(escpos, *jsonTicket[action])
                    rta.append({"action": action, "rta": res})

                elif isinstance(jsonTicket[action], dict):
                    res = fnAction(escpos, **jsonTicket[action])
                    rta.append({"action": action, "rta": res})
                else:
                    res = fnAction(escpos)
                    rta.append({"action": action, "rta": res})

            return rta


    def _sendCommand(self, comando, skipStatusErrors=False):
        try:
            ret = self.printer.sendCommand(comando, skipStatusErrors)
            return ret
        except PrinterException as e:
            logger.error("Error de la impresora: %s.\nComando enviado: %s" % (str(e),comando))

    def getStatus(self):
        printer = self.printer
        printer.start()
        rta = printer.connected
        printer.end()
        if rta:
            if hasattr(printer , "host"):
                return f"Conectada en {printer.host}"
        else:
            return False

    def printTexto(self, printer, texto):
        printer.text(texto)


    def openDrawer(self, escpos: EscposIO, **kwargs):
        escpos.printer.cashdraw(CD_KICK_2)


    def printPedido(self, escpos: EscposIO, **kwargs):
        "imprimir pedido de compras"
        
        printer = escpos.printer
        self.__initPrinter(printer)

        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])

        if encabezado is None or len(items) == 0:
            logger.error("No hay datos suficientes para imprimir")
            return False

        printer.set(font='a', height=1, align='center', normal_textsize=True)

        if "es_pedido" in encabezado:
            printer.text(u"Nuevo Pedido \n")
        else:
            printer.text(u"Nueva OC \n")
        printer.set(font='a', height=1, align='left', normal_textsize=True)
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
            printer.set(font='a', height=1, align='left', normal_textsize=True)
            desc = item.get('ds')[0:24]
            cant = float(item.get('qty'))
            unidad_de_medida = item.get('unidad_de_medida')
            observacion = item.get('observacion')
            cant_tabs = 3
            can_tabs_final = cant_tabs - ceil(len(desc) / 8)
            strTabs = desc.ljust(int(len(desc) + can_tabs_final), '\t')

            printer.text(u"%.2f%s%s\t%s\n" % (cant," ",unidad_de_medida, strTabs))

            if observacion:
                printer.set(font='b', bold=True, align='left', normal_textsize=True)
                printer.text(u"OBS: %s\n" % observacion)

        printer.text("\n")

        barcode = kwargs.get("barcode", None)
        if barcode:            
            printer.barcode(str(barcode).rjust(8, "0"), 'EAN13')

        printer.set(font='a', height=2, width=2, align='center', bold=True)

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D) + chr(0xF9) + chr(0x35) + "0")

        # dejar letra chica alineada izquierda
        printer.set(font='a', height=1, align='left', normal_textsize=True)

        return True

    def __printExtras(self, escpos: EscposIO, kwargs):
        "Imprimir QRs y Barcodes"
        
        printer = escpos.printer
        printer.set(font='a', height=1, align='center')

        barcode = kwargs.get("barcode", None)
        if barcode:
            printer.barcode(str(barcode).rjust(8, "0"), 'EAN13')

        qrcode = kwargs.get("qr", None)
        if qrcode:
            printer.qr(qrcode, size=5)
            printer.ln()

        qrcodeml = kwargs.get("qr-mercadopago", None)
        if qrcodeml:
            
            escpos.writelines(u'ABONE SU CUENTA')
            escpos.writelines(u'ESCANEANDO EL QR')
            escpos.writelines(u'\\______/ ')
            escpos.writelines(u' \\    /  ')
            escpos.writelines(u'  \\  /   ')
            escpos.writelines(u'   \\/    ')
            printer.qr(qrcodeml, size=5)
            printer.ln()
    
    def printFacturaElectronica(self, escpos: EscposIO, **kwargs):
        "Imprimir Factura Electronica"
        
        printer = escpos.printer
        
        self.__initPrinter(printer)

        # Secciones de la Factura
        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        ivas = kwargs.get("ivas", [])
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
        

        # 1- DATOS DEL COMERCIO
        nombreComercio = encabezado.get('nombre_comercio')
        razonSocial = encabezado.get('razon_social')
        cuitComercio = encabezado.get('cuit_empresa')
        ingresosBrutos = encabezado.get('ingresos_brutos')
        domicilioComercial = encabezado.get('domicilio_comercial')
        inicioActividades = encabezado.get('inicio_actividades')
        tipoResponsabilidad = encabezado.get('tipo_responsable')

        printer.set(font='a', height=1, bold=True, align='center')
        printer.text(f"{ nombreComercio }\n\n")

        printer.set(font='a', height=1, align='left', normal_textsize=True)
        printer.text(f"{ razonSocial }\n")
        printer.text(f"CUIT: { cuitComercio }\n")        

        if ingresosBrutos:
            printer.text(f"Ingresos Brutos: {ingresosBrutos}\n")
        printer.text(f"{ domicilioComercial }\n")
        printer.text(f"Inicio de actividades: {inicioActividades}\n")
        printer.text(f"{ tipoResponsabilidad }\n")        

        printer.set(font='a', height=1, align='center')
        printer.text("-" * self.total_cols + "\n")

        # 2- IDENTIFICACIÓN DEL COMPROBANTE
        tipoComprobante = encabezado.get('tipo_comprobante')
        tipoCmp = encabezado.get('tipo_comprobante_codigo')
        nroComprobante = encabezado.get('numero_comprobante')
        fechaComprobante = encabezado.get('fecha_comprobante')
        cae = encabezado.get("cae")
        caeVto = encabezado.get("cae_vto")

        printer.set(font='a', height=1, bold=True, align='center')
        printer.text(f"{ tipoComprobante } Nro. { nroComprobante }\n")
        printer.text(f"Fecha { fechaComprobante }\n")
        printer.set(font='a', height=1, align='center')
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
            
            printer.set(font='b', bold=True, align='left', normal_textsize=True)
            printer.text(f"{cantHeader}\n")
            printer.set(font='a', height=1, align='left', normal_textsize=True)
            printer.text(f"{dsHeader}{precioHeader}\n")
            printer.text("-" * self.total_cols + "\n")
        else:
            cantHeader = pad( "CANT", self.cant_cols, " ", "l")
            dsCentrador = (" " * (self.price_cols - self.cant_cols))
            dsHeader = (dsCentrador + "DESCRIPCIÓN").center(self.desc_cols, " ")
            precioHeader = pad( "PRECIO", self.price_cols, " ", "r")

            
            printer.set(font='a', bold=True, height=1, width=1, align='left')
            printer.text( f"{cantHeader}{dsHeader}{precioHeader}\n" )
            printer.text("\n")
            
        printer.set(font='a', height=1, align='left', normal_textsize=True)

        # 4.2- TABLA ITEMS
        for item in items:

            if item.get('alic_iva'):
                alicIva = float(item.get('alic_iva'))
            else:
                alicIva = 21.00

            qty = float(item.get('qty'))
            importe = float(item.get('importe'))
            ds = item.get('ds')[0:self.desc_cols-2]
           
            itemCant = floatToString( qty )
            importeUnitario = floatToString( importe )
            totalProducto = f"{round( qty * importe , 2 ):,.2f}"

            if tipoComprobante in tiposInscriptoString or tipoCmp in tiposInscriptoCod:
                printer.set(font='b', bold=True, align='left', normal_textsize=True)
                printer.text(f"{itemCant} x {importeUnitario} ({floatToString(alicIva)})\n")
                printer.set(font='a', height=1, align='left', normal_textsize=True)
                printer.text(f'{pad(ds, self.desc_cols_ext, " ", "l")}{pad( totalProducto, self.price_cols , " ", "r")}\n' )
            else:
                printer.set(font='a', height=1, align='left', normal_textsize=True)
                cantTxt = pad(itemCant, self.cant_cols, " ", "l")
                dsTxt = pad(ds, self.desc_cols, " ", "l")
                totalTxt = pad(totalProducto, self.price_cols, " ", "r")
                printer.text(f'{cantTxt}{dsTxt}{totalTxt}\n')

        printer.text("-" * self.total_cols + "\n")

        totalNeto = float( encabezado.get("importe_neto") )
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

            printer.set(font='a', bold=True, height=1, width=1, align='left')
            printer.text(f'{dsSubtotal}{self.signo}{importeSubtotal}\n')
            printer.set(font='a', height=1, align='left', normal_textsize=True)
            printer.text(f'{dsDescuento}{self.signo}{importeDescuento}\n\n')

        # 6- DETALLE IVAS (INSCRIPTO)
        # si tiene el array de ivas tiene items, se detallan los IVAs
        if ivas:
            dsSinIva = pad("Total sin IVA:", self.desc_cols_ext - 1, " ", "l")
            importeSinIva = pad(f"{round(totalNeto, 2):,.2f}",self.price_cols, " ", "r")
            printer.set(font='a', height=1, align='left', normal_textsize=True)
    
            printer.text(f'{dsSinIva}{self.signo}{importeSinIva}\n')

            for iva in ivas:
                dsIva = pad(f"IVA {iva["alic_iva"]}:", self.desc_cols_ext - 1, " ", "l")
                importeIva = pad(f"{round(iva["importe"], 2):,.2f}",self.price_cols, " ", "r")
                printer.set(font='a', height=1, align='left', normal_textsize=True)

                printer.text(f'{dsIva}{self.signo}{importeIva}\n')

        # 7- TOTAL
        printer.set(font='a', bold=True, align='left', double_height=False, double_width=False)
        # Imprime "TOTAL" alineado a la izquierda
        printer.set(align='left')
        printer.text("TOTAL:")

        # Imprime el monto alineado a la derecha en la misma línea
        printer.set(align='right')
        importeTotal =  pad(f"{round(total,2):,.2f}",self.price_cols, " ", "r")
        printer.text(f'{self.signo}{importeTotal}\n\n')


        # NC si hay que firmar        
        printer.set(font='b', bold=False, width=1, height=1, align='left', normal_textsize=True)

        if tipoComprobante in tiposNC or tipoCmp in tiposNC:
            printer.text(u"Firma.......................................\n\n")
            printer.text(u"Aclaración..................................\n")
        else:
            self._printPagoDetallado(escpos, pagos)

        printer.set(font='a', height=1, align='left', normal_textsize=True)
        printer.text("-" * self.total_cols + "\n\n")

        printer.set(font='a', height=1, align='center')
        
        if self.__preFillTrailer:
            self._setTrailer(escpos, self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(escpos, setTrailer)

        # 8- AFIP
        # 8.1- Json Datos AFIP
        felist = fechaComprobante.split("/") if "/" in fechaComprobante else fechaComprobante.split("-")
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

        printer.set(font='a', height=1, align='center')
        printer.text("Comprobante Autorizado por AFIP")
        printer.text("\n")

        # 8.2- QR nueva disposicion de la AFIP
        jsonqr = json.dumps(qrcode)
        qrcode = base64.encodebytes( jsonqr.encode() )
        
        if qrcode:
            data = "https://www.afip.gob.ar/fe/qr/?p=" + qrcode.decode().replace("\n", "")
            printer.qr(data, QR_ECLEVEL_H, size=3)

        printer.set(font='a', height=1, align='center')
        caeTxt = f"CAE: {cae}"
        caeVtoTxt = f"CAE VTO: {caeVto}"
        printer.text("\n")
        printer.text(f"{caeTxt}    {caeVtoTxt}")
        printer.text("\n")

        printer.set(font='a', height=1, bold=True, align='center')
        printer.text("Software PAXAPOS")

        return True

    

    def printRemito(self, escpos: EscposIO, **kwargs):
        "Imprimir remito"
        
        
        printer = escpos.printer
        self.__initPrinter(printer)
        
        logger.info("Imprimiendo Remito en printer %s" % printer)
        
        encabezado = kwargs.get("encabezado", None)
        items = kwargs.get("items", [])
        pagos = kwargs.get("pagos", [])
        addAdditional = kwargs.get("addAdditional", None)
        setTrailer = kwargs.get("setTrailer", None)

        if encabezado is None or len(items) == 0:
            logger.error("No hay datos suficientes para imprimir")
            return False

        printer.set(font='a', height=1, align='center')

        if encabezado and "imprimir_fecha_remito" in encabezado:
            fecha = datetime.datetime.strftime(datetime.datetime.now(), "%d/%m/%Y %H:%M")
            escpos.writelines(f"Fecha: {fecha}")
            printer.ln(2)

        escpos.writelines("Verifique su cuenta por favor")
        escpos.writelines("NO VÁLIDO COMO FACTURA")
        printer.ln()

        if encabezado:
            printer.set(font='b', height=1, align='center', normal_textsize=True)

            if "nombre_cliente" in encabezado:
                escpos.writelines(f'{encabezado.get("nombre_cliente")}')
                if "telefono" in encabezado:
                    escpos.writelines(f'{encabezado.get("telefono")}')
                if "domicilio_cliente" in encabezado:
                    escpos.writelines(f'{encabezado.get("domicilio_cliente")}')
                printer.ln()

        printer.set(font='a', height=1, align='left', bold=False, normal_textsize=True)

        cantHeader = pad( "CANT", self.cant_cols, " ", "l")
        dsCentrador = (" " * (self.price_cols - self.cant_cols))
        dsHeader = (dsCentrador + "DESCRIPCIÓN").center(self.desc_cols, " ")
        precioHeader = pad( "PRECIO", self.price_cols, " ", "r")
        
        escpos.writelines( f"{cantHeader}{dsHeader}{precioHeader}")
        printer.ln()


        importeSubTotal = 0.0

        for item in items:
            qty = float(item.get('qty', 1))
            importe = float(item.get('importe'))
            ds = item.get('ds')[0:self.desc_cols-2]
            total = importe * qty

            itemCant = floatToString( qty )
            totalProducto = f"{round( qty * importe , 2 ):,.2f}"

            cantTxt = pad(itemCant, self.cant_cols, " ", "l")
            dsTxt = pad(ds, self.desc_cols, " ", "l")
            totalTxt = pad(totalProducto, self.price_cols, " ", "r")

            escpos.writelines(f'{cantTxt}{dsTxt}{totalTxt}')            
            
            importeSubTotal += total

        printer.ln()

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

            escpos.writelines(f'{dsSubtotal}{self.signo}{importeSubTotal}')
            escpos.writelines(f'{dsDescuento}{self.signo}{importeDescuento}' )
            printer.ln()

        # Imprimir total
        dsTotal = pad("TOTAL:", self.desc_cols_ext - 1, " ", "l")
        importeTotal = pad(f"{round(importeTotal,2):,.2f}",self.price_cols, " ", "r")

        escpos.writelines(f'{dsTotal}{self.signo}{importeTotal}', bold=True, align='left', height=2, width=2)
        printer.ln();

        # Imprimir pagos "Simple"
        self._printPagoSimple(escpos, pagos)

        # Imprimir pagos "Detallado" (uncomment)
        #self._printPagoDetallado(pagos)

        printer.ln()

        self.__printExtras(escpos, kwargs)

        printer.set(double_height=True, double_width=True, align='center', bold=True)
        if self.__preFillTrailer:
            self._setTrailer(escpos, self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(escpos, setTrailer)   
        
        printer.set(font='a', height=1, align='center', normal_textsize=True)

        return True

    def _printPagoSimple(self, escpos: EscposIO, pagos):
        printer = escpos.printer
        if len(pagos) > 0:
            printer.set(font='a', height=2, align='right', normal_textsize=True)
        else:
            return False

        for pago in pagos:
            desc = pago.get('ds', "Pago")[0:20]
            importe = float(pago.get('importe'))

            dsTxt = pad(desc, self.desc_cols_ext - 1," ","l")
            importeTxt = pad(f"{importe:,.2f}",self.price_cols," ","r")
            
            escpos.writelines(f"{dsTxt}{self.signo}{importeTxt}")
        
        return True

    def _printPagoDetallado(self, escpos: EscposIO, pagos):
        printer = escpos.printer
        if len(pagos) > 0:
            escpos.writelines("Recibimos:", bold=True)
        else: 
            return False

        vuelto = 0
        totalPagos = 0
        cantPagos = 0
        printer.set(font='a', height=1, align='left', normal_textsize=True)
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
            printer.set(font='a', bold=True, height=1, width=1, align='left')
            printer.text(f'{pad("La suma de sus pagos:", self.desc_cols_ext, " ", "l")}{pad(f"{totalPagos:,.2f}", self.price_cols, " ", "r")}\n')
        if vuelto < 0: 
            printer.set(font='a', bold=True, height=1, width=1, align='left')
            printer.text(f'{pad("Su vuelto:", self.desc_cols_ext, " ", "l")}{pad(f"{abs(vuelto):,.2f}", self.price_cols, " ", "r")}\n')
        
        return True

    def setTrailer(self, setTrailer):
        self.__preFillTrailer = setTrailer

    def _setTrailer(self, escpos: EscposIO, setTrailer):
        #print(self.printer)
        printer = escpos.printer
        for trailerLine in setTrailer:
            if trailerLine:
                escpos.writelines(trailerLine, align='center', bold=True)

            printer.ln()

    def printComanda(self, escpos: EscposIO, comanda, setHeader=None, setTrailer=None):
        """id,observacion, entradas{observacion, cant, nombre, sabores}, platos{observacion, cant, nombre, sabores}"""

        printer = escpos.printer
            
        self.__initPrinter(printer)

        printer.set(font='a', height=1, align='center', normal_textsize=True)

        if setHeader:
            for headerLine in setHeader:
                printer.text(headerLine)
                printer.text("\n\n")

        if "id" in comanda:
            printer.text(f"Comanda #{comanda['id']}\n")

        if "created" in comanda:
            fecha = datetime.datetime.strptime(comanda['created'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M',)
        else:
            fecha = datetime.datetime.strftime(datetime.datetime.now(), '%H:%M')
            
        printer.text(fecha + "\n\n")

        def print_plato(plato):
            "Imprimir platos"
            printer.set(font='a', bold=True, height=1, width=2, align='left')

            printer.text(f"{plato['cant']}) {plato['nombre']}")

            if 'sabores' in plato:
                printer.text(f"({', '.join(plato['sabores'])})")

            printer.text("\n")

            if 'observacion' in plato:
                printer.text(f"   OBS: {plato['observacion']}\n")

        if 'observacion' in comanda:
            printer.set(font='a', height=1, bold=True, align='center')
            printer.text(u"OBSERVACIÓN\n")
            printer.text(comanda['observacion'])
            printer.text("\n\n")

        if 'entradas' in comanda:
            printer.set(font='a', height=1, bold=True, align='center')
            printer.text(u"** ENTRADA **\n")
            for entrada in comanda['entradas']:
                print_plato(entrada)
            printer.text("\n\n")

        if 'platos' in comanda:
            printer.set(font='a', height=1, bold=True, align='center')
            printer.text(u"----- PRINCIPAL -----\n")
            for plato in comanda['platos']:
                print_plato(plato)
            printer.text("\n\n")

        printer.set(font='a', height=2, width=2, align='center', bold=True)
        if self.__preFillTrailer:
            self._setTrailer(escpos, self.__preFillTrailer)

        if setTrailer:
            self._setTrailer(escpos, setTrailer)   

        # volver a poner en modo ESC Bematech, temporal para testing
        # printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")

        # dejar letra chica alineada izquierda
        printer.buzzer(1, 1)
        return True
    
    def __initPrinter(self, printer):
        # set all the params printer.set(align='left', font='a', bold=False, underline=?, width=?, height=?, density=?, invert=False, smooth=?, flip=?, normal_textsize=?, double_width=?, double_height=?, custom_size=?)
        
        printer.set(align='left', font='a', bold=False, underline=False, width=1, height=1, density=9, invert=False, smooth=False, flip=False, normal_textsize=True, double_width=False, double_height=False, custom_size=False)
    
    def printArqueo(self, escpos: EscposIO, **kwargs):
        printer = escpos.printer
        
        self.__initPrinter(printer)

        encabezado: dict = kwargs.get('encabezado', None)

        if encabezado is None:
            logger.error("No hay datos suficientes para imprimir")
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
            printer.set(font='a', height=1, bold=True, align='center')
            printer.text("ARQUEO DE CAJA")
            printer.text("\n\n")
            printer.set(font='a', height=1, bold=True, align='center')
            printer.text(f"{encabezado.get('nombreComercio', '')}")
            printer.text("\n")
            printer.set(font='a', height=1, align='center', normal_textsize=True)
            printer.text("-" * self.total_cols + "\n")
            printer.set(font='a', height=1, align='left', normal_textsize=True)
            printer.text(f"'Fecha de Cierre': {fechaArqueo}\n")
            printer.text(f"'Fecha de Turno': {fechaDesde} al {fechaHasta}\n")
            printer.text(f"'Reporte de Caja': {encabezado['nombreCaja']}\n")
            printer.text(f"'Usuario': {encabezado['aliasUsuario']}\n")
            printer.text(f"'Observación': {encabezado['observacion']}\n\n")

        def imprimirTitulo(titulo, ancho=1, alto=1):
            printer.set(font='a', height=1, bold=True, align='center')
            printer.text("-" * self.total_cols + "\n")
            printer.set(font='a', height=1, bold=True, align='center')
            printer.text(f"{titulo}\n")
            printer.set(font='a', height=1, bold=True, align='center')
            printer.text("-" * self.total_cols + "\n")

        #########   ENCABEZADO
        
        imprimirEncabezado()

        ######### INGRESOS POR VENTA

        if 'ingresosPorVentas' in kwargs:
            ingresosPorVentas = kwargs.get("ingresosPorVentas", [])
            if (len(ingresosPorVentas['detalle']) > 0) or ingresosPorVentas['otros']:
                imprimirTitulo(u"INGRESOS POR COBROS")

                printer.set(font='a', height=1, align='left', normal_textsize=True)
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

                printer.set(font='a', bold=True, height=1, width=1, align='left')
                printer.text(pad("    TOTAL",self.desc_cols_ext, " ", "l")
                            + "$" +  pad(f"{totalIngresosPorVenta:,.2f}", self.price_cols - 1, " ","r") + "\n\n")

        ######### EGRESOS POR PAGOS

        if 'egresosPorPagos' in kwargs:
            egresosPorPagos = kwargs.get("egresosPorPagos", []) 
            if (len(egresosPorPagos['detalle']) > 0) or egresosPorPagos['otros']:
                imprimirTitulo(u"EGRESOS POR PAGOS")

                printer.set(font='a', height=1, align='left', normal_textsize=True)
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

                printer.set(font='a', bold=True, height=1, width=1, align='left')
                printer.text(pad("    TOTAL",self.desc_cols_ext, " ", "l")
                            + "$" +  pad(f"{totalEgresosPorPagos:,.2f}", self.price_cols - 1, " ","r") + "\n\n")



        ######### RETIROS TRASPASOS

        if ('retiros' in kwargs):
            retiros = kwargs.get("retiros", [])            
            if (len(retiros) > 0):
                #Solo imprime cuando llega retiros en el JSON

                imprimirTitulo(u"RETIROS DE CAJA")

                printer.set(font='a', height=1, align='left', normal_textsize=True)

                for retiro in retiros:
                    fechaRetiro = datetime.datetime.strptime(retiro['fechaTraspaso'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M',)
                    printer.text(pad(fechaRetiro,self.desc_cols_ext, " ","l")
                                + "$" + pad(f"{retiro['monto']:,.2f}",self.price_cols - 1," ","r") + "\n")
                    totalRetiros += retiro['monto']
                    #TODO traer las observaciones del retiro
                    # if retiro['observacion']:
                    #     printer.set(font='a', height=1, bold=True, align='center'), "A", "A", 1, 1)
                    #     printer.text(retiro['observacion'])        

                printer.text("\n")
                printer.set(font='a', bold=True, height=1, width=1, align='left')
                printer.text(pad("    TOTAL",self.desc_cols_ext, " ", "l")
                            + "$" +  pad(f"{totalRetiros:,.2f}", self.price_cols - 1, " ","r") + "\n\n")

        ######### INGRESOS TRASPASOS

        if ('ingresos' in kwargs):
            ingresos = kwargs.get("ingresos", None)
            if(len(ingresos) > 0):            
                #Solo imprime cuando hay traspasos        

                imprimirTitulo(u"INGRESOS DE CAJA")

                printer.set(font='a', height=1, align='left', normal_textsize=True)

                for ingreso in ingresos:
                    fechaIngreso = datetime.datetime.strptime(ingreso['fechaTraspaso'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M',)
                    printer.text(pad(fechaIngreso,self.desc_cols_ext, " ","l")
                                + "$" + pad(f"{ingreso['monto']:,.2f}",self.price_cols - 1," ","r") + "\n")
                    totalIngresos += ingreso['monto']
                    #TODO traer observaciones de ingresos
                    # if ingreso['observacion']:
                    #     printer.set(font='a', height=1, bold=True, align='center'), "A", "A", 1, 1)
                    #     printer.text(ingreso['observacion'])

                printer.text("\n")
                printer.set(font='a', bold=True, height=1, width=1, align='left')
                printer.text(pad("    TOTAL",self.desc_cols_ext, " ", "l")
                            + "$" +  pad(f"{totalIngresos:,.2f}", self.price_cols - 1, " ","r") + "\n\n")
        
        ######### RESULTADO
        if encabezado['importeFinal']:
            importeFinal = float(encabezado['importeFinal'])
        else:
            importeFinal = 0

        imprimirTitulo(u"RESÚMEN (Efectivo)", 1, 2)

        printer.set(font='a', height=1, align='left', normal_textsize=True)

        ingresosDict = {"Importe Inicial:"    : f"{float(encabezado['importeInicial']):,.2f}",
                        "Ingresos por Cobros:": f"{ingresosEfectivo:,.2f}",
                        "Ingresos de Caja:"   : f"{totalIngresos:,.2f}",
                        "Otros Ingresos:"     : f"{otrosIngresos:,.2f}"}

        for key in ingresosDict:
            printer.text(pad("+",self.cant_cols," ","l") + pad(key,self.desc_cols," ","l") + "$" 
                        + pad(ingresosDict[key],self.price_cols - 1 ," ","r") + "\n")
        
        printer.set(font='a', bold=True, height=1, width=1, align='left')

        sumaIngresos = (ingresosEfectivo + totalIngresos + float(encabezado['importeInicial']))
        printer.text(" " * (self.desc_cols_ext) + "$" 
                    + pad(f"{sumaIngresos:,.2f}",self.price_cols - 1, " ","r") + "\n\n")
        
        printer.set(font='a', height=1, align='left', normal_textsize=True)

        egresosDict = {"Retiros de Caja:"   :   f"{totalRetiros:,.2f}",
                       "Egresos por Pagos"  :   f"{egresosEfectivo:,.2f}",
                       "Otros Egresos"      :   f"{otrosEgresos:,.2f}",
                       "Importe Final:"     :   f"{importeFinal:,.2f}"}

        for key in egresosDict:
            printer.text(pad("-",self.cant_cols," ","l") + pad(key,self.desc_cols," ","l") + "$" 
                        + pad(egresosDict[key],self.price_cols - 1 ," ","r") + "\n")

        printer.set(font='a', bold=True, height=1, width=1, align='left') 

        sumaEgresos = (egresosEfectivo + totalRetiros + importeFinal)
        printer.text(" " * (self.desc_cols_ext) + "$" 
                    + pad(f"{sumaEgresos:,.2f}",self.price_cols - 1, " ","r") + "\n\n")
        
        printer.set(font='a', bold=True, width=2, height=1, align='left', normal_textsize=True, invert=True)

        montoSaldo = float(encabezado['diferencia'])
        if (montoSaldo < 0):
            saldo = "SOBRANTE"
        elif (montoSaldo > 0):
            saldo = "FALTANTE"
        else:
            saldo = ""
            
        printer.set(invert=False)

        printer.text(pad(f"    Saldo {saldo}", self.desc_cols_ext , " ", "l") 
                    + "$" + pad(f"{abs(montoSaldo):,.2f}",self.price_cols - 1, " ", "r"))

        ##########   FIRMA

        printer.text("\n" * 7)
        printer.set(font='a', height=1, align='center', normal_textsize=True)
        printer.text("_" * self.desc_cols + "\n")
        printer.text("Firma Responsable")
        printer.text("\n\n")
        printer.set(font='a', height=1, bold=True, align='center')
        printer.text("Reporte de Cierre de Caja\n")
        printer.text(datetime.datetime.strftime(datetime.datetime.now(), '%d/%m/%y %H:%M'))


        printer.set(font='a', height=1, align='left', normal_textsize=True)

        return True
