#!/usr/bin/env python3
import sys
import webbrowser

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("CLI")
from fiscalberry.common.service_controller import ServiceController
from fiscalberry.common.Configberry import Configberry

def show_adoption_menu(uuid_value, host):
    """
    Muestra el menú de adopción cuando el comercio no está adoptado.
    """
    # Usar la misma estructura de URL que el GUI
    adoption_url = f"{host}/adopt/{uuid_value}"
    
    print("\n" + "="*70)
    print("   COMERCIO NO ADOPTADO - CONFIGURACIÓN REQUERIDA")
    print("="*70)
    print("\nEste dispositivo aún no tiene un comercio asociado.")
    print("\nSe ha creado una cola de mensajería con UUID: " + uuid_value[:8] + "...")
    print("\nPara completar la configuración y adoptar este dispositivo,")
    print("por favor visita el siguiente enlace:\n")
    print(f"   {adoption_url}")
    print("\nAl adoptar el comercio se configurará automáticamente:")
    print("  • Tenant de RabbitMQ")
    print("  • Nombre del sitio")
    print("  • Alias del comercio")
    print("  • Credenciales de RabbitMQ")
    print("\n" + "="*70)
    print("\nOpciones:")
    print("  1. Abrir enlace en el navegador")
    print("  2. Salir")
    print("="*70)
    
    while True:
        try:
            opcion = input("\nSelecciona una opción (1-2): ").strip()
            
            if opcion == "1":
                print(f"\nAbriendo navegador en: {adoption_url}")
                try:
                    webbrowser.open(adoption_url)
                    print("\n¡Navegador abierto! Una vez que hayas adoptado el comercio,")
                    print("reinicia este programa para continuar.\n")
                except Exception as e:
                    logger.error(f"Error al abrir navegador: {e}")
                    print(f"\nNo se pudo abrir el navegador automáticamente.")
                    print(f"Por favor, copia y pega este enlace en tu navegador:\n{adoption_url}\n")
                return False
            elif opcion == "2":
                print("\nSaliendo del programa...")
                return False
            else:
                print("Opción inválida. Por favor, selecciona 1 o 2.")
        except KeyboardInterrupt:
            print("\n\nSaliendo del programa...")
            return False

def main():
    """Función principal que ejecuta el controlador de servicios."""
    logger.info("=== Iniciando Fiscalberry CLI ===")
    logger.info(f"Versión de Python: {sys.version}")
    logger.info(f"Plataforma: {sys.platform}")
    
    # Verificar si el comercio está adoptado
    configberry = Configberry()
    
    if not configberry.is_comercio_adoptado():
        logger.info("Comercio no adoptado. Mostrando menú de adopción.")
        uuid_value = configberry.get("SERVIDOR", "uuid", fallback="")
        host = configberry.get("SERVIDOR", "sio_host", fallback="https://beta.paxapos.com")
        
        if not uuid_value:
            logger.error("UUID no encontrado en la configuración")
            print("\nError: No se pudo obtener el UUID del dispositivo.")
            print("Por favor, verifica tu archivo de configuración.\n")
            sys.exit(1)
        
        # Mostrar el menú de adopción (usando la misma URL que el GUI)
        show_adoption_menu(uuid_value, host)
        sys.exit(0)
    
    # Si el comercio está adoptado, continuar con el flujo normal
    logger.info("Comercio adoptado. Iniciando servicios...")
    controller = ServiceController()
    
    try:
        logger.info("Iniciando controlador de servicios...")
        controller.start()
        logger.info("Controlador de servicios iniciado exitosamente")
    except KeyboardInterrupt:
        logger.info("Interrupción de teclado detectada por usuario")
        print("\nInterrupción de teclado detectada. Cerrando servicios...")
        try:
            controller.stop()
            logger.info("Servicios detenidos correctamente")
        except Exception as stop_error:
            logger.error(f"Error al detener servicios: {stop_error}")
        print("Servicio detenido. Saliendo.")
    except Exception as e:
        logger.error(f"Error inesperado en CLI: {e}", exc_info=True)
        print(f"Error inesperado: {e}")
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

