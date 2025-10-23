#!/usr/bin/env python3
"""
Fiscalberry Developer Panel - Panel Profesional para Monitoreo de Errores
Version profesional con diseño enterprise y funcionalidad completa
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aio_pika
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import socketio

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de seguridad
SECRET_KEY = "fiscalberry-dev-panel-2024"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password"

# Almacenamiento en memoria
errors_storage: List[Dict] = []
rabbitmq_consumer = None
error_counts = {"total": 0, "today": 0, "by_tenant": {}}

# Modelos Pydantic
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str

class ErrorResponse(BaseModel):
    error: str

# Configurar FastAPI
app = FastAPI(title="Fiscalberry Developer Panel", version="2.0.0")

# Configurar Socket.IO
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")
socket_app = socketio.ASGIApp(sio, app)

# Security
security = HTTPBearer()

def verify_token_string(token: str) -> bool:
    """Verificar token JWT simple"""
    return token == SECRET_KEY

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verificar token de autenticación"""
    if not verify_token_string(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )
    return credentials.credentials

def get_fiscalberry_rabbitmq_config():
    """Obtener configuración de RabbitMQ desde Fiscalberry"""
    try:
        sys.path.append("/home/paxapos/Escritorio/fiscalberry/src")
        from fiscalberry.common.Configberry import Configberry
        
        config = Configberry()
        host = config.config.get("SERVIDOR", "ip", fallback="localhost")
        port = config.config.getint("SERVIDOR", "puerto", fallback=5672)
        user = config.config.get("SERVIDOR", "user", fallback="guest")
        password = config.config.get("SERVIDOR", "password", fallback="guest")
        
        logger.info(f"Configuración RabbitMQ desde Fiscalberry: {host}:{port}")
        return host, port, user, password
    except Exception as e:
        logger.error(f"Error al obtener configuración de Fiscalberry: {e}")
        return "localhost", 5672, "guest", "guest"

async def start_rabbitmq_consumer():
    """Iniciar consumer de RabbitMQ para errores"""
    global rabbitmq_consumer
    
    try:
        host, port, user, password = get_fiscalberry_rabbitmq_config()
        
        connection = await aio_pika.connect_robust(
            f"amqp://{user}:{password}@{host}:{port}/"
        )
        
        channel = await connection.channel()
        
        # Cola para el panel de desarrolladores
        queue = await channel.declare_queue("developer_panel", durable=True)
        
        async def process_error_message(message):
            async with message.process():
                try:
                    error_data = json.loads(message.body.decode())
                    await handle_new_error(error_data)
                except Exception as e:
                    logger.error(f"Error procesando mensaje: {e}")
        
        await queue.consume(process_error_message)
        
        rabbitmq_consumer = connection
        logger.info("RabbitMQ Error Consumer conectado exitosamente")
        
    except Exception as e:
        logger.error(f"Error conectando a RabbitMQ: {e}")

async def handle_new_error(error_data: dict):
    """Manejar nuevo error recibido"""
    global error_counts
    
    # Almacenar error
    error_data["timestamp"] = datetime.now(timezone.utc).isoformat()
    errors_storage.insert(0, error_data)
    
    # Mantener solo los últimos 100 errores
    if len(errors_storage) > 100:
        errors_storage.pop()
    
    # Actualizar contadores
    error_counts["total"] += 1
    today = datetime.now(timezone.utc).date()
    if error_data.get("date") == today.isoformat():
        error_counts["today"] += 1
    
    tenant = error_data.get("tenant", "unknown")
    error_counts["by_tenant"][tenant] = error_counts["by_tenant"].get(tenant, 0) + 1
    
    # Enviar a clientes conectados
    await sio.emit("new_error", error_data)
    
    logger.info(f"Nuevo error procesado: {tenant} - {error_data.get('message', 'Sin mensaje')}")

@app.on_event("startup")
async def startup_event():
    """Inicializar aplicación"""
    logger.info("Iniciando Fiscalberry Developer Panel Professional...")
    await start_rabbitmq_consumer()

