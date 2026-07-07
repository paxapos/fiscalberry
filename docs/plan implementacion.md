> ⚠️ **DOCUMENTO HISTÓRICO (v3.0.x).** Esta migración AMQP→MQTT ya está aplicada:
> el consumer consume por **MQTT/Paho** y el spooler durable es el dueño de la
> impresión. Se conserva como referencia del cambio original.
>
> **Estado actual (post-endurecimiento Fiscalberry-only):**
> - Impresión unificada en `DurablePrintSpooler` (MQTT y Socket.IO/directo).
> - Compatibilidad **paho 1.x/2.x** vía `common/rabbitmq/mqtt_compat.py`.
> - **TLS MQTT opt-in** (`[RabbitMq] use_tls`, puerto 8883/1883). Ver `mqtt_seguridad_tls.md`.
> - **ErrorPublisher no bloqueante** (cola + worker de fondo, con saneo y rate-limit).
> - **Circuit breaker** por impresora (`common/printer_circuit_breaker.py`).
> - **Heartbeat** local opcional (`[Heartbeat] enabled`, `common/heartbeat.py`).
> - Binding AMQP `pika` = **legacy opcional** (`[RabbitMq] create_amqp_binding`, default true),
>   ejecutado fuera del callback MQTT. `pika` sigue como dependencia legacy hasta validar
>   recepción sin binding local.
>
> ---

Migración de AMQP (RabbitMQ/Pika) a MQTT (Paho-MQTT)
IMPORTANT

Esta documentación preserva todos los cambios realizados en el commit 4250b9b de la rama v3.0.x para poder replicarlos después de resetear la rama.

Resumen de la Migración
Objetivo: Migrar el sistema de mensajería de Fiscalberry desde AMQP (usando la librería pika) hacia MQTT (usando la librería paho-mqtt).

Fecha del commit original: 2026-01-16 19:46:39 -0300
Autor: Santiago gay 
gaysantiago4@gmail.com

Commit hash: 4250b9bc049e053031ed13833958d655bd7d2799

Archivos Modificados
1. 
requirements.cli.txt
2. 
requirements.txt
3. 
fiscalberry_logger.py
4. 
consumer.py
5. 
error_publisher.py
6. 
process_handler.py
7. 
rabbitmq_check.py
Estadísticas: 7 archivos cambiados, 331 inserciones(+), 377 eliminaciones(-)

Cambios en Dependencias
requirements.cli.txt
-pika==1.3.2
+paho-mqtt==1.6.1
requirements.txt
-pika==1.3.2
+paho-mqtt==1.6.1
 psutil==5.9.8
-PyYAML==6.0.2
+PyYAML==6.0.1
NOTE

Se cambió también la versión de PyYAML de 6.0.2 a 6.0.1

Cambios por Archivo
1. fiscalberry_logger.py
Cambio menor en logging:

-logger.debug(f"Publicando error en RabbitMQ: {error_data}")
+logger.debug(f"Publicando error en MQTT: {error_data}")
2. consumer.py
Este es el archivo con más cambios significativos. La refactorización completa del consumidor.

Imports
-import pika
-from pika.exceptions import AMQPConnectionError, AMQPChannelError
+import paho.mqtt.client as mqtt
Clase RabbitMQConsumer → Refactorizada completamente
Cambios en __init__:

Eliminado: vhost, exchange, queue_name, routing_key
Agregado: mqtt_port (default: 1883), topic (default: "fiscalberry/#")
Cambiado: connection y channel por client (MQTT client)
Agregado: connected flag y subscribed flag
Nuevos métodos de callback MQTT:

on_connect(client, userdata, flags, rc) - Maneja conexión y suscripción automática
on_disconnect(client, userdata, rc) - Maneja desconexiones
on_message(client, userdata, msg) - Procesa mensajes MQTT
on_subscribe(client, userdata, mid, granted_qos) - Confirma suscripción
Método connect() refactorizado:

Usa mqtt.Client() en lugar de pika.BlockingConnection()
Configura callbacks MQTT
Usa client.connect() y client.loop_start()
Espera confirmación de conexión con timeout
Método start_consuming() refactorizado:

Simplificado: solo mantiene el loop activo
La lógica de procesamiento está en on_message
Método stop() refactorizado:

Usa client.loop_stop() y client.disconnect()
Método _process_message() refactorizado:

