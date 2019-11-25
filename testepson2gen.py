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
	comandin.addItem( "coca prueba", 1, 0.1, "21.00")
	#comandin.addItem( "coca prueba2", 1, 0.1, "21.00")

	#comandin.cancelDocument()

	print "cierro coso"
	comandin.close()



if __name__ == '__main__':
    main()