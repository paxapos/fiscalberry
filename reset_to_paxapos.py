"""Script para resetear config.ini a usar el servidor paxapos"""
import os
import sys

# Agregar el directorio src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fiscalberry.common.Configberry import Configberry

def main():
    config = Configberry()
    
    print("\n=== RESETEANDO CONFIG.INI A PAXAPOS ===\n")
    
    # Dejar los campos vacíos para que SocketIO los rellene con paxapos
    config.set("RabbitMq", {
        "host": "",
        "port": "",
        "user": "",
        "password": "",
        "vhost": "",
        "queue": ""
    })
    
    print("✓ Config.ini reseteado - ahora usará www.paxapos.com:5672")
    print("\nConfiguración actual:")
    print(f"  host: '{config.get('RabbitMq', 'host')}'")
    print(f"  port: '{config.get('RabbitMq', 'port')}'")
    print(f"  user: '{config.get('RabbitMq', 'user')}'")

if __name__ == "__main__":
    main()