Recibe msg (MQTT message) en lugar de ch, method, properties, body
Usa msg.payload en lugar de body
Usa msg.topic en lugar de method.routing_key
Eliminado: ch.basic_ack(delivery_tag=method.delivery_tag) (MQTT QoS 0 no requiere ACK manual)
Método _handle_command() - Cambios menores:

Actualizado logging para reflejar MQTT
Eliminadas referencias a routing_key
3. error_publisher.py
Refactorización del publicador de errores.

Imports
-import pika
-from pika.exceptions import AMQPConnectionError
+import paho.mqtt.client as mqtt
Clase ErrorPublisher → Refactorizada
Cambios en __init__:

Eliminado: vhost, exchange
Agregado: mqtt_port (default: 1883)
Cambiado: connection y channel por client
Agregado: connected flag
Nuevos callbacks:

on_connect(client, userdata, flags, rc)
on_disconnect(client, userdata, rc)
on_publish(client, userdata, mid)
Método connect() refactorizado:

Usa mqtt.Client()
Configura callbacks
Usa client.connect() y client.loop_start()
Espera confirmación con timeout
Método publish_error() refactorizado:

Usa client.publish(topic, payload, qos=1) en lugar de channel.basic_publish()
Topic format: fiscalberry/errors/{printer_id}
QoS 1 para garantizar entrega al menos una vez
Método disconnect() refactorizado:

Usa client.loop_stop() y client.disconnect()
4. process_handler.py
Cambios menores en logging y manejo de errores.

Cambios principales:
-logger.error(f"Error publicando a RabbitMQ: {e}")
+logger.error(f"Error publicando a MQTT: {e}")
-logger.warning("No se pudo publicar error a RabbitMQ")
+logger.warning("No se pudo publicar error a MQTT")
-logger.debug(f"Error publicado en RabbitMQ: {error_data}")
+logger.debug(f"Error publicado en MQTT: {error_data}")
5. rabbitmq_check.py
Diagnóstico completamente refactorizado para MQTT.

Imports
-import pika
+import paho.mqtt.client as mqtt
Función check_port_connectivity() - Mensajes actualizados:
-print("  - Verificar que RabbitMQ esté ejecutándose")
+print("  - Verificar que RabbitMQ MQTT plugin esté habilitado")
+print("  - Puerto MQTT por defecto es 1883")
Función check_rabbitmq_connection() → check_mqtt_connection()
Refactorización completa:

Eliminado parámetro vhost
Usa callbacks MQTT para verificar conexión
Códigos de error MQTT:
0: Conexión exitosa
1: Protocolo incorrecto
2: Identificador cliente inválido
3: Servidor no disponible
4: Usuario/contraseña incorrectos
5: No autorizado
Usa client.loop_start() y espera con timeout
Mensajes de error más específicos para MQTT
Función get_config_from_file() - Actualizada:
-'port': int(config.get("RabbitMq", "port")),
+'port': int(config.get("RabbitMq", "mqtt_port", fallback="1883")),
-'vhost': config.get("RabbitMq", "vhost", "/")
+(eliminado)
Función main() - Actualizada:
-parser = argparse.ArgumentParser(description='Diagnosticar conexión RabbitMQ')
+parser = argparse.ArgumentParser(description='Diagnosticar conexión MQTT')
-parser.add_argument('--port', type=int, default=5672, help='Puerto de RabbitMQ')
+parser.add_argument('--port', type=int, default=1883, help='Puerto MQTT (default: 1883)')
Eliminado argumento --vhost
Todos los mensajes actualizados de "RabbitMQ" a "MQTT"
Configuración Requerida
config.ini
Se debe agregar/modificar en la sección [RabbitMq]:

[RabbitMq]
host = rabbitmq
mqtt_port = 1883
user = guest
password = guest
WARNING

El parámetro vhost ya NO se usa en MQTT

