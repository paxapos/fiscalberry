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

	
	# IMPRESORA_FISCAL
	traductor = TraductoresHandler()
	print traductor.traductores
	jsoncoso={
		"printerName": "IMPRESORA_FISCAL",
		"dailyClose":"x"
	}

	jsoncoso = {
		"printerName": "IMPRESORA_FISCAL",
		"printTicket": {
			"encabezado": {
		        "tipo_cbte": "FA",
		        "nro_doc": "30711054231",
		        "domicilio_cliente": "Rua 76 km 34.5 Alagoas",
		        "tipo_doc": "CUIT",
		        "nombre_cliente": "PXA PRUEBA",
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
		    "setTrailer":[
			"TRAILER 1111",
			"TRAILER 2222"
		    ],
		    "pagos": [
		        {
		            "ds": "efectivo",
		            "importe": 1.0
		        }
		    ]
			}
		}
	
	print traductor.json_to_comando(jsoncoso)

	# print traductor.json_to_comando({"getAvaliablePrinters":""})

        #print traductor.json_to_comando(jsoncoso)


