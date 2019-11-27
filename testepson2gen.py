from Comandos.Epson2GenComandos import Epson2GenComandos


def main():
	comandin = Epson2GenComandos()
	print "iniciando"
	comandin.start()
	#comandin.setHeader(["encabezado 1111", "encabezado 2222", "encabezado 3333"])
	#comandin.setTrailer(["pie 1111", "pie 2222", "pie 3333"])
	
	#comandin.dailyClose("Z")
	
	print "abro ticket"
	#comandin.openTicket("FB")
	#comandin.addItem( "coca prueba", 1, 0.1, "21.00")
	#comandin.addItem( "coca prueba2", 1, 0.1, "21.00")


	driverEpson = comandin.conector.driver.EpsonLibInterface
	
	#reporte x dailyClose X
	#------------
	driverEpson.EnviarComando( "0802|0000")

	#abrir ticket 
	#--------------
	#driverEpson.EnviarComando( "0A01|0000")


	#enviar item
	#---------------
	#driverEpson.EnviarComando( "0A02|0000|||||Item descripcion|10000|0001000|2100|||||CodigoInterno4567890123456789012345678901234567890|01|")


	#comandin.cancelDocument()

	print "cierro coso"
	comandin.close()



if __name__ == '__main__':
    main()