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
from fiscalberry.common.rabbitmq.error_publisher import publish_error
from fiscalberry.common.printer_error_detector import PrinterErrorDetector, analyze_printer_response
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


class PrintJobError(Exception):
    """
    Falló la impresión de un trabajo del spooler.

    Existe porque runTraductor a veces DEVUELVE el error en vez de lanzarlo
    (impresora no configurada, config inválida) y el spooler solo interpreta
    excepciones: sin convertirlo, daba el ticket por impreso y lo descartaba.
    """
    pass


# Cola de trabajos de impresión optimizada - mayor capacidad y procesamiento más rápido  
print_queue = Queue(maxsize=500)  # Aumentar capacidad para mayor throughput

# Worker threads pool para procesamiento paralelo
worker_threads = []
MAX_WORKERS = 3  # Número de workers concurrentes
def report_queue_status():
    """Monitorea el estado de la cola y alerta sobre problemas de acumulación"""
    qsize = print_queue.qsize()
    
    # Alertar sobre cola ocupada (más de 50 comandas)
    if qsize > 50:
        logging.warning(f"Print queue busy: {qsize} jobs waiting")
        
        if qsize > 100:
            logging.error(f"Print queue overloaded: {qsize} jobs waiting")
            
            # Publicar alerta crítica de cola sobrecargada
            publish_error(
                error_type="QUEUE_OVERLOADED",
                error_message=f"Print queue has {qsize} pending jobs (capacity: 500)",
                context={
                    "queue_size": qsize,
                    "max_capacity": 500,
                    "utilization_percent": (qsize / 500) * 100,
                    "active_workers": MAX_WORKERS
                }
            )
        
        elif qsize > 200:
            # Alerta crítica - cola cerca de capacidad máxima
            logging.critical(f"Print queue CRITICAL: {qsize} jobs waiting (near capacity)")
            
            publish_error(
                error_type="QUEUE_NEAR_CAPACITY",
                error_message=f"Print queue critically overloaded with {qsize} jobs",
                context={
                    "queue_size": qsize,
                    "max_capacity": 500,
                    "utilization_percent": (qsize / 500) * 100,
                    "warning": "Queue may start rejecting new jobs soon"
                }
            )
    
    _t = threading.Timer(30.0, report_queue_status)
    _t.daemon = True  # no bloquear el cierre del proceso/tests
    _t.start()  # Reportar cada 30 segundos

def process_print_jobs(worker_id=0):
    """Worker optimizado para procesar trabajos de impresión con detección de comandas trabadas"""

    
    # Umbral de tiempo para considerar una comanda como trabada
    STUCK_JOB_THRESHOLD = 30.0  # 30 segundos
    
    while True:
        try:
            # Obtener trabajo con timeout para permitir shutdown limpio
            job_data = print_queue.get(timeout=1.0)
            if job_data is None:
                logger.info(f"Worker {worker_id} received shutdown signal")
                break
            
            jsonTicket, q = job_data
            printer_name = jsonTicket.get('printerName', 'unknown')
            
            start_time = time.time()
            try:
                result = runTraductor(jsonTicket, q)
                processing_time = time.time() - start_time
                
                # Respuesta optimizada sin nested dicts innecesarios
                q.put({"success": True, "result": result, "processing_time": processing_time})
                
                # Detectar trabajos lentos (pueden indicar problemas)
                if processing_time > 5.0:
                    logger.warning(f"Slow print job completed in {processing_time:.2f}s by worker {worker_id} for printer '{printer_name}'")
                    
                    # Alertar si el trabajo está cerca de trabarse
                    if processing_time > 15.0:
                        publish_error(
                            error_type="SLOW_PRINT_JOB",
                            error_message=f"Print job took {processing_time:.2f}s to complete",
                            context={
                                "worker_id": worker_id,
                                "printer_name": printer_name,
                                "processing_time": processing_time,
                                "queue_size": print_queue.qsize()
                            }
                        )
                
                # Detectar comandas trabadas (timeout excedido)
                elif processing_time > STUCK_JOB_THRESHOLD:
                    logger.error(f"STUCK JOB DETECTED: Print job took {processing_time:.2f}s (threshold: {STUCK_JOB_THRESHOLD}s)")
                    
                    publish_error(
                        error_type="STUCK_PRINT_JOB",
                        error_message=f"Print job got stuck for {processing_time:.2f}s",
                        context={
                            "worker_id": worker_id,
                            "printer_name": printer_name,
                            "processing_time": processing_time,
                            "threshold": STUCK_JOB_THRESHOLD,
                            "queue_size": print_queue.qsize()
                        }
                    )
                    
            except Exception as e:
                processing_time = time.time() - start_time
                error_msg = str(e)
                logger.error(f"Worker {worker_id} print job failed in {processing_time:.2f}s: {error_msg}")
                
                # Publicar error de trabajo fallido
                publish_error(
                    error_type="PRINT_JOB_FAILED",
                    error_message=f"Print job failed: {error_msg}",
                    context={
                        "worker_id": worker_id,
                        "printer_name": printer_name,
                        "processing_time": processing_time,
                        "error": error_msg
                    },
                    exception=e
                )
                
                q.put({"success": False, "error": error_msg, "processing_time": processing_time})

            print_queue.task_done()
            
        except queue.Empty:
            # Timeout normal, continuar loop
            continue
        except Exception as e:
            logger.error(f"Worker {worker_id} unexpected error: {e}")
            
            publish_error(
                error_type="WORKER_CRITICAL_ERROR",
                error_message=f"Worker {worker_id} encountered critical error",
                context={"worker_id": worker_id},
                exception=e
            )
            continue

