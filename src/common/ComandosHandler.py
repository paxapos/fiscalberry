# coding=utf-8

import json
import threading
from multiprocessing import Process, Queue, Pool
from common.Configberry import Configberry
from common.fiscalberry_logger import getLogger
from common.EscPComandos import EscPComandos
from escpos import printer
from common.fiscalberry_logger import getLogger

logger = getLogger()

import sys
if sys.platform == 'win32':
    import multiprocessing.reduction    # make sockets pickable/inheritable

INTERVALO_IMPRESORA_WARNING = 30.0


logging = getLogger()

def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec)
        func()

    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t

class DriverError(Exception):
    pass


class TraductorException(Exception):
    pass

def runTraductor(jsonTicket, queue):
    #extraigo el printerName del jsonTicket
    printerName = jsonTicket.pop('printerName')


    config = Configberry()
    try:
        dictSectionConf = config.get_config_for_printer(printerName)
    except KeyError as e:
        raise TraductorException(f"En el archivo de configuracion no existe la impresora: '{printerName}'")

    driverName = dictSectionConf.pop("driver", "Dummy")
        
    driverOps = dictSectionConf
    
    # instanciar el driver dinamicamente segun el driver pasado como parametro
    if driverName == "Win32Raw":
        # classprinter.Win32Raw(printer_name='', *args, **kwargs)[source]
        driver = printer.Win32Raw(**driverOps)
    elif driverName == "Usb":
        # classprinter.Usb(idVendor=None, idProduct=None, usb_args={}, timeout=0, in_ep=130, out_ep=1, *args, **kwargs)
        driver = printer.Usb(**driverOps)
    elif driverName == "Network":
        # classprinter.Network(host='', port=9100, timeout=60, *args, **kwargs)[source]
        driver = printer.Network(**driverOps)
    elif driverName == "Serial":
        # classprinter.Serial(devfile='', baudrate=9600, bytesize=8, timeout=1, parity=None, stopbits=None, xonxoff=False, dsrdtr=True, *args, **kwargs)
        driver = printer.Serial(**driverOps)
    elif driverName == "File":
        # (devfile='', auto_flush=True
        driver = printer.File(**driverOps)
    elif driverName == "Dummy":
        driver = printer.Dummy(**driverOps)
    elif driverName == "CupsPrinter":
        # CupsPrinter(printer_name='', *args, **kwargs)[source]
        driver = printer.CupsPrinter(**driverOps)
    elif driverName == "LP":
        # classprinter.LP(printer_name='', *args, **kwargs)[source]
        driver = printer.LP(**driverOps)
    else:
        raise DriverError(f"Invalid driver: {driver}")

    
    comando = EscPComandos(driver)

    queue.put(comando.run(jsonTicket))
    


class ComandosHandler:
    """Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""

    traductores = {}
    config = Configberry()
    
    
    def send_command(self, comando):
        response = {}
        logger.info(f"Request \n -> {comando}")
        try:
            if isinstance(comando, str):
                jsonMes = json.loads(comando, strict=False)
            else:
                jsonMes = comando
            response = self.__json_to_comando(jsonMes)
        except TypeError as e:
            errtxt = "Error parseando el JSON %s" % e
            logger.exception(errtxt)
            response["err"] = errtxt
        except TraductorException as e:
            errtxt = "Traductor Comandos: %s" % str(e)
            logger.exception(errtxt)
            response["err"] = errtxt
        except KeyError as e:
            errtxt = "El comando no es valido para ese tipo de impresora: %s" % e
            logger.exception(errtxt)
            response["err"] = errtxt
        except Exception as e:
            errtxt = repr(e) + "- " + str(e)
            logger.exception(errtxt)
            response["err"] = errtxt

        logger.info("Response \n <- %s" % response)
        return response
            


    def __json_to_comando(self, jsonTicket): 
        """Leer y procesar una factura en formato JSON 
        ``jsonTicket`` factura a procesar
        """
        traductor = None
        
        rta = {"rta": ""}

        try:

            # seleccionar impresora
            # esto se debe ejecutar antes que cualquier otro comando
            if 'printerName' in jsonTicket:
                # run multiprocessing
                q = Queue()
                p = Process(target=runTraductor, args=(jsonTicket,q))
                p.daemon = True
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
            logging.error(format(e))

        return rta



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