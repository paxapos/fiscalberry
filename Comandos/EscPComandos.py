# -*- coding: latin-1 -*-

import string
import types
import logging
import unicodedata
from ComandoInterface import ComandoInterface, ComandoException, ValidationError, FiscalPrinterError, formatText
from ConectorDriverComando import ConectorDriverComando
import time



class PrinterException(Exception):
    pass

class EscPComandos(ComandoInterface):


	tipoCbte = {
	        "T": "B",
	        "FA":  "A", 
	        "FB": "B", 
	        "NDA": "NDA", 
	        "NCA": "NCA", 
	        "NDB": "NDB", 
	        "NCB": "NCB", 
	        "FC": "C", 
	        "NDC": "NCC",
	        "NDC": "NDC"

	}

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
		"CUIT": 'CUIT',
		"LIBRETA_ENROLAMIENTO": 'LE',
		"LIBRETA_CIVICA": 'LC',
		"DNI": 'DNI',
		"PASAPORTE": 'PASAPORTE',
		"CEDULA": 'CEDULA',
		"SIN_CALIFICADOR": '',
	}

	ivaTypes = {
		"RESPONSABLE_INSCRIPTO": 'Resp. Inscripto',
		"RESPONSABLE_NO_INSCRIPTO": 'N',
		"EXENTO": 'Exento',
		"NO_RESPONSABLE": 'No Responsable',
		"CONSUMIDOR_FINAL": 'Consumidor Final',
		"RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO": 'B',
		"RESPONSABLE_MONOTRIBUTO": 'Monotributo',
		"MONOTRIBUTISTA_SOCIAL": 'Monotributo Social',
		"PEQUENIO_CONTRIBUYENTE_EVENTUAL": 'Peq. Contrib. Eventual',
		"PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL": 'Peq. Contrib. Social',
		"NO_CATEGORIZADO": '',
	}
	

	def __init__(self, deviceFile=None, driverName="ReceipDirectJet"):
		"deviceFile indica la IP o puerto donde se encuentra la impresora"
		self.conector = ConectorDriverComando(self, driverName, deviceFile)

	
	def _sendCommand(self, comando, skipStatusErrors=False):
		try:
			ret = self.conector.sendCommand(comando, skipStatusErrors)
			return ret
		except PrinterException, e:
			logging.getLogger().error("PrinterException: %s" % str(e))
			raise ComandoException("Error de la impresora: %s.\nComando enviado: %s" % \
				(str(e), commandString))

	
	def print_mesa_mozo(self, mesa, mozo):
		self.doble_alto_x_linea("Mesa: %s"%mesa);
		self.doble_alto_x_linea("Mozo: %s"%mozo);



	def printRemito(self, **kwargs):		
		"imprimir remito"
		encabezado = kwargs.get("encabezado", None)
		items = kwargs.get("items", [])
		addAdditional = kwargs.get("addAdditional", None)
		setTrailer = kwargs.get("setTrailer", None)

		printer = self.conector.driver

		printer.set("LEFT", "A", "A", 1, 1)
		
		# colocar en modo ESC P
		printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"1")

		if encabezado:
			if "tipo_cbte" in encabezado:
				printer.text( "%s\n"% self.tipoCbte[encabezado['tipo_cbte']] )

			if "fecha" in encabezado:
				fff_aux = time.strptime( encabezado['fecha'], "%Y-%m-%d %H:%M:%S")
				fecha = time.strftime('%H:%M %x', fff_aux)
				printer.text( fecha +"\n")

		printer.text("CANT   DESCRIPCION              PRECIO")
		printer.text("--------------------------------------")
		tot_chars = 40
		tot_importe = 0.0
		for item in items:
			desc = item['ds']
			cant = item['qty']
			precio = item['importe']
			tot_importe += float(precio)
			printer.text("%s  %s %s\n" % (desc, cant, precio))
		printer.text("--------------------------------------")

		if addAdditional:
			printer.text("                      SUBTOTAL:  %s\n" % tot_importe)
			sAmount = float( addAdditional.get('amount',0) )
			tot_importe = tot_importe - sAmount
			printer.text("%s %s\n" % (addAdditional.get('description'), addAdditional.get('amount') ))

		printer.text("                         TOTAL:  %s\n" % tot_importe)
		printer.text("\n\n\n")

		#plato principal
		if setTrailer:
			self._setTrailer(setTrailer)


		printer.cut("PART")

		# volver a poner en modo ESC Bematech, temporal para testing
		printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")


	def _setTrailer(self, setTrailer):
		print self.conector.driver		
		printer = self.conector.driver

		printer.set("LEFT", "A", "A", 1, 1)

		for trailerLine in setTrailer:
			if trailerLine:
				printer.text( trailerLine )
			else:
				printer.text( " " )
		

	def printComanda(self, comanda, setHeader=None, setTrailer=None):
		"observacion, entradas{observacion, cant, nombre, sabores}, platos{observacion, cant, nombre, sabores}"
		print self.conector.driver		
		printer = self.conector.driver

		# 0x1D 0xF9 0x35 1
		# colocar en modo ESC P
		printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"1")

		if setHeader:
			for headerLine in setHeader:
				printer.text( headerLine )	

		printer.set("CENTER", "A", "A", 1, 1)
		printer.text("Comanda #%s\n" % comanda['id'])

		fff_aux = time.strptime( comanda['created'], "%Y-%m-%d %H:%M:%S")
		fecha = time.strftime('%H:%M %x', fff_aux)

		#fecha = datetime.strftime(comanda['created'], '%Y-%m-%d %H:%M:%S')
		printer.text( fecha +"\n")


		def print_plato(plato):
			"Imprimir platos"
			printer.set("LEFT", "A", "B", 1, 2)

			printer.text( "%s) %s"%( plato['cant'], plato['nombre']) )

			if 'sabores' in plato:
				printer.set("LEFT", "A", "B", 1, 1)
				text = "(%s)" % ", ".join(plato['sabores'])
				printer.text( text )
			
			printer.text("\n")

			if 'observacion' in plato:
				printer.set("LEFT", "B", "B", 1, 1)
				printer.text( "   OBS: %s\n" % plato['observacion'] )

		
		printer.text( "\n")

		if 'observacion' in comanda:
			printer.set( "CENTER", "B", "B", 2, 2)
			printer.text( "OBSERVACION\n")
			printer.text( comanda['observacion'] )
			printer.text( "\n")
			printer.text( "\n")


		if 'entradas' in comanda:
			printer.set("CENTER", "A", "B", 1, 1)
			printer.text( "** ENTRADA **\n" )

			for entrada in comanda['entradas']:
				print_plato(entrada)

			printer.text( "\n\n" )

		if 'platos' in comanda:
			printer.set("CENTER", "A", "B", 1, 1)
			printer.text( "----- PRINCIPAL -----\n" )

			for plato in comanda['platos']:
				print_plato(plato)
			printer.text( "\n\n" )

		#plato principal
		if setTrailer:
			self._setTrailer(setTrailer)
		

		printer.cut("PART")

		# volver a poner en modo ESC Bematech, temporal para testing
		printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")
		

	