# Mejoras en el manejo de errores de RabbitMQ

## Problemas identificados

El error original mostraba:
```
ERROR:pika.adapters.utils.selector_ioloop_adapter:Address resolution failed: gaierror(-2, 'Name or service not known')
socket.gaierror: [Errno -2] Name or service not known
```

Este error indicaba que el hostname 'rabbitmq' no se podía resolver, pero el manejo de errores era genérico y no proporcionaba información útil al usuario.

## Mejoras implementadas

### 1. Manejo específico de errores en `process_handler.py`

- **Errores DNS**: Se detectan específicamente errores `socket.gaierror` y se proporcionan sugerencias claras
- **Errores de autenticación**: Se capturan errores de `ProbableAuthenticationError` y `ProbableAccessDeniedError`
- **Errores de conectividad**: Se distinguen errores de red vs errores de RabbitMQ
- **Backoff exponencial**: Se implementa un sistema de reintentos inteligente que evita saturar el servidor

### 2. Verificación previa de conectividad

Se añadió `_check_network_connectivity()` que:
- Verifica resolución DNS antes de intentar conectar
- Prueba la conectividad del puerto TCP
- Falla rápido para evitar timeouts largos

### 3. Configuración mejorada de timeouts en `consumer.py`

- `socket_timeout=10`: Timeout más corto para detectar errores de red rápidamente
- `connection_attempts=1`: Solo un intento, el retry lo maneja process_handler
- `retry_delay=1`: Delay corto entre intentos

### 4. Herramienta de diagnóstico

Se creó `rabbitmq_check.py` para:
- Diagnosticar problemas de DNS, red y RabbitMQ por separado
- Proporcionar sugerencias específicas para cada tipo de error
- Permitir pruebas rápidas sin tener que ejecutar toda la aplicación

## Uso de la herramienta de diagnóstico

```bash
# Diagnóstico básico
python src/fiscalberry/diagnostics/rabbitmq_check.py

# Usar configuración específica
python src/fiscalberry/diagnostics/rabbitmq_check.py --host localhost --port 5672

# Usar configuración de Fiscalberry
python src/fiscalberry/diagnostics/rabbitmq_check.py --from-config
```

## Comportamiento del nuevo sistema de reintentos

1. **Primeros 3 intentos**: Reintento cada 5 segundos
2. **Después del intento 3**: Backoff exponencial (10s, 20s, 40s, etc.)
3. **Máximo delay**: 300 segundos (5 minutos)
4. **Verificación de conectividad**: Se verifica DNS y puerto antes de cada intento RabbitMQ

## Mensajes de error mejorados

En lugar de:
```
ERROR:fiscalberry.common.rabbitmq.process_handler:Error en RabbitMQConsumer: [Errno -2] Name or service not known
WARNING:fiscalberry.common.rabbitmq.process_handler:RabbitMQConsumer detenido; reintentando en 5 s...
```

Ahora se muestra:
```
ERROR:fiscalberry.common.rabbitmq.process_handler:Error de resolución DNS para 'rabbitmq': [Errno -2] Name or service not known
ERROR:fiscalberry.common.rabbitmq.process_handler:Posibles soluciones:
ERROR:fiscalberry.common.rabbitmq.process_handler:1. Verificar que el hostname 'rabbitmq' esté configurado correctamente
ERROR:fiscalberry.common.rabbitmq.process_handler:2. Verificar conectividad de red
ERROR:fiscalberry.common.rabbitmq.process_handler:3. Verificar que el servidor RabbitMQ esté ejecutándose
ERROR:fiscalberry.common.rabbitmq.process_handler:4. Considerar usar una IP directa en lugar del hostname
WARNING:fiscalberry.common.rabbitmq.process_handler:Reintento 1/3 - esperando 5s antes del siguiente intento...
```

## Soluciones comunes

### Error DNS (Name or service not known)

1. **Configurar /etc/hosts**:
   ```
   127.0.0.1 rabbitmq
   ```

2. **Usar IP directa en configuración**:
   ```ini
   [RabbitMq]
   host = 127.0.0.1
   ```

3. **Verificar que RabbitMQ esté ejecutándose en Docker**:
   ```bash
   docker ps | grep rabbitmq
   ```

### Error de conexión (Connection refused)

1. Verificar que RabbitMQ esté ejecutándose
2. Verificar firewall
3. Verificar puerto correcto (por defecto 5672)

### Error de autenticación

1. Verificar usuario y contraseña
2. Verificar permisos en el vhost
3. Crear usuario si no existe:
   ```bash
   rabbitmqctl add_user myuser mypassword
   rabbitmqctl set_permissions -p / myuser ".*" ".*" ".*"
   ```
