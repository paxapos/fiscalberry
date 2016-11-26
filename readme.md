# fiscalberry

## NOTA IMPORTANTE: Este proyecto es una mejora del original https://github.com/reingart/pyfiscalprinter

Realizé un refactor del proyecto original para adaptarlo a una necesidad distinta y moderna, mejorándolo para tal uso.

## ¿Qué es?
Fiscalberry es un 3x1, actúa como: protocolo, servidor y driver facilitando al programador la impresión de tickets, facturas o comprobantes fiscales.

- _PROCOLO_: Siguiendo la estructura del JSON indicado, se podrá imprimir independientemente de la impresora conectada. Fiscalberry se encargará de conectarse y pelear con los códigos y comandos especiales de cada marca/modelo.
- _SERVIDOR_: gracias al servidor de websockets es posible conectar tu aplicación para que ésta fácilmente pueda enviar JSON's y recibir las respuestas de manera asíncrona.
- _DRIVER_: Es el encargado de transformar el JSON genérico en un conjunto de comandos especiales según marca y modelo de la impresora. Aquí es donde reutilicé el código del proyecto de Reingart (https://github.com/reingart/pyfiscalprinter) para impresoras Hasar y Epson.

Funciona en cualquier PC con cualquier sistema operativo que soporte python.
La idea original fue pensada para que funcione en una raspberry pi, cuyo fin es integrar las fiscales al mundo de la Internet de las Cosas (IOT). Yo tengo funcionando varias fiscales conectadas a una raspberry pi.

## ¿Qué lenguajes de programación pueden usarlo?
Practicamente todos: Javascript, nodejs, python, php, etc.

Los que se puedan actuar como "cliente Web Socket" y conectarse con el servidor para enviar/recibir JSON's.

mas info en la WIKI: https://github.com/ristorantino/fiscalberry/wiki

## PROBALO

### Descargar

usando git
```sh
git clone https://github.com/ristorantino/fiscalberry.git
```
o directamente el ZIP: https://github.com/ristorantino/fiscalberry/archive/master.zip

### Crear archivo de configuracion

Renombrar el archivo "config.ini.install" como "config.ini" y configurar la marca, modelo, path y driver de la impresora.
(al inicializar el servicio "server.py", si el archivo no existe, lo crea automáticamente)

Las opciones son:

  para marca: [Hasar, Epson]

  modelo: 
  	(para Hasar)
		"615"
		"715v1"
		"715v2"
		"320"

	(para Epson)
		"tickeadoras"
		"epsonlx300+"


  path:
  	en windows: (COM1, COM2, etc)
  	en linux: (/dev/ttyUSB0, /dev/ttyS0, etc)

  driver:
  	(puede quedar vacio, en ese caso si la marca setteada es Hasar, el driver sera Hasar, lo mismo con Epson. Modificar File o Dummy es útil para hacer pruebas o desarrollo)
  	Hasar, Epson, Dummy, File

  	En el caso de seleccionar File, en la variable "path" hay que colocar el nombre del archivo que deseo crear para que se escriban las salidas. Ej en linux: "/tmp/archivo.txt"

### Instalar Dependencias


probado bajo python 2.7.6 en Linux, Ubuntu, Raspian

Se necesitan las dependencias:
* serial (para conectarse con impresoras seriales)
* tornado (para usar como servidor de web sockets)

```sh
sudo apt-get install python-pip
sudo pip install pyserial
sudo pip install tornado
```

Si se quiere usar las comanderas hay que instalar
```sh
sudo apt-get install python-imaging python-serial python-setuptools
sudo pip install python-escpos
```

### Instalar Daemond
En el archivo "fiscalberry-server-rc" deberas abrirlo y modificar la lionea donde dice "DIR=/insertPATHHERE" colocanmdo el path donde se encuentra la carpeta de fiscalberry. Ej: "DIR=/home/pi/fiscalberry"

luego deberas copiar el archivo a /etc/init.d/

```sh
sudo update-rc.d fiscalberry-server-rc defaults
```


#### Raspberry

para usar impresora de comandas ESCP en raspbian
```sh
sudo apt-get install libjpeg-dev
```
Además será necesario seguir una serie de pasos adicionales detallados en esta libreria utilizada por fiscalberry:
https://python-escpos.readthedocs.io/en/latest/user/raspi.html


### Iniciar el servicio

```sh
python server.py
```

### Iniciar el cliente para probarlo

Hay un ejemplo de página web con javascript dentro de la carpeta __js_browser_client__. Deberás abrir el HTML en un browser y jugar un poco con él.
el archivo fiscalberry.js te servirá si queres enviar a imprimir desde el browser.




## ¿Cómo funciona?

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

```javascript
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





## Documentación



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
```
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

```
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

		
#### "modelo"

Epson:
* "tickeadoras"
* "epsonlx300+"
* "tm-220-af"

Hasar:
* "615"
* "715v1"
* "715v2"
* "320"


#### "path"

En Windows "COM1"... "COM2", etc.
En linux "/dev/ttyUSB0"

#### "driver" (opcional)
Es la "salida" o sea, es el medio por donde saldrán las impresiones.

Opciones: 
* Hasar
* Epson
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

```
EJ: 
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

```javascript
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