@app.on_event("shutdown")
async def shutdown_event():
    """Cerrar aplicación"""
    logger.info("Cerrando Fiscalberry Developer Panel Professional...")
    if rabbitmq_consumer:
        await rabbitmq_consumer.close()

# API Endpoints
@app.post("/api/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Endpoint de login"""
    if request.username == ADMIN_USERNAME and request.password == ADMIN_PASSWORD:
        return LoginResponse(token=SECRET_KEY)
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas"
    )

@app.get("/api/stats")
async def get_stats(token: str = Depends(verify_token)):
    """Obtener estadísticas del sistema"""
    return {
        "total_errors": error_counts["total"],
        "errors_today": error_counts["today"],
        "active_tenants": len(error_counts["by_tenant"]),
        "errors_by_tenant": error_counts["by_tenant"],
        "uptime": "Online"
    }

@app.get("/api/recent-errors")
async def get_recent_errors(limit: int = 20, token: str = Depends(verify_token)):
    """Obtener errores recientes"""
    return errors_storage[:limit]

# Socket.IO Events
@sio.event
async def connect(sid, environ, auth):
    """Manejar conexión Socket.IO"""
    try:
        token = auth.get("token") if auth else None
        if not token or not verify_token_string(token):
            logger.warning(f"Conexión Socket.IO rechazada: token inválido")
            return False
        
        logger.info(f"Cliente Socket.IO conectado: {sid}")
        return True
    except Exception as e:
        logger.error(f"Error en conexión Socket.IO: {e}")
        return False

