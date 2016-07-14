¿COMO FUNCIONA?


Supongamos que tenemos este JSON en nuestra aplicación

Si vemos la estructira del ticket tiene un primr string que indica la accion 
que vamos a realizar "printTicket"
 esa accion esta compuesto de 2 parametros: "encabezado" e "items"
 A su vez el encabezado indica el tipo de comprobante a imprimir. La "T" significa "Tiquet". Luego los items es una lista de items a imprimir donde, en este ejemplo, tegemos una coca cola, con impuesto de 21%, importe $10, descripcion del producto "COCA COLA" y la cantidad es 2.

json = {"printTicket": {
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


una vez que tenemos el JSON, en nuestra aplicacion debemos enviarlo a la IP donde esta corriendo el servidor de impresion fiscalberry, puerto 12000 (por defecto)

fiscalberry.local:12000



Variables Estaticas

printTicket:

	EJ:
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


	# VARIABLES ESTATICAS

	tipo_cbte String
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



configure 
		"printerName" 
			Se pueden configurar muchas impresoras, pero solo 1 puede ser fiscal.
			La única impresora fiscal se debe llamar "IMPRESORA_FISCAL". Esto es 
			conveniente para cuando se necesita tener impresras de comandas
		marca ("Epson", "Hasar", "Raw") (comando "Raw" es para las impresoras de comandas)
		modelo()
		path (En Windows COM1, en linux /dev/ttyUSB0 )

		EJ: 
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
				"marca": "Hasar",
				"modelo": "715v2",
				"path": "/tmp/respuestas.txt",
				"driver": "File"
			}
		}

openDrawer
	Abre la gaveta de dinero

	EJ:
	{
		"openDrawer": true
	}

getStatus
	retorna la configuracon actual del servidor
	EJ: 
	{
		"getStatus": {}
	}




Marca "Hasar"; modelos: "615", "715v1", "715v2", "320"
Marca "Epson"; modelos: "tickeadoras", "epsonlx300+", "tm-220-af"


NOTA:
deberas enviar JSON validos. Recomendamos usar la pagina http://jsonlint.com/ para verificar lo que se esta enviando al fiscalberry