

class TraductorInterface:
	isRunning=False
	colaImpresion=[]

	def __init__(self, comando, *args):
		self.comando = comando

	
	def encolar(self, jsonobj):

		return self._run_comando(jsonobj)
	
