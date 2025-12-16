#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Servicio Android para Fiscalberry

Permite que RabbitMQ y SocketIO funcionen en segundo plano
incluso cuando la app no está en primer plano.
"""

from time import sleep
import os
import sys

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("AndroidService")

from fiscalberry.common.service_controller import ServiceController
from fiscalberry.common.Configberry import Configberry

# Android APIs
ANDROID_API_LEVEL = 0
ANDROID_AVAILABLE = False

try:
    from jnius import autoclass, cast
    
    BuildVERSION = autoclass('android.os.Build$VERSION')
    ANDROID_API_LEVEL = BuildVERSION.SDK_INT
    
    PythonService = autoclass('org.kivy.android.PythonService')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Context = autoclass('android.content.Context')
    NotificationBuilder = autoclass('android.app.Notification$Builder')
    NotificationManager = autoclass('android.app.NotificationManager')
    PendingIntent = autoclass('android.app.PendingIntent')
    Intent = autoclass('android.content.Intent')
    
    if ANDROID_API_LEVEL >= 26:
        NotificationChannel = autoclass('android.app.NotificationChannel')
    else:
        NotificationChannel = None
    
    ANDROID_AVAILABLE = True
except ImportError:
    ANDROID_AVAILABLE = False


# Variables globales para hardware locks
_wakelock = None
_wifi_lock = None


def acquire_wakelock():
    """Adquiere PARTIAL_WAKE_LOCK para mantener la CPU activa."""
    global _wakelock
    
    if not ANDROID_AVAILABLE:
        return None
    
    try:
        from jnius import autoclass, cast
        PowerManager = autoclass('android.os.PowerManager')
        
        service = PythonService.mService
        if not service:
            return None
        
        pm = service.getSystemService(Context.POWER_SERVICE)
        pm = cast(PowerManager, pm)
        
        _wakelock = pm.newWakeLock(1, "Fiscalberry:ServiceWakeLock")
        _wakelock.acquire()
        return _wakelock
        
    except Exception as e:
        logger.error(f"Error WakeLock: {e}")
        return None


def acquire_wifi_lock():
    """Adquiere WiFi Lock."""
    global _wifi_lock
    
    if not ANDROID_AVAILABLE:
        return None
    
    try:
        from jnius import autoclass, cast
        WifiManager = autoclass('android.net.wifi.WifiManager')
        
        service = PythonService.mService
        if not service:
            return None
        
        wm = service.getSystemService(Context.WIFI_SERVICE)
        wm = cast(WifiManager, wm)
        
        wifi_mode = 4 if ANDROID_API_LEVEL >= 29 else 3
        _wifi_lock = wm.createWifiLock(wifi_mode, "Fiscalberry:ServiceWifiLock")
        _wifi_lock.acquire()
        return _wifi_lock
        
    except Exception as e:
        logger.error(f"Error WiFiLock: {e}")
        return None


def release_hardware_locks():
    """Libera WakeLock y WiFiLock."""
    global _wakelock, _wifi_lock
    
    try:
        if _wakelock is not None and _wakelock.isHeld():
            _wakelock.release()
            _wakelock = None
    except:
        pass
    
    try:
        if _wifi_lock is not None and _wifi_lock.isHeld():
            _wifi_lock.release()
            _wifi_lock = None
    except:
        pass


def create_notification_channel():
    """Crea un canal de notificación para Android 8.0+."""
    if not ANDROID_AVAILABLE or ANDROID_API_LEVEL < 26 or not NotificationChannel:
        return "fiscalberry_service"
    
    try:
        service = PythonService.mService
        if service:
            channel_id = "fiscalberry_service"
            channel = NotificationChannel(channel_id, "Fiscalberry Service", NotificationManager.IMPORTANCE_LOW)
            channel.setDescription("Servicio de impresión Fiscalberry")
            
            notification_service = service.getSystemService(Context.NOTIFICATION_SERVICE)
            notification_manager = cast(NotificationManager, notification_service)
            notification_manager.createNotificationChannel(channel)
            return channel_id
    except:
        pass
    
    return "fiscalberry_service"


def show_foreground_notification():
    """Muestra notificación de servicio en primer plano."""
    if not ANDROID_AVAILABLE:
        return
    
    try:
        service = PythonService.mService
        if not service:
            return
        
        channel_id = create_notification_channel()
        
        intent = Intent(service, PythonActivity)
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK)
        
        pending_flags = PendingIntent.FLAG_IMMUTABLE if ANDROID_API_LEVEL >= 23 else PendingIntent.FLAG_UPDATE_CURRENT
        pending_intent = PendingIntent.getActivity(service, 0, intent, pending_flags)
        
        if ANDROID_API_LEVEL >= 26:
            builder = NotificationBuilder(service, channel_id)
        else:
            builder = NotificationBuilder(service)
            builder.setPriority(NotificationBuilder.PRIORITY_LOW)
            
        builder.setContentTitle("Fiscalberry Activo")
        builder.setContentText("Sistema de impresión fiscal en ejecución")
        builder.setSmallIcon(service.getApplicationInfo().icon)
        builder.setContentIntent(pending_intent)
        builder.setOngoing(True)
        
        notification = builder.build()
        
        if ANDROID_API_LEVEL >= 34:
            try:
                ServiceInfo = autoclass('android.content.pm.ServiceInfo')
                foreground_types = (
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC | 
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
                )
                service.startForeground(1, notification, foreground_types)
            except:
                service.startForeground(1, notification)
        else:
            service.startForeground(1, notification)
            
    except Exception as e:
        logger.error(f"Error notificación: {e}")


service_controller = None


def run_service_logic():
    """Lógica principal del servicio en segundo plano."""
    global service_controller
    
    logger.info("=== Iniciando Fiscalberry Android Service ===")
    logger.info(f"API Level: {ANDROID_API_LEVEL}")
    
    # Mostrar notificación
    show_foreground_notification()
    
    # Adquirir locks
    if acquire_wakelock():
        logger.info("WakeLock adquirido")
    if acquire_wifi_lock():
        logger.info("WiFiLock adquirido")
    
    try:
        configberry = Configberry()
        
        # Esperar adopción si es necesario
        if not configberry.is_comercio_adoptado():
            logger.info("Comercio no adoptado. Esperando adopción...")
            while True:
                sleep(30)
                if configberry.is_comercio_adoptado():
                    logger.info("Comercio adoptado exitosamente")
                    break
        
        # Iniciar servicios
        logger.info("Comercio adoptado. Iniciando servicios...")
        service_controller = ServiceController()
        
        logger.info("Iniciando controlador de servicios...")
        service_controller.start()
        logger.info("Controlador de servicios iniciado exitosamente")
        
        # Mantener servicio activo
        while True:
            sleep(60)
            
    except KeyboardInterrupt:
        logger.info("Interrupción detectada")
    except Exception as e:
        logger.error(f"Error en servicio: {e}", exc_info=True)
    finally:
        if service_controller:
            try:
                service_controller.stop()
                logger.info("Servicios detenidos correctamente")
            except Exception as e:
                logger.error(f"Error al detener: {e}")
        
        release_hardware_locks()
        logger.info("=== Finalizando Fiscalberry Android Service ===")


if __name__ == "__main__":
    run_service_logic()