# -*- coding: iso-8859-1 -*-

#from hasarPrinter import HasarPrinter
# Drivers:

from Drivers.EpsonDriver import EpsonDriver
from Drivers.FileDriver import FileDriver
from Drivers.HasarDriver import HasarDriver
from Drivers.DummyDriver import DummyDriver

from Comandos.EpsonComandos import EpsonComandos
from Comandos.HasarComandos import HasarComandos

from Traductor import Traductor
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


	traductor = Traductor("IMPRESORA_FISCAL")

	'''
	jsonTicket = {
		"openDrawer": 1
	}
	'''

	'''
	jsonTicketFacutaAConConsumidor = {		
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


	jsonTicketSinConsumidor = {
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

	print "\n"
	print traductor.json_to_comando(jsonTicketSinConsumidor)
	print "\n"
	print traductor.json_to_comando(jsonTicketSinConsumidor)


	jsonDailyClose = {
		"dailyClose": "Z"
	}
	print "\n"
	print traductor.json_to_comando(jsonDailyClose)


	#traductor.json_to_comando(jsonDailyClose)
	#hd.openDrawer()

	#hd.dailyClose("X")


	
	jsonBarra = {
		"printerName": "BEMATECH_BARRA",
		"getStatus": ""
	}
	# print traductor.json_to_comando(jsonBarra)


	'''

	jsonBarra = {
		"printerName": "BEMATECH_BARRA",
		"printComanda": {
			"comanda": {
				"id": 12121,
				"created": "2015-12-12 22:22:22",
				"observacion": "Para LLEVAR!",
				"entradas": [
					{
						"cant": 2,
						"nombre": "raba"
					}
				],
				"platos": [
					{
						"cant": 1,
						"nombre": "arroz con pollo",
						"observacion": "sin sal"
					},
					{
						"cant": 2,
						"nombre": "merluza con pure"
					}
				]
			},
			"mesa": "Mesa 21",
			"mozo": "Mozo 23"
		}
	}


	traductor.json_to_comando(jsonBarra)

	#Bematech.control("CR")


	print( "y este cuento se ha terminado" )
	
	

