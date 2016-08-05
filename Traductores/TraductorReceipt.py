from Traductores.TraductorInterface import TraductorInterface

class TraductorReceipt(TraductorInterface):

	
	def _printRemito(self, **kwargs):
		"Imprime un Remito, comando de accion valido solo para Comandos de Receipt"
		return self.comando.printRemito( **kwargs )

	def _printComanda(self, comanda, setHeader=None, setTrailer=None):
		"Imprime una Comanda, comando de accion valido solo para Comandos de Receipt"
		return self.comando.printComanda(comanda, setHeader, setTrailer)



	def _run_comando(self, jsonTicket):
		if 'setHeader' in jsonTicket:
			rta["rta"] =  self._setHeader( jsonTicket["setHeader"] )

		if 'printRemito' in jsonTicket:
			rta["rta"] =  self._printRemito(**jsonTicket["printRemito"])

		if 'printComanda' in jsonTicket:
			rta["rta"] =  self._printComanda(**jsonTicket["printComanda"])

		if 'cancelDocument' in jsonTicket:
			rta["rta"] =  self._cancelDocument()

		
		if 'setTrailer' in jsonTicket:
			rta["rta"] =  self._setTrailer( jsonTicket["setTrailer"] )

		# vuelvo a poner la impresora que estaba por default inicializada
		return rta