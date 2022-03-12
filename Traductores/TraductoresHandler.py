# coding=utf-8

import json
import Configberry
import importlib
import socket
import threading
import tornado.ioloop
import os
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
    logging.info("Mandando comando de impresora")
    print(jsonTicket)
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

    def json_to_comando(self, jsonTicket): 
        traductor = None
        
        try:
            """ leer y procesar una factura en formato JSON
            """
            logging.info(f"Iniciando procesamiento de json:::: {json.dumps(jsonTicket)}")

            rta = {"rta": ""}
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

            # aciones de comando genericos de Status y Control
            elif 'getStatus' in jsonTicket:
                rta["rta"] = self._getStatus()

            # TODO reinicia
            elif 'reboot' in jsonTicket:
                rta["rta"] = self._reboot()

            #  TODO 'restart': FiscalberryApp [INFO]: Response 
            #  <- {'err': 'Socket error: [Errno 98] Address already in use'}
            # /usr/lib/python3.9/asyncio/base_events.py:667: RuntimeWarning: coroutine 'WebSocketProtocol13.write_message.<locals>.wrapper' was never awaited
            #   self._ready.clear()
            # RuntimeWarning: Enable tracemalloc to get the object allocation traceback
            elif 'restart' in jsonTicket:
                rta["rta"] = self._restartService()

            # TODO 'upgrade'
            elif 'upgrade' in jsonTicket:
                rta["rta"] = self._upgrade()

            elif 'getPrinterInfo' in jsonTicket:
                rta["rta"] =  self._getPrinterInfo(jsonTicket["getPrinterInfo"])

            elif 'getAvailablePrinters' in jsonTicket:
                rta["rta"] = self._getAvailablePrinters()

            elif 'getActualConfig' in jsonTicket:
                rta["rta"] = self._getActualConfig()

            elif 'configure' in jsonTicket:
                rta["rta"] = self._configure(**jsonTicket["configure"])

            elif 'removerImpresora' in jsonTicket:
                rta["rta"] =  self._removerImpresora(jsonTicket["removerImpresora"])

            else:

                logging.error("No se pasó un comando válido")
                raise TraductorException("No se pasó un comando válido")

            # cerrar el driver
            if traductor and traductor.comando:
                traductor.comando.close()

            return rta

        except Exception as e:
            # cerrar el driver
            if traductor and traductor.comando:
                traductor.comando.close()
            raise

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
        print(ret)
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
        print(rta)
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
        print(format(err))
        traductor.comando.conector.driver.reconnect()
        # volver a intententar el mismo comando
        try:
            rta = {"action": "getStatus", "rta": {}}
            rta["rta"] = traductor.run(jsonTicket)
            return rta
        except Exception:
            # ok, no quiere conectar, continuar sin hacer nada
            logging.warning("No hay caso, probe de reconectar pero no se pudo")

    def _getActualConfig(self):
        rta = {
            "action": "getActualConfig",
            "rta": self.config.get_actual_config()
        }
        return rta