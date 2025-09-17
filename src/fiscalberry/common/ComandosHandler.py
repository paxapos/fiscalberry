# coding=utf-8

import sys
import json
import threading
import time
import queue
from fiscalberry.common.FiscalberryComandos import FiscalberryComandos
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.EscPComandos import EscPComandos
from escpos import printer
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


# Cola de trabajos de impresión optimizada - mayor capacidad y procesamiento más rápido  
print_queue = Queue(maxsize=500)  # Aumentar capacidad para mayor throughput

# Worker threads pool para procesamiento paralelo
worker_threads = []
MAX_WORKERS = 3  # Número de workers concurrentes
def report_queue_status():
    qsize = print_queue.qsize()
    if qsize > 50:  # Solo reportar cuando la cola esté más cargada
        logging.info(f"Print queue busy: {qsize} jobs waiting")
    elif qsize > 100:
        logging.warning(f"Print queue overloaded: {qsize} jobs waiting")
    threading.Timer(30.0, report_queue_status).start()  # Reportar más frecuentemente

def process_print_jobs(worker_id=0):
    """Worker optimizado para procesar trabajos de impresión"""
    logger.info(f"Print worker {worker_id} started")
    
    while True:
        try:
            # Obtener trabajo con timeout para permitir shutdown limpio
            job_data = print_queue.get(timeout=1.0)
            if job_data is None:
                logger.info(f"Worker {worker_id} received shutdown signal")
                break
            
            jsonTicket, q = job_data
            
            start_time = time.time()
            try:
                result = runTraductor(jsonTicket, q)
                processing_time = time.time() - start_time
                
                # Respuesta optimizada sin nested dicts innecesarios
                q.put({"success": True, "result": result, "processing_time": processing_time})
                
                # Log optimizado solo para trabajos lentos
                if processing_time > 2.0:
                    logger.warning(f"Slow print job completed in {processing_time:.2f}s by worker {worker_id}")
                    
            except Exception as e:
                processing_time = time.time() - start_time
                error_msg = str(e)
                logger.error(f"Worker {worker_id} print job failed in {processing_time:.2f}s: {error_msg}")
                q.put({"success": False, "error": error_msg, "processing_time": processing_time})

            print_queue.task_done()
            
        except queue.Empty:
            # Timeout normal, continuar loop
            continue
        except Exception as e:
            logger.error(f"Worker {worker_id} unexpected error: {e}")
            continue

# Iniciar workers optimizados
for i in range(MAX_WORKERS):
    worker = threading.Thread(target=process_print_jobs, args=(i,), daemon=True)
    worker.start()
    worker_threads.append(worker)

# Iniciar el informe periódico
report_queue_status()




