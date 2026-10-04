# Logs en vivo (live logs)

Permite que un superadmin vea, desde el panel **Fiscalberry Admin**, los logs de
un Fiscalberry en tiempo real, sin acceso remoto al equipo. Se activa solo bajo
demanda y se apaga solo.

## Flujo

```
Panel (drawer de la cola)
  -> paxa-core  POST /paxaprinters/{uuid}/live-logs/{start|renew|stop}
  -> Redis      canal "paxaprinters"
  -> socketio-app -> Socket.IO (namespace /paxaprinter)
  -> Fiscalberry  evento paxaprinter:logs:{start|renew|stop}
  -> MQTT        fiscalberry/logs/{tenant}/{uuid}/{sessionId}   (QoS 0)
  -> RabbitMQ    amq.topic, routing key fiscalberry.logs.{tenant}.{uuid}.{sessionId}
  -> Panel       cola temporal exclusiva de la sesion -> WebSocket -> navegador
```

- `start` abre una sesion: se manda primero el historial reciente (hasta 200
  lineas, `snapshotLines`) y despues cada linea nueva, en batches cada 250 ms.
- El panel renueva el lease (`renew`) cada ~30 s con un `expiresAt` corto. Si el
  panel deja de renovar, la sesion vence sola. El lease nunca supera 600 s.
- `stop` (o el vencimiento de la ultima sesion) restaura el nivel de log y cierra
  la conexion MQTT de logs.
- Solo se atienden comandos cuyo `uuid` es el del propio equipo.

## Conexion MQTT propia

Los logs salen por una conexion MQTT **separada** (`client_id`
`fiscalberry-logs-{uuid}`), igual que los errores. Nunca por la conexion de la
cola de impresion: si el broker rechaza el topic de logs, RabbitMQ **cierra** la
conexion del cliente, y con la conexion compartida el comercio se quedaba sin
imprimir mientras alguien miraba los logs.

## Requisito en el broker

El usuario MQTT de los Fiscalberry necesita permiso de escritura de topic en
`amq.topic` para `fiscalberry.logs.*` (ademas de `errors` y `heartbeat`):

```json
"write": "^fiscalberry\\.(errors|heartbeat|logs)\\..*$"
```

Sin ese permiso no se rompe nada, pero los logs no llegan al panel. En paxa-core
la funcion esta apagada hasta definir `PAXAPRINTER_LIVE_LOGS_ENABLED=true`.

## Payload

```json
{
  "schemaVersion": 1,
  "sessionIds": ["<sessionId>"],
  "uuid": "<uuid>",
  "tenant": "<tenant>",
  "droppedCount": 0,
  "entries": [
    {
      "sequence": 1234,
      "timestamp": "2026-10-04T12:00:00.123456+00:00",
      "level": "WARNING",
      "logger": "SocketIO",
      "message": "...",
      "exception": "Traceback ... (o null)"
    }
  ]
}
```

- Los valores que parecen secretos (`password=`, `token:`, `api_key=`, ...) se
  reemplazan por `***` antes de salir del equipo.
- `droppedCount` informa lineas perdidas (buffer lleno o publicacion fallida).

Codigo: `common/live_log_stream.py` (captura y sesiones),
`common/rabbitmq/live_log_publisher.py` (conexion MQTT) y los handlers en
`common/fiscalberry_sio.py`.
