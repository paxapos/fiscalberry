from Traductores.TraductorInterface import TraductorInterface


class TraductorReceipt(TraductorInterface):
    def printRemito(self, **kwargs):
        "Imprime un Remito, comando de accion valido solo para Comandos de Receipt"
        return self.comando.printRemito(**kwargs)

    def printComanda(self, comanda, setHeader=None, setTrailer=None):
        "Imprime una Comanda, comando de accion valido solo para Comandos de Receipt"
        return self.comando.printComanda(comanda, setHeader, setTrailer)

    def setHeader(self, *args):
        "SetHeader"
        ret = self.comando.setHeader(list(args))
        return ret

    def setTrailer(self, *args):
        "SetTrailer"
        ret = self.comando.setTrailer(list(args))
        return ret
