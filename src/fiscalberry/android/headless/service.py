#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Android Service Entry Point - Fiscalberry CLI (Headless)

Entry point para el servicio Android foreground sin UI.
Integra con el sistema Android (notificaciones, battery exemption, etc.)
y delega la lógica real a fiscalberry.android.headless.main.

Ubicación: fiscalberry/android/headless/service.py
"""
import os
import sys
from time import sleep, monotonic


from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("Service.Android")

# Android APIs
ANDROID_API_LEVEL = 0
ANDROID_AVAILABLE = False

try:
    from jnius import autoclass, cast
    
    # Android classes
    Build = autoclass('android.os.Build')
    ANDROID_API_LEVEL = Build.VERSION.SDK_INT
    
    PythonService = autoclass('org.kivy.android.PythonService')
    Context = autoclass('android.content.Context')
    NotificationBuilder = autoclass('android.app.Notification$Builder')
    NotificationManager = autoclass('android.app.NotificationManager')
    PendingIntent = autoclass('android.app.PendingIntent')
    Intent = autoclass('android.content.Intent')
    
    # NotificationChannel (API 26+)
    if ANDROID_API_LEVEL >= 26:
        NotificationChannel = autoclass('android.app.NotificationChannel')
    else:
        NotificationChannel = None
    
    ANDROID_AVAILABLE = True
    logger.info(f"✓ Android APIs available - API Level: {ANDROID_API_LEVEL}")
    
except ImportError:
    logger.warning("jnius not available - running in non-Android mode")


def request_battery_exemption():
    """
    Solicita exclusión de optimización de batería (Android 6.0+).
    
    CRÍTICO para servicios 24/7 - sin esto, Doze mode matará el servicio.
    """
    if not ANDROID_AVAILABLE or ANDROID_API_LEVEL < 23:
        return
    
    try:
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Settings = autoclass('android.provider.Settings')
        PowerManager = autoclass('android.os.PowerManager')
        Uri = autoclass('android.net.Uri')
        
        activity = PythonActivity.mActivity
        package_name = activity.getPackageName()
        
        power_manager = activity.getSystemService(Context.POWER_SERVICE)
        power_manager = cast(PowerManager, power_manager)
        
        if not power_manager.isIgnoringBatteryOptimizations(package_name):
            logger.warning("⚠ App NO excluida de optimización de batería")
            
            intent = Intent()
            intent.setAction(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            intent.setData(Uri.parse(f"package:{package_name}"))
            activity.startActivity(intent)
            
            logger.info("✓ Solicitud de exclusión enviada")
        else:
            logger.info("✓ App ya excluida de optimización de batería")
            
    except Exception as e:
        logger.error(f"Error solicitando exclusión: {e}", exc_info=True)


# =============================================================================
# HARDWARE LOCKS - Mantener CPU y WiFi activos permanentemente
# =============================================================================

# Variables globales para los locks (para poder liberarlos en shutdown)
_wakelock = None
_wifi_lock = None


def acquire_wakelock():
    """
    Adquiere PARTIAL_WAKE_LOCK para mantener la CPU activa.
    
    CRÍTICO: Sin esto, la CPU entra en deep sleep cuando la pantalla se apaga,
    pausando todos los threads de Python incluyendo RabbitMQ y SocketIO.
    """
    global _wakelock
    
    if not ANDROID_AVAILABLE:
        return None
    
    try:
        PowerManager = autoclass('android.os.PowerManager')
        service = PythonService.mService
        
        if not service:
            logger.warning("WakeLock: PythonService.mService no disponible")
            return None
        
        pm = service.getSystemService(Context.POWER_SERVICE)
        pm = cast(PowerManager, pm)
        
        # PARTIAL_WAKE_LOCK = 1
        _wakelock = pm.newWakeLock(1, "FiscalberryCLI:WakeLock")
        _wakelock.acquire()
        
        logger.critical("🔒 WAKELOCK ADQUIRIDO - CPU forzada a mantenerse activa")
        return _wakelock
        
    except Exception as e:
        logger.error(f"Error adquiriendo WakeLock: {e}", exc_info=True)
        return None


def acquire_wifi_lock():
    """
    Adquiere WiFi Lock en modo HIGH PERFORMANCE.
    
    CRÍTICO: Sin esto, el radio WiFi entra en modo ahorro de energía,
    causando latencia alta y posibles desconexiones de RabbitMQ.
    """
    global _wifi_lock
    
    if not ANDROID_AVAILABLE:
        return None
    
    try:
        WifiManager = autoclass('android.net.wifi.WifiManager')
        service = PythonService.mService
        
        if not service:
            logger.warning("WiFiLock: PythonService.mService no disponible")
            return None
        
        wm = service.getSystemService(Context.WIFI_SERVICE)
        wm = cast(WifiManager, wm)
        
        # WIFI_MODE_FULL_HIGH_PERF = 3, WIFI_MODE_FULL_LOW_LATENCY = 4 (API 29+)
        wifi_mode = 4 if ANDROID_API_LEVEL >= 29 else 3
        mode_name = "LOW_LATENCY" if ANDROID_API_LEVEL >= 29 else "HIGH_PERF"
        
        _wifi_lock = wm.createWifiLock(wifi_mode, "FiscalberryCLI:WifiLock")
        _wifi_lock.acquire()
        
        logger.critical(f"📶 WIFI_LOCK ADQUIRIDO ({mode_name}) - Radio WiFi a máxima potencia")
        return _wifi_lock
        
    except Exception as e:
        logger.error(f"Error adquiriendo WiFi Lock: {e}", exc_info=True)
        return None


def release_hardware_locks():
    """Libera WakeLock y WiFiLock. Solo llamar en shutdown explícito."""
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


def create_notification_channel():
    """
    Crea canal de notificación para API 26+ (Android 8.0+).
    
    Returns:
        str: Channel ID
    """
    channel_id = "fiscalberry_cli"
    
    if not ANDROID_AVAILABLE or ANDROID_API_LEVEL < 26:
        return channel_id
    
    try:
        service = PythonService.mService
        if service:
            channel_name = "Fiscalberry CLI Service"
            importance = NotificationManager.IMPORTANCE_LOW
            
            channel = NotificationChannel(channel_id, channel_name, importance)
            channel.setDescription("Servicio de impresión fiscal (modo CLI)")
            
            notification_service = service.getSystemService(Context.NOTIFICATION_SERVICE)
            notification_manager = cast(NotificationManager, notification_service)
            notification_manager.createNotificationChannel(channel)
            
            logger.info(f"✓ Notification channel created (API {ANDROID_API_LEVEL})")
    except Exception as e:
        logger.error(f"Error creating notification channel: {e}")
    
    return channel_id


def show_foreground_notification():
    """
    Muestra notificación foreground.
    
    CRÍTICO: Sin foreground notification, Android matará el servicio rápidamente.
    """
    if not ANDROID_AVAILABLE:
        logger.info("No Android - skipping notification")
        return
    
    try:
        service = PythonService.mService
        if not service:
            logger.warning("PythonService.mService not available")
            return
        
        channel_id = create_notification_channel()
        
        # Crear intent dummy (no hay activity en CLI puro)
        intent = Intent()
        
        # PendingIntent flags según API level
        if ANDROID_API_LEVEL >= 23:
            pending_intent_flags = PendingIntent.FLAG_IMMUTABLE
        else:
            pending_intent_flags = PendingIntent.FLAG_UPDATE_CURRENT
        
        pending_intent = PendingIntent.getActivity(
            service, 0, intent, pending_intent_flags
        )
        
        # Builder según API level
        if ANDROID_API_LEVEL >= 26:
            builder = NotificationBuilder(service, channel_id)
        else:
            builder = NotificationBuilder(service)
        
        builder.setContentTitle("Fiscalberry CLI")
        builder.setContentText("Servicio de impresión activo (headless)")
        builder.setSmallIcon(service.getApplicationInfo().icon)
        builder.setContentIntent(pending_intent)
        builder.setOngoing(True)  # No dismissable
        
        if ANDROID_API_LEVEL < 26:
            builder.setPriority(NotificationBuilder.PRIORITY_LOW)
        
        notification = builder.build()
        service.startForeground(1, notification)
        
        logger.critical("✓ Foreground notification shown")
        
    except Exception as e:
        logger.critical(f"✗ Error showing notification: {e}", exc_info=True)
        raise  # Fail fast - sin notificación, Android matará el servicio


def run_service():
    """
    Lógica principal del servicio Android.
    
    Configura Android (notificación, hardware locks, battery exemption) y luego
    delega a fiscalberry_cli.main.
    """
    logger.critical("="*70)
    logger.critical("FISCALBERRY CLI ANDROID SERVICE - STARTING")
    logger.critical("="*70)
    logger.info(f"PID: {os.getpid()}")
    logger.info(f"API Level: {ANDROID_API_LEVEL}")
    
    # 1. Mostrar notificación foreground (CRÍTICO - antes que nada)
    show_foreground_notification()
    
    # 2. Adquirir Hardware Locks ANTES de cualquier otra cosa
    logger.info("Adquiriendo hardware locks...")
    acquire_wakelock()
    acquire_wifi_lock()
    
    # 3. Solicitar battery exemption (puede fallar sin Activity)
    request_battery_exemption()
    
    # 4. Delegar a CLI main, con retry + backoff.
    # Un servicio de impresión no puede morir por un error transitorio (red
    # caída al arrancar, config a medias): si el proceso Python termina, queda
    # la notificación "Fiscalberry Activo" sin nada corriendo detrás.
    logger.info("Delegando a fiscalberry_cli.main...")

    backoff = 5
    try:
        while True:
            started_at = monotonic()
            try:
                from fiscalberry.android.headless.main import main
                main()  # Blocking call - retorna solo cuando se detiene
                logger.warning("CLI main retornó inesperadamente")
            except Exception as e:
                logger.critical(f"CLI main crashed: {type(e).__name__}: {e}", exc_info=True)

            if monotonic() - started_at > 600:
                backoff = 5
            logger.warning(f"Reiniciando servicios en {backoff}s...")
            sleep(backoff)
            backoff = min(backoff * 2, 300)
    finally:
        # Liberar hardware locks al salir
        release_hardware_locks()


    logger.critical("="*70)
    logger.critical("FISCALBERRY CLI ANDROID SERVICE - STOPPED")
    logger.critical("="*70)


if __name__ == "__main__":
    run_service()

