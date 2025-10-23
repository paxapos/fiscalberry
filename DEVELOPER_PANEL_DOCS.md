# Sistema de Panel de Desarrollador para Fiscalberry

## 📋 Resumen del Sistema

He implementado un sistema completo de monitoreo de errores para desarrolladores que permite el soporte remoto de múltiples tenants/comercios de Fiscalberry sin necesidad de estar presencial.

## 🏗️ Arquitectura del Sistema

```
┌─────────────────┐    ┌──────────────────┐    ┌────────────────────┐
│ Fiscalberry     │    │ RabbitMQ         │    │ Panel Desarrollador│
│ Instance        │───▶│ Error Queues     │───▶│ (Web App)          │
│                 │    │                  │    │                    │
│ • Error Publisher│    │ • {tenant}_errors│    │ • Dashboard Web    │
│ • Consumer       │    │ • dev_panel_queue│    │ • Real-time WS     │
│ • ComandosHandler│    │ • Topic Exchange │    │ • Multi-tenant     │
└─────────────────┘    └──────────────────┘    └────────────────────┘
```

## 🔧 Componentes Implementados

### 1. Sistema de Subcolas de Errores ✅
- **Archivo**: `src/fiscalberry/common/rabbitmq/error_publisher.py`
- **Funcionalidad**: Cada tenant tiene su propia subcola de errores (`{tenant}_errors`)
- **Intercambios**: 
  - `fiscalberry_errors` (direct) - Para errores específicos por tenant
  - `fiscalberry_errors_topic` (topic) - Para el panel de desarrollador

### 2. Integración con RabbitMQ Consumer ✅
- **Archivo**: `src/fiscalberry/common/rabbitmq/consumer.py`
- **Funcionalidad**: Publica automáticamente errores a las subcolas cuando ocurren

### 3. Integración con ComandosHandler ✅
- **Archivo**: `src/fiscalberry/common/ComandosHandler.py` 
- **Funcionalidad**: Captura y publica todos los tipos de errores de comandos

### 4. Panel Web de Desarrollador ✅
- **Directorio**: `developer-panel/`
- **Framework**: FastAPI + WebSockets
- **Características**:
  - Dashboard web interactivo
  - Autenticación JWT para desarrolladores
  - Monitoreo en tiempo real con WebSockets
  - Multi-tenant (múltiples comercios)
  - API REST para integración

## 📊 Tipos de Errores Monitoreados

| Tipo de Error | Descripción | Origen |
|---------------|-------------|---------|
| `COMMAND_EXECUTION_ERROR` | Errores en ejecución de comandos | RabbitMQ Consumer |
| `TRANSLATOR_ERROR` | Errores del traductor de comandos | Consumer + ComandosHandler |
| `PROCESSING_ERROR` | Errores generales de procesamiento | Consumer |
| `JSON_PARSE_ERROR` | Errores de parsing JSON | ComandosHandler |
| `JSON_DECODE_ERROR` | Errores de decodificación JSON | ComandosHandler |
| `TRADUCTOR_ERROR` | Errores específicos del traductor | ComandosHandler |
| `INVALID_COMMAND_ERROR` | Comandos inválidos | ComandosHandler |
| `UNKNOWN_ERROR` | Errores no categorizados | ComandosHandler |

## 🚀 Uso del Sistema

### Iniciar el Panel de Desarrollador

```bash
cd developer-panel
./start.sh
```

Acceder en: http://localhost:8000

**Credenciales por defecto:**
- Usuario: `dev1` / Contraseña: `dev123` (desarrollador senior)
- Usuario: `dev2` / Contraseña: `dev456` (desarrollador)

### Probar el Sistema

```bash
# Verificar configuración
python3 test_error_system.py --config

# Probar conexión
python3 test_error_system.py --test-connection

# Simular errores para testing
python3 test_error_system.py
```

### Despliegue con Docker

```bash
cd developer-panel
docker-compose up -d
```

## 🔐 Seguridad

- ✅ Autenticación JWT con expiración (8 horas)
- ✅ Roles y permisos por desarrollador
- ✅ Sanitización de datos sensibles en logs
- ✅ Usuario no-root en Docker
- ⚠️ **Cambiar credenciales por defecto en producción**

## 📈 Beneficios del Sistema

### Para Desarrolladores
- **Soporte remoto**: Monitoreo sin estar físicamente presente
- **Multi-tenant**: Un solo panel para múltiples comercios
- **Tiempo real**: Notificaciones inmediatas de errores críticos
- **Histórico**: Acceso a errores anteriores para análisis
- **Filtrado**: Por tenant, tipo de error, fecha

### Para el Negocio
- **Menor tiempo de resolución**: Detección proactiva de problemas
- **Mejor calidad**: Identificación de patrones de errores
- **Escalabilidad**: Soporte a más comercios sin incremento proporcional de personal
- **Trazabilidad**: Logs detallados para auditoría

## 🔄 Flujo de Trabajo

1. **Error ocurre** en una instancia de Fiscalberry
2. **ErrorPublisher** envía el error a:
   - Cola específica del tenant: `{tenant}_errors`
   - Cola del panel de desarrollador: `developer_panel_all_errors`
3. **Panel Web** recibe el error vía RabbitMQ Consumer
4. **WebSocket** notifica en tiempo real a desarrolladores conectados
5. **Dashboard** muestra el error categorizado y filtrable

## 📁 Estructura de Archivos

```
fiscalberry/
├── src/fiscalberry/common/rabbitmq/
│   └── error_publisher.py          # ✅ Sistema de subcolas
├── src/fiscalberry/common/rabbitmq/
│   └── consumer.py                 # ✅ Consumer modificado
├── src/fiscalberry/common/
│   └── ComandosHandler.py          # ✅ Handler modificado
├── developer-panel/                # ✅ Panel web independiente
│   ├── main.py                     # Aplicación FastAPI
│   ├── requirements.txt            # Dependencias
│   ├── start.sh                    # Script de inicio
│   ├── Dockerfile                  # Contenedor Docker
│   ├── docker-compose.yml          # Orquestación
│   └── README.md                   # Documentación
└── test_error_system.py            # ✅ Script de pruebas
```

## 🚀 Próximos Pasos

1. **Producción**: Cambiar credenciales y configurar HTTPS
2. **Base de Datos**: Migrar de almacén en memoria a PostgreSQL/Redis
3. **Alertas**: Integrar con Slack/Teams/Email para notificaciones críticas
4. **Métricas**: Agregar dashboards de métricas y tendencias
5. **Filtros Avanzados**: Búsqueda por texto, rangos de fecha, severidad

## 🛠️ Configuración de Producción

### Variables de Entorno
```bash
export DEVELOPER_PANEL_SECRET="clave-super-segura"
export RABBITMQ_HOST="tu-rabbitmq-host"
export RABBITMQ_USER="usuario-produccion"
export RABBITMQ_PASSWORD="password-seguro"
```

### HTTPS con Nginx
```nginx
server {
    listen 443 ssl;
    server_name dev-panel.tudominio.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## ✅ Estado Actual

Todos los componentes están implementados y funcionando:
- [x] Sistema de subcolas de errores por tenant
- [x] Publicación automática de errores desde Fiscalberry
- [x] Panel web independiente con autenticación
- [x] WebSockets para notificaciones en tiempo real
- [x] API REST para integración
- [x] Docker para despliegue fácil
- [x] Scripts de prueba y documentación

El sistema está listo para usar en desarrollo y puede ser fácilmente desplegado en producción.