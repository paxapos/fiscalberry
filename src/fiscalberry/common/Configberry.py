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
    
    _listeners = []

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
            self._listeners = []
            
            print(f"Configberry: Config file path: {self.configFilePath}")


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
        oldval = self.config.get(section, key, value)
        if oldval == value:
            return 0

        self.config.set(section, key, value)
        with open(self.configFilePath, 'w') as configfile:
            self.config.write(configfile)
            configfile.close()
        self.config.read(self.configFilePath)
        self.notify_listeners()
        return 1

    def saveBackup(self):
        # Guardar backup del archivo
        with open(self.configFilePath, 'r') as file:
            data = file.read()
            with open(self.configFilePath + ".bak", 'w') as backup:
                backup.write(data)
                backup.close()
            file.close()
       


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
        changes_made = False
        
        # Intentar guardar las keys pasadas para la sección dada
        try:
            if not self.config.has_section(section):
                self.config.add_section(section)
                # Si la sección no existía, definitivamente haremos cambios si hay kwargs
                if kwargs:
                    changes_made = True 

            for key, value in kwargs.items():
                current_value_str = self.config.get(section, key, fallback=None)
                
                if value is None:
                    # Si la clave existe, la eliminamos y marcamos que hubo cambios
                    if current_value_str is not None:
                        self.config.remove_option(section, key)
                        changes_made = True
                else:
                    # Convertir el nuevo valor a string para comparación y almacenamiento
                    if isinstance(value, list):
                        new_value_str = ','.join(value)
                    elif isinstance(value, dict):
                        import json
                        new_value_str = json.dumps(value)
                    elif not isinstance(value, str):
                        new_value_str = str(value)
                    else:
                        new_value_str = value

                    # Si el valor es diferente al actual (o si no existía), lo establecemos y marcamos cambio
                    if current_value_str != new_value_str:
                        self.config.set(section, key, new_value_str)
                        changes_made = True

            # Solo guardar si se realizaron cambios
            if changes_made:
                # Guardar backup del archivo ANTES de escribir
                self.saveBackup()
                try:
                    with open(self.configFilePath, 'w') as configfile:
                        self.config.write(configfile)
                    
                    # Recargar la configuración después de escribir
                    self.config.read(self.configFilePath) 
                    
                    # Verificar si se guardó correctamente (opcional, pero bueno para robustez)
                    # for key, value in kwargs.items():
                    #     saved_value = self.config.get(section, key, fallback=None)
                    #     # Re-convertir el valor esperado a string para comparar
                    #     if value is None:
                    #         expected_value_str = None
                    #     elif isinstance(value, list): expected_value_str = ','.join(value)
                    #     elif isinstance(value, dict): import json; expected_value_str = json.dumps(value)
                    #     elif not isinstance(value, str): expected_value_str = str(value)
                    #     else: expected_value_str = value
                        
                    #     if saved_value != expected_value_str:
                    #          raise Exception(f"Verification failed for key '{key}' in section '{section}'. Expected '{expected_value_str}', got '{saved_value}'.")

                    # Si todo salió bien, eliminar el backup
                    if os.path.exists(self.configFilePath + ".bak"):
                        os.remove(self.configFilePath + ".bak")
                    
                    self.notify_listeners() # Notificar solo si hubo cambios guardados
                    
                except Exception as write_error:
                     # Reemplazar por backup si falló la escritura o verificación
                    print(f"Error during config write/verification: {write_error}")
                    if os.path.exists(self.configFilePath + ".bak"):
                        try:
                            os.replace(self.configFilePath + ".bak", self.configFilePath)
                            print("Restored config from backup.")
                            # Recargar la configuración desde el backup restaurado
                            self.config.read(self.configFilePath) 
                        except Exception as restore_error:
                             print(f"FATAL: Could not restore backup: {restore_error}")
                    return False # Indicar fallo

            # Si llegamos aquí, o no hubo cambios o se guardaron correctamente
            return True

        except configparser.Error as e: # Capturar errores específicos de configparser también
            print(f"ConfigParser error: {e}")
            # No intentar restaurar backup aquí si el error fue antes de saveBackup()
            return False
        except Exception as e:
            # Capturar otros errores generales que puedan ocurrir antes de intentar guardar
            print(f"Unexpected error in set method: {e}")
            # No intentar restaurar backup aquí si el error fue antes de saveBackup()
            return False

    def storeConfig(self):
        print(f"Reinicializando config file: {self.configFilePath}")
        self.config.read(self.configFilePath)
        
        try:
            # Guardar backup del archivo
            self.saveBackup()

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
                
        self.notify_listeners()
        



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
        needs_reset = False
        if not os.path.isfile(configFile):
            print(f"NUEVO User config file será creado en {configFile}")
            # Create an empty file first, resetConfigFile will populate it
            try:
                open(configFile, 'w').close()
                needs_reset = True # New file always needs initial config
            except OSError as e:
                print(f"Error creating config file {configFile}: {e}")
                # Handle error appropriately, maybe raise exception or exit
                return 
        else:
            print(f"User Config existente en {configFile}")

        # Always read the config file, even if just created (it will be empty)
        try:
            read_ok = self.config.read(configFile)
            if not read_ok: # Check if read was successful (file might be empty or malformed)
                 print(f"Config file {configFile} could not be read properly.")
                 # Decide if reset is needed even if file exists but is unreadable
                 # needs_reset = True # Optional: uncomment to reset unreadable files
        except configparser.Error as e:
             print(f"Error parsing config file {configFile}: {e}")
             needs_reset = True # Reset if parsing fails

        # Check for essential section/key only if not already marked for reset
        if not needs_reset:
            try:
                # Use configparser directly to check existence before get
                if not self.config.has_section("SERVIDOR") or not self.config.has_option("SERVIDOR", "uuid"):
                     print(f"Section SERVIDOR o UUID no encontrado en {configFile}")
                     needs_reset = True
                else:
                    # Optionally check if uuid value is valid/not empty
                    uuidVal = self.config.get("SERVIDOR", "uuid", fallback=None)
                    if not uuidVal:
                         print(f"Config UUID está vacío en {configFile}")
                         needs_reset = True
            except configparser.Error as e: # Catch potential errors during check
                 print(f"Error checking config structure: {e}")
                 needs_reset = True

        # Perform reset if needed
        if needs_reset:
            print(f"Reseteando configuración en {configFile}")
            self.resetConfigFile() # This method should handle writing the config
        
        # Reload config after potential reset to ensure it's current
        self.config.read(configFile)

        # menos el primero que es el de SERVIDOR, mostrar el el resto en consola ya que son las impresoras
        for s in self.sections()[1:]:
            print("Impresora en Config: %s" % s)
            
        self.notify_listeners()
        
          

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

        if section in self.config.sections():
            self.config.remove_section(section)
            with open(self.configFilePath, 'w') as configfile:
                self.config.write(configfile)
            self.config.read(self.configFilePath)
            self.notify_listeners()
            return True
        else:
            print(f"Section {section} does not exist.")
            return False
    
    def get(self, section, key, fallback=None):
        self.config.read( self.configFilePath )
        return self.config.get(section, key, fallback=fallback)
    
    
    def add_listener(self, callback):
        """callback(section: str, values: dict)"""
        self._listeners.append(callback)

    def remove_listener(self, callback):
        self._listeners.remove(callback)

    def notify_listeners(self ):
        for callback in self._listeners:
            try:
                callback(self.getJSON())
            except Exception as e:
                print(f"Error notifying listener: {e}")