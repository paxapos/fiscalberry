# 🔒 Seguridad MQTT: Puerto 1883 vs 8883

## ⚠️ Estado Actual: SIN ENCRIPTACIÓN

**Puerto actual:** `1883` (MQTT sin TLS)

```
┌─────────────┐                              ┌─────────────┐
│ Fiscalberry │ ──── TEXTO PLANO ────────→   │  RabbitMQ   │
│  (Cliente)  │      (Sin encriptar)          │  (Broker)   │
└─────────────┘                              └─────────────┘
```

**Riesgo:** Cualquier persona en la red puede interceptar:

- Credenciales (user/password)
- Comandos de impresión
- Datos sensibles de tickets

---

## 🔐 Puertos MQTT

| Puerto    | Protocolo      | Seguridad                   | Uso                        |
| --------- | -------------- | --------------------------- | -------------------------- |
| **1883**  | MQTT           | ❌ Sin encriptar            | Desarrollo, redes privadas |
| **8883**  | MQTT over TLS  | ✅ Encriptado SSL/TLS       | **PRODUCCIÓN**             |
| **15675** | MQTT WebSocket | ⚠️ Depende (puede usar WSS) | Web browsers               |

---

## 🎯 Recomendaciones por Ambiente

### Desarrollo Local (OK usar 1883)

```
✅ localhost / 127.0.0.1
✅ Red privada controlada
✅ Testing rápido
```

### Producción (DEBE usar 8883)

```
❌ Internet público
❌ Redes WiFi compartidas
❌ Datos sensibles (tickets, ventas)
```

---

## 🛠️ Configuración TLS en RabbitMQ

### Paso 1: Generar Certificados

```bash
# Opción A: Certificados autofirmados (desarrollo)
cd /etc/rabbitmq/certs

# Generar CA
openssl req -x509 -newkey rsa:4096 -days 365 -nodes \
  -keyout ca-key.pem -out ca-cert.pem \
  -subj "/CN=RabbitMQ CA"

# Generar certificado del servidor
openssl req -newkey rsa:4096 -nodes \
  -keyout server-key.pem -out server-req.pem \
  -subj "/CN=rabbitmq.tudominio.com"

# Firmar con CA
openssl x509 -req -in server-req.pem -days 365 \
  -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
  -out server-cert.pem

# Permisos
chown rabbitmq:rabbitmq *.pem
chmod 600 *-key.pem
```

```bash
# Opción B: Let's Encrypt (producción)
certbot certonly --standalone -d rabbitmq.tudominio.com
```

### Paso 2: Configurar RabbitMQ

**Archivo:** `/etc/rabbitmq/rabbitmq.conf`

```ini
# MQTT sin TLS (puerto 1883) - MANTENER para v1.0.26
mqtt.listeners.tcp.default = 1883

# MQTT con TLS (puerto 8883) - NUEVO para v3.0.x en producción
mqtt.listeners.ssl.default = 8883

# Certificados TLS
ssl_options.cacertfile = /etc/rabbitmq/certs/ca-cert.pem
ssl_options.certfile   = /etc/rabbitmq/certs/server-cert.pem
ssl_options.keyfile    = /etc/rabbitmq/certs/server-key.pem
ssl_options.verify     = verify_peer
ssl_options.fail_if_no_peer_cert = false

# Versiones TLS permitidas
ssl_options.versions.1 = tlsv1.2
ssl_options.versions.2 = tlsv1.3
```

### Paso 3: Reiniciar RabbitMQ

```bash
systemctl restart rabbitmq-server

# Verificar que ambos puertos están escuchando
netstat -tuln | grep -E '1883|8883'
# Debería mostrar:
# tcp  0.0.0.0:1883  (sin TLS)
# tcp  0.0.0.0:8883  (con TLS)
```

---

## 🐍 Configuración en Fiscalberry

### Opción 1: Variable de Entorno

```python
# En consumer.py
import os

class RabbitMQConsumer:
    def __init__(self, host, port, user, password, queue_name, ...):
        self.host = host
        self.port = int(port)

        # Detectar si usar TLS
        self.use_tls = os.getenv('MQTT_USE_TLS', 'false').lower() == 'true'

        # Ruta al certificado CA (si se usa TLS)
        self.ca_cert = os.getenv('MQTT_CA_CERT', '/etc/fiscalberry/ca-cert.pem')
```

```python
# En connect()
def connect(self):
    self.client = mqtt.Client(...)

    # Configurar TLS si está habilitado
    if self.use_tls:
        import ssl
        self.client.tls_set(
            ca_certs=self.ca_cert,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        logger.info(f"TLS habilitado - usando certificado: {self.ca_cert}")

    self.client.connect(self.host, self.port, keepalive=60)
```

### Opción 2: Configuración en config.ini

