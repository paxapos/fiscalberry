# coding=utf-8
import ConfigParser
from Traductores.TraductorInterface import TraductorInterface

traductores = {}
CONFIG_FILE_NAME = "config.ini"
service_name = 'fiscalberry-server-rc'

class TraductorGenerico(TraductorInterface):

    def __init__(self):
        config = ConfigParser.ConfigParser()
        pass

    def _serviceStatus(self):
        import commands
    
        resdict = {
                "action": "serviceStatus", 
                "rta": commands.getoutput('service '+service_name+' status')
                }

        return resdict

    def _serviceStart(self):
        import commands
    
        resdict = {
                "action": "serviceStart", 
                "rta": commands.getoutput('service '+service_name+' start')
                }

        return resdict

    def _serviceStop(self):
        import commands
    
        resdict = {
                "action": "serviceStop", 
                "rta": commands.getoutput('service '+service_name+' stop')
                }

        return resdict

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
                "rta": call(["service", service_name, "restart"])
                }

        return resdict

    def _configure(self, printerName, **kwargs):
        "Configura generando o modificando el archivo config.ini"

        config = ConfigParser.RawConfigParser()
        config.read(CONFIG_FILE_NAME)

        if not config.has_section(printerName):
            config.add_section(printerName)

        for param in kwargs:
            config.set(printerName, param, kwargs[param])

        with open(CONFIG_FILE_NAME, 'w') as configfile:
             config.write(configfile)

        rta = {
            "action": "configure",
            "rta": "ok"
        }

        return rta

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

        resdict = {'action':'testeo','rta': service_name}

        return resdict    