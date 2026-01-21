#!/usr/bin/env python3
"""
Utilidad para diagnosticar problemas de conexión con MQTT (RabbitMQ MQTT Plugin).
Ayuda a identificar si el problema es DNS, conectividad de red, o configuración de MQTT.
"""

import socket
import sys
import argparse
import time
from typing import Dict, Any
import paho.mqtt.client as mqtt


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
        print("  - Verificar que RabbitMQ MQTT plugin esté habilitado")
        print("  - Puerto MQTT por defecto es 1883")
        print("  - Verificar firewall")
        return False
    except Exception as e:
        print(f"✗ Red: Error conectando a {host}:{port}: {e}")
        return False


def check_mqtt_connection(host: str, port: int, user: str, password: str) -> bool:
    """Verifica la conexión completa a MQTT."""
    connected = False
    connection_result = None
    
    def on_connect(client, userdata, flags, rc):
        nonlocal connected, connection_result
        connection_result = rc
        if rc == 0:
            connected = True
    
    try:
        # Crear cliente MQTT
        client = mqtt.Client(
            client_id="fiscalberry-diagnostic",
            clean_session=True,
            protocol=mqtt.MQTTv311
        )
        
        # Configurar credenciales
        client.username_pw_set(user, password)
        
        # Configurar callback
        client.on_connect = on_connect
        
        # Conectar
        client.connect(host, port, keepalive=60)
        
        # Iniciar loop y esperar conexión
        client.loop_start()
        
        # Esperar con timeout
        timeout = 10
        start = time.time()
        while connection_result is None and (time.time() - start) < timeout:
            time.sleep(0.1)
        
        # Desconectar
        client.loop_stop()
        client.disconnect()
        
        if connection_result == 0:
            print(f"✓ MQTT: Conexión exitosa a {host}:{port}")
            print(f"  Usuario: {user}")
            return True
        else:
            # Mensajes de error específicos de MQTT
            error_messages = {
                1: "Protocolo incorrecto",
                2: "Identificador de cliente inválido",
                3: "Servidor no disponible",
                4: "Usuario/contraseña incorrectos",
                5: "No autorizado"
            }
            error_msg = error_messages.get(connection_result, f"Error desconocido (código {connection_result})")
            print(f"✗ MQTT: {error_msg}")
            print("  Sugerencias:")
            if connection_result == 4:
                print(f"  - Verificar usuario '{user}' existe")
                print("  - Verificar contraseña")
            elif connection_result == 5:
                print(f"  - Verificar permisos del usuario '{user}'")
            return False
            
    except Exception as e:
        print(f"✗ MQTT: Error inesperado: {e}")
        return False


def get_config_from_file(config_file: str = None) -> Dict[str, Any]:
    """Intenta leer la configuración del archivo config.ini de Fiscalberry."""
    try:
        from fiscalberry.common.Configberry import Configberry
        config = Configberry()
        return {
            'host': config.get("RabbitMq", "host"),
            'port': int(config.get("RabbitMq", "port", fallback="1883")),
            'user': config.get("RabbitMq", "user"),
            'password': config.get("RabbitMq", "password")
        }
    except Exception as e:
        print(f"No se pudo leer configuración de Fiscalberry: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(description='Diagnosticar conexión MQTT')
    parser.add_argument('--host', default='rabbitmq', help='Hostname del broker MQTT')
    parser.add_argument('--port', type=int, default=1883, help='Puerto MQTT (default: 1883)')
    parser.add_argument('--user', default='guest', help='Usuario MQTT')
    parser.add_argument('--password', default='guest', help='Contraseña MQTT')
    parser.add_argument('--from-config', action='store_true', help='Usar configuración de Fiscalberry')
    
    args = parser.parse_args()
    
    print("=== Diagnóstico de conexión MQTT ===\n")
    
    # Si se especifica --from-config, intentar leer del archivo de configuración
    if args.from_config:
        config = get_config_from_file()
        if config:
            args.host = config['host']
            args.port = config['port']
            args.user = config['user']
            args.password = config['password']
            print(f"Usando configuración de Fiscalberry:")
            print(f"  Host: {args.host}")
            print(f"  Puerto: {args.port}")
            print(f"  Usuario: {args.user}\n")
    
    print(f"Probando conexión a {args.host}:{args.port}...\n")
    
    # 1. Verificar resolución DNS
    dns_ok = check_dns_resolution(args.host)
    
    # 2. Verificar conectividad de puerto
    port_ok = False
    if dns_ok:
        port_ok = check_port_connectivity(args.host, args.port)
    
    # 3. Verificar conexión MQTT completa
    mqtt_ok = False
    if port_ok:
        mqtt_ok = check_mqtt_connection(args.host, args.port, args.user, args.password)
    
    print("\n=== Resumen ===")
    print(f"DNS: {'✓' if dns_ok else '✗'}")
    print(f"Red: {'✓' if port_ok else '✗'}")
    print(f"MQTT: {'✓' if mqtt_ok else '✗'}")
    
    if mqtt_ok:
        print("\n🎉 Conexión exitosa! MQTT está funcionando correctamente.")
        return 0
    else:
        print("\n❌ Hay problemas con la conexión. Revisar los errores anteriores.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