# Arranque LAZY de los workers legacy en memoria.
# No se arrancan al importar el módulo: importar ComandosHandler no debe crear
# threads ni timers de fondo (tests, discover, herramientas). Solo se inician si
# se usa el camino síncrono legacy ([Paxaprinter] sync_print_commands=true).
_legacy_workers_started = False
_legacy_workers_lock = threading.Lock()


def _ensure_legacy_workers_started():
    """Inicia una sola vez el pool de workers en memoria y el reporte periódico."""
    global _legacy_workers_started
    if _legacy_workers_started:
        return
    with _legacy_workers_lock:
        if _legacy_workers_started:
            return
        for i in range(MAX_WORKERS):
            worker = threading.Thread(target=process_print_jobs, args=(i,), daemon=True)
            worker.start()
            worker_threads.append(worker)
        report_queue_status()
        _legacy_workers_started = True




def runTraductor(jsonTicket, queue):
    printerName = jsonTicket.pop('printerName')
    # jobId es metadata de dedup del spooler, no un comando: si quedara en el
    # ticket, EscPComandos.run() lo tomaria como accion inexistente.
    jsonTicket.pop('jobId', None)

    try:
        dictSectionConf = configberry.get_config_for_printer(printerName)
    except KeyError as e:
        error_msg = f"Printer not found in configuration: '{printerName}'"
        logger.error(error_msg)
        
        # Publicar error a RabbitMQ
        publish_error(
            error_type="PRINTER_NOT_FOUND",
            error_message=error_msg,
            context={
                "printer_name": printerName,
                "command": jsonTicket
            },
            exception=e
        )
        
        return {"error": f"Impresora no encontrada: {printerName}"}
    except Exception as e:
        error_msg = f"Error reading printer configuration: '{printerName}' - {str(e)}"
        logger.error(error_msg)
        
        # Publicar error a RabbitMQ
        publish_error(
            error_type="PRINTER_CONFIG_ERROR",
            error_message=error_msg,
            context={
                "printer_name": printerName,
                "command": jsonTicket
            },
            exception=e
        )
        
        return {"error": f"Error de configuración: {str(e)}"}


    driverName = dictSectionConf.pop("driver", "Dummy")
    driverName = driverName.lower()

    driverOps = dictSectionConf

    if driverName == "Fiscalberry".lower():
        try:
            comando = FiscalberryComandos()
            host = driverOps.get('host', 'localhost')
            printerName = driverOps.get('printerName', printerName)
            jsonTicket['printerName'] = printerName
            result = comando.run(host, jsonTicket)
            return queue.put(result)
        except Exception as e:
            logger.error(f"Error FiscalberryComandos: {e}")
            return queue.put({"error": f"Error en FiscalberryComandos: {str(e)}"})

    if driverName == "Win32Raw".lower():
        driverName = "Win32Raw"
        driver = printer.Win32Raw

        if not driver.is_usable():
            raise DriverError(f"Driver {driverName} no disponible")


    elif driverName == "Usb".lower():
        driverName = "Usb"

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

    elif driverName == "Bluetooth".lower():
        # Bluetooth printer for Android
        # BluetoothPrinter(mac_address='XX:XX:XX:XX:XX:XX', timeout=10)

        
        # Validar MAC address
        if 'mac_address' not in driverOps and 'macAddress' not in driverOps:
            raise DriverError("MAC address requerida para Bluetooth: use 'mac_address' en config")
        
        # Normalizar nombre de parámetro
        if 'macAddress' in driverOps:
            driverOps['mac_address'] = driverOps.pop('macAddress')
        
        # Importar driver Bluetooth custom
        from fiscalberry.common.bluetooth_printer import BluetoothPrinter
        driver_class = BluetoothPrinter
        driverName = "Bluetooth"

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
    
    # Manejar drivers custom (ej: Bluetooth) que ya tienen driver_class asignado
    if driverName == "Bluetooth":
        # Ya está configurado arriba con BluetoothPrinter
        pass
    else:
        try:
            driver_class = getattr(printer, driverName)
            if not callable(driver_class):
                raise DriverError(f"Driver {driverName} is not callable")
        except AttributeError:
            raise DriverError(f"Driver {driverName} not found in printer module")
        except Exception as e:
            raise DriverError(f"Error loading driver {driverName}: {e}")

    # Extraer columns antes de crear el driver (no es un parámetro del driver)
    columns = driverOps.pop('columns', None)
    
    try:
        driver = driver_class(**driverOps)
    except Exception as e:
        raise DriverError(f"Error creando driver {driverName}: {e}")

    # ---- Modo RAW: el backend manda bytes ESC/POS ya renderizados ----
    # Permite cambiar cualquier formato (arqueo, comanda, etc.) deployando solo el
    # backend, sin actualizar los Fiscalberry de la calle. El cliente solo escupe
    # los bytes a la impresora vía _raw(); no interpreta el contenido.
    raw_cmd = jsonTicket.get("printRaw")
    if not raw_cmd and jsonTicket.get("type") == "raw":
        raw_cmd = jsonTicket  # variante: envelope plano {type:raw,data,encoding}
    if raw_cmd:
        import base64, gzip
        data = base64.b64decode(raw_cmd["data"])
        if (raw_cmd.get("encoding") or "gzip+base64") in ("gzip", "gzip+base64"):
            data = gzip.decompress(data)
        driver._raw(data)
        try:
            driver.close()
        except Exception:
            pass
        logger.info(f"Impresión RAW OK en '{printerName}' ({len(data)} bytes)")
        return {"message": "Impresion RAW exitosa", "result": "ok", "bytes": len(data)}

    try:
        comando = EscPComandos(driver, columns=columns)
        result = comando.run(jsonTicket)
        
        analyze_printer_response(result, printerName)
        
        return {"message": "Impresión exitosa", "result": result}
    except Exception as e:
        error_msg = f"Print error: {str(e)}"
        logging.error(error_msg)
        
        # Detectar tipo específico de error y publicar
        error_type, description = PrinterErrorDetector.detect_and_publish_error(
            error_message=error_msg,
            exception=e,
            context={
                "printer_name": printerName,
                "driver": driverName,
                "driver_ops": driverOps,
                "command": jsonTicket
            }
        )
        
        raise e


