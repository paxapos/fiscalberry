# /opt/fiscalberryNUEVO/scripts/check_internet.py
import socket
import sys

def check_internet(host="8.8.8.8", port=53, timeout=5):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error as ex:
        print(f"Error checking internet connection: {ex}")
        return False

if not check_internet():
    sys.exit(1)  # Exit with non-zero status to prevent the service from starting