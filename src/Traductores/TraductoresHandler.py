# coding=utf-8

import json
import Configberry
import importlib
import threading
from multiprocessing import Process, Queue, Pool
import logging

import sys
if sys.platform == 'win32':
    import multiprocessing.reduction    # make sockets pickable/inheritable

INTERVALO_IMPRESORA_WARNING = 30.0

def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec)
        func()

    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t


# es un diccionario como clave va el nombre de la impresora que funciona como cola
# cada KEY es una printerName y contiene un a instancia de TraductorReceipt o TraductorFiscal dependiendo
# si la impresora es fiscal o receipt

class TraductorException(Exception):
    pass

def init_printer_traductor(printerName):
    config = Configberry.Configberry()
    try:
        dictSectionConf = config.get_config_for_printer(printerName)
    except KeyError as e:
        raise TraductorException(f"En el archivo de configuracion no existe la impresora: '{printerName}'")

    marca = dictSectionConf.get("marca")
    del dictSectionConf['marca']
    # instanciar los comandos dinamicamente
    libraryName = f"Comandos.{marca}Comandos"
    comandoModule = importlib.import_module(libraryName)
    comandoClass = getattr(comandoModule, marca + "Comandos")
    
    comando = comandoClass(**dictSectionConf)
    return comando.traductor

def runTraductor(jsonTicket, queue):
    printerName = jsonTicket['printerName']
    traductor = init_printer_traductor(printerName)

    if traductor:
        if traductor.comando.conector is not None:
            queue.put(traductor.run(jsonTicket))
        else:
            strError = f"El Driver no esta inicializado para la impresora {printerName}"
            queue.put(strError)
            logging.error(strError)


