# Lógica de Prioridad RabbitMQ: Config.ini vs SocketIO

## Resumen de la Implementación

Hemos implementado una lógica de prioridad robusta en el archivo `process_handler.py` que garantiza que **cada parámetro** de configuración de RabbitMQ sigue la misma regla de prioridad:

### 🎯 Regla de Prioridad (por parámetro individual)

Para cada campo (`host`, `port`, `user`, `password`, `vhost`, `queue`):

1. **Primera prioridad**: Valor en `config.ini` (si existe y no está vacío)
2. **Segunda prioridad**: Valor del mensaje SocketIO
3. **Tercera prioridad**: Valor por defecto

### 📄 Código Implementado

```python
def get_config_or_message_value(config_key, message_key, default_value=""):
    """
    Obtiene valor del config.ini si existe y no está vacío, sino del mensaje SocketIO.
    Prioridad: config.ini -> mensaje SocketIO -> valor por defecto
    """
    config_value = self.config.get("RabbitMq", config_key, fallback="")
    if config_value and str(config_value).strip():
        logger.info(f"{config_key}: usando config.ini -> {config_value}")
        return config_value
    else:
        message_value = rabbit_cfg.get(message_key, default_value)
        logger.info(f"{config_key}: config.ini vacío, usando SocketIO -> {message_value}")
        return message_value

# Aplicar la lógica a todos los parámetros
host = get_config_or_message_value("host", "host")
port_str = get_config_or_message_value("port", "port", "5672")
user = get_config_or_message_value("user", "user", "guest")
pwd = get_config_or_message_value("password", "password", "guest")
vhost = get_config_or_message_value("vhost", "vhost", "/")
queue = get_config_or_message_value("queue", "queue", "")
```

### ✅ Ventajas de la Nueva Lógica

1. **Control Local Total**: Los administradores pueden forzar cualquier valor específico en `config.ini`
2. **Fallback Inteligente**: Campos vacíos se completan automáticamente desde SocketIO
3. **Logs Transparentes**: Cada valor muestra claramente su origen
4. **Configuración Granular**: Cada parámetro puede tener diferente origen sin afectar a los demás
5. **Backwards Compatible**: Funciona con configuraciones existentes

### 🧪 Casos de Prueba Verificados

#### Caso 1: Config.ini completo

```ini
[RabbitMq]
host = localhost
port = 5672
user = admin
password = mi_password
vhost = /prod
queue = my_queue
```

**Resultado**: Se usan TODOS los valores del `config.ini`, ignorando SocketIO.

#### Caso 2: Config.ini parcial

```ini
[RabbitMq]
host = localhost
port =
user = admin
password =
vhost = /prod
queue =
```

**Resultado**:

- `host`, `user`, `vhost` → del `config.ini`
- `port`, `password`, `queue` → del mensaje SocketIO

#### Caso 3: Config.ini vacío

```ini
[RabbitMq]
host =
port =
user =
password =
vhost =
queue =
```

**Resultado**: Se usan TODOS los valores del mensaje SocketIO.

### 🔧 Herramientas de Diagnóstico

Se han creado scripts de prueba para verificar la lógica:

1. **`test_config_priority.py`**: Pruebas unitarias automatizadas
2. **`demo_priority_logic.py`**: Demostración interactiva con el `config.ini` real
3. **`rabbitmq_check.py`**: Diagnóstico completo de conectividad RabbitMQ

### 💡 Uso Práctico

**Para forzar un valor específico:**

```bash
# Editar config.ini
vim ~/.config/Fiscalberry/config.ini

# Establecer el valor deseado
[RabbitMq]
host = mi-servidor-rabbitmq.com
```

**Para permitir configuración remota:**

```bash
# Dejar campo vacío en config.ini
[RabbitMq]
host =
# Este valor vendrá del mensaje SocketIO
```

### 🚀 Mejoras Incluidas

1. **Manejo de Errores Mejorado**: DNS, autenticación, red
2. **Backoff Exponencial**: Reintentos inteligentes
3. **Logging Detallado**: Origen claro de cada configuración
4. **Validación de Tipos**: Puerto convertido a entero con fallback
5. **Diagnósticos Automáticos**: Scripts para troubleshooting

Esta implementación proporciona un control granular y transparente sobre la configuración de RabbitMQ, facilitando tanto la administración manual como la configuración automática remota.
