import configparser
import os
import uuid
import platformdirs
from common.fiscalberry_logger import getLogger

appname = 'Fiscalberry'


class Configberry:
    config = configparser.ConfigParser()

    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(Configberry, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            # Inicializa aquí los atributos de la instancia
            self.logger = getLogger()

            self.config.read( self.getConfigFIle() )
            self.__create_config_if_not_exists()

    def getConfigFIle(self):

        configDirPath = platformdirs.user_config_dir(appname)
        if not os.path.exists(configDirPath):
            os.makedirs(configDirPath)

        CONFIG_FILE_NAME = os.path.join(configDirPath, 'config.ini')

        self.logger.debug("Config file path: %s" % CONFIG_FILE_NAME)

        return CONFIG_FILE_NAME


    def getJSON(self):
        jsondata = {}
        for s in self.sections():
            jsondata.setdefault(s, {})
            for (k, data) in self.config.items(s):
                jsondata[s].setdefault(k, data)
        return jsondata

    def items(self):
        self.config.read( self.getConfigFIle() )
        return self.config.items()

    def sections(self):
        self.config.read( self.getConfigFIle() )
        return self.config.sections()

    def findByMac(self, mac):
        "Busca entre todas las sections por la mac"
        for s in self.sections()[1:]:
            if self.config.has_option(s, 'mac'):
                mymac = self.config.get(s, 'mac')
                self.logger.debug("mymac %s y la otra es mac %s" % (mymac, mac))
                if mymac == mac:
                    self.logger.debug("encontre la mac %s" % mac)
                    return (s, self.get_config_for_printer(s))
        return False

    def writeKeyForSection(self, section, key, value):
        self.config = configparser.RawConfigParser()
        self.config.read( self.getConfigFIle() )

        if not self.config.has_section(section):
            self.config.add_section(section)

        self.config.set(section, key, value)

        with open(self.getConfigFIle(), 'w') as configfile:
            self.config.write(configfile)
            configfile.close()

        return 1


    def writeSectionWithKwargs(self, section, kwargs):
        self.config = configparser.RawConfigParser()
        self.config.read( self.getConfigFIle() )

        if not self.config.has_section(section):
            self.config.add_section(section)

        for param in kwargs:
            self.config.set(section, param, kwargs[param])

        with open(self.getConfigFIle(), 'w') as configfile:
            self.config.write(configfile)
            configfile.close()

        return 1

    def __create_config_if_not_exists(self):
        
        print(f"User config files stored in {platformdirs.user_config_dir(appname)}")

        CONFIG_FILE_NAME = self.getConfigFIle()
        if not os.path.isfile(CONFIG_FILE_NAME):

            curpath = os.path.dirname(os.path.realpath(__file__))

            myUuid = str(uuid.uuid4())

            defaultConfig = f'''
[SERVIDOR]
uuid = {myUuid}
sio_host = https://www.paxapos.com
sio_password =
'''
            with open(CONFIG_FILE_NAME, 'w') as configfile:
                configfile.write(defaultConfig)
                configfile.close()


    def get_config_for_printer(self, printerName):
        '''
        printerName: string
        '''
        
        if isinstance(printerName, dict):
            return printerName
        elif ":" in printerName:
            # if printerName is an IP address, extract IP and PORT.
            # e.g.
            # printerName = "192.168.0.25:9100"
            # host is 192.168.0.25
            # port is 9100
            # e.g. 2
            # printerName = "192.168.0.25"
            # host is 192.168.0.25
            # port is 9100
            # e.g. 3
            # printerName = "192.168.0.25:6100"
            # host is 192.168.0.25
            # port is 6100
            host, port = printerName.split(":")
            ret = {
                "driver": "Network",
                "host": host,
                "port": port
            }
            return ret
        elif "&" in printerName:
            # if printerName is a string with parameters, extract them.
            # e.g.
            # printerName = "marca=EscP&driver=ReceiptDirectJet&host=192.168.0.25&port=9100"
            # or printerName = "marca=EscP&driver=ReceiptUsb&device=/dev/usb/lp0"
            #
            params = printerName.split('&')
            dictConf = {}
            for param in params:
                key, value = param.split('=')
                dictConf[key] = value
            return dictConf
        elif printerName == "":
            return {}
        elif printerName.count(".") == 3:
            # if printerName is an IP address, use it as the host.
            # e.g.
            # printerName = "192.168.0.25"
            # host is 192.168.0.25
            # port is 9100
            host = printerName
            port = 9100
            ret = {
            "driver": "Network",
            "host": host,
            }
            return ret
        else:
            printerName = printerName
            dictConf = {s: dict(self.config.items(s)) for s in self.config.sections()}
            return dictConf[printerName]

    def get_actual_config(self):
        dictConf = {s: dict(self.config.items(s)) for s in self.config.sections()}

        return dictConf

    def delete_printer_from_config(self, printerName):
        self.config = configparser.RawConfigParser()
        
        CONFIG_FILE_NAME = self.getConfigFIle()

        self.config.read(CONFIG_FILE_NAME)

        if self.config.has_section(printerName):
            self.config.remove_section(printerName)

        with open(CONFIG_FILE_NAME, 'w') as configfile:
            self.config.write(configfile)
            configfile.close()

        return 1