def runTraductor(jsonTicket, queue):
    # extraigo el printerName del jsonTicket
    printerName = jsonTicket.pop('printerName')
    logger.info(f"Iniciando proceso de impresión para impresora: '{printerName}'")
    logger.debug(f"JSON ticket recibido: {json.dumps(jsonTicket, indent=2, ensure_ascii=False)}")

    try:
        dictSectionConf = configberry.get_config_for_printer(printerName)
        logger.debug(f"Configuración de impresora '{printerName}' cargada exitosamente")
    except KeyError as e:
        error_msg = f"En el archivo de configuracion no existe la impresora: '{printerName}' :: {e}"
        logger.error(error_msg)
        return {"error": f"Impresora no encontrada: {printerName}"}
    except Exception as e:
        error_msg = f"Error al leer la configuracion de la impresora: '{printerName}' :: {e}"
        logger.error(error_msg, exc_info=True)
        return {"error": f"Error de configuración: {str(e)}"}


    driverName = dictSectionConf.pop("driver", "Dummy")
    # convertir a lowercase
    driverName = driverName.lower()
    logger.info(f"Driver seleccionado para '{printerName}': {driverName}")

    driverOps = dictSectionConf
    logger.debug(f"Opciones del driver: {driverOps}")

    if driverName == "Fiscalberry".lower():
        # proxy pass to FiscalberryComandos
        logger.info(f"Usando FiscalberryComandos para impresora '{printerName}'")
        try:
            comando = FiscalberryComandos()
            host = driverOps.get('host', 'localhost')
            printerName = driverOps.get('printerName', printerName)
            jsonTicket['printerName'] = printerName
            logger.debug(f"Enviando comando a host: {host}")
            result = comando.run(host, jsonTicket)
            logger.info(f"Comando FiscalberryComandos ejecutado exitosamente")
            return queue.put(result)
        except Exception as e:
            logger.error(f"Error ejecutando FiscalberryComandos: {e}", exc_info=True)
            return queue.put({"error": f"Error en FiscalberryComandos: {str(e)}"})

    if driverName == "Win32Raw".lower():
        # printer.Win32Raw(printer_name='', *args, **kwargs)[source]
        driverName = "Win32Raw"
        driver = printer.Win32Raw
        logger.info(f"Configurando driver Win32Raw para '{printerName}'")

        if not driver.is_usable():
            error_msg = f"Driver {driverName} no está disponible en este sistema"
            logger.error(error_msg)
            raise DriverError(error_msg)
        logger.debug("Driver Win32Raw verificado como disponible")


    elif driverName == "Usb".lower():
        
        # printer.Usb(idVendor=None, idProduct=None, usb_args={}, timeout=0, in_ep=130, out_ep=1, *args, **kwargs)
        driverName = "Usb"
        logger.info(f"Configurando driver USB para '{printerName}'")
        logger.debug(f"Parámetros USB: {driverOps}")

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
        driverName = "Network"

    elif driverName == "Serial".lower():
        # printer.Serial(devfile='', baudrate=9600, bytesize=8, timeout=1, parity=None, stopbits=None, xonxoff=False, dsrdtr=True, *args, **kwargs)
        driverName = "Serial"

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
        logger.debug(f"Creando instancia del driver {driverName} con opciones: {driverOps}")
        driver = driver_class(**driverOps)
        logger.info(f"Driver {driverName} creado exitosamente")
    except Exception as e:
        error_msg = f"Error creando driver {driverName}: {e}"
        logger.error(error_msg, exc_info=True)
        raise DriverError(error_msg)

    try:
        comando = EscPComandos(driver)
        logger.info(f"EscPComandos inicializado para '{printerName}'")
        
        logger.info(f"=== INICIANDO IMPRESIÓN ===")
        logger.info(f"Impresora: {printerName}")
        logger.info(f"Driver: {driverName}")
        logger.debug(f"DriverOps: {driverOps}")
        logger.debug(f"Comando JSON:\n{json.dumps(jsonTicket, indent=2, ensure_ascii=False)}")
        
        result = comando.run(jsonTicket)
        logger.info(f"=== IMPRESIÓN EXITOSA ===")
        logger.debug(f"Resultado: {result}")
        return {"message": "Impresión exitosa", "result": result}
    except Exception as e:
        logger.error(f"=== ERROR DURANTE IMPRESIÓN ===")
        logger.error(f"Error en impresora '{printerName}': {e}", exc_info=True)
        raise e



