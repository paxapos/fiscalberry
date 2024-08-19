
# ¿Para qué sirve?
Para enviar un JSON (mediante websocket), que fiscalberry lo reciba, lo transforme en un conjunto de comandos compatible con la impresora instalada, conecte con la impresora y responda al websocket con la respuesta que nos envió la impresora.


Descarga la última versión socketio para windows
[fiscalberry.zip](https://github.com/user-attachments/files/16653314/fiscalberry.zip)


# ¿Qué es?
Fiscalberry es un servidor de websockets desarrollado en Python pensado para que corra en una raspberry-pi (de ahí viene el nombre de este proyecto). **Pero funciona perfectamente en otros sistemas operativos.**
![fiscalberry JSON](http://alevilar.com/uploads/entendiendo%20fiscalberry.jpg)

# ¿Qué impresoras son compatibles?
Fiscalberry tiene drivers desarrollados para conectarse con 2 tipos de impresoras: Fiscales y Receipt.

Impresoras Fiscales compatibles: Hasar y Epson

Nueva versión con soporte para las últimas impresoras Fiscales de segunda generación (2gen) HASAR y EPSON <br>
Modelos compatibles (HASAR: SMH/PT-250F, EPSON: TM-T900FA)


Impresoras Receipt (de comandas) compatibles: las que soportan ESC/P


## Fiscalberry como servidor de impresión (print-server) de impresoras receipt (comanderas) y fiscales
Fiscalberry es un 3x1, actúa como: protocolo, servidor y driver facilitando al programador la impresión de tickets, facturas o comprobantes fiscales.

- _PROTOCOLO_: Siguiendo la estructura del JSON indicado, se podrá imprimir independientemente de la impresora conectada. Fiscalberry se encargará de conectarse y pelear con los códigos y comandos especiales de cada marca/modelo.
- _SERVIDOR_: gracias al servidor de websockets es posible conectar tu aplicación para que ésta fácilmente pueda enviar JSON's y recibir las respuestas de manera asíncrona.
- _DRIVER_: Es el encargado de transformar el JSON genérico en un conjunto de comandos especiales según marca y modelo de la impresora. Aquí es donde se adaptó el código del proyecto de Reingart (https://github.com/reingart/pyfiscalprinter) para impresoras Hasar y Epson.

Funciona en cualquier PC con cualquier sistema operativo que soporte Python.

La idea original fue pensada para que funcione en una raspberry pi, cuyo fin es integrar las fiscales al mundo de la Internet de las Cosas (IOT).

## ¿Para quienes está pensado?
Para los desarrolladores que desean enviar a imprimir mediante JSON (es decir, desde algún lugar de la red, internet, intranet, etc, etc) de una forma "estándar" y que funcione en cualquier impresora, marca y modelo.

## PROBALO

### Descargar

usando git
```sh
git clone https://github.com/paxapos/fiscalberry.git
```
o directamente el ZIP: https://github.com/paxapos/fiscalberry/archive/master.zip

### Instalar Dependencias

ATENCIÓN: Funciona con Python 2.7.* NO en Python 3!

probado bajo python 2.7.6 en Linux, Raspian, Ubuntu, Open Suse y Windows

Se necesitan varias dependencias:
```sh
sudo pip install -r requirements.txt

```

Si te encontras con el error "socket.gaierror:  Name or service not known"

A veces, en Linux (Open Suse), ser necesario poner el nombre del equipo (hostname) en el archivo /etc/hosts, si es que aún no lo tenías.
Generalmente el archivo hosts viene solo con la dirección "127.0.0.1 localhost", 

para solucionarlo debés ejecutar el comando 
```bash
hostname
```
y ver cuál es el nombre de la máquina para agregarlo al archivo /etc/hosts
127.0.0.1 nombre-PC localhost



### Iniciar el programa

```sh
sudo python server.py

# o iniciar como demonio linux
sudo python rundaemon.py
```

Ahora ya puedes conectarte en el puerto 12000
entrando a un browser y la dirección http://localhost:12000

## Conceptos básicos ¿Cómo funciona?

Supongamos que tenemos este JSON genérico:
```
{
    "ACCION_A_EJECUTAR": {
        PARAMETROS_DE_LA_ACCION
        ...
    }
}
```
Lo enviamos usando websockets a un host y puerto determinado (el servidor fiscalberry), éste lo procesa, envía a imprimir, y responde al cliente con la respuesta de la impresora. Por ejemplo, devolviendo el número del último comprobante impreso.


Otro ejemplo más concreto: queremos imprimir un ticket, esta acción en el protocolo fiscalberry se lo llama como acción "printTicket" y está compuesta de 2 parámetros obligatorios: "encabezado" e "items".

El "encabezado" indica el tipo de comprobante a imprimir (y también podría agregarle datos del cliente, que son opcionales). 
Los ítems son una lista de productos a imprimir donde, en este ejemplo, tenemos una coca cola, con impuesto de 21%, importe $10, descripción del producto "COCA COLA" y la cantidad vendida es 2.

```json
{
    "printTicket": {
        "encabezado": {
            "tipo_cbte": "T",      // tipo tiquet *obligatorio
        },
        "items": [
            {
                "alic_iva": 21.0,  // impuesto
                "importe": 10,     // importe
                "ds": "COCA COLA", // descripcion producto
                "qty": 2.0         // cantidad
            }
        ]
    }
}
```



### JSON RESPUESTA
Existen 2 tipos de respuesta y siempre vienen con la forma de un JSON.


Aquellos que son una respuesta a un comando enviado, comienzan con "ret"
**_{"ret": ......}_**


Aquellos que son un mensaje directo de algun dispositivo conectado, vienen con "msg"

**_{"msg": ......}_**

```javascript
// ejemplo retorno de un mensaje cuando no hay papel
{"msg": ["Poco papel para comprobantes o tickets"]}
```



#### NOTA:
Deberás enviar JSON válidos al servidor. Recomendamos usar la pagina http://jsonlint.com/ para verificar como tu programa esta generando los JSON.
