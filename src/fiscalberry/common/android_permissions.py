#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Helper para gestionar permisos de Android en runtime
"""

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("AndroidPermissions")

# Detectar si estamos en Android
ANDROID = False
try:
    from android.permissions import request_permissions, check_permission, Permission
    from jnius import autoclass
    ANDROID = True
    logger.info("Módulo de permisos Android disponible")
except ImportError:
    logger.debug("android.permissions no disponible - no es Android")


# Mapeo de permisos necesarios para Fiscalberry
FISCALBERRY_PERMISSIONS = [
    'android.permission.INTERNET',
    'android.permission.ACCESS_NETWORK_STATE',
    'android.permission.ACCESS_WIFI_STATE',
    'android.permission.WAKE_LOCK',
    'android.permission.FOREGROUND_SERVICE',
    'android.permission.READ_EXTERNAL_STORAGE',
    'android.permission.WRITE_EXTERNAL_STORAGE',
    'android.permission.BLUETOOTH',
    'android.permission.BLUETOOTH_ADMIN',
    'android.permission.BLUETOOTH_CONNECT',
    'android.permission.BLUETOOTH_SCAN',
    'android.permission.ACCESS_COARSE_LOCATION',
    'android.permission.ACCESS_FINE_LOCATION',
]


def check_all_permissions():
    """
    Verifica si todos los permisos necesarios están otorgados.
    
    Returns:
        dict: Diccionario con el estado de cada permiso
    """
    if not ANDROID:
        return {'all_granted': True, 'details': {}}
    
    try:
        results = {}
        all_granted = True
        
        for permission in FISCALBERRY_PERMISSIONS:
            try:
                # Convertir string de permiso a objeto Permission si es posible
                granted = check_permission(permission)
                results[permission] = granted
                
                if not granted:
                    all_granted = False
                    logger.warning(f"Permiso no otorgado: {permission}")
                else:
                    logger.debug(f"Permiso otorgado: {permission}")
                    
            except Exception as e:
                logger.error(f"Error verificando permiso {permission}: {e}")
                results[permission] = False
                all_granted = False
        
        return {
            'all_granted': all_granted,
            'details': results
        }
        
    except Exception as e:
        logger.error(f"Error verificando permisos: {e}", exc_info=True)
        return {'all_granted': False, 'details': {}}


def request_all_permissions():
    """
    Solicita todos los permisos necesarios de una vez.
    
    Returns:
        bool: True si se solicitaron los permisos correctamente
    """
    if not ANDROID:
        logger.debug("No es Android - permisos no necesarios")
        return True
    
    try:
        logger.info("Solicitando permisos de Android...")
        
        # Filtrar solo los permisos que no están otorgados
        missing_permissions = []
        for permission in FISCALBERRY_PERMISSIONS:
            try:
                if not check_permission(permission):
                    missing_permissions.append(permission)
            except:
                missing_permissions.append(permission)
        
        if missing_permissions:
            logger.info(f"Solicitando {len(missing_permissions)} permisos faltantes")
            request_permissions(missing_permissions)
            return True
        else:
            logger.info("Todos los permisos ya están otorgados")
            return True
            
    except Exception as e:
        logger.error(f"Error solicitando permisos: {e}", exc_info=True)
        return False


def request_storage_permissions():
    """Solicita permisos de almacenamiento (para guardar config.ini y logs)"""
    if not ANDROID:
        return True
    
    try:
        permissions = [
            'android.permission.READ_EXTERNAL_STORAGE',
            'android.permission.WRITE_EXTERNAL_STORAGE',
        ]
        
        missing = [p for p in permissions if not check_permission(p)]
        if missing:
            logger.info("Solicitando permisos de almacenamiento...")
            request_permissions(missing)
        return True
    except Exception as e:
        logger.error(f"Error solicitando permisos de almacenamiento: {e}")
        return False


def request_network_permissions():
    """Solicita permisos de red (para RabbitMQ y SocketIO)"""
    if not ANDROID:
        return True
    
    try:
        permissions = [
            'android.permission.INTERNET',
            'android.permission.ACCESS_NETWORK_STATE',
            'android.permission.ACCESS_WIFI_STATE',
        ]
        
        missing = [p for p in permissions if not check_permission(p)]
        if missing:
            logger.info("Solicitando permisos de red...")
            request_permissions(missing)
        return True
    except Exception as e:
        logger.error(f"Error solicitando permisos de red: {e}")
        return False


def request_bluetooth_permissions():
    """Solicita permisos de Bluetooth (para impresoras BT)"""
    if not ANDROID:
        return True
    
    try:
        permissions = [
            'android.permission.BLUETOOTH',
            'android.permission.BLUETOOTH_ADMIN',
            'android.permission.BLUETOOTH_CONNECT',
            'android.permission.BLUETOOTH_SCAN',
            'android.permission.ACCESS_COARSE_LOCATION',
            'android.permission.ACCESS_FINE_LOCATION',
        ]
        
        missing = [p for p in permissions if not check_permission(p)]
        if missing:
            logger.info("Solicitando permisos de Bluetooth...")
            request_permissions(missing)
        return True
    except Exception as e:
        logger.error(f"Error solicitando permisos de Bluetooth: {e}")
        return False


def get_permissions_status_summary():
    """
    Obtiene un resumen legible del estado de los permisos.
    
    Returns:
        str: Resumen en texto del estado de permisos
    """
    if not ANDROID:
        return "Plataforma: No Android\nPermisos: No requeridos"
    
    status = check_all_permissions()
    
    summary = "Estado de Permisos Android:\n"
    summary += "="*50 + "\n"
    
    if status['all_granted']:
        summary += "✅ Todos los permisos otorgados\n"
    else:
        summary += "⚠️ Algunos permisos faltantes\n\n"
        
        for permission, granted in status['details'].items():
            status_icon = "✅" if granted else "❌"
            perm_name = permission.split('.')[-1]
            summary += f"  {status_icon} {perm_name}\n"
    
    return summary


if __name__ == "__main__":
    # Test del módulo
    print(get_permissions_status_summary())
    
    if ANDROID:
        print("\nSolicitando permisos faltantes...")
        request_all_permissions()
