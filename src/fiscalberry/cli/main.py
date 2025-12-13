#!/usr/bin/env python3
import sys
import webbrowser
import time
import threading

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("CLI")
from fiscalberry.common.service_controller import ServiceController
from fiscalberry.common.Configberry import Configberry
from fiscalberry.common.discover import send_discover
from fiscalberry.common.fiscalberry_sio import FiscalberrySio

def wait_for_adoption(uuid_value, host):
    """
    Espera a que el comercio sea adoptado, manteniendo la conexión con el servidor.
    Retorna True si la adopción fue exitosa, False si el usuario cancela.
    """
    adoption_url = f"{host}/adopt/{uuid_value}"
    
    print("\n" + "="*60)
    print("   CONFIGURACIÓN DE FISCALBERRY")
    print("="*60)
    print(f"\n  ID de Cola de Impresión: {uuid_value}")
    print(f"\n  Para adoptar este dispositivo, visita:\n  {adoption_url}")
    print("\n" + "="*60)
    print("\n  Opciones:")
    print("    1. Abrir link y adoptar comercio")
    print("    2. Salir")
    print("="*60)
    
    while True:
        try:
            opcion = input("\n  Selecciona una opción (1-2): ").strip()
            
            if opcion == "1":
                try:
                    webbrowser.open(adoption_url)
                    print("\n  ✓ Link abierto en el navegador")
                except Exception as e:
                    logger.error(f"Error al abrir navegador: {e}")
                    print(f"\n  ⚠ No se pudo abrir el navegador.")
                    print(f"     Copia este link: {adoption_url}\n")
                break
            elif opcion == "2":
                print("\n  Saliendo...")
                return False
            else:
                print("  ⚠ Opción inválida. Selecciona 1 o 2.")
        except KeyboardInterrupt:
            print("\n\n  Saliendo...")
            return False
    
    # Conectar con el servidor y esperar adopción
    print("\n" + "="*60)
    print("   ESPERANDO ADOPCIÓN")
    print("="*60)
    print("\n  🔄 Conectado al servidor")
    print("  ⏳ Esperando que completes la adopción en la web...")
    print("\n  (Presiona Ctrl+C para cancelar)\n")
    
    # Crear instancia de SocketIO con los parámetros requeridos
    sio_client = FiscalberrySio(server_url=host, uuid=uuid_value)
    
    # Variable para controlar cuándo se completa la adopción
    adoption_completed = threading.Event()
    
    # Función para monitorear la adopción
    def check_adoption():
        configberry = Configberry()
        check_count = 0
        while not adoption_completed.is_set():
            time.sleep(2)
            check_count += 1
            
            if configberry.is_comercio_adoptado():
                logger.info("Comercio adoptado exitosamente")
                adoption_completed.set()
                print("\n\n" + "="*60)
                print("   ✅ ADOPCIÓN COMPLETADA")
                print("="*60)
                print("\n  ✓ Dispositivo conectado exitosamente")
                print("  ✓ Iniciando servicios...\n")
                return
            
            # Mostrar un punto cada 5 verificaciones (10 segundos)
            if check_count % 5 == 0:
                print("  .", end="", flush=True)
    
    # Iniciar hilo de monitoreo
    monitor_thread = threading.Thread(target=check_adoption, daemon=True)
    monitor_thread.start()
    
    try:
        # Iniciar SocketIO (esto mantendrá la conexión activa)
        sio_thread = threading.Thread(target=sio_client.start, daemon=True)
        sio_thread.start()
        
        # Esperar a que se complete la adopción o se cancele
        while not adoption_completed.is_set():
            time.sleep(0.5)
        
        # Dar tiempo para que el servidor termine de enviar toda la configuración
        time.sleep(2)
        
        return True
        
    except KeyboardInterrupt:
        print("\n\n  ⚠ Cancelado por el usuario")
        print("     Ejecuta el programa nuevamente para adoptar.\n")
        adoption_completed.set()
        return False
    except Exception as e:
        logger.error(f"Error durante la espera de adopción: {e}")
        print(f"\n  ⚠ Error: {e}\n")
        adoption_completed.set()
        return False

def main():
    """Función principal que ejecuta el controlador de servicios."""
    logger.info("=== Iniciando Fiscalberry CLI ===")
    logger.info(f"Versión de Python: {sys.version}")
    logger.info(f"Plataforma: {sys.platform}")
    
    print("\n" + "="*60)
    print("   FISCALBERRY - SISTEMA DE IMPRESIÓN FISCAL")
    print("="*60)
    
    # Verificar si el comercio está adoptado
    configberry = Configberry()
    
    if not configberry.is_comercio_adoptado():
        logger.info("Comercio no adoptado. Enviando discover primero...")
        uuid_value = configberry.get("SERVIDOR", "uuid", fallback="")
        host = configberry.get("SERVIDOR", "sio_host", fallback="https://beta.paxapos.com")
        
        if not uuid_value:
            logger.error("UUID no encontrado en la configuración")
            print("\nError: No se pudo obtener el UUID del dispositivo.")
            print("Por favor, verifica tu archivo de configuración.\n")
            sys.exit(1)
        
        # Enviar discover ANTES de mostrar el menú
        try:
            send_discover()
            logger.info("Discover enviado exitosamente")
        except Exception as e:
            logger.error(f"Error al enviar discover: {e}")
        
        # Esperar a que se complete la adopción
        adoption_success = wait_for_adoption(uuid_value, host)
        
        if not adoption_success:
            logger.info("Adopción cancelada o fallida. Saliendo...")
            sys.exit(0)
        
        # Si llegamos aquí, la adopción fue exitosa - continuar con el flujo normal
        logger.info("Adopción completada. Continuando con inicio de servicios...")
    
    # Si el comercio está adoptado, continuar con el flujo normal
    logger.info("Comercio adoptado. Iniciando servicios...")
    
    # Obtener UUID para mostrarlo
    uuid_display = configberry.get("SERVIDOR", "uuid", fallback="")
    print(f"\n  ID de Cola: {uuid_display}")
    print("\n  🔄 Conectando servicios...")
    
    controller = ServiceController()
    
    try:
        logger.info("Iniciando controlador de servicios...")
        controller.start()
        logger.info("Controlador de servicios iniciado exitosamente")
        
        print("  ✓ Servicios conectados exitosamente")
        print("\n" + "="*60)
        print("   SISTEMA ACTIVO")
        print("="*60)
        print("\n  El sistema está funcionando correctamente.")
        print("  Presiona Ctrl+C para detener.\n")
        
    except KeyboardInterrupt:
        logger.info("Interrupción de teclado detectada por usuario")
        print("\n\n" + "="*60)
        print("   DETENIENDO SERVICIOS")
        print("="*60)
        try:
            controller.stop()
            logger.info("Servicios detenidos correctamente")
            print("\n  ✓ Servicios detenidos correctamente\n")
        except Exception as stop_error:
            logger.error(f"Error al detener servicios: {stop_error}")
            print(f"\n  ⚠ Error al detener: {stop_error}\n")
    except Exception as e:
        logger.error(f"Error inesperado en CLI: {e}", exc_info=True)
        print(f"\n  ⚠ Error: {e}\n")
        try:
            controller.stop()
            logger.info("Servicios detenidos después de error")
        except Exception as stop_error:
            logger.error(f"Error al detener servicios después de excepción: {stop_error}")
        sys.exit(1)
    finally:
        logger.info("=== Finalizando Fiscalberry CLI ===")
        sys.exit(0)

if __name__ == "__main__":
    main()

