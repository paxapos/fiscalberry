

class TraductorFiscal:

	
	def _abrirComprobante(self, 
						 tipo_cbte="T", 							# tique
						 tipo_responsable="CONSUMIDOR_FINAL",
						 tipo_doc="SIN_CALIFICADOR", nro_doc=0,     # sin especificar
						 nombre_cliente="", domicilio_cliente="",
						 referencia=None,                           # comprobante original (ND/NC)
						 **kwargs
						 ):
		"Creo un objeto factura (internamente) e imprime el encabezado"
		# crear la estructura interna
		self.factura = {"encabezado": dict(tipo_cbte=tipo_cbte,
										   tipo_responsable=tipo_responsable,
										   tipo_doc=tipo_doc, nro_doc=nro_doc,
										   nombre_cliente=nombre_cliente, 
										   domicilio_cliente=domicilio_cliente,
										   referencia=referencia),
						"items": [], "pagos": []}
		printer = self.comando


		letra_cbte = tipo_cbte[-1] if len(tipo_cbte) > 1 else None
		
		# mapear el tipo de cliente (posicion/categoria)
		pos_fiscal = printer.ivaTypes.get(tipo_responsable)
		
		# mapear el numero de documento según RG1361
		doc_fiscal = printer.docTypes.get(tipo_doc)

		# cancelar y volver a un estado conocido
		printer.cancelAnyDocument()
		ret = False
		# enviar los comandos de apertura de comprobante fiscal:
		if tipo_cbte.startswith('T'):
			if letra_cbte:
				ret = printer.openTicket(letra_cbte)
			else:
				ret = printer.openTicket()
		elif tipo_cbte.startswith("F"):
			ret = printer.openBillTicket(letra_cbte, nombre_cliente, domicilio_cliente, 
										 nro_doc, doc_fiscal, pos_fiscal)
		elif tipo_cbte.startswith("ND"):
			ret = printer.openDebitNoteTicket(letra_cbte, nombre_cliente, 
											  domicilio_cliente, nro_doc, doc_fiscal, 
											  pos_fiscal)
		elif tipo_cbte.startswith("NC"):
			ret = printer.openBillCreditTicket(letra_cbte, nombre_cliente, 
											   domicilio_cliente, nro_doc, doc_fiscal, 
											   pos_fiscal, referencia)
		
		return ret

	def _imprimirItem(self, ds, qty, importe, alic_iva=21.):
		"Envia un item (descripcion, cantidad, etc.) a una factura"
		self.factura["items"].append(dict(ds=ds, qty=qty, 
										  importe=importe, alic_iva=alic_iva))
		##ds = unicode(ds, "latin1") # convierto a latin1
		# Nota: no se calcula neto, iva, etc (deben venir calculados!)
		discount = discountDescription =  None
		return self.comando.addItem(ds, float(qty), float(importe), float(alic_iva), 
									discount, discountDescription)

	def _imprimirPago(self, ds, importe):
		"Imprime una linea con la forma de pago y monto"
		self.factura["pagos"].append(dict(ds=ds, importe=importe))
		return self.comando.addPayment(ds, float(importe))

	def _cerrarComprobante(self):
		"Envia el comando para cerrar un comprobante Fiscal"
		return self.comando.closeDocument()


	def _dailyClose(self, type):
		"Comando X o Z"
		ret = self.comando.dailyClose(type)
		return ret



	def _setHeader(self, header):
		"SetHeader"
		ret = self.comando.setHeader(header)
		return ret

	def _setTrailer(self, trailer):
		"SetTrailer"
		ret = self.comando.setTrailer(trailer)
		return ret


	def _openDrawer(self):
		"Abrir caja registradora"
		return self.comando.openDrawer()


	def _getLastNumber(self, tipo_cbte):
		"Devuelve el último número de comprobante"
		
		letra_cbte = tipo_cbte[-1] if len(tipo_cbte) > 1 else None
		return self.comando.getLastNumber(letra_cbte)

	def _cancelDocument(self):
		"Cancelar comprobante en curso"
		return self.comando.cancelDocument()






	def _run_comando(self, jsonTicket):
		if 'setHeader' in jsonTicket:
			rta["rta"] =  self._setHeader( jsonTicket["setHeader"] )

		if 'printRemito' in jsonTicket:
			rta["rta"] =  self._printRemito(**jsonTicket["printRemito"])

		if 'printComanda' in jsonTicket:
			rta["rta"] =  self._printComanda(**jsonTicket["printComanda"])

		if 'cancelDocument' in jsonTicket:
			rta["rta"] =  self._cancelDocument()

		if 'dailyClose' in jsonTicket:
			rta["rta"] =  self._dailyClose(jsonTicket["dailyClose"])

		if 'openDrawer' in jsonTicket:
			rta["rta"] =  self._openDrawer()


		
		if 'getLastNumber' in jsonTicket:
			rta["rta"] =  self._getLastNumber(jsonTicket["getLastNumber"])			

		
		
		if 'setTrailer' in jsonTicket:
			rta["rta"] =  self._setTrailer( jsonTicket["setTrailer"] )

		if 'printTicket' in jsonTicket:
			'''	
			if "setHeader" in jsonTicket['printTicket']:
				self.comando.setHeader( jsonTicket['printTicket']["setHeader"] )

			if "setTrailer" in jsonTicket['printTicket']:
				self.comando.setHeader( jsonTicket['printTicket']["setTrailer"] )
			'''
			
			ok = self._abrirComprobante(**jsonTicket['printTicket']["encabezado"])


			if "items" in jsonTicket['printTicket']:
				for item in jsonTicket['printTicket']["items"]:
					ok = self._imprimirItem(**item)
			else:
				raise TraductorException("Debe incluir 'items' en el JSON")

			if "pagos" in jsonTicket['printTicket']:
				for pago in jsonTicket['printTicket']["pagos"]:
					print pago
					ok = self._imprimirPago(**pago)

			if "addAdditional" in jsonTicket['printTicket']:
				self.comando.addAdditional(**jsonTicket['printTicket']['addAdditional'])

			rta["rta"] =  self._cerrarComprobante()

		return rta