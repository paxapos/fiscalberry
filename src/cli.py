#!/usr/bin/env python3
import time
import os, asyncio
import threading

from common.fiscalberry_logger import getLogger
logger = getLogger()


from common.Configberry import Configberry


# importo el modulo que se encarga de la comunicacion con el servidor
from common.discover import send_discover_in_thread

cantRetries = 0


def startSocketio(sio_host, uuid):
    from common.fiscalberry_sio import FiscalberrySio
    
    sio = FiscalberrySio(sio_host, uuid)
    t = sio.start()
    t.join()  # bloquea hasta que ese hilo termine
    logger.warning("Termino ejecucion de server socketio?.. reconectando en 5s")
    

def discover():
    send_discover_in_thread()
    logger.info("Discover enviado")
    

def start_services():
    global cantRetries
    
    configberry = Configberry()


    uuidval = configberry.get("SERVIDOR", "uuid", fallback="")
    if not uuidval:
        if cantRetries > 5:
            logger.error("No Esta configurado el uuid en el archivo de configuracion, MAX RETRIES")
            os._exit(1)
            
        logger.warning("Faltan parametros para conectar a SocketIO.. reconectando en 5s")
        time.sleep(5)
        start_services()
        return
    
    
    logger.info("Iniciando Fiscalberry Server")

    # iniciar en 3 threads distintos los servicios
    discover_thread = threading.Thread(target=discover)
    
    
    sio_host = configberry.get("SERVIDOR", "sio_host")
    socketio_thread = threading.Thread(target=startSocketio, args=(sio_host, uuidval))
    

    discover_thread.start()
    socketio_thread.start()
    discover_thread.join()
    socketio_thread.join()


if __name__ == "__main__":
    try:
        start_services()
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        os._exit(1)

    