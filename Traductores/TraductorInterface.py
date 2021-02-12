class TraductorInterface:
    isRunning = False
    colaImpresion = []
    isProxy = False

    def __init__(self, comando, *args):
        self.comando = comando

    def run(self, jsonTicket):

        
        if (self.isProxy): 
            self.comando.conector.sendCommand(jsonTicket)
            return []

        printerName = jsonTicket.pop('printerName')
        actions = jsonTicket.keys()
        rta = []
        for action in actions:
            fnAction = getattr(self, action)

            if isinstance(jsonTicket[action], list):
                res = fnAction(*jsonTicket[action])
                rta.append({"action": action, "rta": res})

            elif isinstance(jsonTicket[action], dict):
                res = fnAction(**jsonTicket[action])
                rta.append({"action": action, "rta": res})

            else:
                res = fnAction(jsonTicket[action])
                rta.append({"action": action, "rta": res})

        # vuelvo a poner la impresora que estaba por default inicializada
        return rta
