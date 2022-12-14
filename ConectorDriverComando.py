# -*- coding: iso-8859-1 -*-
from serial import SerialException
import importlib
import threading
import logging


class ConectorError(Exception):
    pass


class ConectorDriverComando:
    driver = None

    def __init__(self, comando, driver, *args, **kwargs):
        logging.getLogger().info("inicializando ConectorDriverComando driver de %s" % driver)

        self._comando = comando
        self.driver_name = driver

        # instanciar el driver dinamicamente segun el driver pasado como parametro
        libraryName = "Drivers." + driver + "Driver"
        driverModule = importlib.import_module(libraryName)
        driverClass = getattr(driverModule, driver + "Driver")

        self.driver = driverClass(**kwargs)

    def sendCommand(self, *args):
        # logging.getLogger().info("Enviando comando %s" % args)
        logging.getLogger().info("Enviando comando '${0}'".format(args))
        return self.driver.sendCommand(*args)

    def close(self):
        # Si el driver es Receipt, se cierra desde la misma clase del driver, sino, tira error de Bad File Descriptor por querer cerrarlo dos veces.
        if self.driver_name == "ReceiptDirectJet":
            if self.driver.connected is False:
                return None
        self.driver.close()
        self.driver = None
