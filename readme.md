# ¿Para qué sirve?
Para enviar un JSON (mediante websocket), que fiscalberry lo reciba, lo transforme en un conjunto de comandos compatible con la impresora instalada, conecte con la impresora y responda al websocket con la respuesta que nos envió la impresora.

# ¿Qué es?
Fiscalberry es un servidor de websockets desarrollado en python pensado para que corra en una raspberry-pi (de ahi viene el nombre de este proyecto). **Pero funciona perfectamente en otros sistemas operativos.**
![fiscalberry JSON](http://alevilar.com/uploads/entendiendo%20fiscalberry.jpg)

# ¿Qué impresoras son compatibles?
Fiscalberry tiene drivers desarrollados para conectarse con 2 tipos de impresoras: Fiscales y Receipt.

Impresoras Fiscales compatibles: Hasar y Epson

Impresoras Receipt (de comandas) compatibles: las que soportan ESC/P


## NOTA IMPORTANTE: Este proyecto es una adaptación del original https://github.com/reingart/pyfiscalprinter

Realizé un refactor del proyecto original para adaptarlo a una necesidad distinta y moderna, mejorándolo para usar mediante websockets con un protocolo genérico JSON.

## Fiscalberry como servidor de impresión (print-server) de impresoras receipt (comanderas) y fiscales
Fiscalberry es un 3x1, actúa como: protocolo, servidor y driver facilitando al programador la impresión de tickets, facturas o comprobantes fiscales.

- _PROCOLO_: Siguiendo la estructura del JSON indicado, se podrá imprimir independientemente de la impresora conectada. Fiscalberry se encargará de conectarse y pelear con los códigos y comandos especiales de cada marca/modelo.
- _SERVIDOR_: gracias al servidor de websockets es posible conectar tu aplicación para que ésta fácilmente pueda enviar JSON's y recibir las respuestas de manera asíncrona.
- _DRIVER_: Es el encargado de transformar el JSON genérico en un conjunto de comandos especiales según marca y modelo de la impresora. Aquí es donde reutilicé el código del proyecto de Reingart (https://github.com/reingart/pyfiscalprinter) para impresoras Hasar y Epson.

Funciona en cualquier PC con cualquier sistema operativo que soporte python.

La idea original fue pensada para que funcione en una raspberry pi, cuyo fin es integrar las fiscales al mundo de la Internet de las Cosas (IOT).

## ¿Para quienes esta pensado?
Para los desarrolladores que desean enviar a imprimir mediante JSON (es decir, desde algun lugar de la red, internet, intranet, etc, etc) de una forma "estandar" y que funcione en cualquier impresora, marca y modelo.

## PROBALO

### Descargar

usando git
```sh
git clone https://github.com/paxapos/fiscalberry.git
```
o directamente el ZIP: https://github.com/paxapos/fiscalberry/archive/master.zip

### Instalar Dependencias

ATENCION: Funciona con python 2.7.* NO en python 3!

probado bajo python 2.7.6 en Linux, Raspian, Ubuntu, Open Suse y Windows

Se necesitan varias dependencias:
```sh
sudo apt-get install python-pip libjpeg-dev
sudo pip install pyserial requests
sudo apt-get install build-essential python-dev
sudo pip install tornado
sudo apt-get install nmap
sudo pip install python-nmap
sudo apt-get install python-imaging python-dev python-setuptools
sudo pip install python-escpos
```

Si te encontras con el error "socket.gaierror:  Name or service not known"

A veces, en Linux, ser necesario poner el nombre del equipo (hostname) en el archivo /etc/hosts, si es que aun no lo tenias.
Generalmente el archivo hosts viene solo con la direccion "127.0.0.1 localhost", 

para solucionarlo debés ejecutar el comando 
```bash
hostname
```
y ver cual es el nombre de la máquina para agregarlo al archivo /etc/hosts
127.0.0.1 nombre-PC localhost


### Instalar Daemond
```
// TODO
```

### Iniciar el programa

```sh
sudo python server.py

# o iniciar como demonio
sudo python rundaemon.py
```

Ahora ya puedes conectarte en el puerto 12000
entrando a un browser y la direccion http://localhost:12000

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
Lo enviamos usando websockets a un host y puerto determinado (el servidor fiscalberry), éste lo procesa, envia a imprimir, y responde al cliente con la respuesta de la impresora. Por ejemplo, devolviendo el número del último comprobante impreso.


Otro ejemplo más concreto: queremos imprimir un ticket, esta acción en el protocolo fiscalberry se lo llama como accion "printTicket" y está compuesta de 2 parámetros obligatorios: "encabezado" e "items".

El "encabezado" indica el tipo de comprobante a imprimir (y también podria agregarle datos del cliente, que son opcionales). 
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




### JSON Accion: **printTicket**

Protocolo para formar un JSON con el objetivo de imprimir un ticket.
Se compone de 3 distintas partes:
* Encabezado
* Ítems
* Pagos (opcional)

Al imprimir un ticket el servidor enviará 3 comandos previos que pueden resultar en un mensaje de warning: "comando no es valido para el estado de la impresora fiscal ".
Esto no es un error, sino que antes de imprimir un tiquet envia:
* CANCELAR CUALQUIER TIQUET ABIERTO
* CANCELAR COMPROBANTE NO FISCAL
* CANCELAR NOTA ED CREDITO O DEBITO
Es una comprobación útil que ahorrará dolores de cabeza y posibilidades de bloquear la impresora fiscal.

#### Encabezado (Obligatorio)
tipo: Json

```javascript
{
    "encabezado": {
        "tipo_cbte": "FA", // tipo tiquet VARIABLE ESTATICA *obligatorio
        "nro_doc": "20267565393", // identificacion cliente
        "domicilio_cliente": "Rua 76 km 34.5 Alagoas", // domicilio
        "tipo_doc": "DNI", // tipo documento VARIABLE ESTATICA (mas abajo se detallan)
        "nombre_cliente": "Joao Da Silva", // nombre cliente
        "tipo_responsable": "RESPONSABLE_INSCRIPTO" // VARIABLE ESTATICA
    }
}     
```
ejemplo Nota de Crédito "A"     
```javascript
{
    "encabezado": {
        "tipo_cbte": "NCB", // tipo tiquet VARIABLE ESTATICA *obligatorio		        
        "referencia": 000100012 // numero de comprobante impreso
    }
}
                
```


##### Variables Estáticas Para Encabezado

	tipo_cbte
	        "T"  # tiques
	        "FA", 
	        "FB", 
	        "NDA", 
	        "NCA", 
	        "NDB", 
	        "NCB", 
	        "FC", 
	        "NDC", 
	        "NDC",

        
	tipo_responsable
	        "RESPONSABLE_INSCRIPTO"
	        "RESPONSABLE_NO_INSCRIPTO"
	        "NO_RESPONSABLE"
	        "EXENTO"
	        "CONSUMIDOR_FINAL"
	        "RESPONSABLE_MONOTRIBUTO"
	        "NO_CATEGORIZADO"
	        "PEQUENIO_CONTRIBUYENTE_EVENTUAL"
	        "MONOTRIBUTISTA_SOCIAL"
	        "PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL"
	                        

	tipo_doc
	        "DNI"
	        "CUIT"
	        "LIBRETA_ENROLAMIENTO"
	        "LIBRETA_CIVICA"
	        "CEDULA"
	        "PASAPORTE"
	        "SIN_CALIFICADOR"




#### Ítems (Obligatorio)
tipo: list

```javascript
{
    "items": [
        {
            "alic_iva": 21.0, // * Obligatorio
            "importe": 0.01, // * Obligatorio
            "ds": "Descripcion Producto", // * Obligatorio
            "qty": 1.0 // * Obligatorio
        },
        {
            "alic_iva": 21.0,
            "importe": 0.22,
            "ds": "COCA COLA",
            "qty": 2.0
        }
    ]  
}               
                
```
__Todos los campos del ítem son obligatorios__



#### Pagos (Opcional)
tipo: list
```javascript
{
    "pagos": [
            {
            "ds": "efectivo", // * Obligatorio
            "importe": 1.0    // * Obligatorio
            }
        ]
    }
```

#### Ejemplo completo de "printTicket"

```javascript
json = {		
    "printTicket": {
        "encabezado": {
            "tipo_cbte": "FA",
            "nro_doc": "20267565393",
            "domicilio_cliente": "Rua 76 km 34.5 Alagoas",
            "tipo_doc": "DNI",
            "nombre_cliente": "Joao Da Silva",
            "tipo_responsable": "RESPONSABLE_INSCRIPTO"
        },
        "items": [
            {
                "alic_iva": 21.0,
                "importe": 0.01,
                "ds": "PIPI",
                "qty": 1.0
            },
            {
                "alic_iva": 21.0,
                "importe": 0.22,
                "ds": "COCA",
                "qty": 2.0
            }
        ],
        "pagos": [
            {
                "ds": "efectivo",
                "importe": 1.0
            }
        ]
    }
}

json = {
    "printTicket": {
        "encabezado": {
            "tipo_cbte": "T"
        },
        "items": [{
            "alic_iva": 21.0,
            "importe": 0.01,
            "ds": "PEPSI",
            "qty": 1.0
        }, {
            "alic_iva": 21.0,
            "importe": 0.12,
            "ds": "COCA",
            "qty": 2.0
        }]
    }
}
```





### JSON Accion: **configure**

Al enviar este JSON se puede configurar el servidor de impresión directamente desde el cliente.
El archivo de configuración que será modificado es **config.ini** que también puede ser modificado a mano desde consola.

Los parámetros son:
		
#### "printerName" 

Se pueden configurar muchas impresoras. Cada impresora estara como nombre de segmento del archivo config.ini

se deberá indicar un nombre para cada impresora.

**_NOTA: Tiene que haber al menos una impresora fiscal con el nombre "IMPRESORA_FISCAL"_**


#### "marca" 
Las opciones son: 
* "Epson"
* "Hasar"
* "Epsond" Para Dummy
* "Hasard" Para Dummy
		
#### "modelo"

Epson:
* "tickeadoras"
* "epsonlx300+"
* "tm-220-af"
* "tm-t900fa"

Hasar:
* "615"
* "715v1"
* "715v2"
* "320"


#### "path"

En Windows "COM1"... "COM2", etc.  
En linux "/dev/ttyUSB0". Pueden listarse con `./linux_ls_ttyusb.sh`  
No es requerido para Epson y Hasard  

#### "driver" (opcional)
Es la "salida" o sea, es el medio por donde saldrán las impresiones.

Opciones: 
* Hasar
* Epson
* Hasard -> Dummy Driver
* Epsond -> Dummy Driver
* Dummy
* File

Por defecto se utiliza el mismo driver que la impresora, pero en algunas casos (desarrollo) se pueden utilizar drivers extra:
* Dummy (no presenta salidas en ningun lado, por lo tanto no usa el campo "path")
* File (para usar este driver es necesario que en el campo "path" se coloque la ruta donde escribir la salida que será un archivo donde imprimirá las respuestas.


```javascript
// EJ: 
{
    "configure": {
        "printerName": "IMPRESORA_FISCAL",
        "marca": "Hasar",
        "modelo": "715v2",
        "path": "/dev/ttyUSB0"
    }
}

{
    "configure": {
        "printerName": "IMPRESORA_FISCAL",
        "marca": "Epson",
        "modelo": "tm-220-af",
        "path": "/tmp/respuestas.txt",
        "driver": "File"
    }
}
```

### JSON Accion: **openDrawer**


Abre la gaveta de dinero. No es necesario pasar parámetros extra.

```javascript
// EJ:
{
    "openDrawer": true
}
```


### JSON Accion: **getStatus**

retorna la configuracon actual del servidor.  No es necesario pasar parámetros extra.

```javascript
// EJ: 
{
    "getStatus": {}
}
```


### JSON Accion: **dailyClose**


Imprime un cierre fiscal X o Z dependiendo el parámetro enviado

```javascript
// EJ: Imprime un cierre "Zeta"
{
    "dailyClose": "Z"
}

// Ej: imprimiendo un "X"
{
    "dailyClose": "X"
}
```


### JSON Accion: **getAvaliablePrinters**

lista todas las impresoras configuradas en el archivo config.ini


### JSON Accion: **setHeader**

Permite agregar lineas al encabezado

```json
{
    "setHeader": [
        "Linea 1",
        "Linea 22 22",
        "Linea 3 3 3 3 3"
    ]
}

```

### JSON Accion: **setTrailer**

Permite agregar lineas al encabezado

```javascript
{
    "setTrailer": [
        "Linea 1",
        "Linea 22 22",
        "Linea 3 3 3 3 3"
    ]
}

// cada item de la lista es una linea a modificar, por ejemplo
{
    "setTrailer": [
        "", 				// dejara la linea 1 vacia
        "Linea 22 modif",   // modificara la linea 2		
    ]
}

```


### JSON Accion: **getLastNumber**

Devuelve el numero del ultimo comprobante impreso segun tipo de factura
como parámetro hay que pasarle una variable estatica "tipo_cbte"

```javascript
// EJ: ultimo numero de tiquet
{
    "getLastNumber": "T"
}

// EJ: ultimo comprobante Factura A
{
    "getLastNumber": "FA"
}


// EJ: ultimo comprobante Nota de Credito A
{
    "getLastNumber": "NCA"
}

```



### JSON RESPUESTA
Existen 2 tipos de respuesta y siempre vienen con la forma de un JSON.


Aquellos que son una respuesta a un comando enviado, comienzan con "ret"
**_{"ret": ......}_**


Aquellos que son un mensaje de la impresora fiscal, vienen con "msg"

**_{"msg": ......}_**

```javascript
// ejemplo retorno de un mensaje cuando no hay papel
{"msg": ["Poco papel para comprobantes o tickets"]}
```



#### NOTA:
Deberas enviar JSON válidos al servidor. Recomendamos usar la pagina http://jsonlint.com/ para verificar como tu programa esta generando los JSON.
