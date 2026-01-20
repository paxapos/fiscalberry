#!/usr/bin/env python3
import sys
import webbrowser
import time
import threading
import os

# Solo imports livianos al inicio
from fiscalberry.common.Configberry import Configberry

# Variable global para reintentos (estilo v1.0.26)
cantRetries = 0

def wait_for_adoption(uuid_value, host):
    """
    Espera a que el comercio sea adoptado, manteniendo la conexión con el servidor.
    Retorna True si la adopción fue exitosa, False si el usuario cancela.
    """
    # Import lazy de FiscalberrySio (solo cuando se necesita)
    from fiscalberry.common.fiscalberry_sio import FiscalberrySio
    
    adoption_url = f"{host}/adopt/{uuid_value}"
    
    print(f"\nID de Cola de Impresion: {uuid_value}")
    print(f"Para adoptar este dispositivo, visita: {adoption_url}")
    print("\nOpciones:")
    print("  1. Abrir link y adoptar comercio")
    print("  2. Salir")
    
    while True:
        try:
            opcion = input("\nSelecciona una opcion (1-2): ").strip()
            
            if opcion == "1":
                try:
                    webbrowser.open(adoption_url)
                    print("Link abierto en el navegador")
                except Exception as e:
                    print(f"No se pudo abrir el navegador. Copia este link: {adoption_url}")
                break
            elif opcion == "2":
                print("Saliendo...")
                return False
            else:
                print("Opcion invalida. Selecciona 1 o 2.")
        except KeyboardInterrupt:
            print("\nSaliendo...")
            return False
    
    # Conectar con el servidor y esperar adopción
    print("Conectado al servidor, esperando adopcion...")
    print("(Presiona Ctrl+C para cancelar)")
    
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
                adoption_completed.set()
                print("\nADOPCION COMPLETADA")
                print("Dispositivo conectado exitosamente")
                print("Iniciando servicios...")
                return
            
            # Mostrar un punto cada 5 verificaciones (10 segundos)
            if check_count % 5 == 0:
                print(".", end="", flush=True)
    
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
        print("\nCancelado por el usuario")
        print("Ejecuta el programa nuevamente para adoptar.")
        adoption_completed.set()
        return False
    except Exception as e:
        print(f"Error: {e}")
        adoption_completed.set()
        return False

def main():
    """Función principal que ejecuta el controlador de servicios."""
    global cantRetries
    
    print("Iniciando Fiscalberry Server")
    
    # Verificar si el comercio está adoptado
    configberry = Configberry()
    
    if not configberry.is_comercio_adoptado():
        uuid_value = configberry.get("SERVIDOR", "uuid", fallback="")
        host = configberry.get("SERVIDOR", "sio_host", fallback="https://beta.paxapos.com")
        
        if not uuid_value:
            cantRetries += 1
            if cantRetries > 5:
                print("No Esta configurado el uuid, MAX RETRIES")
                os._exit(1)
            print("Faltan parametros para conectar a SocketIO.. reconectando en 5s")
            time.sleep(5)
            main()  # Recursión estilo v1.0.26
            return
        
        # Enviar discover ANTES de mostrar el menú
        # CRÍTICO: Esperar a que el servidor confirme el registro antes de mostrar opciones
        print("Registrando dispositivo en el servidor...")
        
        from fiscalberry.common.discover import send_discover
        
        max_retries = 3
        discover_success = False
        
        for attempt in range(1, max_retries + 1):
            try:
                discover_success = send_discover()
                if discover_success:
                    print("Dispositivo registrado correctamente")
                    # Dar tiempo al servidor para completar el commit a DB
                    # El endpoint responde 200 pero el procesamiento interno puede tardar
                    time.sleep(1.5)
                    break
                else:
                    if attempt < max_retries:
                        print(f"Reintentando registro ({attempt}/{max_retries})...")
                        time.sleep(2)
            except Exception as e:
                print(f"Error al enviar discover: {e}")
                if attempt < max_retries:
                    print(f"Reintentando ({attempt}/{max_retries})...")
                    time.sleep(2)
        
        if not discover_success:
            print("No se pudo registrar el dispositivo en el servidor.")
            print("Verifica tu conexion a internet y vuelve a intentar.")
            sys.exit(1)
        
        # Esperar a que se complete la adopción
        adoption_success = wait_for_adoption(uuid_value, host)
        
        if not adoption_success:
            print("Adopcion cancelada o fallida. Saliendo...")
            sys.exit(0)
        
        # Si llegamos aquí, la adopción fue exitosa
        print("Adopcion completada. Continuando con inicio de servicios...")
    
    # Import lazy del ServiceController (solo cuando comercio está adoptado)
    from fiscalberry.common.service_controller import ServiceController
    controller = ServiceController()
    
    try:
        controller.start()
        
    except KeyboardInterrupt:
        pass  # Silencioso como v1.0.26
    except Exception as e:
        print(f"Error occurred: {e}")
        try:
            controller.stop()
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error occurred: {e}")
        os._exit(1)
