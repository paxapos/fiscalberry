"""Ver contenido actual del config.ini"""
import os
import sys

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fiscalberry.common.Configberry import Configberry

def main():
    config = Configberry()
    
    print("\n=== CONTENIDO ACTUAL DE CONFIG.INI ===\n")
    print("[RabbitMq]")
    print(f"  host = {config.get('RabbitMq', 'host', fallback='(vacío)')}")
    print(f"  port = {config.get('RabbitMq', 'port', fallback='(vacío)')}")
    print(f"  user = {config.get('RabbitMq', 'user', fallback='(vacío)')}")
    print(f"  password = {config.get('RabbitMq', 'password', fallback='(vacío)')}")
    print(f"  vhost = {config.get('RabbitMq', 'vhost', fallback='(vacío)')}")
    print(f"  queue = {config.get('RabbitMq', 'queue', fallback='(vacío)')}")
    
    print(f"\nRuta del archivo: {config.get_config_file_name()}")

if __name__ == "__main__":
    main()