class ComandosHandler:
    """Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""

    traductores = {}

    def send_command(self, comando):
        response = {}
        logger.info(f"=== PROCESANDO COMANDO ===")
        logger.debug(f"Comando recibido (tipo: {type(comando).__name__}): {str(comando)[:200]}...")
        
        try:
            if isinstance(comando, str):
                logger.debug("Parseando comando desde string JSON")
                jsonMes = json.loads(comando, strict=False)
            #si es un diccionario o json, no hacer nada
            elif isinstance(comando, dict):
                logger.debug("Comando recibido como diccionario")
                jsonMes = comando
            #si es del typo class bytes, convertir a string y luego a json
            elif isinstance(comando, bytes):
                logger.debug("Parseando comando desde bytes")
                jsonMes = json.loads(comando.decode("utf-8"), strict=False)
            else:
                error_msg = f"Tipo de dato no soportado: {type(comando).__name__}"
                logger.error(error_msg)
                raise TypeError(error_msg)
            
            logger.info("Comando parseado exitosamente, ejecutando...")
            response = self.__json_to_comando(jsonMes)
            logger.info("Comando ejecutado exitosamente")
            
        except TypeError as e:
            errtxt = f"Error parseando el JSON: {e}"
            logger.error(errtxt, exc_info=True)
            response["err"] = errtxt
        except json.JSONDecodeError as e:
            errtxt = f"JSON inválido: {e}"
            logger.error(errtxt)
            response["err"] = errtxt
        except TraductorException as e:
            errtxt = f"Error en traductor de comandos: {str(e)}"
            logger.error(errtxt, exc_info=True)
            response["err"] = errtxt
        except KeyError as e:
            errtxt = f"Comando no válido para este tipo de impresora - Clave faltante: {e}"
            logger.error(errtxt, exc_info=True)
            response["err"] = errtxt
        except Exception as e:
            errtxt = f"Error desconocido: {repr(e)} - {str(e)}"
            logger.error(errtxt, exc_info=True)
            response["err"] = errtxt

        logger.info(f"=== RESPUESTA DEL COMANDO ===")
        if "err" in response:
            logger.error(f"Comando falló con error: {response.get('err', 'Error desconocido')}")
        else:
            logger.info("Comando ejecutado exitosamente")
            
        logger.debug(f"Respuesta completa: {json.dumps(response, indent=2, ensure_ascii=False)}")
        return response

    def __json_to_comando(self, jsonTicket):
        """Leer y procesar una factura en formato JSON 
        ``jsonTicket`` factura a procesar
        """
        traductor = None

        rta = {"rta": ""}
        try:

            # si no se pasa el nombre de la impresora, se toma la primera# seleccionar impresora
            # esto se debe ejecutar antes que cualquier otro comando
            if 'printerName' in jsonTicket:
                printer_name = jsonTicket.get('printerName')
                logger.info(f"=== PROCESANDO IMPRESIÓN ===")
                logger.info(f"Impresora destino: '{printer_name}'")
                logger.debug(f"Ticket de impresión: {json.dumps(jsonTicket, indent=2, ensure_ascii=False)}")

                # Procesamiento optimizado con cola de alta velocidad
                q = Queue()
                
                # Verificar capacidad de cola antes de agregar
                current_queue_size = print_queue.qsize()
                if current_queue_size > 400:  # 80% de capacidad
                    logger.warning(f"Print queue near capacity: {current_queue_size}/500")
                
                try:
                    # Agregar trabajo sin bloqueo
                    print_queue.put_nowait((jsonTicket, q))
                    logger.debug(f"Job queued fast. Queue size: {current_queue_size + 1}")
                    
                    # Timeout más agresivo para mayor throughput
                    result = q.get(timeout=15)  # Reducido de 30 a 15 segundos
                    
                    if isinstance(result, dict):
                        if not result.get("success", True):
                            error_msg = result.get("error", "Error desconocido en la impresión")
                            logger.error(f"Print job failed: {error_msg}")
                            rta["err"] = error_msg
                        else:
                            # Log optimizado con tiempo de procesamiento
                            processing_time = result.get("processing_time", 0)
                            if processing_time > 0:
                                logger.info(f"Print completed in {processing_time:.2f}s for '{printer_name}'")
                            rta["rta"] = result.get("result", result)
                    else:
                        logger.info(f"Print completed successfully for '{printer_name}'")
                        rta["rta"] = result
                        
                except queue.Full:
                    error_msg = f"Print queue full. Cannot queue job for '{printer_name}'"
                    logger.error(error_msg)
                    rta["err"] = error_msg
                except queue.Empty:
                    error_msg = f"Print timeout for '{printer_name}' (15s)"
                    logger.error(error_msg)
                    rta["err"] = error_msg
                except Exception as e:
                    error_msg = f"Print queue error: {e}"
                    logger.error(error_msg, exc_info=True)
                    rta["err"] = error_msg

            

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
            
            raise TraductorException(
                "Error en el comando %s" % e)

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
