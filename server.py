#!/usr/bin/env python
# coding=utf-8

from multiprocessing import freeze_support
import argparse

from FiscalberryApp import FiscalberryApp


def init_server():
	
	fbserver = FiscalberryApp()

	# lanzar discover a URL de servidor configurado con datos del config actual
	fbserver.discover()

	# iniciar tornado server
	fbserver.start()


def send_discover():
	fbserver = FiscalberryApp()

	# lanzar discover a URL de servidor configurado con datos del config actual
	fbserver.discover()


if __name__ == "__main__":
	freeze_support()
	
	parser = argparse.ArgumentParser(description='servidor websockets para impresión fiscal y ESCP')
	parser.add_argument('--discover', '-d', 
							help='envia a la URL información de este servicio.', 
							action='store_true')
	args = parser.parse_args()

	if args.discover:
		send_discover()
		exit()

	init_server()