Diferencias Clave: AMQP vs MQTT
Conceptos que cambian:
AMQP (Pika)	MQTT (Paho)
Exchange + Queue + Routing Key	Topic
Virtual Host (vhost)	❌ No existe
Puerto 5672	Puerto 1883
basic_publish()	publish()
basic_consume()	subscribe() + callback
basic_ack()	❌ No requerido en QoS 0
Connection + Channel	Client
start_consuming() (blocking)	loop_start() (non-blocking)
Patrones de Topic MQTT:
Publicación de errores: fiscalberry/errors/{printer_id}
Suscripción de comandos: fiscalberry/# (wildcard para todos los subtopics)
Quality of Service (QoS):
QoS 0: Fire and forget (usado en consumidor)
QoS 1: At least once delivery (usado en error publisher)
Pasos para Replicar la Migración
1. Actualizar dependencias
# Editar requirements.txt y requirements.cli.txt
# Cambiar pika==1.3.2 por paho-mqtt==1.6.1
# Cambiar PyYAML==6.0.2 por PyYAML==6.0.1
pip install -r requirements.txt
2. Modificar archivos en orden:
✅ requirements.txt y requirements.cli.txt
✅ fiscalberry_logger.py (cambio menor)
✅ process_handler.py (cambios menores en logging)
✅ error_publisher.py (refactorización completa)
✅ consumer.py (refactorización completa)
✅ rabbitmq_check.py (refactorización completa)
3. Actualizar configuración
Agregar mqtt_port = 1883 en config.ini

4. Habilitar plugin MQTT en RabbitMQ
rabbitmq-plugins enable rabbitmq_mqtt
5. Probar conexión
python -m fiscalberry.diagnostics.rabbitmq_check --from-config
Notas de Implementación
TIP

Orden recomendado de implementación:

Primero actualizar las dependencias
Luego modificar los archivos de menor a mayor complejidad
Probar cada componente individualmente antes de integrar
CAUTION

Puntos críticos a verificar:

El plugin MQTT debe estar habilitado en RabbitMQ
El puerto 1883 debe estar abierto
Los callbacks MQTT deben configurarse ANTES de llamar a connect()
El loop_start() debe llamarse para que los callbacks funcionen
Testing
Comandos de verificación:
# Verificar conexión MQTT
python -m fiscalberry.diagnostics.rabbitmq_check --from-config
# Verificar con parámetros manuales
python -m fiscalberry.diagnostics.rabbitmq_check --host rabbitmq --port 1883 --user guest --password guest
Verificar que RabbitMQ tiene MQTT habilitado:
rabbitmq-plugins list | grep mqtt
Debe mostrar:

[E*] rabbitmq_mqtt
Referencias
Paho MQTT Documentation: https://www.eclipse.org/paho/index.php?page=clients/python/docs/index.php
RabbitMQ MQTT Plugin: https://www.rabbitmq.com/mqtt.html
MQTT QoS Levels: http://www.steves-internet-guide.com/understanding-mqtt-qos-levels-part-1/



lan de Implementación: Fiscalberry v3.0.x (MQTT)
Migración de AMQP (pika) a MQTT (paho-mqtt) manteniendo RabbitMQ como broker.

User Review Required
IMPORTANT

Decisión requerida: ¿Querés que mantenga los nombres actuales (RabbitMQConsumer, rabbitMqConnected) por compatibilidad, o preferís renombrarlos?

Proposed Changes
Fase 1: Preparación de Branch
git checkout v2.0.x
git pull origin v2.0.x
git checkout -b v3.0.x
Fase 2: Core - Consumer AMQP → MQTT
[MODIFY] 
consumer.py
Cambios principales:

❌ Eliminar: import pika, import pika.exceptions
✅ Agregar: import paho.mqtt.client as mqtt
🔄 Reescribir connect(): usar mqtt.Client() en lugar de pika.BlockingConnection
🔄 Reescribir start(): usar client.loop_forever() en lugar de channel.start_consuming()
❌ Eliminar métodos: _declare_exchange(), _declare_queue(), _bind_queue()
🔄 Cambiar ACK manual (basic_ack/nack) por automático (QoS 1)
Fase 3: Factory - Simplificar
[MODIFY] 
factory.py
Cambios:

❌ Eliminar bloque if protocol == "amqp" (L37-49)
✅ Mantener solo lógica MQTT (sin el else)
🔄 Actualizar docstring
Fase 4: Process Handler - Limpiar excepciones pika
[MODIFY] 
process_handler.py
Cambios:

❌ Eliminar: import pika.exceptions (L7)
❌ Eliminar bloques except pika.exceptions.* (L190-204)
🔄 Agregar manejo de excepciones MQTT equivalentes
✅ Mantener lógica de backoff exponencial
Fase 5: Error Publisher - pika → paho-mqtt
[MODIFY] 
error_publisher.py
Cambios:

