# coding=utf-8
from common.fiscalberry_logger import getLogger
from common.Drivers.FiscalberryDriver import FiscalberryDriver
from common.Drivers.ReceiptDirectJetDriver import ReceiptDirectJetDriver
from common.Drivers.ReceiptFileDriver import ReceiptFileDriver
from common.Drivers.ReceiptUSBDriver import ReceiptUSBDriver
from common.Drivers.DummyDriver import DummyDriver

class ConectorError(Exception):
    pass

class ConectorDriverComando:
    driver = None

    def __init__(self, comando, driver, *args, **kwargs):
        self.logger = getLogger()
        self.logger.info(f"Inicializando ConectorDriverComando driver de '${driver}'")

        self._comando = comando
        self.driver_name = driver

        # instanciar el driver dinamicamente segun el driver pasado como parametro
        driverClass = driver + "Driver"
        if driverClass == "FiscalberryDriver":
            self.driver = FiscalberryDriver(**kwargs)
        elif driverClass == "ReceiptDirectJetDriver":
            self.driver = ReceiptDirectJetDriver(**kwargs)
        elif driverClass == "ReceiptFileDriver":
            self.driver = ReceiptFileDriver(**kwargs)
        elif driverClass == "ReceiptUSBDriver":
            self.driver = ReceiptUSBDriver(**kwargs)
        elif driverClass == "DummyDriver":
            self.driver = DummyDriver(**kwargs)
        else:
            raise ConectorError(f"Invalid driver: {driverClass}")

    def sendCommand(self, *args):

        self.logger.info(f"Enviando comando '${args}'")
        return self.driver.sendCommand(*args)

    def close(self):

        # Si el driver es Receipt, se cierra desde la misma clase del driver, sino, tira error de Bad File Descriptor por querer cerrarlo dos veces.
        if self.driver_name == "ReceiptDirectJet":
            if self.driver.connected is False:
                return None
        self.driver.close()
        self.driver = None