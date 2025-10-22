#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Helper para gestionar permisos de Android en runtime
"""

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("AndroidPermissions")

# Detectar si estamos en Android y obtener información de la versión
ANDROID = False
ANDROID_API_LEVEL = 0
try:
    from android.permissions import request_permissions, check_permission, Permission
    from jnius import autoclass
    ANDROID = True
    
    # Obtener el nivel de API actual
    Build = autoclass('android.os.Build')
    ANDROID_API_LEVEL = Build.VERSION.SDK_INT
    logger.info(f"Módulo de permisos Android disponible - API Level: {ANDROID_API_LEVEL}")
except ImportError:
    logger.debug("android.permissions no disponible - no es Android")


# Mapeo de permisos necesarios para Fiscalberry por versión de API
FISCALBERRY_PERMISSIONS_BASE = [
    'android.permission.INTERNET',
    'android.permission.ACCESS_NETWORK_STATE',
    'android.permission.ACCESS_WIFI_STATE',
    'android.permission.WAKE_LOCK',
    'android.permission.READ_EXTERNAL_STORAGE',
    'android.permission.WRITE_EXTERNAL_STORAGE',
    'android.permission.BLUETOOTH',
    'android.permission.BLUETOOTH_ADMIN',
]

# Permisos adicionales según versión de API
FISCALBERRY_PERMISSIONS_API_23_PLUS = [
    'android.permission.ACCESS_COARSE_LOCATION',  # Requerido para Bluetooth desde API 23
]

FISCALBERRY_PERMISSIONS_API_28_PLUS = [
    'android.permission.FOREGROUND_SERVICE',  # Requerido desde API 28
]

FISCALBERRY_PERMISSIONS_API_31_PLUS = [
    'android.permission.BLUETOOTH_CONNECT',  # Nuevos permisos de Bluetooth desde API 31
    'android.permission.BLUETOOTH_SCAN',
    'android.permission.ACCESS_FINE_LOCATION',  # Requerido para BLUETOOTH_SCAN
]


def get_required_permissions():
    """
    Obtiene la lista de permisos requeridos según la versión de Android.
    
    Returns:
        list: Lista de permisos requeridos para la versión actual
    """
    if not ANDROID:
        return []
    
    permissions = FISCALBERRY_PERMISSIONS_BASE.copy()
    
    # Agregar permisos según nivel de API
    if ANDROID_API_LEVEL >= 23:  # Android 6.0+
        permissions.extend(FISCALBERRY_PERMISSIONS_API_23_PLUS)
        
    if ANDROID_API_LEVEL >= 28:  # Android 9.0+
        permissions.extend(FISCALBERRY_PERMISSIONS_API_28_PLUS)
        
    if ANDROID_API_LEVEL >= 31:  # Android 12.0+
        permissions.extend(FISCALBERRY_PERMISSIONS_API_31_PLUS)
    
    logger.debug(f"Permisos requeridos para API {ANDROID_API_LEVEL}: {permissions}")
    return permissions


# Mantener compatibilidad con código existente
FISCALBERRY_PERMISSIONS = get_required_permissions()


def is_permission_supported(permission):
    """
    Verifica si un permiso es soportado en la versión actual de Android.
    
    Args:
        permission (str): Nombre del permiso
        
    Returns:
        bool: True si el permiso es soportado
    """
    if not ANDROID:
        return True  # En desarrollo, asumimos que sí
    
    # Permisos que requieren API específica
    api_requirements = {
        'android.permission.FOREGROUND_SERVICE': 28,
        'android.permission.BLUETOOTH_CONNECT': 31,
        'android.permission.BLUETOOTH_SCAN': 31,
        'android.permission.ACCESS_COARSE_LOCATION': 23,
    }
    
    required_api = api_requirements.get(permission, 1)  # API 1 por defecto
    supported = ANDROID_API_LEVEL >= required_api
    
    if not supported:
        logger.debug(f"Permiso {permission} requiere API {required_api}, actual: {ANDROID_API_LEVEL}")
    
    return supported


def check_all_permissions():
    """
    Verifica si todos los permisos necesarios están otorgados.
    
    Returns:
        dict: Diccionario con el estado de cada permiso
    """
    if not ANDROID:
        return {'all_granted': True, 'details': {}}
    
    try:
        required_permissions = get_required_permissions()
        results = {}
        all_granted = True
        
        for permission in required_permissions:
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
            'details': results,
            'api_level': ANDROID_API_LEVEL,
            'total_permissions': len(required_permissions)
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
        logger.info(f"Solicitando permisos de Android para API {ANDROID_API_LEVEL}...")
        required_permissions = get_required_permissions()
        
        # Filtrar solo los permisos que no están otorgados
        missing_permissions = []
        for permission in required_permissions:
            try:
                if not check_permission(permission):
                    missing_permissions.append(permission)
                    logger.info(f"Permiso faltante: {permission}")
            except:
                missing_permissions.append(permission)
        
        if missing_permissions:
            logger.info(f"Solicitando {len(missing_permissions)} permisos faltantes...")
            
            # Método 1: Usar request_permissions de python-for-android
            try:
                logger.info("Intentando solicitar permisos con request_permissions()...")
                request_permissions(missing_permissions)
                logger.info("✓ request_permissions() ejecutado")
            except Exception as e1:
                logger.warning(f"request_permissions() falló: {e1}")
                
                # Método 2: Usar ActivityCompat directamente
                try:
                    logger.info("Intentando con ActivityCompat...")
                    _request_permissions_via_activity_compat(missing_permissions)
                except Exception as e2:
                    logger.error(f"ActivityCompat también falló: {e2}")
            
            return True
        else:
            logger.info("Todos los permisos ya están otorgados")
            return True
            
    except Exception as e:
        logger.error(f"Error solicitando permisos: {e}", exc_info=True)
        return False


def _request_permissions_via_activity_compat(permissions):
    """
    Solicita permisos usando ActivityCompat directamente (método alternativo).
    Esto es necesario en Android 12+ para Bluetooth.
    """
    try:
        from jnius import autoclass
        
        # Obtener la actividad actual
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        
        if not activity:
            logger.error("No se pudo obtener PythonActivity")
            return
        
        logger.info(f"Activity obtenida: {activity}")
        
        # Usar ActivityCompat para solicitar permisos
        ActivityCompat = autoclass('androidx.core.app.ActivityCompat')
        
        # Convertir lista Python a array Java
        String = autoclass('java.lang.String')
        permissions_array = [String(p) for p in permissions]
        
        logger.info(f"Solicitando {len(permissions_array)} permisos vía ActivityCompat...")
        
        # Request code arbitrario
        REQUEST_CODE = 1001
        
        # Solicitar permisos
        ActivityCompat.requestPermissions(
            activity,
            permissions_array,
            REQUEST_CODE
        )
        
        logger.info("✓ ActivityCompat.requestPermissions() ejecutado")
        logger.info("⚠️ El usuario debe aprobar los permisos en el diálogo que apareció")
        
    except Exception as e:
        logger.error(f"Error en _request_permissions_via_activity_compat: {e}", exc_info=True)


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
    """
    Solicita permisos de Bluetooth (para impresoras BT).
    CRÍTICO: Android 12+ requiere BLUETOOTH_CONNECT y BLUETOOTH_SCAN.
    """
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
            logger.info(f"⚠️ Solicitando {len(missing)} permisos de Bluetooth...")
            logger.info("Lista de permisos faltantes:")
            for p in missing:
                logger.info(f"  - {p}")
            
            # Intentar ambos métodos
            try:
                request_permissions(missing)
                logger.info("✓ request_permissions() ejecutado para Bluetooth")
            except Exception as e:
                logger.warning(f"request_permissions() falló: {e}")
                try:
                    _request_permissions_via_activity_compat(missing)
                except Exception as e2:
                    logger.error(f"ActivityCompat también falló: {e2}")
        else:
            logger.info("✓ Todos los permisos de Bluetooth ya otorgados")
            
        return True
    except Exception as e:
        logger.error(f"Error solicitando permisos de Bluetooth: {e}", exc_info=True)
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
