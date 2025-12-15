#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Servicio Android para Fiscalberry (UI Version)

Permite que RabbitMQ y SocketIO funcionen en segundo plano
incluso cuando la app no está en primer plano.

Ubicación: fiscalberry/android/ui/service.py
"""

from time import sleep
import os
import sys


from fiscalberry.common.fiscalberry_logger import getLogger
logger = getLogger("AndroidService")

# Importar componentes de Fiscalberry
from fiscalberry.common.service_controller import ServiceController
from fiscalberry.common.Configberry import Configberry

# Android APIs usando jnius
ANDROID_API_LEVEL = 0
try:
    from jnius import autoclass
    
    # Obtener el nivel de API actual
    Build = autoclass('android.os.Build')
    ANDROID_API_LEVEL = Build.VERSION.SDK_INT
    
    PythonService = autoclass('org.kivy.android.PythonService')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Context = autoclass('android.content.Context')
    NotificationBuilder = autoclass('android.app.Notification$Builder')
    NotificationManager = autoclass('android.app.NotificationManager')
    PendingIntent = autoclass('android.app.PendingIntent')
    Intent = autoclass('android.content.Intent')
    String = autoclass('java.lang.String')
    
    # NotificationChannel solo disponible en API 26+
    if ANDROID_API_LEVEL >= 26:
        NotificationChannel = autoclass('android.app.NotificationChannel')
    else:
        NotificationChannel = None
    
    from jnius import cast  # Para hacer cast de tipos Java
    
    ANDROID_AVAILABLE = True
    logger.info(f"APIs de Android disponibles - API Level: {ANDROID_API_LEVEL}")
except ImportError:
    ANDROID_AVAILABLE = False
    logger.warning("jnius no disponible - APIs de Android no estarán disponibles")


def request_battery_exemption():
    """
    Solicita exclusión de optimización de batería si no está ya excluida.
    
    POR QUÉ: Doze mode mata servicios en background después de 30 min.
    La exclusión permite que el service corra 24/7 sin interrupciones.
    """
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
        package_name = activity.getPackageName()
        
        power_manager = activity.getSystemService(Context.POWER_SERVICE)
        power_manager = cast(PowerManager, power_manager)
        
        if not power_manager.isIgnoringBatteryOptimizations(package_name):
            logger.warning("⚠️  App NO excluida de optimización de batería")
            
            intent = Intent()
            intent.setAction(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            intent.setData(Uri.parse(f"package:{package_name}"))
            activity.startActivity(intent)
            
            logger.info("✅ Solicitud de exclusión enviada al usuario")
        else:
            logger.info("✅ App ya excluida de optimización de batería")
            
    except Exception as e:
        logger.error(f"Error solicitando exclusión de batería: {e}", exc_info=True)


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
    
    PARTIAL_WAKE_LOCK (flag=1): CPU activa, pantalla puede apagarse.
    acquire() sin timeout: Mantiene el lock indefinidamente.
    """
    global _wakelock
    
    if not ANDROID_AVAILABLE:
        logger.debug("WakeLock: No Android, omitiendo")
        return None
    
    try:
        from jnius import autoclass, cast
        
        PowerManager = autoclass('android.os.PowerManager')
        service = PythonService.mService
        
        if not service:
            logger.warning("WakeLock: PythonService.mService no disponible")
            return None
        
        pm = service.getSystemService(Context.POWER_SERVICE)
        pm = cast(PowerManager, pm)
        
        # PARTIAL_WAKE_LOCK = 1
        # Tag para identificar en debug: "Fiscalberry:ServiceWakeLock"
        _wakelock = pm.newWakeLock(1, "Fiscalberry:ServiceWakeLock")
        
        # acquire() sin timeout = lock permanente hasta release()
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
    
    WIFI_MODE_FULL_HIGH_PERF (flag=3): WiFi a máxima potencia, sin PSM.
    WIFI_MODE_FULL_LOW_LATENCY (flag=4): API 29+, latencia mínima.
    """
    global _wifi_lock
    
    if not ANDROID_AVAILABLE:
        logger.debug("WiFiLock: No Android, omitiendo")
        return None
    
    try:
        from jnius import autoclass, cast
        
        WifiManager = autoclass('android.net.wifi.WifiManager')
        service = PythonService.mService
        
        if not service:
            logger.warning("WiFiLock: PythonService.mService no disponible")
            return None
        
        wm = service.getSystemService(Context.WIFI_SERVICE)
        wm = cast(WifiManager, wm)
        
        # Elegir modo según API level
        # WIFI_MODE_FULL_HIGH_PERF = 3 (API 12+)
        # WIFI_MODE_FULL_LOW_LATENCY = 4 (API 29+)
        if ANDROID_API_LEVEL >= 29:
            wifi_mode = 4  # WIFI_MODE_FULL_LOW_LATENCY
            mode_name = "LOW_LATENCY"
        else:
            wifi_mode = 3  # WIFI_MODE_FULL_HIGH_PERF
            mode_name = "HIGH_PERF"
        
        _wifi_lock = wm.createWifiLock(wifi_mode, "Fiscalberry:ServiceWifiLock")
        
        # acquire() sin timeout = lock permanente hasta release()
        _wifi_lock.acquire()
        
        logger.critical(f"📶 WIFI_LOCK ADQUIRIDO ({mode_name}) - Radio WiFi a máxima potencia")
        return _wifi_lock
        
    except Exception as e:
        logger.error(f"Error adquiriendo WiFi Lock: {e}", exc_info=True)
        return None


def release_hardware_locks():
    """
    Libera WakeLock y WiFiLock.
    
    IMPORTANTE: Solo llamar en shutdown explícito de la app.
    Si se liberan mientras el servicio corre, Android dormirá el dispositivo.
    """
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


# Variable global para el controlador de servicios
service_controller = None


def create_notification_channel():
    """
    Crea un canal de notificación para Android 8.0+ (API 26+).
    Para versiones anteriores, esta función no hace nada ya que no se requieren canales.
    """
    if not ANDROID_AVAILABLE:
        return "fiscalberry_service"
    
    # Los canales de notificación solo son necesarios en API 26+
    if ANDROID_API_LEVEL < 26:
        logger.debug(f"API {ANDROID_API_LEVEL} < 26: No se requieren canales de notificación")
        return "fiscalberry_service"
    
    if not NotificationChannel:
        logger.warning("NotificationChannel no disponible")
        return "fiscalberry_service"
    
    try:
        service = PythonService.mService
        if service:
            channel_id = "fiscalberry_service"
            channel_name = "Fiscalberry Service"
            importance = NotificationManager.IMPORTANCE_LOW
            
            channel = NotificationChannel(channel_id, channel_name, importance)
            channel.setDescription("Servicio de impresión Fiscalberry")
            
            notification_service = service.getSystemService(Context.NOTIFICATION_SERVICE)
            notification_manager = cast(NotificationManager, notification_service)
            notification_manager.createNotificationChannel(channel)
            
            logger.info(f"Canal de notificación creado para API {ANDROID_API_LEVEL}")
            return channel_id
    except Exception as e:
        logger.error(f"Error creando canal de notificación: {e}")
    
    return "fiscalberry_service"


def show_foreground_notification():
    """
    Muestra una notificación permanente para servicio en primer plano.
    Funciona desde API 22 (Android 5.1.1) hasta API 35 (Android 16).
    """
    if not ANDROID_AVAILABLE:
        return
    
    try:
        service = PythonService.mService
        if not service:
            logger.warning("PythonService.mService no disponible")
            return
        
        # Crear canal de notificación (solo para API 26+)
        channel_id = create_notification_channel()
        
        # Crear intent para abrir la app al tocar la notificación
        intent = Intent(service, PythonActivity)
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK)
        
        # PendingIntent con flags apropiados según la versión de API
        if ANDROID_API_LEVEL >= 23:  # API 23+
            pending_intent_flags = PendingIntent.FLAG_IMMUTABLE
        else:  # API 22
            pending_intent_flags = PendingIntent.FLAG_UPDATE_CURRENT
            
        pending_intent = PendingIntent.getActivity(service, 0, intent, pending_intent_flags)
        
        # Crear notificación según la versión de API
        if ANDROID_API_LEVEL >= 26:  # API 26+ (Android 8.0+) - Usar canal
            builder = NotificationBuilder(service, channel_id)
        else:  # API 22-25 (Android 5.1.1 - 7.1) - Sin canal
            builder = NotificationBuilder(service)
            
        builder.setContentTitle("Fiscalberry Activo")
        builder.setContentText("Sistema de impresión fiscal en ejecución")
        builder.setSmallIcon(service.getApplicationInfo().icon)
        builder.setContentIntent(pending_intent)
        builder.setOngoing(True)  # No se puede quitar deslizando
        
        # Para API 22-25, establecer prioridad manualmente
        if ANDROID_API_LEVEL < 26:
            builder.setPriority(NotificationBuilder.PRIORITY_LOW)
        
        notification = builder.build()
        
        # Mostrar como servicio en primer plano
        service.startForeground(1, notification)
        logger.info(f"Notificación de servicio en primer plano mostrada (API {ANDROID_API_LEVEL})")
        
    except Exception as e:
        logger.error(f"Error mostrando notificación: {e}", exc_info=True)


def run_service_logic():
    """Lógica principal del servicio en segundo plano"""
    global service_controller
    
    logger.info("=== Iniciando Servicio Android de Fiscalberry ===")
    
    # PASO 1: Mostrar notificación de servicio en primer plano
    show_foreground_notification()
    
    # PASO 2: Adquirir Hardware Locks ANTES de cualquier otra cosa
    # Esto garantiza que CPU y WiFi estén activos para RabbitMQ/SocketIO
    logger.info("Adquiriendo hardware locks...")
    acquire_wakelock()
    acquire_wifi_lock()
    
    # Obtener argumento de inicio del servicio (opcional)
    service_argument = os.environ.get('PYTHON_SERVICE_ARGUMENT', 'default')
    logger.info(f"Argumento del servicio: {service_argument}")
    
    # Inicializar configuración
    try:
        configberry = Configberry()
        logger.info("Configberry inicializado")
        
        # Solicitar exclusión de optimización de batería (Android 6.0+)
        # NOTA: Esto puede fallar si no hay Activity, pero los locks ya están activos
        request_battery_exemption()
        
        if not configberry.is_comercio_adoptado():
            logger.warning("Comercio no adoptado - servicio esperará adopción")
            # En un servicio, no podemos mostrar UI, solo esperar o detener
            # Por ahora, el servicio seguirá corriendo pero sin hacer nada
            while True:
                sleep(30)
                if configberry.is_comercio_adoptado():
                    logger.info("Comercio adoptado! Iniciando servicios...")
                    break
        
        # Iniciar controlador de servicios (RabbitMQ, SocketIO)
        logger.info("Iniciando ServiceController...")
        service_controller = ServiceController()
        service_controller.start()
        logger.info("ServiceController iniciado exitosamente")
        
        # Mantener el servicio corriendo
        logger.info("Servicio en ejecución - esperando trabajos de impresión...")
        while True:
            sleep(60)  # Verificar cada minuto que todo sigue funcionando
            # El ServiceController maneja RabbitMQ y SocketIO en sus propios threads
            
    except KeyboardInterrupt:
        logger.info("Servicio interrumpido por usuario")
    except Exception as e:
        logger.error(f"Error en servicio: {e}", exc_info=True)
    finally:
        # Limpiar recursos
        if service_controller:
            try:
                logger.info("Deteniendo ServiceController...")
                service_controller.stop()
                logger.info("ServiceController detenido")
            except Exception as e:
                logger.error(f"Error al detener ServiceController: {e}")
        
        # Liberar hardware locks al final
        release_hardware_locks()
        
        logger.info("=== Servicio Android de Fiscalberry finalizado ===")


if __name__ == "__main__":
    """
    Este bloque se ejecuta cuando el servicio es iniciado por Android.
    
    Para iniciar este servicio desde la app principal de Kivy:
    
    ```python
    from android import AndroidService
    service = AndroidService('Fiscalberry Service', 'running')
    service.start('service started')
    ```
    
    O usando jnius directamente:
    
    ```python
    from jnius import autoclass
    PythonService = autoclass('org.kivy.android.PythonService')
    PythonService.start(mActivity, '')
    ```
    """
    run_service_logic()
#     service_class_name = f'{activity.getPackageName()}.Service{service_name}'
#
#     intent = Intent()
#     intent.setClassName(activity, service_class_name)
#
#     # Pass data to the service (optional)
#     argument = "Data for the service"
#     intent.putExtra('PYTHON_SERVICE_ARGUMENT', argument)
#     os.environ['PYTHON_SERVICE_ARGUMENT'] = argument # Set env var too
#
#     activity.startService(intent)
#     ```
# 4.  **Permissions:** Add necessary permissions to `buildozer.spec`:
#     ```
#     android.permissions = INTERNET, FOREGROUND_SERVICE, ...
#     ```
#     `FOREGROUND_SERVICE` is often required for long-running tasks on newer Android versions.
# 5.  **Foreground Service:** For long-running tasks, consider running as a foreground service
#     to prevent Android from killing it. This requires showing a persistent notification.
#     You'll need more jnius code to create the notification channel and notification itself.