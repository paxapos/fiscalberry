#!/usr/bin/env python3
"""
Utilidad para diagnosticar problemas de conexión con RabbitMQ.
Ayuda a identificar si el problema es DNS, conectividad de red, o configuración de RabbitMQ.
"""

import socket
import pika
import sys
import argparse
from typing import Dict, Any

def check_dns_resolution(host: str) -> bool:
    """Verifica si el hostname se puede resolver."""
    try:
        result = socket.getaddrinfo(host, None)
        print(f"✓ DNS: {host} se resuelve a {result[0][4][0]}")
        return True
    except socket.gaierror as e:
        print(f"✗ DNS: Error resolviendo {host}: {e}")
        print("  Sugerencias:")
        print("  - Verificar /etc/hosts")
        print("  - Verificar configuración DNS")
        print("  - Usar IP directa en lugar del hostname")
        return False

def check_port_connectivity(host: str, port: int, timeout: int = 5) -> bool:
    """Verifica si el puerto está abierto."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            print(f"✓ Red: Puerto {port} en {host} está abierto")
            return True
    except socket.timeout:
        print(f"✗ Red: Timeout conectando a {host}:{port}")
        return False
    except ConnectionRefusedError:
        print(f"✗ Red: Conexión rechazada en {host}:{port}")
        print("  Sugerencias:")
        print("  - Verificar que RabbitMQ esté ejecutándose")
        print("  - Verificar firewall")
        return False
    except Exception as e:
        print(f"✗ Red: Error conectando a {host}:{port}: {e}")
        return False

def check_rabbitmq_connection(host: str, port: int, user: str, password: str, vhost: str = "/") -> bool:
    """Verifica la conexión completa a RabbitMQ."""
    try:
        params = pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host=vhost,
            credentials=pika.PlainCredentials(user, password),
            socket_timeout=10,
            connection_attempts=1
        )
        
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        
        # Verificar que podemos declarar un exchange temporal
        test_exchange = "test_connection_check"
        channel.exchange_declare(exchange=test_exchange, exchange_type='direct', durable=False, auto_delete=True)
        channel.exchange_delete(exchange=test_exchange)
        
        connection.close()
        print(f"✓ RabbitMQ: Conexión exitosa a {host}:{port}")
        print(f"  Usuario: {user}")
        print(f"  VHost: {vhost}")
        return True
        
    except pika.exceptions.ProbableAuthenticationError as e:
        print(f"✗ RabbitMQ: Error de autenticación: {e}")
        print("  Sugerencias:")
        print(f"  - Verificar usuario '{user}' existe")
        print(f"  - Verificar contraseña")
        print(f"  - Verificar permisos en vhost '{vhost}'")
        return False
    except pika.exceptions.ProbableAccessDeniedError as e:
        print(f"✗ RabbitMQ: Acceso denegado: {e}")
        print("  Sugerencias:")
        print(f"  - Verificar permisos del usuario '{user}' en vhost '{vhost}'")
        return False
    except pika.exceptions.AMQPConnectionError as e:
        print(f"✗ RabbitMQ: Error de conexión AMQP: {e}")
        return False
    except Exception as e:
        print(f"✗ RabbitMQ: Error inesperado: {e}")
        return False

def get_config_from_file(config_file: str = None) -> Dict[str, Any]:
    """Intenta leer la configuración del archivo config.ini de Fiscalberry."""
    try:
        from fiscalberry.common.Configberry import Configberry
        config = Configberry()
        return {
            'host': config.get("RabbitMq", "host"),
            'port': int(config.get("RabbitMq", "port")),
            'user': config.get("RabbitMq", "user"),
            'password': config.get("RabbitMq", "password"),
            'vhost': config.get("RabbitMq", "vhost", "/")
        }
    except Exception as e:
        print(f"No se pudo leer configuración de Fiscalberry: {e}")
        return {}

def main():
    parser = argparse.ArgumentParser(description='Diagnosticar conexión RabbitMQ')
    parser.add_argument('--host', default='rabbitmq', help='Hostname de RabbitMQ')
    parser.add_argument('--port', type=int, default=5672, help='Puerto de RabbitMQ')
    parser.add_argument('--user', default='guest', help='Usuario de RabbitMQ')
    parser.add_argument('--password', default='guest', help='Contraseña de RabbitMQ')
    parser.add_argument('--vhost', default='/', help='Virtual host de RabbitMQ')
    parser.add_argument('--from-config', action='store_true', help='Usar configuración de Fiscalberry')
    
    args = parser.parse_args()
    
    print("=== Diagnóstico de conexión RabbitMQ ===\n")
    
    # Si se especifica --from-config, intentar leer del archivo de configuración
    if args.from_config:
        config = get_config_from_file()
        if config:
            args.host = config['host']
            args.port = config['port']
            args.user = config['user']
            args.password = config['password']
            args.vhost = config['vhost']
            print(f"Usando configuración de Fiscalberry:")
            print(f"  Host: {args.host}")
            print(f"  Puerto: {args.port}")
            print(f"  Usuario: {args.user}")
            print(f"  VHost: {args.vhost}\n")
    
    print(f"Probando conexión a {args.host}:{args.port}...\n")
    
    # 1. Verificar resolución DNS
    dns_ok = check_dns_resolution(args.host)
    
    # 2. Verificar conectividad de puerto
    port_ok = False
    if dns_ok:
        port_ok = check_port_connectivity(args.host, args.port)
    
    # 3. Verificar conexión RabbitMQ completa
    rabbitmq_ok = False
    if port_ok:
        rabbitmq_ok = check_rabbitmq_connection(args.host, args.port, args.user, args.password, args.vhost)
    
    print("\n=== Resumen ===")
    print(f"DNS: {'✓' if dns_ok else '✗'}")
    print(f"Red: {'✓' if port_ok else '✗'}")
    print(f"RabbitMQ: {'✓' if rabbitmq_ok else '✗'}")
    
    if rabbitmq_ok:
        print("\n🎉 Conexión exitosa! RabbitMQ está funcionando correctamente.")
        return 0
    else:
        print("\n❌ Hay problemas con la conexión. Revisar los errores anteriores.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