```ini
[RabbitMq]
host = rabbitmq.tudominio.com
port = 8883
use_tls = true
ca_cert = /etc/fiscalberry/certs/ca-cert.pem
```

---

## 🧪 Testing TLS

### Verificar conexión TLS con mosquitto_pub

```bash
# Sin TLS (puerto 1883)
mosquitto_pub -h localhost -p 1883 -t test -m "hola"

# Con TLS (puerto 8883)
mosquitto_pub -h rabbitmq.tudominio.com -p 8883 \
  --cafile /etc/rabbitmq/certs/ca-cert.pem \
  -t test -m "hola seguro"
```

### Verificar certificado

```bash
openssl s_client -connect rabbitmq.tudominio.com:8883 -showcerts
```

---

## 📊 Comparación de Rendimiento

| Aspecto         | Puerto 1883 | Puerto 8883           |
| --------------- | ----------- | --------------------- |
| **Latencia**    | ~1ms        | ~2-3ms (overhead TLS) |
| **CPU**         | Bajo        | Medio (encriptación)  |
| **Seguridad**   | ❌ Ninguna  | ✅ Alta               |
| **Complejidad** | ✅ Simple   | ⚠️ Requiere certs     |

**Conclusión:** El overhead de TLS es **mínimo** comparado con el beneficio de seguridad.

---

## 🚀 Plan de Migración a TLS

### Fase 1: Preparación (1 semana)

- [ ] Generar certificados
- [ ] Configurar puerto 8883 en RabbitMQ
- [ ] Mantener puerto 1883 activo (backward compatibility)

### Fase 2: Testing (1 semana)

- [ ] Probar conexión TLS en desarrollo
- [ ] Verificar rendimiento
- [ ] Documentar proceso

### Fase 3: Rollout Gradual (1 mes)

- [ ] Nuevos clientes v3.0.x usan puerto 8883
- [ ] Clientes v1.0.26 siguen en puerto 1883
- [ ] Monitorear errores

### Fase 4: Deprecación (3-6 meses)

- [ ] Migrar clientes v1.0.26 restantes
- [ ] Cerrar puerto 1883
- [ ] Solo TLS en producción

---

## ⚠️ Consideraciones Importantes

### 1. Certificados Autofirmados

Si usás certificados autofirmados, Fiscalberry debe tener el `ca-cert.pem`:

```python
# Opción: Deshabilitar verificación (SOLO DESARROLLO)
client.tls_set(cert_reqs=ssl.CERT_NONE)
client.tls_insecure_set(True)  # ⚠️ INSEGURO
```

### 2. Let's Encrypt

Para producción, usar Let's Encrypt es **gratis** y **automático**:

```bash
# Instalar certbot
apt install certbot

# Obtener certificado
certbot certonly --standalone -d rabbitmq.tudominio.com

# Auto-renovación
certbot renew --dry-run
```

### 3. Firewall

```bash
# Abrir puerto 8883 (MQTT TLS)
ufw allow 8883/tcp

# Opcional: Cerrar 1883 si ya no se usa
ufw deny 1883/tcp
```

---

## 🔍 Debugging TLS

### Logs de RabbitMQ

```bash
tail -f /var/log/rabbitmq/rabbit@hostname.log | grep -i tls
```

### Logs de Fiscalberry

```python
# Habilitar logs de SSL en paho-mqtt
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Errores Comunes

| Error                       | Causa                    | Solución                             |
| --------------------------- | ------------------------ | ------------------------------------ |
| `certificate verify failed` | CA cert incorrecto       | Verificar ruta a `ca-cert.pem`       |
| `Connection refused`        | Puerto cerrado           | Verificar firewall y RabbitMQ config |
| `SSL handshake failed`      | Versión TLS incompatible | Usar TLSv1.2 o superior              |

---

## 📝 Resumen

### Estado Actual (Desarrollo Express)

```
Puerto: 1883 (sin TLS)
Seguridad: ❌ Texto plano
Uso: ✅ OK para desarrollo local
```

### Recomendación Producción

```
Puerto: 8883 (con TLS)
Seguridad: ✅ Encriptado
Uso: ✅ OBLIGATORIO para producción
```

### Próximos Pasos

1. **Corto plazo (ahora):** Usar 1883 para desarrollo
2. **Mediano plazo (1-2 meses):** Implementar TLS en producción
3. **Largo plazo (6 meses):** Deprecar puerto 1883

---

## 📚 Referencias

- [RabbitMQ MQTT Plugin](https://www.rabbitmq.com/mqtt.html)
- [RabbitMQ TLS Support](https://www.rabbitmq.com/ssl.html)
- [Paho MQTT TLS](https://www.eclipse.org/paho/index.php?page=clients/python/docs/index.php#tls-set)
- [Let's Encrypt](https://letsencrypt.org/)
