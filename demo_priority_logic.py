#!/usr/bin/env python3
"""
Demostración de la nueva lógica de prioridad config.ini vs SocketIO
para configuración de RabbitMQ en Fiscalberry.
"""

import configparser
import os
import sys

def demonstrate_priority_logic():
    """Demuestra cómo funciona la nueva lógica de prioridad"""
    
    # Leer el config.ini real del usuario
    config_path = os.path.expanduser("~/.config/Fiscalberry/config.ini")
    
    if not os.path.exists(config_path):
        print(f"❌ No se encontró {config_path}")
        return
        
    config = configparser.ConfigParser()
    config.read(config_path)
    
    print("🔧 DEMOSTRACIÓN: Lógica de Prioridad RabbitMQ Config.ini vs SocketIO")
    print("=" * 70)
    
    # Mostrar valores actuales del config.ini
    print("\n📄 Valores actuales en config.ini:")
    if config.has_section('RabbitMq'):
        for key in ['host', 'port', 'user', 'password', 'vhost', 'queue']:
            value = config.get('RabbitMq', key, fallback='')
            status = "✓ Tiene valor" if value and value.strip() else "❌ Vacío"
            print(f"  {key}: '{value}' {status}")
    else:
        print("  ❌ No hay sección [RabbitMq]")
    
    # Simular un mensaje SocketIO con valores diferentes
    print("\n📡 Mensaje SocketIO simulado:")
    rabbit_cfg = {
        'host': 'rabbitmq.server.socketio.com',
        'port': '5673',
        'user': 'socketio_user',
        'password': 'socketio_password',
        'vhost': '/socketio_vhost',
        'queue': 'socketio_queue'
    }
    
    for key, value in rabbit_cfg.items():
        print(f"  {key}: '{value}'")
    
    # Aplicar la nueva lógica
    print("\n🎯 APLICANDO NUEVA LÓGICA (config.ini tiene prioridad):")
    print("-" * 50)
    
    def get_config_or_message_value(config_key, message_key, default_value=""):
        """Lógica exacta implementada en process_handler.py"""
        config_value = config.get("RabbitMq", config_key, fallback="") if config.has_section('RabbitMq') else ""
        if config_value and str(config_value).strip():
            print(f"  {config_key}: 📄 config.ini -> '{config_value}'")
            return config_value
        else:
            message_value = rabbit_cfg.get(message_key, default_value)
            print(f"  {config_key}: 📡 SocketIO -> '{message_value}' (config vacío)")
            return message_value
    
    # Aplicar la lógica
    host = get_config_or_message_value("host", "host")
    port_str = get_config_or_message_value("port", "port", "5672")
    user = get_config_or_message_value("user", "user", "guest")
    pwd = get_config_or_message_value("password", "password", "guest")
    vhost = get_config_or_message_value("vhost", "vhost", "/")
    queue = get_config_or_message_value("queue", "queue", "")
    
    # Convertir puerto a entero
    try:
        port = int(port_str)
    except (ValueError, TypeError):
        print(f"  ⚠️  Puerto inválido '{port_str}', usando 5672 por defecto")
        port = 5672
    
    print("\n🎯 CONFIGURACIÓN FINAL QUE USARÍA LA APLICACIÓN:")
    print("=" * 50)
    print(f"  Host:     {host}")
    print(f"  Port:     {port}")
    print(f"  User:     {user}")
    print(f"  Password: {'*' * len(pwd) if pwd else '(vacío)'}")
    print(f"  VHost:    {vhost}")
    print(f"  Queue:    {queue}")
    
    print("\n✅ VENTAJAS DE LA NUEVA LÓGICA:")
    print("  • Config.ini siempre tiene prioridad (control local)")
    print("  • SocketIO solo completa campos vacíos en config.ini")
    print("  • Logs claros muestran el origen de cada valor")
    print("  • Facilita debugging y configuración manual")
    
    print("\n💡 PARA PROBAR:")
    print("  1. Modifica valores en ~/.config/Fiscalberry/config.ini")
    print("  2. Esos valores tendrán prioridad sobre cualquier mensaje SocketIO")
    print("  3. Deja campos vacíos en config.ini para usar valores remotos")

if __name__ == "__main__":
    demonstrate_priority_logic()