class TraductoresHandler:
    """Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""

    traductores = {}
    fbApp = None
    webSocket = None
    config = Configberry.Configberry()

    def __init__(self, webSocket = None, fbApp = None):
        self.webSocket = webSocket
        self.fbApp = fbApp

    async def json_to_comando(self, jsonTicket): 
        """Leer y procesar una factura en formato JSON 
        ``jsonTicket`` factura a procesar
        """
        traductor = None
        
        rta = {"rta": ""}

        try:
            logging.info(f"Iniciando procesamiento de json:::: {json.dumps(jsonTicket)}")

            # Interceptar la key 'uuid'
            if 'uuid' in jsonTicket:
                uuidFb = jsonTicket.pop("uuid")
                if (self.fbApp.isSioServer):
                    status = await self.fbApp.socketio.sendCommand(command=jsonTicket,uuid=uuidFb)
                    rta["rta"] = {"action":"sio:sendCommand", "rta": "Sent"} if status else {"action":"sio:sendCommand", "rta": "Failed"}                        
                    return rta

            # seleccionar impresora
            # esto se debe ejecutar antes que cualquier otro comando
            if 'printerName' in jsonTicket:
                # run multiprocessing
                q = Queue()
                p = Process(target=runTraductor, args=(jsonTicket,q))
                p.daemon = True
                #p = MultiprocesingTraductor(traductorhandler=self, jsonTicket=jsonTicket, q=q)
                p.start()
                p.join()
                if q.empty() == False:
                    rta["rta"] = q.get(timeout=1)
                q.close()

            # Acciones de comando genericos de Status y Control
            elif 'getStatus' in jsonTicket:
                rta["rta"] = self._getStatus()

            elif 'reboot' in jsonTicket:
                rta["rta"] = self._reboot()

            elif 'restart' in jsonTicket:
                rta["rta"] = self._restartService()

            elif 'upgrade' in jsonTicket:
                rta["rta"] = self._upgrade()

            elif 'getPrinterInfo' in jsonTicket:
                rta["rta"] =  self._getPrinterInfo(jsonTicket["getPrinterInfo"])

            elif 'getAvailablePrinters' in jsonTicket:
                rta["rta"] = self._getAvailablePrinters()

            elif 'getActualConfig' in jsonTicket: #pasarle la contraseña porque muestra datos del servidor y la mostraría
                rta["rta"] = self._getActualConfig(jsonTicket['getActualConfig'])

            elif 'configure' in jsonTicket:
                rta["rta"] = self._configure(**jsonTicket["configure"])

            elif 'removerImpresora' in jsonTicket:
                rta["rta"] =  self._removerImpresora(jsonTicket["removerImpresora"])

            ### Comandos Socket.io Server
            elif 'flushDisconnectedClients' in jsonTicket:
                rta["rta"] = await self.fbApp.socketio.flushDisconnectedClients()

            elif 'listClients' in jsonTicket:
                rta["rta"] = await self.fbApp.socketio.listClients()

            elif 'getClientConfig' in jsonTicket:
                rta["rta"] = await self.fbApp.socketio.getClientConfig(jsonTicket['getClientConfig'])
            
            elif 'disconnectClient' in jsonTicket:
                rta["rta"] = await self.fbApp.socketio.disconnectByUuid(jsonTicket['disconnectClient'])

            elif 'disconnectAll' in jsonTicket:
                rta["rta"] = await self.fbApp.socketio.disconnectAll()

            else:
                logging.error("No se pasó un comando válido")
                raise TraductorException("No se pasó un comando válido")

            # cerrar el driver
            if traductor and traductor.comando:
                traductor.comando.close()

        except Exception as e:
            # cerrar el driver
            if traductor and traductor.comando:
                traductor.comando.close()
            raise

        return rta

    def getWarnings(self):
        """ Recolecta los warning que puedan ir arrojando las impresoraas
            devuelve un listado de warnings
        """
        collect_warnings = {}
        for trad in self.traductores:
            if self.traductores[trad]:
                warn = self.traductores[trad].comando.getWarnings()
                if warn:
                    collect_warnings[trad] = warn
        return collect_warnings


    def _upgrade(self):
        ret = self.fbApp.upgradeGitPull()
        rta = {
            "rta": ret
        }
        self.fbApp.restart_service()
        return rta

    def _getPrinterInfo(self, printerName):
        rta = {
            "printerName": printerName,
            "action": "getPrinterInfo",
            "rta": self.config.get_config_for_printer(printerName)
        }
        return rta

    def _restartService(self):
        """ Reinicializa el WS server tornado y levanta la configuracion nuevamente """
        self.fbApp.restart_service()
        rta = {
            "action": "restartService",
            "rta": "servidor reiniciado"
        }
        return rta

    def _rebootFiscalberry(self):
        "reinicia el servicio fiscalberry"
        from subprocess import call

        rta = {
            "action": "rebootFiscalberry",
            "rta": call(["reboot"])
        }

        return rta

    def _configure(self, **kwargs):
        "Configura generando o modificando el archivo configure.ini"
        printerName = kwargs["printerName"]
        propiedadesImpresora = kwargs
        if "nombre_anterior" in kwargs:
            self._removerImpresora(kwargs["nombre_anterior"])
            del propiedadesImpresora["nombre_anterior"]
        del propiedadesImpresora["printerName"]
        self.config.writeSectionWithKwargs(printerName, propiedadesImpresora)

        return {
            "action": "configure",
            "rta": "La seccion " + printerName + " ha sido guardada"
        }

    def _removerImpresora(self, printerName):
        "elimina la sección del config.ini"

        self.config.delete_printer_from_config(printerName)

        return {
            "action": "removerImpresora",
            "rta": "La impresora " + printerName + " fue removida con exito"
        }



    def _getAvailablePrinters(self):

        # la primer seccion corresponde a SERVER, el resto son las impresoras
        rta = {
            "action": "getAvailablePrinters",
            "rta": self.config.sections()[1:]
        }

        return rta

    def _getStatus(self, *args):

        rta = {"action": "getStatus", "rta": {}}
        for tradu in self.traductores:
            if self.traductores[tradu]:
                rta["rta"][tradu] = "ONLINE"
            else:
                rta["rta"][tradu] = "OFFLINE"
        return rta

    def _handleSocketError(self, err, jsonTicket, traductor):
        logging.error(format(err))
        traductor.comando.conector.driver.reconnect()
        # volver a intententar el mismo comando
        try:
            rta = {"action": "getStatus", "rta": {}}
            rta["rta"] = traductor.run(jsonTicket)
            return rta
        except Exception:
            # ok, no quiere conectar, continuar sin hacer nada
            logging.warning("No hay caso, probe de reconectar pero no se pudo")

    def _getActualConfig(self, password):
        rta = {"action":"getActualConfig", "rta":"Contraseña incorrecta"}
        if password == self.config.config.get("SERVIDOR", 'sio_password',fallback="password"):
            rta['rta']=self.config.get_actual_config()
        return rta