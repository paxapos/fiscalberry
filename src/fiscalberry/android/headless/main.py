#!/usr/bin/env python3
"""
Android CLI Main - Entry Point (Headless)

Reusa ServiceController, Configberry, FiscalberrySio del desktop CLI.
Diferencias: headless (sin input/webbrowser), abre navegador automáticamente.

Ubicación: fiscalberry/android/headless/main.py
"""
import os
import sys
import signal
import time

# Setup crash reporting FIRST
from fiscalberry.android.headless.crash_reporter import setup_crash_reporting
setup_crash_reporting()

# Import from common (REUTILIZADO de desktop)
from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.service_controller import ServiceController
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.discover import send_discover

logger = getLogger("AndroidCLI")


def open_adoption_url_android(adoption_url):
    """
    Abre automáticamente la URL de adopción en Chrome.
    Usa Android Intent - igual que botón de pantalla adopt.
    """
    try:
        from jnius import autoclass
        
        Intent = autoclass('android.content.Intent')
        Uri = autoclass('android.net.Uri')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        
        intent = Intent()
        intent.setAction(Intent.ACTION_VIEW)
        intent.setData(Uri.parse(adoption_url))
        
        activity = PythonActivity.mActivity
        activity.startActivity(intent)
        
        logger.critical(f"✓ Navegador abierto: {adoption_url}")
        return True
        
    except Exception as e:
        logger.error(f"Error abriendo navegador: {e}", exc_info=True)
        return False


def wait_for_adoption_headless(adoption_url):
    """
    Espera adopción CON apertura automática de navegador.
    
    Flujo:
    1. Abre Chrome automáticamente
    2. Polling loop cada 30s hasta adopción
    """
    configberry = Configberry()
    
    logger.info("Comercio NO adoptado")
    logger.info(f"URL adopción: {adoption_url}")
    
    # Abrir navegador automáticamente
    if not open_adoption_url_android(adoption_url):
        logger.warning("No se pudo abrir navegador - usuario debe hacerlo manualmente")
    
    logger.info("Esperando adopción (check cada 30s)...")
    
    check_count = 0
    while True:
        time.sleep(30)
        check_count += 1
        
        configberry = Configberry()  # Reload
        if configberry.is_comercio_adoptado():
            logger.critical("✓ COMERCIO ADOPTADO")
            return True
        
        logger.debug(f"Check #{check_count} - aún no adoptado")


def main():
    """
    Main entry point Android CLI.
    REUTILIZA ServiceController del desktop CLI.
    """
    logger.critical("="*70)
    logger.critical("FISCALBERRY ANDROID CLI - STARTING")
    logger.critical("="*70)
    logger.info(f"PID: {os.getpid()}")
    logger.info(f"Python: {sys.version}")
    
    # 1. Config
    configberry = Configberry()
    uuid = configberry.get("SERVIDOR", "uuid", fallback="")
    host = configberry.get("SERVIDOR", "sio_host", fallback="https://beta.paxapos.com")
    
    if not uuid:
        logger.critical("UUID NO configurado - ABORTANDO")
        sys.exit(1)
    
    logger.info(f"UUID: {uuid[:12]}...")
    logger.info(f"Host: {host}")
    
    # 2. Discover (REUTILIZADO)
    try:
        send_discover()
        logger.info("✓ Discover sent")
    except Exception as e:
        logger.error(f"Discover failed: {e}")
    
    # 3. Check adoption
    if not configberry.is_comercio_adoptado():
        adoption_url = f"{host}/adopt/{uuid}"
        logger.warning("Comercio NO adoptado - iniciando flow...")
        wait_for_adoption_headless(adoption_url)
    
    # 4. Start services (REUTILIZA ServiceController completo)
    logger.info("Iniciando ServiceController...")
    controller = ServiceController()
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.critical(f"Signal {signum} - SHUTDOWN")
        controller.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        controller.start()  # ← MISMO código que desktop CLI
        logger.critical("✓ ServiceController started - SISTEMA OPERACIONAL")
        
        # Loop forever
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        logger.critical("KeyboardInterrupt")
    except Exception as e:
        logger.critical(f"Error: {e}", exc_info=True)
    finally:
        controller.stop()
        logger.critical("ANDROID CLI STOPPED")


if __name__ == "__main__":
    main()
