"""
Panel de Desarrollador para Fiscalberry - Aplicación Web Independiente

Esta aplicación permite a los desarrolladores monitorear errores de múltiples
tenants/comercios de Fiscalberry desde un dashboard web centralizado.

Características:
- Monitoreo en tiempo real de subcolas de errores por tenant
- Dashboard con filtros por tenant, tipo de error, fecha
- Notificaciones WebSocket en tiempo real
- Autenticación JWT para desarrolladores
- API REST para integración con otros sistemas
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import jwt
import pika
import pika.exceptions
from pydantic import BaseModel
import threading
import queue
import os
from pathlib import Path

# Configuración
SECRET_KEY = os.getenv("DEVELOPER_PANEL_SECRET", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas

# Configuración de logging más silenciosa para RabbitMQ
logging.getLogger("pika").setLevel(logging.CRITICAL)
logging.getLogger("pika.adapters").setLevel(logging.CRITICAL)
logging.getLogger("pika.adapters.utils").setLevel(logging.CRITICAL)
logging.getLogger("pika.adapters.blocking_connection").setLevel(logging.CRITICAL)
logging.getLogger("pika.adapters.utils.selector_ioloop_adapter").setLevel(logging.CRITICAL)
logging.getLogger("pika.adapters.utils.connection_workflow").setLevel(logging.CRITICAL)

# Configuración de logging principal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fiscalberry Developer Panel",
    description="Panel de monitoreo de errores para desarrolladores",
    version="1.0.0"
)

# Configuración de seguridad
security = HTTPBearer()

# Modelos Pydantic
class LoginRequest(BaseModel):
    username: str
    password: str

class ErrorMessage(BaseModel):
    timestamp: str
    tenant: str
    error_type: str
    message: str
    device_uuid: str
    context: Dict
    exception: Optional[Dict] = None

class DeveloperInfo(BaseModel):
    username: str
    role: str
    permissions: List[str]

# Almacén en memoria para errores (en producción usar Redis o DB)
error_store: Dict[str, List[ErrorMessage]] = {}
connected_websockets: Set[WebSocket] = set()

# Credenciales de desarrolladores (en producción usar base de datos)
DEVELOPERS = {
    "dev1": {
        "password": "dev123",  # En producción usar hash
        "role": "senior_developer",
        "permissions": ["view_all_tenants", "export_data", "real_time_monitoring"]
    },
    "dev2": {
        "password": "dev456",
        "role": "developer", 
        "permissions": ["view_assigned_tenants", "real_time_monitoring"]
    }
}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Crea un token JWT para autenticación."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifica el token JWT."""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return username
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_developer_info(username: str = Depends(verify_token)) -> DeveloperInfo:
    """Obtiene información del desarrollador autenticado."""
    if username not in DEVELOPERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Desarrollador no encontrado"
        )
    
    dev_data = DEVELOPERS[username]
    return DeveloperInfo(
        username=username,
        role=dev_data["role"],
        permissions=dev_data["permissions"]
    )

