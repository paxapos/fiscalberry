# coding=utf-8
import ConfigParser
from Traductores.TraductorInterface import TraductorInterface

traductores = {}
CONFIG_FILE_NAME = "config.ini"

class TraductorGenerico(TraductorInterface):

    def __init__(self):
        config = ConfigParser.ConfigParser()
        pass

    def _systemPowerOff(self):# en caso de exito no habra retorno, de existir retorno legible en el cliente sera señal de que algo fue mal
        import commands
    
        resdict = {
                "action": "systemPowerOff", 
                "rta": commands.getoutput('halt -h -i -p')
                }

        return resdict
        
    def _systemReboot(self):# en caso de exito no habra retorno, de existir retorno legible en el cliente sera señal de que algo fue mal
        import commands
    
        resdict = {
                "action": "systemReboot", 
                "rta": commands.getoutput('reboot')
                }

        return resdict

    def _restartFiscalberry(self):
        "reinicia el servicio fiscalberry"
        from subprocess import call

        resdict = {
                "action": "restartFIscalberry", 
                "rta": call(["service", "fiscalberry-server-rc", "restart"])
                }

        return resdict

    def _configure(self, printerName, **kwargs):
        "Configura generando o modificando el archivo configure.ini"

        config = ConfigParser.RawConfigParser()
        config.read(CONFIG_FILE_NAME)

        if not config.has_section(printerName):
            config.add_section(printerName)

        for param in kwargs:
            config.set(printerName, param, kwargs[param])

        with open(CONFIG_FILE_NAME, 'w') as configfile:
            config.write(configfile)

        return {
            "action": "configure",
            "rta": "ok"
        }

    def _getAvaliablePrinters(self):
        config = ConfigParser.RawConfigParser()
        config.read(CONFIG_FILE_NAME)
        # la primer seccion corresponde a SERVER, el resto son las impresoras
        rta = {
            "action": "getAvaliablePrinters",
            "rta": config.sections()[1:]
        }

        return rta

    def _getStatus(self, *args):
        global traductores

        resdict = {"action": "getStatus", "rta":{}}
        for tradu in traductores:
            if traductores[tradu]:
                resdict["rta"][tradu] = "ONLINE"
            else:
                resdict["rta"][tradu] = "OFFLINE"
        return resdict

    def _testFunction(self,mode):

        resdict = 'un testeo'

        return resdict    