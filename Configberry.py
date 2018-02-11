import ConfigParser
import os

CONFIG_FILE_NAME = "config.ini"


class Configberry:
    config = ConfigParser.ConfigParser()

    def __init__(self):
        self.config.read(CONFIG_FILE_NAME)

        self.__create_config_if_not_exists()

    def getJSON(self):
        jsondata = {}
        for s in self.sections():
            jsondata.setdefault(s, {})
            for (k, data) in self.config.items(s):
                jsondata[s].setdefault(k, data)
        return jsondata

    def items(self):
        self.config.read(CONFIG_FILE_NAME)
        return self.config.items()

    def sections(self):
        self.config.read(CONFIG_FILE_NAME)
        return self.config.sections()

    def findByMac(self, mac):
        "Busca entre todas las sections por la mac"
        for s in self.sections()[1:]:
            if self.config.has_option(s, 'mac'):
                mymac = self.config.get(s, 'mac')
                print("mymac %s y la otra es mac %s" % (mymac, mac))
                if mymac == mac:
                    print(s)
                    return (s, self.get_config_for_printer(s))
        return False

    def writeSectionWithKwargs(self, printerName, kwargs):
        self.config = ConfigParser.RawConfigParser()
        self.config.read(CONFIG_FILE_NAME)

        if not self.config.has_section(printerName):
            self.config.add_section(printerName)

        for param in kwargs:
            self.config.set(printerName, param, kwargs[param])

        with open(CONFIG_FILE_NAME, 'w') as configfile:
            self.config.write(configfile)

        return 1;

    def __create_config_if_not_exists(self):
        newpath = os.path.dirname(os.path.realpath(__file__))
        os.chdir(newpath)
        if not os.path.isfile(CONFIG_FILE_NAME):
            import shutil
            shutil.copy("config.ini.install", CONFIG_FILE_NAME)

    def get_config_for_printer(self, printerName):
        dictConf = {s: dict(self.config.items(s)) for s in self.config.sections()}

        return dictConf[printerName]

    def get_actual_config(self):
        dictConf = {s: dict(self.config.items(s)) for s in self.config.sections()}

        return dictConf