❌ Eliminar: import pika, import pika.exceptions (L14-15)
✅ Agregar: import paho.mqtt.client as mqtt
🔄 Reescribir connect(): MQTT en lugar de AMQP
🔄 Cambiar basic_publish() → client.publish()
🔄 Topic: {tenant}/errors en lugar de exchange/queue
Fase 6: Diagnósticos
[MODIFY] 
rabbitmq_check.py
Cambios:

❌ Eliminar: import pika (L8)
✅ Agregar: import paho.mqtt.client as mqtt
🔄 Cambiar verificación de conexión AMQP → MQTT
Fase 7: Dependencias
[MODIFY] 
requirements.txt
-pika
 paho-mqtt>=1.6.0
[MODIFY] 
requirements.cli.txt
-pika
 paho-mqtt>=1.6.0
Fase 8: Logger (opcional)
[MODIFY] 
fiscalberry_logger.py
-logging.getLogger("pika").setLevel(logging.WARNING)
+logging.getLogger("paho").setLevel(logging.WARNING)
Verification Plan
Automated Tests
# Instalar dependencias
pip install -r requirements.txt
# Verificar que pika NO está instalado
pip list | grep pika  # Debe estar vacío
# Verificar que paho-mqtt está instalado
pip list | grep paho  # Debe mostrar paho-mqtt
# Ejecutar diagnóstico
python -m fiscalberry.diagnostics.rabbitmq_check
Manual Verification
Verificar conexión MQTT a RabbitMQ (puerto 1883)
Enviar mensaje de prueba desde Paxapos
Verificar recepción y procesamiento del mensaje
Provocar error de impresora y verificar publicación a topic de errores
Simular desconexión y verificar reconexión automática




#################IMPORTANTE#####################


import paho.mqtt.client as mqtt
import json
# Configuración de conexión
MQTT_BROKER = "tu-servidor.com"  # o IP del servidor
MQTT_PORT = 1883
MQTT_USER = "fiscalberry"
MQTT_PASSWORD = "hiperquantum"
PRINTER_UUID = "12345678-1234-1234-1234-123456789abc"  # UUID de tu impresora
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Conectado a RabbitMQ MQTT")
        # Suscribirse al topic de esta impresora con QoS 1
        client.subscribe(PRINTER_UUID, qos=1)
    else:
        print(f"❌ Error de conexión: {rc}")
def on_message(client, userdata, msg):
    """
    Callback cuando llega un mensaje
    """
    try:
        # Decodificar el mensaje
        print_job = json.loads(msg.payload.decode())
        print(f"📄 Trabajo de impresión recibido: {print_job}")
        
        # AQUÍ PROCESAS LA IMPRESIÓN
        # ... tu lógica de impresión ...
        
        # ✅ IMPORTANTE: El ACK se envía automáticamente con QoS 1
        # No necesitas hacer nada extra, Paho lo maneja
        
    except Exception as e:
        print(f"❌ Error procesando mensaje: {e}")
        # Si hay error, el mensaje NO se marca como ACK
        # y quedará en la cola para reintentar
# Crear cliente MQTT
client = mqtt.Client(
    client_id=f"fiscalberry-{PRINTER_UUID}",  # ID único del cliente
    clean_session=False,  # 🔥 CRÍTICO: Sesión persistente
    protocol=mqtt.MQTTv311
)
# Configurar credenciales
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
# Configurar callbacks
client.on_connect = on_connect
client.on_message = on_message
# Conectar al broker
client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
# Loop infinito (bloqueante)
client.loop_forever()



🔑 Puntos Clave:
1. Credenciales
python
client.username_pw_set("fiscalberry", "hiperquantum")
Usa el mismo usuario que en AMQP/Pika
RabbitMQ valida los permisos del usuario fiscalberry
2. Sesión Persistente (CRÍTICO)
python
clean_session=False
Con False: RabbitMQ guarda la suscripción y los mensajes pendientes aunque se corte internet
Con True: Si se desconecta, pierde todos los mensajes pendientes
3. QoS 1 (Quality of Service)
python
client.subscribe(PRINTER_UUID, qos=1)
QoS 0: Fire and forget (no garantía)
QoS 1: At least once (con ACK automático) ✅ RECOMENDADO
QoS 2: Exactly once (más lento, innecesario para impresión)
4. ACK Automático
Con QoS 1, Paho MQTT envía el ACK automáticamente DESPUÉS de ejecutar on_message. Si tu función on_message termina sin errores, el mensaje se marca como procesado y se elimina de la cola.

Si hay una excepción, el mensaje NO se marca como ACK y quedará en la cola para reintentar.