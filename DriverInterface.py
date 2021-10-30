# -*- coding: iso-8859-1 -*-

class DriverInterface:
    """Interfaz que deben cumplir las impresoras fiscales."""

    # Documentos no fiscales

    def close(self):
        """Cierra recurso de conexion con impresora"""
        raise NotImplementedError

    def sendCommand(self, commandNumber, parameters, skipStatusErrors):
        """Envia comando a impresora"""
        raise NotImplementedError

    def start(self):
        """ iniciar """
        raise NotImplementedError

    def end(self):
        pass
