#!/usr/bin/env python3
"""
Script de prueba para verificar el comportamiento del manejo de errores mejorado.
"""

import sys
import os
import threading
import time

# Agregar el directorio src al path para importar los módulos
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fiscalberry.common.rabbitmq.process_handler import RabbitMQProcessHandler
from fiscalberry.common.Configberry import Configberry
import queue

def test_error_handling():
    """Prueba el manejo de errores con configuración que causará error DNS."""
    print("=== Prueba del manejo de errores mejorado ===\n")
    
    # Configurar valores que causarán error DNS
    config = Configberry()
    
    # Guardar configuración original
    original_config = {
        "host": config.get("RabbitMq", "host"),
        "port": config.get("RabbitMq", "port"),
        "user": config.get("RabbitMq", "user"),
        "password": config.get("RabbitMq", "password"),
        "vhost": config.get("RabbitMq", "vhost"),
        "queue": config.get("RabbitMq", "queue"),
    }
    
    try:
        # Configurar para causar error DNS (hostname inexistente)
        test_config = {
            "host": "rabbitmq",  # Este hostname causará error DNS
            "port": "5672",
            "user": "guest",
            "password": "guest",
            "vhost": "/",
            "queue": "test-queue"
        }
        
        config.set("RabbitMq", test_config)
        print(f"Configuración de prueba establecida: {test_config}")
        
        # Crear queue para mensajes
        message_queue = queue.Queue()
        
        # Inicializar el manejador de proceso
        handler = RabbitMQProcessHandler()
        
        print("\nIniciando RabbitMQ process handler...")
        print("Esperando ver errores DNS mejorados y sistema de backoff...\n")
        
        # Iniciar el handler
        handler.start(message_queue)
        
        # Esperar un poco para ver algunos intentos de conexión
        print("Dejando que el sistema intente conectar por 30 segundos...")
        print("Deberías ver mensajes de error más descriptivos y reintentos con backoff.\n")
        
        time.sleep(30)
        
        print("\nDeteniendo el handler...")
        handler.stop(timeout=2)
        print("Handler detenido.")
        
    except KeyboardInterrupt:
        print("\nInterrumpido por usuario.")
        handler.stop(timeout=2)
    
    finally:
        # Restaurar configuración original
        config.set("RabbitMq", original_config)
        print("Configuración original restaurada.")

if __name__ == "__main__":
    test_error_handling()
