# -*- coding: utf-8 -*-

#from hasarPrinter import HasarPrinter
# Drivers:

from Drivers.EpsonDriver import EpsonDriver
from Drivers.FileDriver import FileDriver
from Drivers.HasarDriver import HasarDriver
from Drivers.DummyDriver import DummyDriver

from Comandos.EpsonComandos import EpsonComandos
from Comandos.HasarComandos import HasarComandos

from Traductores.TraductoresHandler import TraductoresHandler
from escpos import printer




if __name__ == '__main__':

	#marca = conf.get("marca", "epson")
	modelo = "441"
	puerto = "/dev/ttyUSB0"
	
	driver = "Epson"
	
	#hd = HasarComandos(driver, puerto)
	#hd = EpsonComandos(puerto, driverName="File")

	# File
	#hd = HasarComandos("/tmp/archivin.txt", driverName="File")


	traductor = TraductoresHandler()

	'''
	jsonTicket = {
		"openDrawer": 1
	}
	'''

	
	jsonTicketFacutaAConConsumidor = {
		"printerName": "IMPRESORA_FISCAL",
		"printTicket": {
			"encabezado": {
		        "tipo_cbte": "FA",
		        "nro_doc": "20267565393",
		        "domicilio_cliente": "Rua 76 km 34.5 Alagoas",
		        "tipo_doc": "DNI",
		        "nombre_cliente": "Gonzales Oro",
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


	jsonTicketSinConsumidor = {
			"printerName": "IMPRESORA_FISCAL",
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
				}],
				"addAdditional":{
					"description": "Descuento",
					"amount": "10",
					"iva": 21
				},
				"setHeader": [
					"Encabezado 111",
					"Encabezado 222",
					"Encabezado 333"
				],
				"setTrailer": [
					"",
					"MOZO: xxxxx",
					"MESA: 11111",
					""
				]
			}
		}


	print "\n"
	print traductor.json_to_comando(jsonTicketSinConsumidor)


	jsonDailyClose = {
		"printerName": "IMPRESORA_FISCAL",
		"dailyClose": "Z"
	}
	print "\n"
	#print traductor.json_to_comando(jsonDailyClose)


	#traductor.json_to_comando(jsonDailyClose)
	#hd.openDrawer()

	#hd.dailyClose("X")



	print( "y este cuento se ha terminado" )
	
	

