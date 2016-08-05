

class TraductorInterface:
	isRunning=False

    def __init__(self, comando, *args):
		self.comando = comando

	
	def encolar(self, jsonobj):
		self.colaImpresion.append(jsonobj)
		self.runNextEncolada()
	

	def __process_cola_comando(self):
		""" Agarra el primer elemento de la cola para procesar """
		self.isRunning = True
		jsonObj = self.colaImpresion.remove(0)
		self._run_comando(jsonObj)
		self.runNextEncolada()
		self.isRunning = False


	def runNextEncolada(self):
		if len(self.colaImpresion) > 0 and not self.isRunning:
			self.__process_cola_comando()

		
