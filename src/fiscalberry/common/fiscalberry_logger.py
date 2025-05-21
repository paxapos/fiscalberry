import os
import sys
import logging
import logging.config
import tempfile
import platform
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
import traceback

# Evitar referencia circular en la importación
def get_configberry():
    from fiscalberry.common.Configberry import Configberry
    return Configberry()

class FiscalberryLogger:
    """Sistema centralizado de logging para Fiscalberry."""
    
    # Instancia singleton
    _instance = None
    _initialized = False
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        if FiscalberryLogger._initialized:
            return
            
        # Inicialización básica
        self.logger = logging.getLogger("Fiscalberry")
        self.logger.setLevel(logging.DEBUG)
        
        # Limpiar handlers existentes para evitar duplicados
        if self.logger.handlers:
            self.logger.handlers.clear()
            
        # Determinar ambiente y configurar nivel de detalle
        try:
            configberry = get_configberry()
            self.environment = configberry.config.get("SERVIDOR", "environment", fallback="production").lower()
            self.log_level = configberry.config.get("SERVIDOR", "log_level", fallback="INFO").upper()
            
            # Anunciar el modo de ejecución
            if self.environment == "development":
                print("* * * * * Modo de desarrollo * * * * *")
            else:
                print("@ @ @ @ @ Modo de producción @ @ @ @ @")
        except Exception as e:
            self.environment = "production"
            self.log_level = "INFO"
            print(f"Error al cargar configuración de logger: {e}")
            print(traceback.format_exc())
            
        # Configurar rutas de log
        self.log_dir = self._determine_log_directory()
        self.log_file = os.path.join(self.log_dir, "fiscalberry.log")
        
        # Crear formateador de logs
        self.formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # Configurar handlers
        self._setup_file_handler()
        self._setup_console_handler()
        
        # Configurar loggers de terceros
        self._configure_third_party_loggers()
        
        FiscalberryLogger._initialized = True
        
        # Auto-log de inicio
        self.logger.info(f"Sistema de logging inicializado en modo {self.environment}")
        self.logger.info(f"Archivos de log en: {self.log_file}")
    
    def _determine_log_directory(self):
        """Determina el directorio de logs según la plataforma."""
        app_name = "fiscalberry"
        
        # Android
        if hasattr(os, 'getenv') and os.getenv('ANDROID_STORAGE') is not None:
            log_dir = os.path.join(os.getenv('EXTERNAL_STORAGE', '/sdcard'), app_name, 'logs')
        
        # Windows
        elif platform.system() == 'Windows':
            log_dir = os.path.join(os.getenv('LOCALAPPDATA', os.path.expanduser('~')), app_name, 'logs')
        
        # Linux y otros Unix
        else:
            log_dir = os.path.join(os.path.expanduser('~'), '.local', 'share', app_name, 'logs')
        
        # Crear directorio si no existe
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            print(f"No se pudo crear directorio de logs: {e}")
            log_dir = tempfile.gettempdir()
            
        return log_dir
    
    def _setup_file_handler(self):
        """Configura el handler para archivo de logs."""
        try:
            # RotatingFileHandler: máximo 5MB por archivo, con 5 backups
            file_handler = RotatingFileHandler(
                self.log_file,
                maxBytes=5*1024*1024,
                backupCount=5,
                encoding='utf-8'
            )
            
            # Como alternativa, también puedes usar TimedRotatingFileHandler
            # file_handler = TimedRotatingFileHandler(
            #     self.log_file, 
            #     when='midnight', 
            #     interval=1,
            #     backupCount=30,
            #     encoding='utf-8'
            # )
            
            file_handler.setFormatter(self.formatter)
            file_handler.setLevel(getattr(logging, self.log_level))
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"Error al configurar file handler: {e}")
            print(traceback.format_exc())
    
    def _setup_console_handler(self):
        """Configura el handler para salida a consola."""
        try:
            console_handler = logging.StreamHandler(stream=sys.stdout)
            console_handler.setFormatter(self.formatter)
            
            # En desarrollo mostramos más información
            if self.environment == "development":
                console_level = logging.DEBUG
            else:
                console_level = logging.WARNING
                
            console_handler.setLevel(console_level)
            self.logger.addHandler(console_handler)
        except Exception as e:
            print(f"Error al configurar console handler: {e}")
    
    def _configure_third_party_loggers(self):
        """Configura niveles para loggers de librerías externas."""
        # Reducir el ruido de logs de librerías externas
        logging.getLogger("pika").setLevel(logging.WARNING)
        logging.getLogger("socketio").setLevel(logging.INFO)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    def get_logger(self, name=None):
        """Devuelve el logger, opcionalmente con un nombre específico."""
        if name:
            return logging.getLogger(f"Fiscalberry.{name}")
        return self.logger
    
    def get_log_file_path(self):
        """Devuelve la ruta del archivo de log."""
        return self.log_file

# API pública simplificada
def getLogger(name=None):
    """Obtiene el logger global o uno específico por nombre."""
    logger_instance = FiscalberryLogger.get_instance()
    return logger_instance.get_logger(name)

def getLogFilePath():
    """Devuelve la ruta del archivo de log."""
    logger_instance = FiscalberryLogger.get_instance()
    return logger_instance.get_log_file_path()

# Para mantener compatibilidad con el código existente
Logger = getLogger()