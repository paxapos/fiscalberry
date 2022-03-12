from Traductores.TraductorInterface import TraductorInterface


class TraductorReceipt(TraductorInterface):

    def printTicket(self, **kwargs):
        "Imprime un Ticket fiscal, realizado mediante facturacion electronica"
        return self.comando.printTicket(**kwargs)

    def printRemito(self, **kwargs):
        "Imprime un Remito, comando de accion valido solo para Comandos de Receipt"
        return self.comando.printRemito(**kwargs)

    def printRemitoCorto(self, **kwargs):
        "Imprime un Remito, comando de accion valido solo para Comandos de Receipt"
        return self.comando.printRemitoCorto(**kwargs)

    def printPedido(self, **kwargs):
        "Imprime un Pedido de compras, comando de accion valido solo para Comandos de Receipt"
        return self.comando.printPedido(**kwargs)

    def printComanda(self, comanda, setHeader=None, setTrailer=None):
        "Imprime una Comanda, comando de accion valido solo para Comandos de Receipt"
        return self.comando.printComanda(comanda, setHeader, setTrailer)

    def printTexto(self, texto):
       "Imprime texto libre"
       return self.comando.printTexto(texto)

    def printMuestra(self, *args):
        "Imprime muestra de fuentes"
        return self.comando.printMuestra()

    def openDrawer(self, *args):
        return self.comando.openDrawer()

    def setHeader(self, *args):
        "SetHeader"
        ret = self.comando.setHeader(list(args))
        return ret

    def setTrailer(self, *args):
        "SetTrailer"
        ret = self.comando.setTrailer(list(args))
        return ret

    def printFacturaElectronica(self, **kwargs):
        "Factura Electronica"
        try:
            return self.comando.printFacturaElectronica(**kwargs)        
        except Exception as e:
            print(e)
        else:
            pass
        finally:    
            pass
    
    def printArqueo(self, **kwargs):
        "Imprimir Cierre de Caja"
        return self.comando.printArqueo(**kwargs)

    def getStatus(self, **kwargs):
        "Devuelve la ip si es DirectJet"
        return self.comando.getStatus()