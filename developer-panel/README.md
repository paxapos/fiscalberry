# Fiscalberry Developer Panel

Panel web independiente para que los desarrolladores puedan monitorear errores de múltiples tenants/comercios de Fiscalberry desde un dashboard centralizado.

## Características

- 🔍 **Monitoreo en tiempo real** de subcolas de errores por tenant
- 📊 **Dashboard interactivo** con filtros por tenant, tipo de error, fecha
- 🔔 **Notificaciones WebSocket** en tiempo real
- 🔐 **Autenticación JWT** para desarrolladores
- 📡 **API REST** para integración con otros sistemas
- 🏢 **Multi-tenant** - monitoreo de múltiples comercios desde un solo panel

## Instalación

1. **Instalar dependencias:**
```bash
cd developer-panel
pip install -r requirements.txt
```

2. **Configurar variables de entorno:**
```bash
export DEVELOPER_PANEL_SECRET="tu-clave-secreta-super-segura"
export RABBITMQ_HOST="rabbitmq.restodigital.com.ar"
export RABBITMQ_PORT="5672"
export RABBITMQ_USER="fiscalberry"
export RABBITMQ_PASSWORD="fiscalberry123"
export RABBITMQ_VHOST="/"
```

3. **Ejecutar el panel:**
```bash
python main.py
```

O usando uvicorn directamente:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Uso

1. **Accede al panel:** http://localhost:8000
2. **Credenciales por defecto:**
   - Usuario: `dev1` / Contraseña: `dev123` (desarrollador senior)
   - Usuario: `dev2` / Contraseña: `dev456` (desarrollador)

## Estructura del Sistema

### Flujo de Errores
```
[Fiscalberry Instance] → [RabbitMQ Error Queue] → [Developer Panel] → [Web Dashboard]
                                ↓
                        {tenant}_errors queues
```

### Tipos de Errores Monitoreados
- `COMMAND_EXECUTION_ERROR`: Errores en la ejecución de comandos
- `TRANSLATOR_ERROR`: Errores en el traductor de comandos
- `PROCESSING_ERROR`: Errores generales de procesamiento
- `JSON_PARSE_ERROR`: Errores de parsing de JSON
- `JSON_DECODE_ERROR`: Errores de decodificación JSON
- `INVALID_COMMAND_ERROR`: Comandos inválidos
- `PRINTER_ERROR`: Errores específicos de impresora
- `UNKNOWN_ERROR`: Errores no categorizados

### API Endpoints

#### Autenticación
- `POST /auth/login` - Login de desarrollador

#### Datos
- `GET /api/tenants` - Lista de tenants con errores
- `GET /api/errors/{tenant}` - Errores de un tenant específico
- `GET /api/stats` - Estadísticas generales de errores

#### WebSocket
- `WS /ws` - Conexión para notificaciones en tiempo real

## Configuración de Producción

### 1. Usar Base de Datos Real
Reemplazar el almacén en memoria por Redis o PostgreSQL:

```python
# Ejemplo con Redis
import redis
r = redis.Redis(host='localhost', port=6379, db=0)
```

### 2. Configurar HTTPS
```bash
uvicorn main:app --host 0.0.0.0 --port 443 --ssl-keyfile=key.pem --ssl-certfile=cert.pem
```

### 3. Variables de Entorno de Producción
```bash
export DEVELOPER_PANEL_SECRET="clave-super-segura-de-produccion"
export DATABASE_URL="postgresql://user:pass@localhost/devpanel"
export REDIS_URL="redis://localhost:6379/0"
```

### 4. Docker Deployment
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Seguridad

- ✅ Autenticación JWT con expiración
- ✅ Validación de permisos por rol
- ✅ Sanitización de datos sensibles
- ⚠️ **IMPORTANTE:** Cambiar credenciales por defecto en producción
- ⚠️ **IMPORTANTE:** Usar HTTPS en producción
- ⚠️ **IMPORTANTE:** Configurar firewall para acceso restringido

## Monitoreo y Alertas

El panel incluye:
- Notificaciones en tiempo real por WebSocket
- Contador de errores por tenant
- Histórico de errores con timestamps
- Filtrado por tipo de error y tenant

## Desarrollo

### Agregar Nuevo Tipo de Error
1. Modificar `fiscalberry/common/rabbitmq/error_publisher.py`
2. Publicar error con `publish_error(error_type="NUEVO_TIPO", ...)`
3. El panel detectará automáticamente el nuevo tipo

### Agregar Desarrollador
```python
DEVELOPERS["nuevo_dev"] = {
    "password": "password_hash",
    "role": "developer",
    "permissions": ["view_assigned_tenants", "real_time_monitoring"]
}
```

## Troubleshooting

### Error de Conexión RabbitMQ
1. Verificar que RabbitMQ esté ejecutándose
2. Verificar credenciales y configuración de red
3. Revisar logs: `tail -f /var/log/fiscalberry/fiscalberry.log`

### WebSocket No Conecta
1. Verificar que no haya firewall bloqueando
2. Revisar logs del navegador (F12)
3. Verificar que el puerto 8000 esté accesible