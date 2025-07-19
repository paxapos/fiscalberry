#!/usr/bin/env python3
"""
Script de prueba para verificar la lógica de prioridad config.ini vs SocketIO
en la configuración de RabbitMQ.
"""

import configparser
import tempfile
import os
import sys
sys.path.insert(0, 'src')

def simulate_config_priority_logic():
    """Simula la lógica de prioridad sin dependencias externas"""
    
    # Crear un config temporal para las pruebas
    config = configparser.ConfigParser()
    config.add_section('RabbitMq')
    
    # CASO 1: Config.ini tiene valores, mensaje SocketIO también
    print("=== CASO 1: Config.ini con valores, SocketIO con valores ===")
    config.set('RabbitMq', 'host', 'localhost')
    config.set('RabbitMq', 'port', '5672')
    config.set('RabbitMq', 'user', 'admin')
    config.set('RabbitMq', 'password', 'secret')
    config.set('RabbitMq', 'vhost', '/prod')
    config.set('RabbitMq', 'queue', 'config_queue')
    
    # Datos del mensaje SocketIO (estos deberían ser ignorados)
    rabbit_cfg = {
        'host': 'rabbitmq.server.com',
        'port': '5673',
        'user': 'socketio_user',
        'password': 'socketio_pass',
        'vhost': '/socketio',
        'queue': 'socketio_queue'
    }
    
    def get_config_or_message_value(config_key, message_key, default_value=""):
        """Lógica exacta del código real"""
        config_value = config.get("RabbitMq", config_key, fallback="")
        if config_value and str(config_value).strip():
            print(f"  {config_key}: usando config.ini -> {config_value}")
            return config_value
        else:
            message_value = rabbit_cfg.get(message_key, default_value)
            print(f"  {config_key}: config.ini vacío, usando SocketIO -> {message_value}")
            return message_value
    
    host = get_config_or_message_value("host", "host")
    port_str = get_config_or_message_value("port", "port", "5672")
    user = get_config_or_message_value("user", "user", "guest")
    pwd = get_config_or_message_value("password", "password", "guest")
    vhost = get_config_or_message_value("vhost", "vhost", "/")
    queue = get_config_or_message_value("queue", "queue", "")
    
    print(f"Resultado final: host={host}, port={port_str}, user={user}, vhost={vhost}, queue={queue}")
    assert host == 'localhost', f"Expected localhost, got {host}"
    assert port_str == '5672', f"Expected 5672, got {port_str}"
    assert user == 'admin', f"Expected admin, got {user}"
    assert pwd == 'secret', f"Expected secret, got {pwd}"
    assert vhost == '/prod', f"Expected /prod, got {vhost}"
    assert queue == 'config_queue', f"Expected config_queue, got {queue}"
    print("✓ CASO 1 CORRECTO: Se usaron todos los valores del config.ini\n")
    
    # CASO 2: Config.ini parcialmente vacío
    print("=== CASO 2: Config.ini parcialmente vacío ===")
    config.set('RabbitMq', 'host', 'localhost')  # Tiene valor
    config.set('RabbitMq', 'port', '')  # Vacío
    config.set('RabbitMq', 'user', 'admin')  # Tiene valor
    config.set('RabbitMq', 'password', '')  # Vacío
    config.set('RabbitMq', 'vhost', '/prod')  # Tiene valor
    config.set('RabbitMq', 'queue', '')  # Vacío
    
    host = get_config_or_message_value("host", "host")
    port_str = get_config_or_message_value("port", "port", "5672")
    user = get_config_or_message_value("user", "user", "guest")
    pwd = get_config_or_message_value("password", "password", "guest")
    vhost = get_config_or_message_value("vhost", "vhost", "/")
    queue = get_config_or_message_value("queue", "queue", "")
    
    print(f"Resultado final: host={host}, port={port_str}, user={user}, vhost={vhost}, queue={queue}")
    assert host == 'localhost', f"Expected localhost, got {host}"
    assert port_str == '5673', f"Expected 5673 (from SocketIO), got {port_str}"
    assert user == 'admin', f"Expected admin, got {user}"
    assert pwd == 'socketio_pass', f"Expected socketio_pass (from SocketIO), got {pwd}"
    assert vhost == '/prod', f"Expected /prod, got {vhost}"
    assert queue == 'socketio_queue', f"Expected socketio_queue (from SocketIO), got {queue}"
    print("✓ CASO 2 CORRECTO: Se usó config.ini donde tenía valores, SocketIO donde estaba vacío\n")
    
    # CASO 3: Config.ini completamente vacío
    print("=== CASO 3: Config.ini completamente vacío ===")
    config.set('RabbitMq', 'host', '')
    config.set('RabbitMq', 'port', '')
    config.set('RabbitMq', 'user', '')
    config.set('RabbitMq', 'password', '')
    config.set('RabbitMq', 'vhost', '')
    config.set('RabbitMq', 'queue', '')
    
    host = get_config_or_message_value("host", "host")
    port_str = get_config_or_message_value("port", "port", "5672")
    user = get_config_or_message_value("user", "user", "guest")
    pwd = get_config_or_message_value("password", "password", "guest")
    vhost = get_config_or_message_value("vhost", "vhost", "/")
    queue = get_config_or_message_value("queue", "queue", "")
    
    print(f"Resultado final: host={host}, port={port_str}, user={user}, vhost={vhost}, queue={queue}")
    assert host == 'rabbitmq.server.com', f"Expected rabbitmq.server.com, got {host}"
    assert port_str == '5673', f"Expected 5673, got {port_str}"
    assert user == 'socketio_user', f"Expected socketio_user, got {user}"
    assert pwd == 'socketio_pass', f"Expected socketio_pass, got {pwd}"
    assert vhost == '/socketio', f"Expected /socketio, got {vhost}"
    assert queue == 'socketio_queue', f"Expected socketio_queue, got {queue}"
    print("✓ CASO 3 CORRECTO: Se usaron todos los valores del SocketIO\n")
    
    print("🎉 TODAS LAS PRUEBAS PASARON - La lógica de prioridad funciona correctamente")

if __name__ == "__main__":
    simulate_config_priority_logic()
