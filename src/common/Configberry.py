import configparser
import os
import uuid
import platformdirs
import platform


appname = 'Fiscalberry'


class Configberry:
    config = configparser.ConfigParser()
    config.optionxform=str
    
    _instance = None
    
    configFilePath = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(Configberry, cls).__new__(cls)
        return cls._instance

    def __init__(self):

        if not hasattr(self, 'initialized'):
            self.initialized = True
            # Inicializa aquí los atributos de la instancia
            
            self.configFilePath = self.getConfigFIle()
            self.__create_config_if_not_exists(self.configFilePath)
            

    def getConfigFIle(self):

        configDirPath = platformdirs.user_config_dir(appname)
        if not os.path.exists(configDirPath):
            os.makedirs(configDirPath)

        CONFIG_FILE_NAME = os.path.join(configDirPath, 'config.ini')

        return CONFIG_FILE_NAME


    def getJSON(self):
        jsondata = {}
        for s in self.sections():
            jsondata.setdefault(s, {})
            for (k, data) in self.config.items(s):
                jsondata[s].setdefault(k, data)
        return jsondata

    def items(self):
        return self.config.items()

    def sections(self):
        return self.config.sections()

    def findByMac(self, mac):
        "Busca entre todas las sections por la mac"
        for s in self.sections()[1:]:
            if self.config.has_option(s, 'mac'):
                mymac = self.config.get(s, 'mac')
                if mymac == mac:
                    return (s, self.get_config_for_printer(s))
        return False
    
    def validateIniFile(self, filepath):
        '''
        Valida que el archivo de configuracion sea valido
        '''
        try:
            self.config.read(filepath)
            return True
        except Exception as e:
            print(f"Error reading config file: {e}")
            return False
        

    def writeKeyForSection(self, section, key, value):
        self.config.read(self.configFilePath)
        self.config.set(section, key, value)
        with open(self.configFilePath, 'w') as configfile:
            self.config.write(configfile)
            configfile.close()
        self.config.read(self.configFilePath)
        return 1


    def set(self, section: str, kwargs: dict):
        """
        Sets the configuration parameters for a given section and saves the changes to the configuration file.
        A backup of the original configuration file is created before making any changes.
        Args:
            section (str): The section of the configuration file to update.
            kwargs (dict): A dictionary of key-value pairs to set in the specified section.
        Returns:
            int: Returns Bool, True si se guardo ok, False si fallo
        """
        self.config.read(self.configFilePath)
        
        #guardar backup del archivo
        with open(self.configFilePath, 'r') as file:
            data = file.read()
            with open(self.configFilePath + ".bak", 'w') as backup:
                backup.write(data)
                backup.close()
            file.close()
        
        #intentar guardar las keys pasadas para el section dado
        try:
            if not self.config.has_section(section):
                self.config.add_section(section)

            for param in kwargs:
                self.config.set(section, param, kwargs[param])

            temp_config_file = self.configFilePath + '.tmp'

            self.config.read(self.configFilePath)
            return True

        except Exception as e:
            # reemplazar por backup si fallo
            if os.path.exists(self.configFilePath + ".bak"):
                os.replace(self.configFilePath + ".bak", self.configFilePath)
            print(f"Error writing config file: {e}")
            return False

    def storeConfig(self):
        # Guardar backup del archivo
        with open(self.configFilePath, 'r') as file:
            data = file.read()
            with open(self.configFilePath + ".bak", 'w') as backup:
                backup.write(data)
                backup.close()
            file.close()

        try:
            # Guardar en el archivo
            with open(self.configFilePath, 'w') as configfile:
                self.config.write(configfile)
                configfile.close()
        except Exception as e:
            # Restaurar desde el backup en caso de error
            if os.path.exists(self.configFilePath + ".bak"):
                os.replace(self.configFilePath + ".bak", self.configFilePath)
            
            print(f"Error writing config file: {e}")
        
        self.config.read(self.configFilePath)
                
        print("resetado el config file quedo asi:")
        print(self.get_actual_config())
        



    def resetConfigFile(self):
        myUuid = str(uuid.uuid4())
        self.set("SERVIDOR", {
            "uuid": myUuid,
            "platform": f"{os.name} {platform.system()} {platform.release()} {platform.machine()}",
            "sio_host": "https://www.paxapos.com",
            "sio_password": ""
            })
        
        self.storeConfig()


    def __create_config_if_not_exists(self, configFile):

        if not os.path.isfile(configFile):
            print(f"NUEVO User config files creado en {configFile}")

            with open(configFile, 'w') as configfile:
                configfile.write(defaultConfig)
                configfile.close()
        else:
            print(f"User Config existente en {configFile}")
        
        self.config.read(configFile)
        
        try:
            uuidVal = self.get("SERVIDOR", "uuid", fallback=None)
            if not uuidVal:
                raise Exception("UUID not found")
        except configparser.NoSectionError as e:
            print(f"Section SERVIDOR no encontrado, reseteando {configFile}")
            self.resetConfigFile()
        except Exception as e:
            print(f"Config UUID no encontrado, reseteando {configFile}")
            self.resetConfigFile()
            
        # menos el primero que es el de SERVIDOR, mostrar el el resto en consola ya que son las impresoras
        for s in self.sections()[1:]:
            print("Impresora en Config: %s" % s)
        
          

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
        elif "=" in printerName:
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

    def delete_section(self, section):
        
        self.config.read(self.configFilePath)

        if self.config.has_section(section):
            self.config.remove_section(section)

        with open(self.configFilePath, 'w') as configfile:
            self.config.write(configfile)
            configfile.close()

        self.config.read(self.configFilePath)

        return 1
    
    def get(self, section, key, fallback=None):
        self.config.read( self.configFilePath )
        return self.config.get(section, key, fallback=fallback)
    