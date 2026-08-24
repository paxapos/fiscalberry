import configparser
import logging
import os
import tempfile
import threading
import uuid

# Logger de la stdlib a propósito, no getLogger() de fiscalberry_logger: ese
# módulo importa Configberry para resolver la ruta del log, y usarlo acá crearía
# una recursión durante la construcción del propio Configberry. Como
# setup_file_logging() configura el logger raíz, esto igual termina en el
# archivo de log.
#
# Importa que estos mensajes SE VEAN: los errores de escritura del config se
# reportaban con print(), que en Android no va a ningún lado. Un config que no
# se pudo guardar quedaba como una falla silenciosa.
logger = logging.getLogger("fiscalberry.Configberry")
import platformdirs
import platform


appname = 'Fiscalberry'


class Configberry:
    config = configparser.ConfigParser()
    config.optionxform=str
    _instance = None

    configFilePath = None

    _listeners = []

    # ConfigParser NO es thread-safe y get()/set() releen/reescriben el mismo objeto
    # compartido desde varios hilos (SIO, consumer MQTT, discover, Clock de la GUI).
    # Este lock reentrante serializa el acceso para evitar lecturas a medias y
    # escrituras que se pisan. Reentrante porque set()->notify_listeners()->getJSON().
    _rlock = threading.RLock()

    # Cache de lectura: evita releer el INI del disco en cada get(). Se invalida
    # cuando cambia el mtime del archivo o tras un set()/delete que reescribe.
    _last_mtime = None
    _loaded = False

    def _reload_if_changed(self):
        """Relee el INI solo si aun no se cargo o si cambio su mtime. Bajo _rlock."""
        try:
            mtime = os.path.getmtime(self.configFilePath)
        except OSError:
            mtime = None
        if (not self._loaded) or (mtime != self._last_mtime):
            self.config.read(self.configFilePath)
            self._loaded = True
            self._last_mtime = mtime

    def _invalidate_cache(self):
        """Fuerza recarga en el proximo get() (llamar tras escribir el INI)."""
        self._loaded = False


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
            


    def getConfigFIle(self):

        configDirPath = platformdirs.user_config_dir(appname)
        if not os.path.exists(configDirPath):
            os.makedirs(configDirPath)

        CONFIG_FILE_NAME = os.path.join(configDirPath, 'config.ini')

        return CONFIG_FILE_NAME


    def getJSON(self):
        with self._rlock:
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
        with self._rlock:
            return self._set_impl(section, kwargs)

    def _set_impl(self, section: str, kwargs: dict):
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
                    self._write_atomic()

                    # Recargar la configuración después de escribir
                    self.config.read(self.configFilePath) 
                    # Invalidar cache de get(): el archivo cambió en disco.
                    self._invalidate_cache()
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
                    logger.error(f"No se pudo guardar el config: {write_error}")
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

    def _write_atomic(self):
        """
        Vuelca el INI a disco de forma atómica: temporal + rename encima.

        `open(path, 'w')` trunca el archivo al instante, así que mientras se
        escribe queda vacío o a medias. En Android eso es una carrera real:
        el proceso de la UI y el del servicio comparten este mismo config.ini.
        Si el otro proceso lee justo en esa ventana, encuentra un config SIN la
        sección SERVIDOR, concluye que está corrupto y lo resetea — y el equipo
        se queda sin uuid (o con otro).

        Sin uuid, la pantalla de vinculación arma `<host>/adopt/` sin
        identificador: el servidor devuelve 500 y el QR queda en blanco. Pasó
        en producción.

        `os.replace()` es atómico en POSIX y en Windows: el que lee ve el
        archivo viejo o el nuevo, nunca uno a medio escribir. Y si el proceso
        muere en el medio, el original queda intacto.
        """
        directorio = os.path.dirname(self.configFilePath) or "."
        fd, tmp_path = tempfile.mkstemp(dir=directorio, prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as configfile:
                self.config.write(configfile)
                configfile.flush()
                os.fsync(configfile.fileno())
            os.replace(tmp_path, self.configFilePath)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def storeConfig(self):
        with self._rlock:
            return self._store_config_impl()

    def _store_config_impl(self):
        print(f"Reinicializando config file: {self.configFilePath}")
        self.config.read(self.configFilePath)
        
        try:
            # Guardar backup del archivo
            self.saveBackup()

            self._write_atomic()
        except Exception as e:
            # Restaurar desde el backup en caso de error
            if os.path.exists(self.configFilePath + ".bak"):
                os.replace(self.configFilePath + ".bak", self.configFilePath)
            
            logger.error(f"No se pudo escribir el config: {e}")
        
        self.config.read(self.configFilePath)
                
        self.notify_listeners()
        



    # Claves que [SERVIDOR] necesita para que el cliente funcione, con su valor
    # por defecto. NO incluye uuid: ese es la identidad del equipo y se genera
    # aparte, nunca se pisa.
    SERVIDOR_DEFAULTS = {
        "sio_host": "https://beta.paxapos.com",
        "sio_password": "",
        "verify_ssl": "true",
    }

    def _asegurar_claves_servidor(self):
        """
        Agrega las claves de [SERVIDOR] que falten, sin tocar las que ya están.

        El chequeo de integridad del config solo exigía que existiera `uuid`, de
        modo que un config con uuid pero SIN `sio_host` se consideraba válido
        para siempre y nada volvía a completarlo. Y `sio_host` solo se escribe
        en el reset, que en ese estado ya no se dispara nunca.

        Consecuencia real en un celular: sin `sio_host`, ni el discover ni
        SocketIO salían —el cliente ni siquiera intentaba conectarse— y la
        vinculación moría con ":: Paxaprinter no encontrada", porque el servidor
        jamás se enteró de que el dispositivo existía.

        Solo se completa lo ausente: si alguien apuntó el equipo a otro host,
        ese valor se respeta.
        """
        # Se mira EL ARCHIVO con un parser limpio, no `self.config`.
        #
        # `config` es un atributo de clase, o sea que el ConfigParser se comparte
        # entre todas las instancias, y `read()` FUSIONA: nunca borra claves que
        # ya no estén en el archivo. Un valor viejo en memoria puede entonces
        # tapar una clave que en disco no existe, y la reparación no se haría —
        # dejando el archivo incompleto para el próximo arranque, que es
        # exactamente el problema que esto viene a resolver.
        en_disco = configparser.ConfigParser()
        en_disco.optionxform = str
        try:
            en_disco.read(self.configFilePath)
        except Exception as e:
            logger.error(f"No se pudo releer el config para validarlo: {e}")
            return False

        faltantes = {}
        for clave, valor in self.SERVIDOR_DEFAULTS.items():
            if en_disco.get("SERVIDOR", clave, fallback=None) is None:
                faltantes[clave] = valor

        if not faltantes:
            return False

        logger.warning(
            "Faltaban claves en [SERVIDOR] del config (%s). Se completan con "
            "los valores por defecto; el resto de la configuración no se toca.",
            ", ".join(sorted(faltantes)))
        try:
            self.set("SERVIDOR", faltantes)
        except Exception as e:
            logger.error(f"No se pudieron completar las claves faltantes: {e}")
            return False
        return True

    def resetConfigFile(self):
        # El uuid es la identidad del dispositivo ante Paxapos (y el topic MQTT):
        # si ya hay uno, se conserva. Un reset por config corrupta o por una
        # sección faltante no puede convertir al equipo en otro dispositivo y
        # obligar a re-vincular el comercio.
        from fiscalberry.common.device_uuid import generate_device_uuid

        myUuid = self.config.get("SERVIDOR", "uuid", fallback="") or generate_device_uuid()
        self.set("SERVIDOR", {
            "uuid": myUuid,
            "platform": f"{os.name} {platform.system()} {platform.release()} {platform.machine()}",
            "sio_host": "https://beta.paxapos.com",
            "sio_password": "",
            # Verificación TLS. Poner en false (o definir ca_bundle) para backends con
            # CA privada como dev2.paxapos.com. Default true para prod.
            "verify_ssl": "true"
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
                logger.error(f"No se pudo crear el config {configFile}: {e}")
                # Handle error appropriately, maybe raise exception or exit
                return 
        else:
            print(f"User Config existente en {configFile}")

        # Always read the config file, even if just created (it will be empty)
        try:
            read_ok = self.config.read(configFile)
            if not read_ok: # Check if read was successful (file might be empty or malformed)
                 logger.warning(f"El config {configFile} no se pudo leer bien.")
                 # Decide if reset is needed even if file exists but is unreadable
                 # needs_reset = True # Optional: uncomment to reset unreadable files
        except configparser.Error as e:
             logger.error(f"Config {configFile} ilegible: {e}")
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

        # Completar claves faltantes SIN resetear nada de lo que ya hay.
        self._asegurar_claves_servidor()

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
        elif ":" in printerName and "=" not in printerName:
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
            #
            # Se exige que NO haya "=": una config embebida
            # (driver=Bluetooth&mac_address=00:11:22:AA:BB:CC) también trae ":"
            # en la MAC y caía acá, reventando con "too many values to unpack".
            # Eso dejaba sin salida a las impresoras Bluetooth, que son las
            # únicas cuyo parámetro obligatorio contiene ":".
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
        with self._rlock:
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
        with self._rlock:
            self._reload_if_changed()
            return self.config.get(section, key, fallback=fallback)

    def get_ssl_verify(self):
        """
        Resuelve el valor de verificación TLS para requests / socketio.

        Prioridad:
          1) [SERVIDOR] ca_bundle = /ruta/ca.pem  -> verifica contra esa CA propia
             (ideal para backends con CA privada como dev2). Aplica a requests.
          2) [SERVIDOR] verify_ssl = false        -> desactiva la verificación
             (solo entornos de desarrollo; ej. dev2 con CA no instalada).
          3) por defecto True (CAs del sistema/certifi).

        Devuelve str (ruta de bundle) o bool.
        """
        ca = self.get("SERVIDOR", "ca_bundle", fallback="")
        if ca and str(ca).strip():
            return str(ca).strip()
        val = self.get("SERVIDOR", "verify_ssl", fallback="true")
        return str(val).strip().lower() not in ("false", "0", "no", "off")
    
    def is_comercio_adoptado(self):
        """
        Verifica si el comercio ha sido adoptado.
        Un comercio se considera adoptado si tiene configuración de RabbitMQ
        con un tenant asociado en la sección [Paxaprinter].
        
        Retorna True si existe la sección Paxaprinter y tiene un tenant configurado,
        False en caso contrario.
        """
        # Releer bajo lock para no competir con un set()/delete_section() en curso.
        with self._rlock:
            self.config.read(self.configFilePath)
            # Verificar si existe la sección Paxaprinter
            if not self.config.has_section("Paxaprinter"):
                return False

        # Verificar si tiene un tenant configurado
        tenant = self.get("Paxaprinter", "tenant", fallback="")
        
        # El tenant debe existir y no estar vacío ni ser un valor de ejemplo
        if not tenant or tenant.strip() == "":
            return False
        
        # Valores de ejemplo que no se consideran válidos
        example_values = ["your-tenant-name", "tenant-name", "example", "test"]
        if tenant.lower() in example_values:
            return False
        
        return True
    
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