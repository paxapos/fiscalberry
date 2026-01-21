# Fiscalberry v3.0.x

> **⚠️ IMPORTANTE:** Esta rama utiliza exclusivamente el protocolo **MQTT** (paho-mqtt).  
> Para AMQP (pika), usar la rama `v2.0.x`.

---

## Requisitos

- Python 3.10+
- RabbitMQ con **plugin MQTT habilitado**

```bash
# Habilitar MQTT en RabbitMQ
rabbitmq-plugins enable rabbitmq_mqtt
```

---

## Instalación

```bash
# Clonar y cambiar a rama v3.0.x
git clone https://github.com/paxapos/fiscalberry.git
cd fiscalberry
git checkout v3.0.x

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt
```

---

## Configuración MQTT

Editar `config.ini`:

```ini
[RabbitMq]
host = tu-servidor.com
port = 1883
user = fiscalberry
password = tu_password

[SERVIDOR]
uuid = 12345678-1234-1234-1234-123456789abc
```

> **Nota:** El `uuid` es el topic MQTT al que se suscribe el dispositivo.

---

## Diferencias con v2.0.x (AMQP)

| Aspecto  | v2.0.x (AMQP)      | v3.0.x (MQTT)                     |
| -------- | ------------------ | --------------------------------- |
| Librería | pika               | paho-mqtt                         |
| Puerto   | 5672               | 1883                              |
| Concepto | Exchange + Queue   | Topic                             |
| ACK      | Manual (basic_ack) | Automático (QoS 1)                |
| Sesión   | N/A                | Persistente (clean_session=False) |

---

## Ejecución

```bash
# CLI
python -m fiscalberry

# Diagnóstico MQTT
python -m fiscalberry.diagnostics.rabbitmq_check --from-config
```

---

## Arquitectura MQTT

```
                    ┌─────────────────┐
                    │   RabbitMQ      │
                    │  (MQTT Plugin)  │
                    │    :1883        │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Topic:   │   │ Topic:   │   │ Topic:   │
        │ UUID-1   │   │ UUID-2   │   │ UUID-N   │
        └────┬─────┘   └────┬─────┘   └────┬─────┘
             │              │              │
             ▼              ▼              ▼
        Fiscalberry    Fiscalberry    Fiscalberry
        (Impresora 1)  (Impresora 2)  (Impresora N)
```

---

## Características MQTT Clave

1. **Sesión Persistente** (`clean_session=False`)
   - RabbitMQ guarda mensajes pendientes si el cliente se desconecta
   - Al reconectar, recibe los mensajes que perdió

2. **QoS 1** (At Least Once)
   - ACK automático cuando `on_message` termina sin errores
   - Si hay excepción, el mensaje queda en cola para reintentar

3. **Topic = UUID**
   - Cada impresora se suscribe a su propio UUID
   - Simplifica el routing vs exchanges/queues de AMQP
