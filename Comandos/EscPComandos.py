# -*- coding: iso-8859-1 -*-
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

	def printRemito(self, mesa, items, cliente=None ):
		return True

	def printComanda(self, comanda, mesa=None, mozo=None):
		"observacion, entradas{observacion, cant, nombre, sabores}, platos{observacion, cant, nombre, sabores}"
		print self.conector.driver		
		printer = self.conector.driver.get_printer()
		printer.set("CENTER", "A", "A", 1, 1)


		printer.text("Comanda #%s\n" % comanda['id'])

		fff_aux = time.strptime( comanda['created'], "%Y-%m-%d %H:%M:%S")
		fecha = time.strftime('%a %X %x %Z', fff_aux)

		#fecha = datetime.strftime(comanda['created'], '%Y-%m-%d %H:%M:%S')
		printer.text( fecha +"\n")


		def print_plato(plato):
			"Imprimir platos"
			printer.set("LEFT", "A", "B", 1, 2)

			printer.text( "%s) %s \n"%( plato['cant'], plato['nombre']) )

			if 'observacion' in plato:
				printer.text( "OBS: %s\n" % plato['observacion'] )


			if 'sabores' in plato:
				printer.text( "(" )
				for sabor in plato['sabores']:
					printer.text( sabor )
				printer.text( ")\n" )
		
		printer.text( "\n")

		if 'observacion' in comanda:
			printer.set("CENTER", "B", "B", 2, 2)
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
			printer.text( "- PRINCIPAL -\n" )

			for plato in comanda['platos']:
				print_plato(plato)
			printer.text( "\n\n" )


		#plato principal
		printer.set("LEFT", "A", "A", 1, 2)
		printer.text( "Mesa : %s\n"%mesa )

		printer.set("LEFT", "A", "B", 1, 2)
		printer.text( "Mozo : %s\n"%mozo )


		printer.cut()

		# volver a poner en modo ESC Bematech, temporal para testing
		printer._raw(chr(0x1D)+chr(0xF9)+chr(0x35)+"0")
		

	