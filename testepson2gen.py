from Comandos.Epson2GenComandos import Epson2GenComandos
import ctypes
from ctypes import byref, c_int, c_char, c_char_p, c_long, c_short, create_string_buffer

fullpath = "/lib64/libEpsonFiscalInterface.so"
EpsonLibInterface = ctypes.cdll.LoadLibrary(fullpath)


def jsontest():
	jsoncomando = {
		"printerName":"fiscalEpson",
		"printTicket":{
			"encabezado":{
				"tipo_cbte":"FB",
				"imprimir_fecha_remito":1
			},
			"items":[
				{
				"alic_iva":"21.00",
				"importe":1,
				"ds":"prueba 1pe",
				"qty":1
				},
			],
			"setTrailer":[" ","Mozo: Alejandra","Mesa: 1"," "]
		}
	}

def geterr():


	# connect
	EpsonLibInterface.ConfigurarVelocidad( c_int(9600).value )
	EpsonLibInterface.ConfigurarPuerto( "0" )
	error = EpsonLibInterface.Conectar()
	print "Connect               : ",
	print error

	# get last error
	error = EpsonLibInterface.ConsultarUltimoError()
	print "Last Error            : ",
	print error


	# close port
	error = EpsonLibInterface.Desconectar()
	print "Disconect             : ",
	print error
	

def e2c():
	comandin = Epson2GenComandos()
	print "iniciando"
	comandin.start()
	
	comandin.setHeader([" ", "     software paxapos", "      www.paxapos.com"])
	comandin.setTrailer(["", "", ""])
	
	#comandin.dailyClose("x")
	
	print "abro ticket"
	#comandin.openTicket("T")
	#comandin.addItem( "coca prueba", 1, 10, "21.00")
	
	#comandin.addItem( "coca prueba2", 1, 0.1, "21.00")


	#reporte x dailyClose X
	#------------
	#driverEpson.EnviarComando( "0802|0000")

	#abrir ticket 
	#--------------
	#driverEpson.EnviarComando( "0A01|0000")


	#enviar item
	#---------------
	#driverEpson.EnviarComando( "0A02|0000|||||Item descripcion|10000|0001000|2100|||||CodigoInterno4567890123456789012345678901234567890|01|")

	#comandin.addAdditional("Recargo", 2, "21.00", False)
	#comandin.closeDocument()
	#comandin.cancelDocument()

	print "cierro coso"
	comandin.close()



if __name__ == '__main__':
    geterr()