@sio.event
async def disconnect(sid):
    """Manejar desconexión Socket.IO"""
    logger.info(f"Cliente Socket.IO desconectado: {sid}")

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Panel principal"""
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fiscalberry Developer Panel Professional</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.4/socket.io.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }

        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }

        .login-form {
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 400px;
            text-align: center;
        }

        .login-form h2 {
            margin-bottom: 30px;
            color: #333;
            font-size: 24px;
        }

        .login-form input {
            width: 100%;
            padding: 12px 16px;
            margin: 10px 0;
            border: 2px solid #e1e5e9;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s ease;
        }

        .login-form input:focus {
            outline: none;
            border-color: #667eea;
        }

        .dashboard {
            display: none;
            min-height: 100vh;
            background: #f8fafc;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .header-content {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header h1 {
            font-size: 28px;
            font-weight: 600;
        }

        .connection-status {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255,255,255,0.1);
            padding: 8px 16px;
            border-radius: 25px;
            backdrop-filter: blur(10px);
        }

        .status-indicator {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        .status-indicator.connected {
            background: #10b981;
        }

        .status-indicator.disconnected {
            background: #ef4444;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 30px 20px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }

        .stat-card {
            background: white;
            padding: 24px;
            border-radius: 16px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            display: flex;
            align-items: center;
            gap: 16px;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        }

        .stat-icon {
            font-size: 32px;
            width: 60px;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px;
            color: white;
        }

        .stat-content {
            flex: 1;
        }

        .stat-value {
            font-size: 32px;
            font-weight: 700;
            color: #1f2937;
            line-height: 1;
        }

        .stat-label {
            font-size: 14px;
            color: #6b7280;
            margin-top: 4px;
        }

        .section {
            margin-bottom: 40px;
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .section-title {
            font-size: 24px;
            font-weight: 600;
            color: #1f2937;
        }

        .commerce-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }

        .commerce-card {
            background: white;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .commerce-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        }

        .commerce-card.empty {
            text-align: center;
            color: #6b7280;
            grid-column: 1 / -1;
        }

        .commerce-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }

        .commerce-icon {
            font-size: 24px;
        }

        .commerce-status {
            font-size: 20px;
        }

        .commerce-status.healthy {
            color: #10b981;
        }

        .commerce-status.warning {
            color: #f59e0b;
        }

        .commerce-status.error {
            color: #ef4444;
        }

        .commerce-name {
            font-size: 18px;
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 16px;
        }

        .commerce-stats {
            display: flex;
            gap: 20px;
            margin-bottom: 16px;
        }

        .commerce-stat {
            text-align: center;
        }

        .commerce-stat-value {
            display: block;
            font-size: 20px;
            font-weight: 600;
            color: #1f2937;
        }

        .commerce-stat-label {
            font-size: 12px;
            color: #6b7280;
        }

        .commerce-actions {
            text-align: center;
        }

        .error-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border-left: 4px solid #ef4444;
        }

        .error-card.warning {
            border-left-color: #f59e0b;
        }

        .error-card.info {
            border-left-color: #3b82f6;
        }

        .error-card.empty {
            text-align: center;
            color: #6b7280;
            border-left-color: #10b981;
        }

        .error-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }

        .error-info {
            flex: 1;
        }

        .error-severity {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }

        .error-level {
            background: #ef4444;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }

        .error-tenant {
            font-size: 14px;
            color: #6b7280;
        }

        .error-time {
            font-size: 12px;
            color: #9ca3af;
        }

        .error-message {
            font-size: 14px;
            color: #374151;
            line-height: 1.5;
            margin-bottom: 12px;
        }

        .error-traceback {
            margin-top: 12px;
        }

        .error-traceback summary {
            cursor: pointer;
            color: #6b7280;
            font-size: 12px;
        }

        .error-traceback pre {
            background: #f9fafb;
            padding: 12px;
            border-radius: 6px;
            font-size: 11px;
            overflow-x: auto;
            margin-top: 8px;
        }

        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            display: inline-block;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }

        .btn-secondary {
            background: #f3f4f6;
            color: #374151;
        }

        .btn-secondary:hover {
            background: #e5e7eb;
        }

        .btn-sm {
            padding: 6px 12px;
            font-size: 12px;
        }

        @media (max-width: 768px) {
            .header-content {
                flex-direction: column;
                gap: 16px;
            }

            .stats-grid {
                grid-template-columns: 1fr;
            }

            .commerce-grid {
                grid-template-columns: 1fr;
            }

            .error-header {
                flex-direction: column;
                gap: 8px;
            }
        }
    </style>
</head>
<body>
    <div class="login-container" id="loginForm">
        <div class="login-form">
            <h2>🔧 Panel Desarrollador</h2>
            <input type="text" id="username" placeholder="Usuario" value="admin">
            <input type="password" id="password" placeholder="Contraseña" value="password">
            <button onclick="login()" class="btn btn-primary">Iniciar Sesión</button>
            <div id="loginError" style="color: #e53e3e; margin-top: 16px; display: none; text-align: center;"></div>
        </div>
    </div>

    <div class="dashboard" id="dashboard">
        <div class="header">
            <div class="header-content">
                <h1>🚀 Fiscalberry Developer Panel</h1>
                <div id="connectionStatus" class="connection-status">
                    <span class="status-indicator connected" id="statusIndicator"></span>
                    <span id="statusText">Conectado</span>
                </div>
            </div>
        </div>
        
        <div class="container">
            <!-- Estadísticas principales -->
            <div class="stats-grid" id="statsGrid">
                <!-- Se cargan dinámicamente -->
            </div>
            
            <!-- Sección de comercios -->
            <div class="section">
                <div class="section-header">
                    <h2 class="section-title">🏪 Comercios Monitoreados</h2>
                </div>
                <div class="commerce-grid" id="commerceGrid">
                    <!-- Se cargan dinámicamente -->
                </div>
            </div>
            
            <!-- Sección de errores recientes -->
            <div class="section">
                <div class="section-header">
                    <h2 class="section-title">🚨 Errores Recientes</h2>
                </div>
                <div id="recentErrors">
                    <!-- Se cargan dinámicamente -->
                </div>
            </div>
        </div>
    </div>

    <script>
        // Estado de la aplicación
        let token = null;
        let socket = null;
        
        // Función de login
        async function login() {
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const errorDiv = document.getElementById('loginError');
            
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ username, password })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    token = data.token;
                    document.getElementById('loginForm').style.display = 'none';
                    document.getElementById('dashboard').style.display = 'block';
                    connectWebSocket();
                    loadInitialData();
                } else {
                    errorDiv.textContent = data.detail || 'Error de autenticación';
                    errorDiv.style.display = 'block';
                }
            } catch (error) {
                errorDiv.textContent = 'Error de conexión';
                errorDiv.style.display = 'block';
            }
        }
        
        // Conexión WebSocket
        function connectWebSocket() {
            socket = io('/', {
                auth: {
                    token: token
                }
            });
            
            socket.on('connect', () => {
                console.log('Conectado al servidor');
                updateConnectionStatus(true);
            });
            
            socket.on('disconnect', () => {
                console.log('Desconectado del servidor');
                updateConnectionStatus(false);
            });
            
            socket.on('new_error', (data) => {
                console.log('Nuevo error recibido:', data);
                addErrorToUI(data);
                updateStats();
            });
        }
        
        // Actualizar estado de conexión
        function updateConnectionStatus(isConnected) {
            const indicator = document.getElementById('statusIndicator');
            const text = document.getElementById('statusText');
            
            if (isConnected) {
                indicator.className = 'status-indicator connected';
                text.textContent = 'Conectado';
            } else {
                indicator.className = 'status-indicator disconnected';
                text.textContent = 'Desconectado';
            }
        }
        
        // Cargar datos iniciales
        async function loadInitialData() {
            await updateStats();
            await loadRecentErrors();
        }
        
        // Cargar estadísticas
        async function updateStats() {
            try {
                const response = await fetch('/api/stats', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    displayStats(data);
                    displayCommerces(data);
                } else {
                    console.error('Error al cargar estadísticas');
                }
            } catch (error) {
                console.error('Error al cargar estadísticas:', error);
            }
        }
        
        // Mostrar estadísticas principales
        function displayStats(stats) {
            const statsGrid = document.getElementById('statsGrid');
            
            statsGrid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-icon">🚨</div>
                    <div class="stat-content">
                        <div class="stat-value">${stats.total_errors}</div>
                        <div class="stat-label">Total Errores</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">📅</div>
                    <div class="stat-content">
                        <div class="stat-value">${stats.errors_today}</div>
                        <div class="stat-label">Errores Hoy</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">🏪</div>
                    <div class="stat-content">
                        <div class="stat-value">${stats.active_tenants}</div>
                        <div class="stat-label">Comercios Activos</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon">⚡</div>
                    <div class="stat-content">
                        <div class="stat-value">${stats.uptime || 'N/A'}</div>
                        <div class="stat-label">Tiempo Activo</div>
                    </div>
                </div>
            `;
        }
        
        // Mostrar comercios
        function displayCommerces(stats) {
            const commerceGrid = document.getElementById('commerceGrid');
            
            if (!stats.errors_by_tenant || Object.keys(stats.errors_by_tenant).length === 0) {
                commerceGrid.innerHTML = `
                    <div class="commerce-card empty">
                        <div class="commerce-icon">🏪</div>
                        <h3>No hay comercios activos</h3>
                        <p>Esperando conexiones de tenants...</p>
                    </div>
                `;
                return;
            }
            
            let commerceHtml = '';
            for (const [tenant, errorCount] of Object.entries(stats.errors_by_tenant)) {
                const statusClass = errorCount === 0 ? 'healthy' : errorCount < 5 ? 'warning' : 'error';
                const statusIcon = errorCount === 0 ? '✅' : errorCount < 5 ? '⚠️' : '🚨';
                
                commerceHtml += `
                    <div class="commerce-card">
                        <div class="commerce-header">
                            <div class="commerce-icon">🏪</div>
                            <div class="commerce-status ${statusClass}">${statusIcon}</div>
                        </div>
                        <h3 class="commerce-name">${tenant}</h3>
                        <div class="commerce-stats">
                            <div class="commerce-stat">
                                <span class="commerce-stat-value">${errorCount}</span>
                                <span class="commerce-stat-label">Errores</span>
                            </div>
                            <div class="commerce-stat">
                                <span class="commerce-stat-value">Online</span>
                                <span class="commerce-stat-label">Estado</span>
                            </div>
                        </div>
                        <div class="commerce-actions">
                            <button class="btn btn-secondary btn-sm" onclick="viewCommerceDetails('${tenant}')">
                                Ver Detalles
                            </button>
                        </div>
                    </div>
                `;
            }
            commerceGrid.innerHTML = commerceHtml;
        }
        
        // Cargar errores recientes
        async function loadRecentErrors() {
            try {
                const response = await fetch('/api/recent-errors', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                
                if (response.ok) {
                    const errors = await response.json();
                    displayRecentErrors(errors);
                } else {
                    console.error('Error al cargar errores recientes');
                }
            } catch (error) {
                console.error('Error al cargar errores recientes:', error);
            }
        }
        
        // Mostrar errores recientes
        function displayRecentErrors(errors) {
            const errorsDiv = document.getElementById('recentErrors');
            
            if (errors.length === 0) {
                errorsDiv.innerHTML = `
                    <div class="error-card empty">
                        <div class="error-icon">✅</div>
                        <h3>No hay errores recientes</h3>
                        <p>El sistema está funcionando correctamente</p>
                    </div>
                `;
                return;
            }
            
            let errorsHtml = '';
            errors.forEach(error => {
                errorsHtml += createErrorCard(error);
            });
            
            errorsDiv.innerHTML = errorsHtml;
        }
        
        // Crear card de error profesional
        function createErrorCard(error) {
            const timestamp = new Date(error.timestamp).toLocaleString();
            const severity = error.level || 'error';
            const severityIcon = severity === 'error' ? '🚨' : severity === 'warning' ? '⚠️' : 'ℹ️';
            
            return `
                <div class="error-card ${severity}">
                    <div class="error-header">
                        <div class="error-info">
                            <div class="error-severity">
                                <span class="error-icon">${severityIcon}</span>
                                <span class="error-level">${severity.toUpperCase()}</span>
                            </div>
                            <div class="error-tenant">📍 ${error.tenant}</div>
                        </div>
                        <div class="error-time">${timestamp}</div>
                    </div>
                    <div class="error-message">${error.message}</div>
                    ${error.traceback ? `
                        <details class="error-traceback">
                            <summary>🔍 Ver stack trace</summary>
                            <pre><code>${error.traceback}</code></pre>
                        </details>
                    ` : ''}
                </div>
            `;
        }
        
        // Agregar error nuevo a la UI
        function addErrorToUI(error) {
            const errorsDiv = document.getElementById('recentErrors');
            const errorCard = createErrorCard(error);
            
            // Si no hay errores, reemplazar el mensaje vacío
            if (errorsDiv.querySelector('.error-card.empty')) {
                errorsDiv.innerHTML = errorCard;
            } else {
                errorsDiv.insertAdjacentHTML('afterbegin', errorCard);
            }
            
            // Limitar a 20 errores mostrados
            const errorCards = errorsDiv.querySelectorAll('.error-card:not(.empty)');
            if (errorCards.length > 20) {
                errorCards[errorCards.length - 1].remove();
            }
        }
        
        // Ver detalles de un comercio
        function viewCommerceDetails(tenant) {
            alert(`Función en desarrollo: Ver detalles de ${tenant}`);
        }
        
        // Event listeners
        document.addEventListener('DOMContentLoaded', () => {
            // Inicializar con el formulario de login
            document.getElementById('loginForm').style.display = 'flex';
            document.getElementById('dashboard').style.display = 'none';
            
            // Permitir login con Enter
            document.getElementById('password').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    login();
                }
            });
        });
    </script>
</body>
</html>
    """)

if __name__ == "__main__":
    uvicorn.run(socket_app, host="0.0.0.0", port=8000)