# ---------------------------------------------------------------------------
# Spooler durable (cola persistente en disco) para el camino MQTT.
# Desacopla "recibi de la nube" de "imprimi": el ACK se hace al PERSISTIR, y la
# impresion se reintenta hasta lograrse (tolerante a impresora caida / reinicios
# / mala conectividad). Deduplica reentregas QoS1 por job_id.
# ---------------------------------------------------------------------------
_print_spooler = None
_print_spooler_lock = threading.Lock()


def _spooler_print_fn(ticket):
    """Imprime un ticket ya persistido. Lanza excepcion si falla (-> reintento).

    Integra el circuit breaker por impresora (Fase 8): si el circuito de esa
    impresora esta abierto, no se toca el driver y se lanza CircuitOpenError para
    que el spooler reprograme con backoff. Exito -> cierra circuito; fallo -> lo
    registra (puede abrirlo tras varios fallos consecutivos).
    """
    from fiscalberry.common.printer_circuit_breaker import (
        get_circuit_breaker, CircuitOpenError)

    printer_name = ticket.get("printerName")
    breaker = get_circuit_breaker()

    if printer_name and not breaker.allow(printer_name):
        raise CircuitOpenError(
            f"Circuito abierto para '{printer_name}': impresora con fallos recientes")

    try:
        result = runTraductor(dict(ticket), Queue())

        # runTraductor no siempre lanza: ante "impresora no encontrada" o un
        # error de configuración DEVUELVE {"error": ...}. El spooler solo
        # entiende excepciones, así que sin esto daba el trabajo por "impreso
        # OK" y lo descartaba: el ticket se perdía en silencio y jamás se
        # reintentaba, ni siquiera después de configurar la impresora.
        if isinstance(result, dict) and result.get("error"):
            raise PrintJobError(str(result["error"]))

        if printer_name:
            breaker.record_success(printer_name)
        return result
    except Exception:
        if printer_name:
            breaker.record_failure(printer_name)
        raise


