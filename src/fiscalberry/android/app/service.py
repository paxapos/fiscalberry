#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Servicio Android para Fiscalberry (UI Version)

Permite que RabbitMQ y SocketIO funcionen en segundo plano
incluso cuando la app no está en primer plano.

Ubicación: fiscalberry/android/app/service.py
"""

from time import sleep
import os
import sys

from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("AndroidService")

from fiscalberry.common.service_controller import ServiceController
from fiscalberry.common.Configberry import Configberry

# Android APIs usando jnius
ANDROID_API_LEVEL = 0
ANDROID_AVAILABLE = False

try:
    from jnius import autoclass
    
    BuildVERSION = autoclass('android.os.Build$VERSION')
    ANDROID_API_LEVEL = BuildVERSION.SDK_INT
    
    PythonService = autoclass('org.kivy.android.PythonService')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Context = autoclass('android.content.Context')
    NotificationBuilder = autoclass('android.app.Notification$Builder')
    NotificationManager = autoclass('android.app.NotificationManager')
    PendingIntent = autoclass('android.app.PendingIntent')
    Intent = autoclass('android.content.Intent')
    String = autoclass('java.lang.String')
    
    if ANDROID_API_LEVEL >= 26:
        NotificationChannel = autoclass('android.app.NotificationChannel')
    else:
        NotificationChannel = None
    
    from jnius import cast
    
    ANDROID_AVAILABLE = True
    logger.info(f"APIs de Android disponibles - API Level: {ANDROID_API_LEVEL}")
except ImportError:
    ANDROID_AVAILABLE = False
    logger.warning("jnius no disponible - APIs de Android no estarán disponibles")


def request_battery_exemption():
    """Solicita exclusión de optimización de batería."""
    if not ANDROID_AVAILABLE or ANDROID_API_LEVEL < 23:
        return
    
    try:
        from jnius import autoclass, cast
        
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Settings = autoclass('android.provider.Settings')
        PowerManager = autoclass('android.os.PowerManager')
        Intent = autoclass('android.content.Intent')
        Uri = autoclass('android.net.Uri')
        Context = autoclass('android.content.Context')
        
        activity = PythonActivity.mActivity
        
        if activity is None:
            logger.debug("mActivity es None - normal en servicio")
            return
            
        package_name = activity.getPackageName()
        power_manager = activity.getSystemService(Context.POWER_SERVICE)
        power_manager = cast(PowerManager, power_manager)
        
        if not power_manager.isIgnoringBatteryOptimizations(package_name):
            logger.warning("App NO excluida de optimización de batería")
            intent = Intent()
            intent.setAction(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            intent.setData(Uri.parse(f"package:{package_name}"))
            activity.startActivity(intent)
            logger.info("Solicitud de exclusión enviada al usuario")
        else:
            logger.info("✅ App ya excluida de optimización de batería")
            
    except Exception as e:
        logger.error(f"Error solicitando exclusión de batería: {e}")


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
            logger.warning("WakeLock: mService no disponible")
            return None
        
        pm = service.getSystemService(Context.POWER_SERVICE)
        pm = cast(PowerManager, pm)
        
        _wakelock = pm.newWakeLock(1, "Fiscalberry:ServiceWakeLock")
        _wakelock.acquire()
        
        logger.critical("🔒 WAKELOCK ADQUIRIDO - CPU activa")
        return _wakelock
        
    except Exception as e:
        logger.error(f"Error adquiriendo WakeLock: {e}")
        return None


def acquire_wifi_lock():
    """Adquiere WiFi Lock en modo HIGH PERFORMANCE."""
    global _wifi_lock
    
    if not ANDROID_AVAILABLE:
        return None
    
    try:
        from jnius import autoclass, cast
        WifiManager = autoclass('android.net.wifi.WifiManager')
        
        service = PythonService.mService
        if not service:
            logger.warning("WiFiLock: mService no disponible")
            return None
        
        wm = service.getSystemService(Context.WIFI_SERVICE)
        wm = cast(WifiManager, wm)
        
        wifi_mode = 4 if ANDROID_API_LEVEL >= 29 else 3
        mode_name = "LOW_LATENCY" if ANDROID_API_LEVEL >= 29 else "HIGH_PERF"
        
        _wifi_lock = wm.createWifiLock(wifi_mode, "Fiscalberry:ServiceWifiLock")
        _wifi_lock.acquire()
        
        logger.critical(f"📶 WIFI_LOCK ADQUIRIDO ({mode_name})")
        return _wifi_lock
        
    except Exception as e:
        logger.error(f"Error adquiriendo WiFi Lock: {e}")
        return None


def release_hardware_locks():
    """Libera WakeLock y WiFiLock."""
    global _wakelock, _wifi_lock
    
    released = []
    
    try:
        if _wakelock is not None and _wakelock.isHeld():
            _wakelock.release()
            released.append("WakeLock")
            _wakelock = None
    except Exception as e:
        logger.error(f"Error liberando WakeLock: {e}")
    
    try:
        if _wifi_lock is not None and _wifi_lock.isHeld():
            _wifi_lock.release()
            released.append("WiFiLock")
            _wifi_lock = None
    except Exception as e:
        logger.error(f"Error liberando WiFiLock: {e}")
    
    if released:
        logger.info(f"🔓 Hardware locks liberados: {', '.join(released)}")


service_controller = None


def create_notification_channel():
    """Crea un canal de notificación para Android 8.0+ (API 26+)."""
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
    except Exception as e:
        logger.error(f"Error creando canal de notificación: {e}")
    
    return "fiscalberry_service"


def show_foreground_notification():
    """Muestra una notificación permanente para servicio en primer plano."""
    if not ANDROID_AVAILABLE:
        return
    
    try:
        service = PythonService.mService
        if not service:
            logger.warning("mService no disponible para notificación")
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
            except Exception:
                service.startForeground(1, notification)
        else:
            service.startForeground(1, notification)
        
        logger.info(f"Foreground notification mostrada (API {ANDROID_API_LEVEL})")
        
    except Exception as e:
        logger.error(f"Error mostrando notificación: {e}")


def run_service_logic():
    """Lógica principal del servicio en segundo plano."""
    global service_controller
    
    logger.info("=== Iniciando Servicio Android de Fiscalberry ===")
    
    # PASO 1: Mostrar notificación de servicio en primer plano
    show_foreground_notification()
    
    # PASO 2: Adquirir Hardware Locks
    acquire_wakelock()
    acquire_wifi_lock()
    
    # Inicializar configuración
    try:
        configberry = Configberry()
        request_battery_exemption()
        
        if not configberry.is_comercio_adoptado():
            logger.warning("Comercio no adoptado - esperando adopción...")
            while True:
                sleep(30)
                if configberry.is_comercio_adoptado():
                    logger.info("Comercio adoptado! Iniciando servicios...")
                    break
        
        # Iniciar ServiceController (RabbitMQ, SocketIO)
        logger.info("Iniciando ServiceController...")
        service_controller = ServiceController()
        service_controller.start()
        
        # Mantener el servicio corriendo
        logger.info("Servicio en ejecución...")
        while True:
            sleep(60)
            
    except KeyboardInterrupt:
        logger.info("Servicio interrumpido")
    except Exception as e:
        logger.error(f"Error en servicio: {e}", exc_info=True)
    finally:
        if service_controller:
            try:
                service_controller.stop()
            except Exception as e:
                logger.error(f"Error deteniendo ServiceController: {e}")
        
        release_hardware_locks()
        logger.info("=== Servicio Android de Fiscalberry finalizado ===")


if __name__ == "__main__":
    run_service_logic()