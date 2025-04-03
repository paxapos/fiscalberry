# coding=utf-8

import sys
import json
import threading
from common.FiscalberryComandos import FiscalberryComandos
from common.Configberry import Configberry
from common.fiscalberry_logger import getLogger
from common.EscPComandos import EscPComandos
from escpos import printer
from common.fiscalberry_logger import getLogger
from queue import Queue
import traceback

configberry = Configberry()


logger = getLogger()

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


# Cola de trabajos de impresión
print_queue = Queue()

def process_print_jobs():
    while True:
        jsonTicket, q = print_queue.get()
        if jsonTicket is None:
            break
        
        try:
            runTraductor(jsonTicket, q)
        except Exception as e:
            logging.error(f"Error al procesar el trabajo de impresión: {e}")
            logging.error(traceback.format_exc())

        print_queue.task_done()

# Iniciar el hilo que procesa la cola de trabajos de impresión
threading.Thread(target=process_print_jobs, daemon=True).start()



def runTraductor(jsonTicket, queue):
    # extraigo el printerName del jsonTicket
    printerName = jsonTicket.pop('printerName')

    try:
        dictSectionConf = configberry.get_config_for_printer(printerName)
    except KeyError as e:
        logger.error(f"En el archivo de configuracion no existe la impresora: '{printerName}' :: {e}")
        return
    except Exception as e:
        logger.error(f"Error al leer la configuracion de la impresora: '{printerName}' :: {e}")
        return

    driverName = dictSectionConf.pop("driver", "Dummy")
    # convertir a lowercase
    driverName = driverName.lower()

    driverOps = dictSectionConf

    if driverName == "Fiscalberry".lower():
        # proxy pass to FiscalberryComandos
        comando = FiscalberryComandos()
        host = driverOps.get('host', 'localhost')
        printerName = driverOps.get('printerName', printerName)
        jsonTicket['printerName'] = printerName
        return queue.put(comando.run(host, jsonTicket))

    if driverName == "Win32Raw".lower():
        # printer.Win32Raw(printer_name='', *args, **kwargs)[source]
        diverName = "Win32Raw"
        driver = printer.Win32Raw

        if not driver.is_usable():
            raise DriverError(f"Driver {driverName} not usable")


    elif driverName == "Usb".lower():
        
        # printer.Usb(idVendor=None, idProduct=None, usb_args={}, timeout=0, in_ep=130, out_ep=1, *args, **kwargs)
        diverName = "Usb"

        # convertir de string eJ: 0x82 a int
        if 'out_ep' in driverOps:
            driverOps['out_ep'] = int(driverOps['out_ep'], 16)

        if 'in_ep' in driverOps:
            driverOps['in_ep'] = int(driverOps['in_ep'], 16)

        driverOps['idProduct'] = int(driverOps['idProduct'], 16)
        driverOps['idVendor'] = int(driverOps['idVendor'], 16)


    elif driverName == "Network".lower():
        # printer.Network(host='', port=9100, timeout=60, *args, **kwargs)[source]
        if 'port' in driverOps:
            driverOps['port'] = int(driverOps['port'])
        diverName = "Network"

    elif driverName == "Serial".lower():
        # printer.Serial(devfile='', baudrate=9600, bytesize=8, timeout=1, parity=None, stopbits=None, xonxoff=False, dsrdtr=True, *args, **kwargs)
        diverName = "Serial"

    elif driverName == "File".lower():
        # (devfile='', auto_flush=True
        # printer.File(devfile='', auto_flush=True, *args, **kwargs)[source]
        driverName = "File"

    elif driverName == "Dummy".lower():
        # printer.Dummy(*args, **kwargs)[source]
        driverName = "Dummy"


    elif driverName == "Cups".lower():
        # printer.CupsPrinter(printer_name='', *args, **kwargs)[source]
        driverName = "CupsPrinter"


    elif driverName == "LP".lower():
        # printer.LP(printer_name='', *args, **kwargs)[source]
        driverName = "LP"


    else:
        raise DriverError(f"Invalid driver: {driver}")
    
    try:
        driver_class = getattr(printer, driverName)
        if not callable(driver_class):
            raise DriverError(f"Driver {driverName} is not callable")
    except AttributeError:
        raise DriverError(f"Driver {driverName} not found in printer module")
    except Exception as e:
        raise DriverError(f"Error loading driver {driverName}: {e}")

    try:
        # crear el driver
        driver = driver_class(**driverOps)
    except Exception as e:
        raise DriverError(f"Error creating driver {driverName}: {e}")

    comando = EscPComandos(driver)
    logging.info(f"Imprimiendo en: {printerName}")
    logging.info(f"Driver: {driverName}")
    logging.info(f"DriverOps: {driverOps}")
    logging.info(f"Comando:\n%s" % jsonTicket) 
    comando.run(jsonTicket)
    


class ComandosHandler:
    """Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""

    traductores = {}

    def send_command(self, comando):
        response = {}
                
        try:
            if isinstance(comando, str):
                jsonMes = json.loads(comando, strict=False)
            #si es un diccionario o json, no hacer nada
            elif isinstance(comando, dict):
                jsonMes = comando
            #si es del typo class bytes, convertir a string y luego a json
            elif isinstance(comando, bytes):
                jsonMes = json.loads(comando.decode("utf-8"), strict=False)
            else:
                raise TypeError("Tipo de dato no soportado")
            
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
            errtxt = "Error desconocido: " + repr(e) + "- " + str(e)
            logger.exception(errtxt)
            response["err"] = errtxt

        logger.info("Command Response \n <- %s" % response)
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
                logger.info("Imprimiendo en: \"%s\"" % jsonTicket.get('printerName'))

                # run multiprocessing
                q = Queue()
                print_queue.put((jsonTicket, q))
                q.join()  # Esperar a que el trabajo de impresión se complete
                if not q.empty():
                    rta["rta"] = q.get(timeout=1)

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
                rta["rta"] = self._getPrinterInfo(jsonTicket["getPrinterInfo"])

            elif 'getAvailablePrinters' in jsonTicket:
                rta["rta"] = self._getAvailablePrinters()

            elif 'getActualConfig' in jsonTicket:  # pasarle la contraseña porque muestra datos del servidor y la mostraría
                rta["rta"] = self._getActualConfig(
                    jsonTicket['getActualConfig'])

            elif 'configure' in jsonTicket:
                rta["rta"] = self._configure(**jsonTicket["configure"])

            elif 'removerImpresora' in jsonTicket:
                rta["rta"] = self._removerImpresora(
                    jsonTicket["removerImpresora"])
            else:
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
            "rta": configberry.get_config_for_printer(printerName)
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
        configberry.set(printerName, propiedadesImpresora)

        return {
            "action": "configure",
            "rta": "La seccion " + printerName + " ha sido guardada"
        }

    def _removerImpresora(self, printerName):
        "elimina la sección del configberry.ini"

        configberry.delete_section(printerName)

        return {
            "action": "removerImpresora",
            "rta": "La impresora " + printerName + " fue removida con exito"
        }

    def _getAvailablePrinters(self):

        # la primer seccion corresponde a SERVER, el resto son las impresoras
        rta = {
            "action": "getAvailablePrinters",
            "rta": configberry.sections()[1:]
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
        rta = {"action": "getActualConfig", "rta": "Contraseña incorrecta"}
        if password == configberry.configberry.get("SERVIDOR", 'sio_password', fallback="password"):
            rta['rta'] = configberry.get_actual_config()
        return rta
