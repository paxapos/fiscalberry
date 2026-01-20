#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pantalla de gestión de permisos de Android
Muestra el estado de permisos y permite solicitarlos
"""

from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty, BooleanProperty, ListProperty, NumericProperty
from kivy.clock import Clock
from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("UI.PermissionsScreen")


class PermissionsScreen(Screen):
    """Pantalla que gestiona los permisos de Android"""
    
    # Propiedades para el estado de permisos
    permissions_granted = BooleanProperty(False)
    permissions_message = StringProperty("Verificando permisos...")
    missing_count = NumericProperty(0)
    total_count = NumericProperty(0)
    missing_permissions = ListProperty([])
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.debug("Inicializando PermissionsScreen")
        self._is_android = self._detect_android()
        
    def _detect_android(self):
        """Detecta si estamos en Android"""
        try:
            from jnius import autoclass
            return True
        except ImportError:
            return False
    
    def on_enter(self):
        """Se llama cuando se entra a la pantalla"""
        logger.debug("Entrando a PermissionsScreen")
        if self._is_android:
            self.check_permissions_status()
        else:
            self.permissions_granted = True
            self.permissions_message = "Plataforma de escritorio - No se requieren permisos"
    
    def check_permissions_status(self):
        """Verifica el estado actual de los permisos"""
        if not self._is_android:
            self.permissions_granted = True
            return
        
        try:
            from fiscalberry.common.android_permissions import check_all_permissions
            
            logger.debug("Verificando estado de permisos...")
            status = check_all_permissions()
            
            self.permissions_granted = status.get('all_granted', False)
            self.missing_count = status.get('missing_count', 0)
            self.total_count = status.get('total_permissions', 0)
            self.missing_permissions = status.get('missing', [])
            
            if self.permissions_granted:
                self.permissions_message = f"✅ Todos los permisos otorgados ({self.total_count}/{self.total_count})"
            else:
                self.permissions_message = f"⚠️ Faltan {self.missing_count} de {self.total_count} permisos"
                logger.warning(f"Permisos faltantes: {self.missing_permissions}")
                
        except Exception as e:
            logger.error(f"Error verificando permisos: {e}", exc_info=True)
            self.permissions_granted = False
            self.permissions_message = f"Error verificando permisos: {str(e)}"
    
    def request_all_permissions(self):
        """Solicita todos los permisos necesarios"""
        if not self._is_android:
            return
        
        try:
            from fiscalberry.common.android_permissions import request_all_permissions
            
            logger.debug("Solicitando todos los permisos...")
            self.permissions_message = "Solicitando permisos..."
            
            # Solicitar permisos con callback
            request_all_permissions(callback_on_complete=self._on_permissions_requested)
            
        except Exception as e:
            logger.error(f"Error solicitando permisos: {e}", exc_info=True)
            self.permissions_message = f"Error: {str(e)}"
    
    def _on_permissions_requested(self, success):
        """Callback cuando se completa la solicitud de permisos"""
        logger.debug(f"Solicitud de permisos completada: {success}")
        
        # Esperar un poco y verificar de nuevo
        Clock.schedule_once(lambda dt: self.check_permissions_status(), 1)
    
    def open_app_settings(self):
        """Abre la configuración de la app en Android"""
        if not self._is_android:
            return
        
        try:
            from jnius import autoclass
            
            logger.debug("Abriendo configuración de la app...")
            
            # Obtener contexto de la actividad
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            Settings = autoclass('android.provider.Settings')
            Uri = autoclass('android.net.Uri')
            
            activity = PythonActivity.mActivity
            
            # Crear intent para abrir configuración de la app
            intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
            uri = Uri.fromParts("package", activity.getPackageName(), None)
            intent.setData(uri)
            
            activity.startActivity(intent)
            
        except Exception as e:
            logger.error(f"Error abriendo configuración: {e}", exc_info=True)
            self.permissions_message = f"Error abriendo configuración: {str(e)}"
    
    def continue_anyway(self):
        """Continúa a la aplicación aunque falten permisos"""
        logger.warning("Usuario decide continuar sin todos los permisos")
        
        # Verificar qué pantalla seguir
        try:
            from fiscalberry.common.Configberry import Configberry
            configberry = Configberry()
            
            if configberry.is_comercio_adoptado():
                self.manager.current = 'main'
            else:
                self.manager.current = 'adopt'
                
        except Exception as e:
            logger.error(f"Error determinando siguiente pantalla: {e}")
            self.manager.current = 'adopt'
    
    def get_permission_display_name(self, permission):
        """Convierte nombre técnico de permiso a nombre amigable"""
        permission_names = {
            'BLUETOOTH': 'Bluetooth',
            'BLUETOOTH_ADMIN': 'Administración Bluetooth',
            'BLUETOOTH_CONNECT': 'Conexión Bluetooth',
            'BLUETOOTH_SCAN': 'Escaneo Bluetooth',
            'INTERNET': 'Internet',
            'ACCESS_NETWORK_STATE': 'Estado de Red',
            'ACCESS_WIFI_STATE': 'Estado WiFi',
            'ACCESS_COARSE_LOCATION': 'Ubicación Aproximada',
            'ACCESS_FINE_LOCATION': 'Ubicación Precisa',
            'ACCESS_BACKGROUND_LOCATION': 'Ubicación en Segundo Plano',
            'READ_EXTERNAL_STORAGE': 'Lectura Almacenamiento',
            'WRITE_EXTERNAL_STORAGE': 'Escritura Almacenamiento',
            'WAKE_LOCK': 'Mantener Despierto',
            'FOREGROUND_SERVICE': 'Servicio en Primer Plano',
            'POST_NOTIFICATIONS': 'Notificaciones',
            'SCHEDULE_EXACT_ALARM': 'Alarmas Exactas',
            'USE_EXACT_ALARM': 'Usar Alarmas Exactas',
        }
        
        # Extraer el nombre corto del permiso
        perm_name = permission.split('.')[-1]
        return permission_names.get(perm_name, perm_name)
