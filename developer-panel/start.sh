#!/bin/bash

# Script de inicio para el Panel de Desarrollador de Fiscalberry

set -e

echo "🔧 Iniciando Fiscalberry Developer Panel..."

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función de logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar si estamos en el directorio correcto
if [ ! -f "main.py" ]; then
    log_error "No se encuentra main.py. Ejecuta este script desde el directorio developer-panel"
    exit 1
fi

# Verificar Python
if ! command -v python3 &> /dev/null; then
    log_error "Python3 no está instalado"
    exit 1
fi

log_info "Python encontrado: $(python3 --version)"

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    log_info "Creando entorno virtual..."
    python3 -m venv venv
    log_success "Entorno virtual creado"
fi

# Activar entorno virtual
log_info "Activando entorno virtual..."
source venv/bin/activate

# Instalar dependencias
log_info "Instalando dependencias..."
pip install -r requirements.txt

# Configurar variables de entorno por defecto si no están definidas
export DEVELOPER_PANEL_SECRET="${DEVELOPER_PANEL_SECRET:-fiscalberry-dev-panel-secret-change-in-production}"
export RABBITMQ_HOST="${RABBITMQ_HOST:-rabbitmq.restodigital.com.ar}"
export RABBITMQ_PORT="${RABBITMQ_PORT:-5672}"
export RABBITMQ_USER="${RABBITMQ_USER:-fiscalberry}"
export RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-fiscalberry123}"
export RABBITMQ_VHOST="${RABBITMQ_VHOST:-/}"

log_info "Configuración:"
log_info "  RabbitMQ Host: $RABBITMQ_HOST"
log_info "  RabbitMQ Port: $RABBITMQ_PORT"
log_info "  RabbitMQ User: $RABBITMQ_USER"
log_info "  RabbitMQ VHost: $RABBITMQ_VHOST"

# Verificar conexión a RabbitMQ (opcional)
if command -v nc &> /dev/null; then
    log_info "Verificando conexión a RabbitMQ..."
    if nc -z $RABBITMQ_HOST $RABBITMQ_PORT; then
        log_success "RabbitMQ accesible en $RABBITMQ_HOST:$RABBITMQ_PORT"
    else
        log_warning "No se puede conectar a RabbitMQ en $RABBITMQ_HOST:$RABBITMQ_PORT"
        log_warning "El panel seguirá funcionando pero no recibirá errores en tiempo real"
    fi
fi

# Crear directorio de logs si no existe
mkdir -p logs

# Función para manejar señales de cierre
cleanup() {
    log_info "Cerrando panel de desarrollador..."
    exit 0
}

trap cleanup SIGINT SIGTERM

# Iniciar el servidor
log_info "Iniciando servidor en http://0.0.0.0:8000"
log_info "Panel web disponible en: http://localhost:8000"
log_info ""
log_info "Credenciales por defecto:"
log_info "  Usuario: dev1 / Contraseña: dev123 (desarrollador senior)"
log_info "  Usuario: dev2 / Contraseña: dev456 (desarrollador)"
log_info ""
log_warning "IMPORTANTE: Cambiar credenciales por defecto en producción"
log_info ""
log_info "Presiona Ctrl+C para detener el servidor"
log_info "═══════════════════════════════════════════════════════════════"

# Ejecutar con logs
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info \
    --access-log \
    2>&1 | tee logs/panel-$(date +%Y%m%d-%H%M%S).log