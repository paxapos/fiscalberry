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


	
	jsonBarra = {
		"printerName": "BEMATECH_BARRA",
		"getStatus": ""
	}
	# print traductor.json_to_comando(jsonBarra)


	

	jsonBarra = {
		"printerName": "BEMATECH_BARRA",
		"printComanda": {
			"comanda": {
				"id": 12121,
				"created": "2015-12-12 22:15:20",		
				"observacion": "ALE PROBANDO!",
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
						"nombre": "Ensalada",
						"observacion": "con aceite de oliva",
						"sabores":["tomate", "zanahoria", "remolacha", "chaucha", "cebolla", "rodriguez"]
					}
				]
			},
			"setTrailer": [
					"",
					"MOZO: xxxxx",
					"MESA: 11111",
					""
				]
		}
	}


	traductor.json_to_comando(jsonBarra)



	jsonTicketSinConsumidor = {
			"printerName": "BEMATECH_BARRA",
			"printRemito": {
				"extra": {
					"mesa_id": 123445
				},
				"encabezado": {
			        "tipo_cbte": "FA",
			        "nro_doc": "20267565393",
			        "domicilio_cliente": "Rua 76 km 34.5 Alagoas",
			        "tipo_doc": "DNI",
			        "nombre_cliente": "Gonzales Oro",
			        "tipo_responsable": "RESPONSABLE_INSCRIPTO"
			    },
				"items": [{
					"alic_iva": 21.0,
					"importe": 0.01,
					"ds": "Arroz con Pollo",
					"qty": 1.0
				}, {
					"alic_iva": 21.0,
					"importe": 30.22,
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
					"MOZO: Carlos EL REY Dominguez",
					"MESA: 13",
					""
				]
			}
	}

	traductor.json_to_comando(jsonTicketSinConsumidor)