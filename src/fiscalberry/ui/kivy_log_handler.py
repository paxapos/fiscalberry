import logging
from collections import deque
from kivy.clock import Clock

class KivyLogHandler(logging.Handler):
    """
    Handler de logging que captura mensajes y los almacena en un buffer circular.
    Se integra con Kivy para actualizar la UI en el hilo principal.
    """
    
    def __init__(self, max_lines=200):
        """
        Args:
            max_lines: Número máximo de líneas a mantener en el buffer
        """
        super().__init__()
        self.log_buffer = deque(maxlen=max_lines)
        self._app_ref = None
        
        # Formato de los mensajes (similar a CLI)
        formatter = logging.Formatter(
            '[%(levelname)-7s] [%(name)-12s] %(message)s'
        )
        self.setFormatter(formatter)
    
    def set_app(self, app):
        """Establece referencia a la aplicación Kivy para actualizar app.logs"""
        self._app_ref = app
    
    def emit(self, record):
        """
        Llamado automáticamente cuando se genera un log.
        Almacena el mensaje formateado en el buffer.
        """
        try:
            msg = self.format(record)
            self.log_buffer.append(msg)
            
            # Actualizar la UI en el hilo principal de Kivy
            if self._app_ref:
                Clock.schedule_once(lambda dt: self._update_app_logs(), 0)
                
        except Exception:
            self.handleError(record)
    
    def _update_app_logs(self):
        """Actualiza la propiedad app.logs con el contenido del buffer"""
        if self._app_ref:
            self._app_ref.logs = '\n'.join(self.log_buffer)
    
    def get_logs(self):
        """Retorna todos los logs actuales como string"""
        return '\n'.join(self.log_buffer)