def get_print_spooler():
    """Spooler durable (singleton, lazy)."""
    global _print_spooler
    if _print_spooler is None:
        with _print_spooler_lock:
            if _print_spooler is None:
                from fiscalberry.common.print_spooler import DurablePrintSpooler
                _print_spooler = DurablePrintSpooler(_spooler_print_fn)
    return _print_spooler


def shutdown_print_spooler():
    """Cierra el spooler durable de forma ordenada, si llegó a crearse.

    NO lo instancia si nunca se usó (evita crear un .db solo para cerrarlo).
    Pensado para invocarse al detener el servicio (SIGTERM/stop): antes el
    proceso terminaba con `os._exit()` sin tocar el spooler en absoluto (ver
    issue fiscalberry#165, propuesta 3). Con PRAGMA synchronous=FULL los jobs
    ya son durables sin este cierre ordenado, pero cerrar bien evita dejar el
    WAL creciendo entre reinicios frecuentes (ej. auto-actualización).
    """
    global _print_spooler
    with _print_spooler_lock:
        sp = _print_spooler
        _print_spooler = None
    if sp is not None:
        try:
            sp.stop()
        except Exception as e:
            logger.debug("Error deteniendo el spooler durable: %s", e)


def _is_sync_print_mode():
    """Modo legacy: responder de forma sincrona con el resultado real de impresion.

    Por defecto False -> se usa el spooler durable (persiste y responde "aceptado",
    imprime con reintentos, tolera impresora caida/reinicios). Activar solo si hay
    clientes Socket.IO que dependan del resultado inmediato de impresion:
        [Paxaprinter] sync_print_commands = true
    """
    try:
        val = configberry.get("Paxaprinter", "sync_print_commands", fallback="false")
    except Exception:
        val = "false"
    return str(val).strip().lower() in ("true", "1", "yes", "on")


