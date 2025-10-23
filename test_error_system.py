#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prueba para el sistema de errores de Fiscalberry
Simula diferentes tipos de errores para verificar que se publican correctamente
"""

import sys
import json
import time
import os
from pathlib import Path

# Agregar el directorio src al path para importar módulos de Fiscalberry
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fiscalberry.common.rabbitmq.error_publisher import publish_error

def test_direct_error_publisher():
    """Prueba directa del publicador de errores"""
    print("\n=== PRUEBA 1: Publicador de errores directo ===")
    
    try:
        # Simular diferentes tipos de errores
        errors_to_test = [
            {
                "error_type": "PRINTER_CONNECTION_ERROR",
                "error_message": "No se pudo conectar a la impresora USB",
                "context": {
                    "printer_name": "EPSON_TM_T20",
                    "driver": "USB",
                    "vendor_id": "0x04b8",
                    "product_id": "0x0202"
                }
            },
            {
                "error_type": "CASH_DRAWER_ERROR", 
                "error_message": "Error al abrir cajón: timeout, comando alternativo falló",
                "context": {
                    "primary_error": "Timeout waiting for response",
                    "secondary_error": "Alternative command failed",
                    "exception_types": ["TimeoutError", "ConnectionError"]
                }
            },
            {
                "error_type": "PRINTER_ACTION_ERROR",
                "error_message": "Error ejecutando acción 'printFacturaElectronica': Invalid paper size",
                "context": {
                    "action": "printFacturaElectronica",
                    "params": {"encabezado": {"tipo_factura": "A"}, "items": []},
                    "exception_type": "ValueError"
                }
            },
            {
                "error_type": "RABBITMQ_PROCESSING_ERROR",
                "error_message": "Error procesando comando JSON: Malformed JSON data",
                "context": {
                    "raw_data": "{'invalid': json}",
                    "exception_type": "JSONDecodeError"
                }
            }
        ]
        
        for i, error_data in enumerate(errors_to_test, 1):
            print(f"\nEnviando error {i}: {error_data['error_type']}")
            publish_error(**error_data)
            print(f"✓ Error {i} publicado exitosamente")
            time.sleep(1)  # Pausa entre errores
            
    except Exception as e:
        print(f"✗ Error en prueba directa: {e}")

def monitor_rabbitmq_connection():
    """Monitorea la conexión a RabbitMQ"""
    print("\n=== PRUEBA 2: Verificación de conexión RabbitMQ ===")
    
    try:
        from fiscalberry.common.Configberry import Configberry
        
        config = Configberry()
        
        # Verificar configuración de RabbitMQ
        print("Verificando configuración de RabbitMQ...")
        
        rabbitmq_config = {}
        if config.has_section('RabbitMq'):
            for key in config.options('RabbitMq'):
                rabbitmq_config[key] = config.get('RabbitMq', key)
        
        print(f"Configuración RabbitMQ: {rabbitmq_config}")
        
        # Verificar configuración de tenant
        tenant = None
        if config.has_section('Paxaprinter'):
            tenant = config.get('Paxaprinter', 'tenant', fallback=None)
        
        print(f"Tenant configurado: {tenant}")
        
        if not tenant:
            print("⚠ No hay tenant configurado - los errores irán solo al panel de desarrollador")
        else:
            print(f"✓ Errores se enviarán a tenant '{tenant}' y panel de desarrollador")
            
    except Exception as e:
        print(f"✗ Error verificando configuración: {e}")

def test_multi_tenant_errors():
    """Simula errores para múltiples tenants"""
    print("\n=== PRUEBA 3: Errores multi-tenant ===")
    
    test_errors = [
        {
            "error_type": "PRINTER_CONNECTION_ERROR",
            "error_message": "No se pudo conectar con la impresora fiscal Hasar 715v2",
            "context": {
                "printer_name": "HASAR_PRINCIPAL",
                "driver": "Hasar715v2",
                "port": "/dev/ttyUSB0",
                "timeout": 30
            }
        },
        {
            "error_type": "JSON_PARSE_ERROR", 
            "error_message": "Error parseando comando JSON: campo 'items' requerido",
            "context": {
                "command": {"action": "print_ticket", "invalid": True},
                "line_number": 15
            }
        },
        {
            "error_type": "PROCESSING_ERROR",
            "error_message": "Error procesando cola RabbitMQ: timeout en respuesta de impresora",
            "context": {
                "queue_name": "restaurant_main_queue",
                "processing_time": 45.2,
                "timeout_limit": 30
            }
        }
    ]
    
    # Simular errores para diferentes tenants
    tenants = ["restaurant_demo", "pizzeria_test", "cafe_sample"]
    
    for i, tenant in enumerate(tenants):
        print(f"\n🏢 Simulando errores para tenant: {tenant}")
        
        for j, error in enumerate(test_errors):
            try:
                print(f"   📤 Enviando error {j+1}/{len(test_errors)}: {error['error_type']}")
                
                # Agregar información del tenant al contexto
                error_context = error["context"].copy()
                error_context["simulation"] = True
                error_context["test_sequence"] = f"{i+1}-{j+1}"
                error_context["simulated_tenant"] = tenant
                
                publish_error(
                    error_type=error["error_type"],
                    error_message=error["error_message"],
                    context=error_context
                )
                
                print(f"   ✅ Error enviado exitosamente")
                time.sleep(1)
                
            except Exception as e:
                print(f"   ❌ Error enviando: {e}")
        
        print(f"   ✅ Completado tenant {tenant}")
        time.sleep(2)  # Pausa entre tenants
    
    print(f"\n📊 Total de errores enviados: {len(tenants) * len(test_errors)}")

def main():
    """Ejecuta todas las pruebas del sistema de errores"""
    print("� INICIANDO PRUEBAS DEL SISTEMA DE ERRORES DE FISCALBERRY")
    print("=" * 60)
    
    # Ejecutar todas las pruebas
    monitor_rabbitmq_connection()
    test_direct_error_publisher()
    test_multi_tenant_errors()
    
    print("\n" + "=" * 60)
    print("🏁 PRUEBAS COMPLETADAS")
    print("\nRevisa el panel del desarrollador en http://localhost:8000")
    print("para ver si los errores se están recibiendo correctamente.")
    print("\nTambién puedes revisar los logs de Fiscalberry para ver")
    print("si los errores se están publicando a RabbitMQ.")

if __name__ == "__main__":
    main()