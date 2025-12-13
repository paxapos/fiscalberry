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
    
    Configura Android (notificación, battery exemption) y luego
    delega a fiscalberry_cli.main.
    """
    logger.critical("="*70)
    logger.critical("FISCALBERRY CLI ANDROID SERVICE - STARTING")
    logger.critical("="*70)
    logger.info(f"PID: {os.getpid()}")
    logger.info(f"API Level: {ANDROID_API_LEVEL}")
    
    # 1. Mostrar notificación foreground (CRÍTICO - antes que nada)
    show_foreground_notification()
    
    # 2. Solicitar battery exemption
    request_battery_exemption()
    
    # 3. Delegar a CLI main
    logger.info("Delegando a fiscalberry_cli.main...")
    
    try:
        from fiscalberry.android.headless.main import main
        main()  # Blocking call - retorna solo cuando se detiene
    except Exception as e:
        logger.critical(f"CLI main crashed: {type(e).__name__}: {e}", exc_info=True)
        raise  # Re-raise para que crash reporter lo capture
    
    logger.critical("="*70)
    logger.critical("FISCALBERRY CLI ANDROID SERVICE - STOPPED")
    logger.critical("="*70)


if __name__ == "__main__":
    run_service()
