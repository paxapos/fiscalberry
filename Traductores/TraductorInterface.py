class TraductorInterface:
    isRunning = False
    colaImpresion = []

    def __init__(self, comando, *args):
        self.comando = comando

    def run(self, jsonTicket):
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
                print("asjkhashahsaishauhsiahiushaihs")
                print(fnAction)
                print(jsonTicket[action])
                print("asjkhashahsaishauhsiahiushaihs")
                res = fnAction(jsonTicket[action])
                rta.append({"action": action, "rta": res})

        # vuelvo a poner la impresora que estaba por default inicializada
        return rta
