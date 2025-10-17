#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Detector de impresoras multi-plataforma
Soporta: Windows, Linux, Android
"""

import platform
import sys

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("PrinterDetector")

# Detectar si estamos en Android
ANDROID = False
try:
    from jnius import autoclass
    from jnius import cast
    ANDROID = True
    logger.info("Ejecutando en Android - usando detección USB con pyjnius")
except ImportError:
    logger.debug("pyjnius no disponible - no es Android")


def get_android_usb_printers():
    """
    Obtiene lista de impresoras USB conectadas en Android.
    Requiere permisos USB en runtime.
    
    Returns:
        list: Lista de diccionarios con información de impresoras USB
    """
    if not ANDROID:
        return []
    
    try:
        # Obtener contexto de Android
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Context = autoclass('android.content.Context')
        UsbManager = autoclass('android.hardware.usb.UsbManager')
        
        activity = PythonActivity.mActivity
        usb_service = activity.getSystemService(Context.USB_SERVICE)
        usb_manager = cast('android.hardware.usb.UsbManager', usb_service)
        
        # Obtener lista de dispositivos USB
        device_list = usb_manager.getDeviceList()
        
        printers = []
        for device_name in device_list.keySet().toArray():
            device = device_list.get(device_name)
            
            # Clase de dispositivo 7 = Impresora
            # También verificar subclase 1 = Impresora
            device_class = device.getDeviceClass()
            
            # Obtener información del dispositivo
            vendor_id = device.getVendorId()
            product_id = device.getProductId()
            device_id = device.getDeviceId()
            device_name_str = device.getDeviceName()
            
            # Verificar si es una impresora o si tiene interfaz de impresora
            is_printer = False
            
            # Opción 1: Clase de dispositivo es impresora
            if device_class == 7:
                is_printer = True
            
            # Opción 2: Verificar interfaces (algunas impresoras no reportan clase correcta)
            interface_count = device.getInterfaceCount()
            for i in range(interface_count):
                interface = device.getInterface(i)
                interface_class = interface.getInterfaceClass()
                if interface_class == 7:  # Clase impresora en interfaz
                    is_printer = True
                    break
            
            # También podemos identificar por vendor_id conocidos de impresoras fiscales
            # Vendor IDs comunes:
            # - Epson: 0x04b8
            # - Hasar: 0x04b8 (algunos modelos usan chips Epson)
            known_printer_vendors = [0x04b8, 0x0483, 0x067b]
            if vendor_id in known_printer_vendors:
                is_printer = True
            
            if is_printer:
                printer_info = {
                    'name': f"USB Printer {vendor_id:04x}:{product_id:04x}",
                    'device_name': device_name_str,
                    'vendor_id': vendor_id,
                    'product_id': product_id,
                    'device_id': device_id,
                    'device_class': device_class,
                    'platform': 'Android',
                    'connection': 'USB',
                    'has_permission': usb_manager.hasPermission(device)
                }
                printers.append(printer_info)
                logger.info(f"Impresora USB encontrada: {printer_info['name']} - Permiso: {printer_info['has_permission']}")
        
        return printers
        
    except Exception as e:
        logger.error(f"Error detectando impresoras USB en Android: {e}", exc_info=True)
        return []


def request_android_usb_permission(device_name=None):
    """
    Solicita permiso USB para un dispositivo específico o todos los dispositivos.
    
    Args:
        device_name (str, optional): Nombre del dispositivo USB. Si es None, solicita para todos.
    
    Returns:
        bool: True si se solicitó el permiso (no garantiza que se otorgue)
    """
    if not ANDROID:
        return False
    
    try:
        from android.permissions import request_permissions, Permission, check_permission
        
        # Verificar si ya tenemos el permiso general
        if not check_permission(Permission.INTERNET):
            logger.warning("Permiso INTERNET no otorgado")
        
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Context = autoclass('android.content.Context')
        UsbManager = autoclass('android.hardware.usb.UsbManager')
        PendingIntent = autoclass('android.app.PendingIntent')
        Intent = autoclass('android.content.Intent')
        
        activity = PythonActivity.mActivity
        usb_service = activity.getSystemService(Context.USB_SERVICE)
        usb_manager = cast('android.hardware.usb.UsbManager', usb_service)
        
        # Crear intent para la solicitud de permiso
        ACTION_USB_PERMISSION = "com.paxapos.fiscalberry.USB_PERMISSION"
        
        device_list = usb_manager.getDeviceList()
        
        for dev_name in device_list.keySet().toArray():
            device = device_list.get(dev_name)
            
            if device_name and device.getDeviceName() != device_name:
                continue
            
            if not usb_manager.hasPermission(device):
                logger.info(f"Solicitando permiso USB para: {device.getDeviceName()}")
                
                permission_intent = Intent(ACTION_USB_PERMISSION)
                pending_intent = PendingIntent.getBroadcast(
                    activity, 0, permission_intent, 
                    PendingIntent.FLAG_IMMUTABLE
                )
                
                usb_manager.requestPermission(device, pending_intent)
        
        return True
        
    except Exception as e:
        logger.error(f"Error solicitando permiso USB: {e}", exc_info=True)
        return False


def listar_impresoras():
    """
    Lista todas las impresoras disponibles según la plataforma.
    
    Returns:
        list: Lista de nombres de impresoras o diccionarios con info (Android)
    """
    sistema_operativo = platform.system()
    impresoras = []

    # Detección específica para Android
    if ANDROID:
        logger.info("Detectando impresoras en Android...")
        
        # Detectar USB
        usb_printers = get_android_usb_printers()
        
        # Detectar Bluetooth
        try:
            from fiscalberry.common.bluetooth_printer import scan_bluetooth_printers
            logger.info("Escaneando impresoras Bluetooth...")
            bt_printers = scan_bluetooth_printers(timeout=5)
            
            if bt_printers:
                logger.info(f"Encontradas {len(bt_printers)} impresoras Bluetooth")
                impresoras.extend(bt_printers)
        except Exception as e:
            logger.error(f"Error escaneando Bluetooth: {e}")
            bt_printers = []
        
        if usb_printers:
            logger.info(f"Encontradas {len(usb_printers)} impresoras USB")
            impresoras.extend(usb_printers)
        
        if impresoras:
            return impresoras
        else:
            logger.warning("No se encontraron impresoras en Android")
            logger.info("Asegúrate de que:")
            logger.info("  1. La impresora esté conectada vía USB OTG o emparejada por Bluetooth")
            logger.info("  2. Los permisos USB/Bluetooth estén otorgados")
            logger.info("  3. El Bluetooth esté activado (para impresoras BT)")
            return []
    
    # Linux (incluyendo Raspberry Pi)
    elif sistema_operativo == "Linux":
        logger.info("Detectando impresoras en Linux...")
        try:
            import subprocess
            resultado = subprocess.run(['lpstat', '-e'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            impresoras = resultado.stdout.decode('utf-8').splitlines()
            logger.info(f"Encontradas {len(impresoras)} impresoras en Linux")
        except FileNotFoundError:
            logger.warning("Comando 'lpstat' no encontrado. Instala CUPS: sudo apt install cups")
        except Exception as e:
            logger.error(f"Error detectando impresoras en Linux: {e}")
    
    # Windows
    elif sistema_operativo == "Windows":
        logger.info("Detectando impresoras en Windows...")
        try:
            import win32print
            impresoras = [printer[2] for printer in win32print.EnumPrinters(2)]
            logger.info(f"Encontradas {len(impresoras)} impresoras en Windows")
        except ImportError:
            logger.error("pywin32 no instalado. Instala con: pip install pywin32")
        except Exception as e:
            logger.error(f"Error detectando impresoras en Windows: {e}")
    
    else:
        logger.error(f"Sistema operativo no soportado: {sistema_operativo}")
        raise NotImplementedError(f"Sistema operativo no soportado: {sistema_operativo}")

    return impresoras


def get_printer_info(printer_name_or_dict):
    """
    Obtiene información detallada de una impresora.
    
    Args:
        printer_name_or_dict: Nombre de la impresora (str) o diccionario con info (Android)
    
    Returns:
        dict: Información de la impresora
    """
    if isinstance(printer_name_or_dict, dict):
        # Ya es un diccionario de Android
        return printer_name_or_dict
    
    # Es un nombre simple (Windows/Linux)
    return {
        'name': printer_name_or_dict,
        'platform': platform.system(),
        'connection': 'Unknown'
    }