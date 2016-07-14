# fiscalberry

## NOTA IMPORTANTE: Este proyecto es una mejora del original https://github.com/reingart/pyfiscalprinter

Realizé un refactor del proyecto original para adaptarlo a una necesidad distinta y moderna, mejorándolo para tal uso.

## ¿Qué es?
Es un proyecto open source desarrollado en python para conectar impresoras "especiales" (comanderas, receipt, fiscales, tickets, etc) con cualquier tipo de lenguaje de programación utilizando un protocolo de comunicación JSON conectado mediante web sockets.
Con fiscalberry podrás imprimir a una impresora fiscal desde la misma página web usando javascript, por ejemplo.

Fiscalberry actua como servidor Web Socket. Con cualquier lenguaje de programación que se conecte a este servidor, podrá enviarle instrucciones JSON para imprimir.

Funciona en una raspberry. Pero también deberia andar en windows, mac, y cualquier otra PC con python instalado.

## ¿Qué lenguajes de programación pueden usarlo?
Practicamente todos: Javascript, nodejs, python, php, etc.

Los que se te ocurran que puedan actuar como "cliente Web Socket" para conectarse con el servidor y enviar y recibir JSON's.


## PROBALO


### Instalar Dependencias

probado bajo python 2.7.6 en Linux, Ubuntu, Raspian

Se necesitan 2 dependencias:
* serial (para conectarse con impresoras seriales)
* tornado (para usar como servidor de web sockets)

```sh
sudo pip install pyserial
sudo pip install tornado
```


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
* Ìtems
* Pagos (opcional)

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
						"ds": "PIPI",
						"qty": 1.0
					}, {
						"alic_iva": 21.0,
						"importe": 0.22,
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

Se pueden configurar muchas impresoras, pero solo 1 puede ser fiscal.

La única impresora fiscal se debe llamar "IMPRESORA_FISCAL". Esto es conveniente para cuando se necesita tener impresoras de comandas

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

Por defecto se utiliza el mismo driver que la impresora, pero en algunas casos (desarrollo) se pueden utilizar drivers extra:
* Dummy (no presenta salidas en ningun lado)
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


#### NOTA:
Deberas enviar JSON válidos al servidor. Recomendamos usar la pagina http://jsonlint.com/ para verificar como tu programa esta generando los JSON.
