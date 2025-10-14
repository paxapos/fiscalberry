#!/usr/bin/env python3
"""
Script para simular la adopción de un comercio agregando configuración de RabbitMQ.
"""
import sys
import os

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fiscalberry.common.Configberry import Configberry

def adopt_comercio(tenant_name, site_name, alias, rabbitmq_host="rabbitmq.restodigital.com.ar"):
    """
    Simula la adopción de un comercio configurando la sección Paxaprinter.
    
    Args:
        tenant_name: Nombre del tenant (ej: "mirestaurante")
        site_name: Nombre del sitio (ej: "Mi Restaurante")
        alias: Alias del sitio (ej: "local-centro")
        rabbitmq_host: Host de RabbitMQ (por defecto: rabbitmq.restodigital.com.ar)
    """
    try:
        configberry = Configberry()
        
        print("\n" + "="*70)
        print("SIMULACIÓN DE ADOPCIÓN DE COMERCIO")
        print("="*70)
        
        # Mostrar estado actual
        uuid_value = configberry.get("SERVIDOR", "uuid", fallback="")
        is_adopted_before = configberry.is_comercio_adoptado()
        
        print(f"\nUUID del dispositivo: {uuid_value}")
        print(f"Estado antes de adoptar: {'ADOPTADO' if is_adopted_before else 'NO ADOPTADO'}")
        
        # Configurar la sección Paxaprinter
        print(f"\nConfigurando comercio con:")
        print(f"  Tenant: {tenant_name}")
        print(f"  Nombre del sitio: {site_name}")
        print(f"  Alias: {alias}")
        print(f"  RabbitMQ Host: {rabbitmq_host}")
        
        success = configberry.set("Paxaprinter", {
            "tenant": tenant_name,
            "site_name": site_name,
            "alias": alias,
            "rabbitmq_host": rabbitmq_host,
            "rabbitmq_port": "5672",
            "rabbitmq_user": "fiscalberry",
            "rabbitmq_password": "fiscalberry123",
            "rabbitmq_vhost": "/"
        })
        
        if success:
            is_adopted_after = configberry.is_comercio_adoptado()
            print(f"\nEstado después de adoptar: {'ADOPTADO' if is_adopted_after else 'NO ADOPTADO'}")
            
            if is_adopted_after:
                print("\n✓ ¡Comercio adoptado exitosamente!")
                print("\nEl CLI ahora iniciará los servicios normalmente.")
            else:
                print("\n✗ Error: El comercio no fue adoptado correctamente")
                return False
        else:
            print("\n✗ Error al guardar la configuración")
            return False
        
        print("\n" + "="*70)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def remove_adoption():
    """
    Elimina la configuración de adopción (para pruebas).
    """
    try:
        configberry = Configberry()
        
        print("\n" + "="*70)
        print("ELIMINANDO CONFIGURACIÓN DE ADOPCIÓN")
        print("="*70)
        
        if configberry.config.has_section("Paxaprinter"):
            success = configberry.delete_section("Paxaprinter")
            if success:
                print("\n✓ Sección [Paxaprinter] eliminada exitosamente")
                print("\nEl comercio ahora aparecerá como NO ADOPTADO")
            else:
                print("\n✗ Error al eliminar la sección")
                return False
        else:
            print("\nLa sección [Paxaprinter] no existe")
        
        print("\n" + "="*70)
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def show_menu():
    """Muestra un menú para gestionar la adopción"""
    print("\n" + "="*70)
    print("   GESTIÓN DE ADOPCIÓN DE COMERCIO")
    print("="*70)
    print("\nOpciones:")
    print("  1. Simular adopción (agregar configuración Paxaprinter)")
    print("  2. Remover adopción (eliminar configuración)")
    print("  3. Ver estado actual")
    print("  4. Salir")
    print("="*70)
    
    while True:
        try:
            opcion = input("\nSelecciona una opción (1-4): ").strip()
            
            if opcion == "1":
                print("\n--- Configuración del comercio ---")
                tenant = input("Nombre del tenant (ej: mirestaurante): ").strip()
                if not tenant:
                    print("El tenant es obligatorio")
                    continue
                
                site_name = input("Nombre del sitio (ej: Mi Restaurante): ").strip()
                if not site_name:
                    site_name = tenant
                
                alias = input("Alias (ej: local-centro): ").strip()
                if not alias:
                    alias = tenant + "-principal"
                
                rabbitmq_host = input("RabbitMQ Host [rabbitmq.restodigital.com.ar]: ").strip()
                if not rabbitmq_host:
                    rabbitmq_host = "rabbitmq.restodigital.com.ar"
                
                adopt_comercio(tenant, site_name, alias, rabbitmq_host)
                break
                
            elif opcion == "2":
                remove_adoption()
                break
                
            elif opcion == "3":
                os.system("python3 test_adoption_check.py")
                
            elif opcion == "4":
                print("\nSaliendo...")
                break
            else:
                print("Opción inválida. Por favor, selecciona 1-4.")
                
        except KeyboardInterrupt:
            print("\n\nSaliendo...")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "remove":
            remove_adoption()
        elif sys.argv[1] == "adopt" and len(sys.argv) >= 3:
            tenant = sys.argv[2]
            site_name = sys.argv[3] if len(sys.argv) > 3 else tenant
            alias = sys.argv[4] if len(sys.argv) > 4 else tenant + "-principal"
            adopt_comercio(tenant, site_name, alias)
        else:
            print("Uso:")
            print("  python3 manage_adoption.py                    # Menú interactivo")
            print("  python3 manage_adoption.py adopt <tenant> [site_name] [alias]")
            print("  python3 manage_adoption.py remove             # Eliminar adopción")
    else:
        show_menu()
