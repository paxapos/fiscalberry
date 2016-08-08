

class TraductorInterface:
	isRunning=False
	colaImpresion=[]

	def __init__(self, comando, *args):
		self.comando = comando

	
	def run(self, jsonobj):

		return self._run_comando(jsonobj)
	


	def _run_comando(self, jsonTicket):
		actions = jsonTicket.keys()
		rta = []

		for action in actions:
			fnAction = getattr(self, action)

			if isinstance( jsonTicket[action], list):
				res = fnAction( *jsonTicket[action] )
				rta.append( {"action":  action, "rta": res } )

			elif isinstance( jsonTicket[action], dict):
				res = fnAction( **jsonTicket[action] )
				rta.append( {"action":  action, "rta": res } )

			else:
				res = fnAction( jsonTicket[action] )
				rta.append( {"action":  action, "rta": res } )

		# vuelvo a poner la impresora que estaba por default inicializada
		return rta