class RabbitMQErrorConsumer:
    """Consumer de RabbitMQ para escuchar errores de todos los tenants."""
    
    def __init__(self, rabbitmq_config: Dict[str, str]):
        self.config = rabbitmq_config
        self.connection = None
        self.channel = None
        self.is_running = False
        self.message_queue = queue.Queue()
        
    def connect(self):
        """Conecta a RabbitMQ."""
        try:
            credentials = pika.PlainCredentials(
                self.config["user"], 
                self.config["password"]
            )
            
            parameters = pika.ConnectionParameters(
                host=self.config["host"],
                port=int(self.config["port"]),
                virtual_host=self.config["vhost"],
                credentials=credentials,
                socket_timeout=5,
                connection_attempts=1
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declarar exchange de errores
            self.channel.exchange_declare(
                exchange="fiscalberry_errors",
                exchange_type='direct',
                durable=True
            )
            
            logger.info("RabbitMQ Error Consumer conectado exitosamente")
            return True
            
        except Exception as e:
            # Ser más silencioso con errores de conexión
            logger.debug(f"RabbitMQ no disponible: {e}")
            return False
    
    def start_consuming(self):
        """Inicia el consumo de mensajes de error."""
        if not self.connect():
            return
            
        self.is_running = True
        
        def callback(ch, method, properties, body):
            try:
                error_data = json.loads(body.decode('utf-8'))
                error_msg = ErrorMessage(**error_data)
                
                # Almacenar error
                tenant = error_msg.tenant
                if tenant not in error_store:
                    error_store[tenant] = []
                
                error_store[tenant].append(error_msg)
                
                # Mantener solo últimos 1000 errores por tenant
                if len(error_store[tenant]) > 1000:
                    error_store[tenant] = error_store[tenant][-1000:]
                
                # Notificar a WebSockets conectados
                asyncio.create_task(broadcast_error(error_msg))
                
                logger.info(f"Error recibido de tenant {tenant}: {error_msg.error_type}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                logger.error(f"Error procesando mensaje: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        # Declarar cola temporal para escuchar todos los errores
        result = self.channel.queue_declare(queue='developer_panel_errors', durable=True)
        queue_name = result.method.queue
        
        # Como el exchange es 'direct', necesitamos hacer bind para cada tenant conocido
        # Por ahora, creamos una cola que capture todos los mensajes del exchange
        # usando una cola especial para el panel de desarrollador
        
        # Declarar la cola específica del panel
        self.channel.queue_declare(queue='developer_panel_all_errors', durable=True)
        
        # Para capturar errores de todos los tenants, necesitamos una estrategia diferente
        # Opción 1: Usar un exchange de tipo 'fanout' adicional
        # Opción 2: Modificar el error_publisher para enviar también a una cola global
        
        # Por ahora, implementamos una solución temporal:
        # Escuchamos en una cola específica donde se replican todos los errores
        try:
            self.channel.queue_bind(
                exchange="fiscalberry_errors",
                queue="developer_panel_all_errors",
                routing_key="*"  # Esto no funcionará con direct, necesitamos una cola especial
            )
        except pika.exceptions.ChannelClosedByBroker:
            # Si falla, declaramos el exchange como topic para usar wildcards
            logger.info("Recreando exchange como topic para wildcard support")
            self.channel = self.connection.channel()
            
            # Declarar exchange como topic que soporta wildcards
            self.channel.exchange_declare(
                exchange="fiscalberry_errors_topic",
                exchange_type='topic',
                durable=True
            )
            
            self.channel.queue_bind(
                exchange="fiscalberry_errors_topic",
                queue="developer_panel_all_errors",
                routing_key="*.errors"  # Captura todos los {tenant}.errors
            )
        
        self.channel.basic_consume(
            queue="developer_panel_all_errors",
            on_message_callback=callback
        )
        
        logger.info("Iniciando consumo de errores...")
        
        try:
            self.channel.start_consuming()
        except Exception as e:
            logger.error(f"Error en consumo: {e}")
        finally:
            self.is_running = False

# Instancia global del consumer
rabbitmq_consumer = None

async def broadcast_error(error_msg: ErrorMessage):
    """Envía el error a todos los WebSockets conectados."""
    if connected_websockets:
        message = {
            "type": "new_error",
            "data": error_msg.dict()
        }
        
        # Crear lista de WebSockets para evitar modificación durante iteración
        websockets_copy = connected_websockets.copy()
        
        for websocket in websockets_copy:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error enviando a WebSocket: {e}")
                connected_websockets.discard(websocket)

def start_rabbitmq_consumer():
    """Inicia el consumer de RabbitMQ en un hilo separado."""
    global rabbitmq_consumer
    
    # Intentar obtener configuración desde Fiscalberry
    rabbitmq_config = None
    try:
        # Importar Configberry de Fiscalberry
        import sys
        import os
        fiscalberry_src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
        if fiscalberry_src_path not in sys.path:
            sys.path.insert(0, fiscalberry_src_path)
        
        from fiscalberry.common.Configberry import Configberry
        config = Configberry()
        
        # Intentar configuración de RabbitMq primero (más confiable)
        if config.config.has_section("RabbitMq"):
            rabbitmq_config = {
                "host": config.get("RabbitMq", "host", fallback="localhost"),
                "port": config.get("RabbitMq", "port", fallback="5672"),
                "user": config.get("RabbitMq", "user", fallback="guest"),
                "password": config.get("RabbitMq", "password", fallback="guest"),
                "vhost": config.get("RabbitMq", "vhost", fallback="/")
            }
            logger.info("Usando configuración RabbitMQ desde RabbitMq (Fiscalberry)")
        
        # Fallback a sección Paxaprinter
        elif config.config.has_section("Paxaprinter"):
            rabbitmq_config = {
                "host": config.get("Paxaprinter", "rabbitmq_host", fallback="localhost"),
                "port": config.get("Paxaprinter", "rabbitmq_port", fallback="5672"),
                "user": config.get("Paxaprinter", "rabbitmq_user", fallback="guest"),
                "password": config.get("Paxaprinter", "rabbitmq_password", fallback="guest"),
                "vhost": config.get("Paxaprinter", "rabbitmq_vhost", fallback="/")
            }
            logger.info("Usando configuración RabbitMQ desde Paxaprinter (Fiscalberry)")
        
    except Exception as e:
        logger.debug(f"No se pudo cargar configuración de Fiscalberry: {e}")
    
    # Configuración de fallback desde variables de entorno
    if not rabbitmq_config:
        rabbitmq_config = {
            "host": os.getenv("RABBITMQ_HOST", "localhost"),
            "port": os.getenv("RABBITMQ_PORT", "5672"),
            "user": os.getenv("RABBITMQ_USER", "guest"),
            "password": os.getenv("RABBITMQ_PASSWORD", "guest"),
            "vhost": os.getenv("RABBITMQ_VHOST", "/")
        }
        logger.info("Usando configuración RabbitMQ desde variables de entorno")
    
    logger.info(f"Configuración RabbitMQ: {rabbitmq_config['host']}:{rabbitmq_config['port']}")
    
    rabbitmq_consumer = RabbitMQErrorConsumer(rabbitmq_config)
    
    def run_consumer():
        try:
            rabbitmq_consumer.start_consuming()
        except Exception as e:
            logger.debug(f"RabbitMQ consumer no pudo iniciar: {e}")
    
    consumer_thread = threading.Thread(target=run_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Intento de conexión RabbitMQ iniciado")

def stop_rabbitmq_consumer():
    """Detiene el consumer de RabbitMQ."""
    global rabbitmq_consumer
    if rabbitmq_consumer:
        rabbitmq_consumer.is_running = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el ciclo de vida de la aplicación."""
    # Startup
    logger.info("Iniciando Fiscalberry Developer Panel...")
    start_rabbitmq_consumer()
    yield
    # Shutdown
    logger.info("Cerrando Fiscalberry Developer Panel...")
    stop_rabbitmq_consumer()

app = FastAPI(
    title="Fiscalberry Developer Panel",
    description="Panel de monitoreo de errores para desarrolladores",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/auth/login")
async def login(login_request: LoginRequest):
    """Endpoint de autenticación para desarrolladores."""
    username = login_request.username
    password = login_request.password
    
    if username not in DEVELOPERS or DEVELOPERS[username]["password"] != password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "developer_info": DeveloperInfo(
            username=username,
            role=DEVELOPERS[username]["role"],
            permissions=DEVELOPERS[username]["permissions"]
        )
    }

@app.get("/api/tenants")
async def get_tenants(developer: DeveloperInfo = Depends(get_developer_info)):
    """Obtiene lista de tenants con errores."""
    tenants = list(error_store.keys())
    
    # Filtrar por permisos si es necesario
    if "view_all_tenants" not in developer.permissions:
        # Implementar lógica de filtrado por tenants asignados
        pass
    
    return {"tenants": tenants}

@app.get("/api/errors/{tenant}")
async def get_tenant_errors(
    tenant: str, 
    limit: int = 100,
    error_type: Optional[str] = None,
    developer: DeveloperInfo = Depends(get_developer_info)
):
    """Obtiene errores de un tenant específico."""
    if tenant not in error_store:
        return {"errors": []}
    
    errors = error_store[tenant]
    
    # Filtrar por tipo de error si se especifica
    if error_type:
        errors = [e for e in errors if e.error_type == error_type]
    
    # Limitar cantidad de resultados
    errors = errors[-limit:]
    
    return {
        "tenant": tenant,
        "errors": [error.dict() for error in errors],
        "total_count": len(error_store.get(tenant, []))
    }

@app.get("/api/stats")
async def get_error_stats(developer: DeveloperInfo = Depends(get_developer_info)):
    """Obtiene estadísticas generales de errores."""
    stats = {}
    
    for tenant, errors in error_store.items():
        stats[tenant] = {
            "total_errors": len(errors),
            "error_types": {},
            "last_error": None
        }
        
        # Contar tipos de errores
        for error in errors:
            error_type = error.error_type
            if error_type not in stats[tenant]["error_types"]:
                stats[tenant]["error_types"][error_type] = 0
            stats[tenant]["error_types"][error_type] += 1
        
        # Último error
        if errors:
            stats[tenant]["last_error"] = errors[-1].timestamp
    
    return {"stats": stats}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket para notificaciones en tiempo real."""
    await websocket.accept()
    connected_websockets.add(websocket)
    
    try:
        # Enviar mensaje de bienvenida
        welcome_msg = {
            "type": "connected",
            "message": "Conectado al panel de desarrollador"
        }
        await websocket.send_text(json.dumps(welcome_msg))
        
        # Mantener conexión viva
        while True:
            try:
                # Esperar por mensajes del cliente (ping/pong)
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Enviar ping para mantener conexión
                ping_msg = {"type": "ping"}
                await websocket.send_text(json.dumps(ping_msg))
                
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado")
    except Exception as e:
        logger.error(f"Error en WebSocket: {e}")
    finally:
        connected_websockets.discard(websocket)

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Página principal del dashboard."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fiscalberry Developer Panel</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
            .header { background: #2c3e50; color: white; padding: 20px; margin: -20px -20px 20px -20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .login-form { background: white; padding: 20px; border-radius: 8px; max-width: 400px; margin: 0 auto; }
            .dashboard { display: none; }
            .tenant-card { background: white; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #3498db; }
            .error-item { padding: 10px; margin: 5px 0; background: #ffeaa7; border-radius: 4px; }
            .error-critical { background: #fab1a0; }
            .error-warning { background: #ffeaa7; }
            .error-info { background: #74b9ff; color: white; }
            button { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
            button:hover { background: #2980b9; }
            input { width: 100%; padding: 10px; margin: 5px 0; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
            .status { position: fixed; top: 20px; right: 20px; padding: 10px; border-radius: 4px; color: white; }
            .status.connected { background: #00b894; }
            .status.disconnected { background: #e74c3c; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔧 Fiscalberry Developer Panel</h1>
            <p>Monitoreo en tiempo real de errores por tenant</p>
        </div>
        
        <div class="container">
            <div id="loginForm" class="login-form">
                <h2>Acceso para Desarrolladores</h2>
                <input type="text" id="username" placeholder="Usuario" />
                <input type="password" id="password" placeholder="Contraseña" />
                <button onclick="login()">Iniciar Sesión</button>
                <div id="loginError" style="color: red; margin-top: 10px; display: none;"></div>
            </div>
            
            <div id="dashboard" class="dashboard">
                <div id="status" class="status disconnected">Desconectado</div>
                
                <h2>Estadísticas de Errores</h2>
                <div id="stats"></div>
                
                <h2>Tenants Activos</h2>
                <div id="tenants"></div>
                
                <h2>Errores Recientes</h2>
                <div id="recent-errors"></div>
            </div>
        </div>

        <script>
            let token = '';
            let websocket = null;
            
            async function login() {
                const username = document.getElementById('username').value;
                const password = document.getElementById('password').value;
                
                try {
                    const response = await fetch('/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, password })
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        token = data.access_token;
                        document.getElementById('loginForm').style.display = 'none';
                        document.getElementById('dashboard').style.display = 'block';
                        connectWebSocket();
                        loadDashboard();
                    } else {
                        document.getElementById('loginError').textContent = 'Credenciales inválidas';
                        document.getElementById('loginError').style.display = 'block';
                    }
                } catch (error) {
                    console.error('Error en login:', error);
                }
            }
            
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                websocket = new WebSocket(`${protocol}//${window.location.host}/ws`);
                
                websocket.onopen = function() {
                    document.getElementById('status').className = 'status connected';
                    document.getElementById('status').textContent = 'Conectado';
                };
                
                websocket.onclose = function() {
                    document.getElementById('status').className = 'status disconnected';
                    document.getElementById('status').textContent = 'Desconectado';
                };
                
                websocket.onmessage = function(event) {
                    const message = JSON.parse(event.data);
                    if (message.type === 'new_error') {
                        addNewErrorToUI(message.data);
                    }
                };
            }
            
            async function loadDashboard() {
                await loadStats();
                await loadTenants();
            }
            
            async function loadStats() {
                try {
                    const response = await fetch('/api/stats', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    const data = await response.json();
                    
                    let statsHtml = '';
                    for (const [tenant, stats] of Object.entries(data.stats)) {
                        statsHtml += `
                            <div class="tenant-card">
                                <h3>${tenant}</h3>
                                <p>Total errores: ${stats.total_errors}</p>
                                <p>Último error: ${stats.last_error || 'N/A'}</p>
                            </div>
                        `;
                    }
                    document.getElementById('stats').innerHTML = statsHtml;
                } catch (error) {
                    console.error('Error loading stats:', error);
                }
            }
            
            async function loadTenants() {
                try {
                    const response = await fetch('/api/tenants', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    const data = await response.json();
                    
                    let tenantsHtml = '';
                    for (const tenant of data.tenants) {
                        tenantsHtml += `
                            <div class="tenant-card">
                                <h3>${tenant}</h3>
                                <button onclick="loadTenantErrors('${tenant}')">Ver Errores</button>
                            </div>
                        `;
                    }
                    document.getElementById('tenants').innerHTML = tenantsHtml;
                } catch (error) {
                    console.error('Error loading tenants:', error);
                }
            }
            
            async function loadTenantErrors(tenant) {
                try {
                    const response = await fetch(`/api/errors/${tenant}?limit=10`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    const data = await response.json();
                    
                    let errorsHtml = `<h3>Errores de ${tenant}</h3>`;
                    for (const error of data.errors) {
                        errorsHtml += `
                            <div class="error-item ${getErrorClass(error.error_type)}">
                                <strong>${error.error_type}</strong> - ${error.timestamp}<br>
                                ${error.message}
                            </div>
                        `;
                    }
                    document.getElementById('recent-errors').innerHTML = errorsHtml;
                } catch (error) {
                    console.error('Error loading tenant errors:', error);
                }
            }
            
            function addNewErrorToUI(errorData) {
                const recentErrors = document.getElementById('recent-errors');
                const errorDiv = document.createElement('div');
                errorDiv.className = `error-item ${getErrorClass(errorData.error_type)}`;
                errorDiv.innerHTML = `
                    <strong>${errorData.error_type}</strong> - ${errorData.timestamp}<br>
                    <strong>Tenant:</strong> ${errorData.tenant}<br>
                    ${errorData.message}
                `;
                recentErrors.insertBefore(errorDiv, recentErrors.firstChild);
                
                // Mantener solo los últimos 20 errores en UI
                const errors = recentErrors.querySelectorAll('.error-item');
                if (errors.length > 20) {
                    recentErrors.removeChild(errors[errors.length - 1]);
                }
            }
            
            function getErrorClass(errorType) {
                if (errorType.includes('CRITICAL') || errorType.includes('UNKNOWN')) return 'error-critical';
                if (errorType.includes('WARNING')) return 'error-warning';
                return 'error-info';
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Función duplicada removida - se usa la versión correcta arriba

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)