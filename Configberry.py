import configparser
import os
import logging


class Configberry:
    config = configparser.ConfigParser()


    def __init__(self):
        self.logger = logging.getLogger("Configberry")

        self.config.read( self.getConfigFIle() )
        self.__create_config_if_not_exists()

    def getConfigFIle(self):
        FILE_PATH = os.getenv('CONFIG_FILE_PATH', './')
        CONFIG_FILE_NAME = os.path.join(FILE_PATH, 'config.ini')

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

    def writeSectionWithKwargs(self, printerName, kwargs):
        self.config = configparser.RawConfigParser()
        self.config.read( self.getConfigFIle() )

        if not self.config.has_section(printerName):
            self.config.add_section(printerName)

        for param in kwargs:
            self.config.set(printerName, param, kwargs[param])

        with open(self.getConfigFIle(), 'w') as configfile:
            self.config.write(configfile)
            configfile.close()

        return 1

    def __create_config_if_not_exists(self):
        newpath = os.path.dirname(os.path.realpath(__file__))
        os.chdir(newpath)
        CONFIG_FILE_NAME = self.getConfigFIle()
        if not os.path.isfile(CONFIG_FILE_NAME):
            import shutil
            shutil.copy("config.ini.install", CONFIG_FILE_NAME)

    def get_config_for_printer(self, printerName):
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