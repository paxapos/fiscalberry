#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Driver Bluetooth para impresoras ESC/POS en Android
Compatible con impresoras SmartPOS Payway y similares
"""

import os
import time
from threading import Lock
from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("BluetoothPrinter")

# Detectar si estamos en Android
ANDROID = False
try:
    from jnius import autoclass, cast
    ANDROID = True
    logger.debug("Módulo Bluetooth Android disponible")
except ImportError:
    logger.warning("jnius no disponible - Bluetooth solo funciona en Android")


class BluetoothConnection:
    """
    Conexión Bluetooth a impresora ESC/POS usando Android BluetoothSocket.
    """
    
    def __init__(self, mac_address, timeout=10):
        """
        Inicializa conexión Bluetooth.
        
        Args:
            mac_address (str): Dirección MAC de la impresora (ej: "00:11:22:AA:BB:CC")
            timeout (int): Timeout de conexión en segundos
        """
        if not ANDROID:
            raise RuntimeError("Bluetooth solo está disponible en Android")
        
        self.mac_address = mac_address.upper().replace("-", ":")
        self.timeout = timeout
        self.socket = None
        self.output_stream = None
        self.input_stream = None
        self._lock = Lock()
        self.connected = False
        
        logger.debug(f"BluetoothConnection inicializada para MAC: {self.mac_address}")
    
    def connect(self):
        """
        Establece conexión Bluetooth con la impresora.
        
        Returns:
            bool: True si la conexión fue exitosa
        """
        try:
            logger.debug(f"Conectando a impresora Bluetooth: {self.mac_address}")
            
            # Obtener adaptador Bluetooth
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            BluetoothDevice = autoclass('android.bluetooth.BluetoothDevice')
            BluetoothSocket = autoclass('android.bluetooth.BluetoothSocket')
            UUID = autoclass('java.util.UUID')
            
            adapter = BluetoothAdapter.getDefaultAdapter()
            
            if adapter is None:
                raise RuntimeError("No hay adaptador Bluetooth en este dispositivo")
            
            if not adapter.isEnabled():
                logger.error("Bluetooth está desactivado")
                raise RuntimeError("Por favor activa el Bluetooth")
            
            # Obtener dispositivo por MAC
            device = adapter.getRemoteDevice(self.mac_address)
            
            if device is None:
                raise RuntimeError(f"No se pudo obtener dispositivo Bluetooth: {self.mac_address}")
            
            logger.debug(f"Dispositivo encontrado: {device.getName() or 'Sin nombre'}")
            
            # UUID estándar para Serial Port Profile (SPP)
            # Este es el UUID que usan la mayoría de impresoras Bluetooth
            spp_uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
            
            # Crear socket Bluetooth
            logger.debug("Creando BluetoothSocket...")
            
            # Intentar primero con secure socket
            try:
                self.socket = device.createRfcommSocketToServiceRecord(spp_uuid)
            except Exception as e:
                logger.warning(f"No se pudo crear socket seguro, intentando insecure: {e}")
                # Fallback a socket inseguro (algunos dispositivos lo requieren)
                self.socket = device.createInsecureRfcommSocketToServiceRecord(spp_uuid)
            
            # Cancelar discovery para mejorar performance
            if adapter.isDiscovering():
                adapter.cancelDiscovery()
            
            # Conectar socket
            logger.debug("Conectando socket Bluetooth...")
            self.socket.connect()
            
            # Obtener streams de entrada/salida
            self.output_stream = self.socket.getOutputStream()
            self.input_stream = self.socket.getInputStream()
            
            self.connected = True
            logger.info(f"✓ Conectado exitosamente a {self.mac_address}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error conectando Bluetooth: {e}", exc_info=True)
            self.close()
            raise RuntimeError(f"No se pudo conectar a la impresora Bluetooth: {e}")
    
    def write(self, data):
        """
        Escribe datos a la impresora Bluetooth.
        
        Args:
            data (bytes): Datos a enviar
        """
        if not self.connected or self.output_stream is None:
            raise RuntimeError("No hay conexión Bluetooth activa")
        
        with self._lock:
            try:
                if isinstance(data, str):
                    data = data.encode('utf-8')
                
                # Convertir bytes Python a array Java
                jbytes = []
                for byte in data:
                    # Convertir a signed byte para Java (-128 a 127)
                    jbytes.append(byte if byte < 128 else byte - 256)
                
                # Escribir al stream
                self.output_stream.write(jbytes)
                self.output_stream.flush()
                
                logger.debug(f"Enviados {len(data)} bytes vía Bluetooth")
                
            except Exception as e:
                logger.error(f"Error escribiendo a Bluetooth: {e}", exc_info=True)
                self.connected = False
                raise RuntimeError(f"Error enviando datos: {e}")
    
    def read(self, size=1):
        """
        Lee datos de la impresora (si soporta respuestas).
        
        Args:
            size (int): Cantidad de bytes a leer
            
        Returns:
            bytes: Datos leídos
        """
        if not self.connected or self.input_stream is None:
            raise RuntimeError("No hay conexión Bluetooth activa")
        
        try:
            available = self.input_stream.available()
            if available > 0:
                jbytes = []
                for _ in range(min(size, available)):
                    jbytes.append(self.input_stream.read())
                
                # Convertir signed bytes Java a unsigned Python
                return bytes([(b + 256) if b < 0 else b for b in jbytes])
            
            return b''
            
        except Exception as e:
            logger.error(f"Error leyendo de Bluetooth: {e}")
            return b''
    
    def close(self):
        """Cierra la conexión Bluetooth."""
        logger.debug(f"Cerrando conexión Bluetooth: {self.mac_address}")
        
        try:
            if self.output_stream:
                self.output_stream.close()
        except:
            pass
        
        try:
            if self.input_stream:
                self.input_stream.close()
        except:
            pass
        
        try:
            if self.socket:
                self.socket.close()
        except:
            pass
        
        self.connected = False
        self.socket = None
        self.output_stream = None
        self.input_stream = None
        
        logger.debug("Conexión Bluetooth cerrada")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class BluetoothPrinter:
    """
    Impresora Bluetooth compatible con python-escpos.
    Implementa la interfaz necesaria para funcionar con escpos.printer.
    """
    
    def __init__(self, mac_address, timeout=10, *args, **kwargs):
        """
        Inicializa impresora Bluetooth.
        
        Args:
            mac_address (str): Dirección MAC de la impresora
            timeout (int): Timeout de conexión
        """
        self.mac_address = mac_address
        self.timeout = timeout
        self.connection = None
        self.device_name = f"BT Printer {mac_address}"
        
        logger.debug(f"BluetoothPrinter inicializada: {mac_address}")
    
    def open(self):
        """Abre conexión a la impresora."""
        if self.connection is None or not self.connection.connected:
            self.connection = BluetoothConnection(self.mac_address, self.timeout)
            self.connection.connect()
    
    def _raw(self, data):
        """
        Envía datos raw a la impresora (compatible con python-escpos).
        
        Args:
            data (bytes): Datos a enviar
        """
        if self.connection is None or not self.connection.connected:
            self.open()
        
        self.connection.write(data)
    
    def close(self):
        """Cierra conexión a la impresora."""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def __del__(self):
        """Destructor - asegura que se cierre la conexión."""
        self.close()


# =============================================================================
# FUNCIONES DE UTILIDAD PARA ESCANEO Y EMPAREJAMIENTO
# =============================================================================

def scan_bluetooth_printers(timeout=10):
    """
    Escanea impresoras Bluetooth disponibles.
    
    Args:
        timeout (int): Tiempo de escaneo en segundos
        
    Returns:
        list: Lista de diccionarios con información de impresoras encontradas
    """
    if not ANDROID:
        logger.error("Escaneo Bluetooth solo disponible en Android")
        return []
    
    try:
        logger.debug("Iniciando escaneo de impresoras Bluetooth...")
        
        BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
        adapter = BluetoothAdapter.getDefaultAdapter()
        
        if adapter is None:
            raise RuntimeError("No hay adaptador Bluetooth")
        
        if not adapter.isEnabled():
            logger.warning("Bluetooth desactivado")
            return []
        
        printers = []
        
        # 1. Obtener dispositivos ya emparejados
        logger.debug("Buscando dispositivos emparejados...")
        bonded_devices = adapter.getBondedDevices()
        
        if bonded_devices:
            for device in bonded_devices.toArray():
                device_name = device.getName() or "Sin nombre"
                mac_address = device.getAddress()
                
                # Filtrar solo impresoras (por nombre común o clase de dispositivo)
                is_printer = False
                
                # Detectar por nombre
                printer_keywords = ['printer', 'print', 'pos', 'receipt', 'ticket', 
                                   'epson', 'star', 'bixolon', 'custom', 'payway']
                if any(keyword in device_name.lower() for keyword in printer_keywords):
                    is_printer = True
                
                # Detectar por clase de dispositivo (0x0680 = Impresora)
                try:
                    device_class = device.getBluetoothClass().getDeviceClass()
                    if device_class == 0x0680:  # Clase: Impresora
                        is_printer = True
                except:
                    pass
                
                if is_printer:
                    printer_info = {
                        'name': device_name,
                        'mac_address': mac_address,
                        'bonded': True,
                        'type': 'Bluetooth',
                        'connection': 'Bluetooth'
                    }
                    printers.append(printer_info)
                    logger.debug(f"Impresora encontrada: {device_name} ({mac_address})")
        
        # 2. Descubrir nuevos dispositivos (opcional)
        if adapter.startDiscovery():
            logger.debug(f"Descubriendo nuevos dispositivos Bluetooth ({timeout}s)...")
            time.sleep(timeout)
            adapter.cancelDiscovery()
        
        logger.debug(f"Escaneo completo: {len(printers)} impresoras encontradas")
        return printers
        
    except Exception as e:
        logger.error(f"Error escaneando Bluetooth: {e}", exc_info=True)
        return []


def pair_bluetooth_device(mac_address):
    """
    Empareja un dispositivo Bluetooth.
    
    Args:
        mac_address (str): Dirección MAC del dispositivo
        
    Returns:
        bool: True si se emparejó correctamente
    """
    if not ANDROID:
        logger.error("Emparejamiento Bluetooth solo disponible en Android")
        return False
    
    try:
        logger.debug(f"Intentando emparejar dispositivo: {mac_address}")
        
        BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
        adapter = BluetoothAdapter.getDefaultAdapter()
        
        if adapter is None or not adapter.isEnabled():
            raise RuntimeError("Bluetooth no disponible")
        
        device = adapter.getRemoteDevice(mac_address)
        
        # Crear bond (emparejar)
        result = device.createBond()
        
        if result:
            logger.info(f"✓ Emparejamiento iniciado para {mac_address}")
            return True
        else:
            logger.warning(f"No se pudo iniciar emparejamiento para {mac_address}")
            return False
            
    except Exception as e:
        logger.error(f"Error emparejando dispositivo: {e}", exc_info=True)
        return False


def get_paired_printers():
    """
    Obtiene lista de impresoras Bluetooth ya emparejadas.
    
    Returns:
        list: Lista de impresoras emparejadas
    """
    return [p for p in scan_bluetooth_printers(timeout=0) if p.get('bonded', False)]


# Exportar clases principales
__all__ = [
    'BluetoothPrinter',
    'BluetoothConnection',
    'scan_bluetooth_printers',
    'pair_bluetooth_device',
    'get_paired_printers'
]