def _compute_job_id(jsonTicket):
    """job_id estable para dedup en el spooler.

    Usa 'jobId' si viene en el ticket; si no, un sha1 del payload normalizado.
    Mismo criterio conceptual que RabbitMQConsumer._on_message() para que un mismo
    ticket no se imprima dos veces.
    """
    import hashlib
    jid = jsonTicket.get("jobId")
    if jid:
        return str(jid)
    payload = json.dumps(jsonTicket, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class ComandosHandler:
    """Convierte un JSON a Comando Fiscal Para Cualquier tipo de Impresora fiscal"""

    traductores = {}

    def send_command(self, comando):
        response = {}
        
        try:
            if isinstance(comando, str):
                jsonMes = json.loads(comando, strict=False)
            elif isinstance(comando, dict):
                jsonMes = comando
            elif isinstance(comando, bytes):
                jsonMes = json.loads(comando.decode("utf-8"), strict=False)
            else:
                raise TypeError(f"Tipo no soportado: {type(comando).__name__}")
            
            response = self.__json_to_comando(jsonMes)
            
        except TypeError as e:
            errtxt = "Invalid command data type: %s" % e
            logger.exception(errtxt)
            response["err"] = errtxt
            
            # Publicar error a RabbitMQ
            publish_error(
                error_type="INVALID_COMMAND_ERROR",
                error_message=errtxt,
                context={"comando": str(comando)[:500]},
                exception=e
            )
            
        except TraductorException as e:
            errtxt = "Command translation error: %s" % str(e)
            logger.exception(errtxt)
            response["err"] = errtxt
            
            # Publicar error a RabbitMQ
            publish_error(
                error_type="TRANSLATOR_ERROR",
                error_message=errtxt,
                context={"comando": str(comando)[:500]},
                exception=e
            )
            
        except KeyError as e:
            errtxt = "Invalid command for printer type: %s" % e
            logger.exception(errtxt)
            response["err"] = errtxt
            
            # Publicar error a RabbitMQ
            publish_error(
                error_type="INVALID_COMMAND_ERROR",
                error_message=errtxt,
                context={"comando": str(comando)[:500]},
                exception=e
            )
            
        except Exception as e:
            errtxt = "Unknown error: " + repr(e) + " - " + str(e)
            logger.exception(errtxt)
            response["err"] = errtxt
            
            # Publicar error a RabbitMQ
            publish_error(
                error_type="UNKNOWN_ERROR",
                error_message=errtxt,
                context={"comando": str(comando)[:500]},
                exception=e
            )

        if "err" in response:
            logger.error(f"Error: {response.get('err')}")
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
                # Log con JSON compacto del ticket
                ticket_copy = {k: v for k, v in jsonTicket.items() if k != 'printerName'}
                logger.info(f"Imprimiendo: '{printer_name}' {json.dumps(ticket_copy, ensure_ascii=False)}")

                # Camino DURABLE por defecto: persistir en el spooler y responder
                # "aceptado" de inmediato. La impresion real se hace con reintentos
                # (tolera impresora caida / reinicios). Deduplica por job_id.
                if not _is_sync_print_mode():
                    job_id = _compute_job_id(jsonTicket)
                    spooler = get_print_spooler()
                    is_new = spooler.enqueue(job_id, jsonTicket, printer_name)
                    rta["rta"] = {
                        "accepted": True,
                        "queued": True,
                        "duplicate": not is_new,
                        "job_id": job_id,
                        "pending_count": spooler.pending_count(),
                        "failed_count": spooler.failed_count(),
                    }
                    logger.info(
                        "Encolado durable: '%s' job=%s (nuevo=%s, pending=%s, failed=%s)",
                        printer_name, job_id, is_new,
                        rta["rta"]["pending_count"], rta["rta"]["failed_count"])
                    return rta

                # Camino LEGACY sincrono ([Paxaprinter] sync_print_commands=true):
                # workers en memoria + respuesta con el resultado real de impresion.
                _ensure_legacy_workers_started()

                # Procesamiento optimizado con cola de alta velocidad
                q = Queue()
                
                # Verificar capacidad de cola antes de agregar
                current_queue_size = print_queue.qsize()
                if current_queue_size > 400:  # 80% de capacidad
                    logger.warning(f"Print queue near capacity: {current_queue_size}/500")
                
                try:
                    # Agregar trabajo sin bloqueo
                    print_queue.put_nowait((jsonTicket, q))
                    
                    # Timeout de 30 segundos para detectar comandas trabadas
                    result = q.get(timeout=30)
                    
                    if isinstance(result, dict):
                        if not result.get("success", True):
                            error_msg = result.get("error", "Error desconocido en la impresión")
                            logger.error(f"Print job failed: {error_msg}")
                            
                            # Publicar error de impresión fallida
                            publish_error(
                                error_type="PRINT_JOB_ERROR",
                                error_message=error_msg,
                                context={
                                    "printer_name": printer_name,
                                    "processing_time": result.get("processing_time", 0)
                                }
                            )
                            
                            rta["err"] = error_msg
                        else:
                            processing_time = result.get("processing_time", 0)
                            if processing_time > 0:
                                logger.info(f"Print OK: '{printer_name}' ({processing_time:.2f}s)")
                            else:
                                logger.info(f"Print OK: '{printer_name}'")
                            rta["rta"] = result.get("result", result)
                    else:
                        logger.info(f"Print OK: '{printer_name}'")
                        rta["rta"] = result
                        
                except queue.Full:
                    error_msg = f"Print queue full ({current_queue_size}/500). Cannot queue job for '{printer_name}'"
                    logger.error(error_msg)
                    
                    # Publicar alerta de cola llena
                    publish_error(
                        error_type="QUEUE_FULL",
                        error_message=error_msg,
                        context={
                            "printer_name": printer_name,
                            "queue_size": current_queue_size,
                            "max_capacity": 500
                        }
                    )
                    
                    rta["err"] = error_msg
                    
                except queue.Empty:
                    error_msg = f"Print TIMEOUT for '{printer_name}' (30s) - Job may be stuck"
                    logger.error(error_msg)
                    
                    # Publicar alerta de timeout (comanda trabada)
                    publish_error(
                        error_type="PRINT_TIMEOUT",
                        error_message=error_msg,
                        context={
                            "printer_name": printer_name,
                            "timeout_seconds": 30,
                            "queue_size": print_queue.qsize()
                        }
                    )
                    
                    rta["err"] = error_msg
                    
                except Exception as e:
                    error_msg = f"Print queue error: {e}"
                    logger.error(error_msg, exc_info=True)
                    
                    # Publicar error de cola
                    publish_error(
                        error_type="QUEUE_ERROR",
                        error_message=error_msg,
                        context={"printer_name": printer_name},
                        exception=e
                    )
                    
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

            # Acciones sobre la cola del spooler durable (issue #166): el
            # equipo puede correr headless (CLI, sin GUI), así que el aviso
            # visual no alcanza para toda la flota. Estos dos comandos son el
            # "endpoint para drenar o descartar" operable de forma remota
            # (server -> SIO/MQTT -> acá), guiado por los contadores que ya
            # viajan por heartbeat/getStatus.
            elif 'imprimirPendientes' in jsonTicket:
                rta["rta"] = self._imprimirPendientes()

            elif 'descartarPendientes' in jsonTicket:
                rta["rta"] = self._descartarPendientes()
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

    def _imprimirPendientes(self):
        """Comando remoto 'imprimir todos' (issue #166): reintenta la cola.

        Re-encola los 'failed' (dead-letter) para que el worker del spooler
        los retome de inmediato. `requeue_failed()` ya existía pero nadie la
        llamaba desde ningún comando: era código muerto.
        """
        spooler = get_print_spooler()
        n = spooler.requeue_failed()
        return {
            "action": "imprimirPendientes",
            "rta": {
                "requeued": n,
                "pending_count": spooler.pending_count(),
                "failed_count": spooler.failed_count(),
            },
        }

    def _descartarPendientes(self):
        """Comando remoto 'descartar' (issue #166): vacía la cola sin imprimir.

        Destructivo a propósito: se tiran comprobantes fiscales y comandas
        sin imprimir. `discard_all()` deja constancia en el log (WARNING).
        """
        spooler = get_print_spooler()
        n = spooler.discard_all()
        return {
            "action": "descartarPendientes",
            "rta": {
                "discarded": n,
                "pending_count": spooler.pending_count(),
                "failed_count": spooler.failed_count(),
            },
        }

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
