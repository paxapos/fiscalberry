# fiscalberry

## NOTA IMPORTANTE: Este proyecto es una mejora del original https://github.com/reingart/pyfiscalprinter

Ŕealizé un refactor del proyecto original para adaptarlo a una necesidad distinta y mejorándolo para tal uso.

## ¿Qué es?
Es un proyecto open source desarrollado en python 2.7 para conectar impresoras "especiales" (comanderas, receipt, fiscales, tickets, etc) con cualquier tipo de lenguaje de programación utilizando un protocolo de comunicación JSON conectado mediante web sockets.
Con fiscalberry podrás imprimir a una impresora fiscal desde la misma página web usando javascript, por ejemplo.

Fiscalberry actua como servidor Web Socket. Con cualquier lenguaje de programación que se conecte a este servidor, podrá enviarle instrucciones JSON para imprimir.

## ¿Qué lenguajes soporta?
Javascript, nodejs, python, php, y todos los que se te ocurran que puedan actuar como "cliente Web Socket" para conectarse con el servidor y enviar y recibir JSON's.

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

Por ejemplo queremos imprimir un ticket, esta acción se denomina "printTicket" y está compuesta de 2 parámetros obligatorios: "encabezado" e "items".

El "encabezado" indica el tipo de comprobante a imprimir. 
Los items son una lista de productos a imprimir donde, en este ejemplo, tegemos una coca cola, con impuesto de 21%, importe $10, descripcion del producto "COCA COLA" y la cantidad vendida es 2.

```javascript
{
"printTicket": {
			"encabezado": {
		        "tipo_cbte": "T",
		    },
		    "items": [
		        {
		            "alic_iva": 21.0,
		            "importe": 10,
		            "ds": "COCA COLA",
		            "qty": 2.0
		        }
		    ]
			}
		}
```

## Ejemplo de uso

1) __Iniciamos el servicio:__ para ello debemos pararnos en nuestra carpeta principal del proyecto y hacer:

```sh
python server.py
```

2) __Iniciar cliente:__ hay un ejemplo en javascript dentro de la carpeta __js_browser_client__. Deberás abrir el HTML en un browser y jugar un poco con él.



## Documentación para su uso


### Accion: **printTicket**

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
			        "tipo_cbte": "FA", // * Obligatorio
			        "nro_doc": "20267565393",
			        "domicilio_cliente": "Rua 76 km 34.5 Alagoas",
			        "tipo_doc": "DNI",
			        "nombre_cliente": "Joao Da Silva",
			        "tipo_responsable": "RESPONSABLE_INSCRIPTO"
			    }
}
                
```

#### Ítems (Obligatorio)
tipo: list

```javascript
{
 "items": [
    {
        "alic_iva": 21.0, // * Obligatorio
        "importe": 0.01, // * Obligatorio
        "ds": "PIPI", // * Obligatorio
        "qty": 1.0 // * Obligatorio
    },
    {
        "alic_iva": 21.0,
        "importe": 0.22,
        "ds": "COCA",
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



#### Variables Estáticas Para Encabezado

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



### Accion: **configure**

Al enviar este JSON se puede configurar el servidor de impresión directamente desde el cliente.
El archivo de configuración que será modificado es **config.ini** que tambiém puede ser modificado a mano desde consola.

Los parámetros que puede llevar el JSON son:
		
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

En Windows COM1... COM2, etc.
En linux /dev/ttyUSB0

#### "driver" (opcional)
Es la "salida" o sea, es el medio por donde saldrán las impresiones.

Por defecto se utiliza el mismo driver que la impresora, pero en algunas casos (desarrollo) se pueden utilizar 2 drivers extra:
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

### Accion: **openDrawer**


Abre la gaveta de dinero. No es necesario pasar parámetros extra.

```avascript
// EJ:
{
  "openDrawer": true
}
```


### Accion: **getStatus**

retorna la configuracon actual del servidor.  No es necesario pasar parámetros extra.

```
EJ: 
{
  "getStatus": {}
}
```



#### NOTA:
Deberas enviar JSON válidos al servidor. Recomendamos usar la pagina http://jsonlint.com/ para verificar como tu programa esta generando los JSON.
