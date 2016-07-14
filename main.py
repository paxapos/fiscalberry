#from hasarPrinter import HasarPrinter
# Drivers:

from Drivers.EpsonDriver import EpsonDriver
from Drivers.FileDriver import FileDriver
from Drivers.HasarDriver import HasarDriver
from Drivers.DummyDriver import DummyDriver

from Comandos.EpsonComandos import EpsonComandos
from Comandos.HasarComandos import HasarComandos

from Traductor import Traductor





if __name__ == '__main__':

	#marca = conf.get("marca", "epson")
	modelo = "441"
	puerto = "/dev/ttyUSB0"
	
	driver = "Epson"
	
	#hd = HasarComandos(driver, puerto)
	#hd = EpsonComandos(puerto, driverName="File")

	# File
	#hd = HasarComandos("/tmp/archivin.txt", driverName="File")


	traductor = Traductor()

	'''
	jsonTicket = {
		"openDrawer": 1
	}
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

	traductor.json_to_comando(jsonTicketSinConsumidor)
	#hd.openDrawer()

	#hd.dailyClose("X")

	print( "y este cuento se ha terminado" )
	
	

