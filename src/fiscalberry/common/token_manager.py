import os
import requests
import json
import platformdirs

# Define your app name and author for proper directory structure
APP_NAME = "fiscalberry"
APP_AUTHOR = "fiscalberry"

# Use platformdirs to get the correct config directory
TOKEN_FILE = os.path.join(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR), "fiscalberry_jwt_token.json")

# Ensure the directory exists
os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)

def do_login(username, password):
    """Autentica al usuario contra el backend y guarda el token JWT."""
    
    from fiscalberry.common.Configberry import Configberry

    cfg = Configberry()
    host = cfg.get("SERVIDOR","sio_host")
    backend_url = host.rstrip("/") + "/login.json"
    
    response = requests.post(backend_url, json={"email": username, "password": password})
    if response.status_code == 200:
        # Login exitoso, guardar el token JWT
        token = response.json().get("jwt")
        if token:
            save_token(token)
            return token
        else:
            raise Exception("Error: No se recibió un token.")
    elif response.status_code == 401:
        error_message = response.json().get("message", f"Error de autenticación 401 (Código {response.status_code}). Verifique sus credenciales.")
        raise Exception(error_message)
    else:
        error_message = response.json().get("message", f"Error de autenticación (Código {response.status_code}). Verifique sus credenciales.")
        raise Exception(error_message)
    return ""
    
    
def save_token(token):
    """Guarda el token JWT en un archivo local."""
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token}, f)


def get_token():
    """Carga el token JWT desde un archivo local."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return data.get("token")
    return None

def delete_token():
    """Elimina el token JWT del archivo local."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)

    

def make_authenticated_request(url, method="GET", data=None):
    """Realiza una solicitud autenticada usando el token JWT."""
    token = get_token()
    if not token:
        raise Exception("No se encontró un token JWT. Inicie sesión primero.")

    headers = {"Authorization": f"Bearer {token}"}
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers)
        else:
            raise ValueError("Método HTTP no soportado.")
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error en la solicitud: {e}")
        return None