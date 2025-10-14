# 📱 Plan de Migración de Fiscalberry a Android

## 🎯 Objetivo
Adaptar Fiscalberry para que funcione en una PC con Android, con soporte completo para impresoras fiscales USB y conexión a RabbitMQ/SocketIO.

## 📋 Estado Actual
- ✅ GUI con Kivy ya implementada
- ✅ Buildozer.spec configurado
- ✅ Requirements para Android definidos
- ✅ Estructura de proyecto compatible

## 🔧 Cambios Necesarios

### 1. **Permisos Android** (buildozer.spec)
Agregar permisos necesarios:
```ini
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,USB_PERMISSION,WAKE_LOCK
```

### 2. **Adaptación de Rutas (Configberry.py)**
- ✅ Ya usa `platformdirs` (compatible con Android)
- Android guardará en: `/data/data/com.paxapos.fiscalberry/files/`
- Verificar que no haya rutas hardcoded de Windows

### 3. **Detección de Impresoras USB (printer_detector.py)**
Necesita usar **pyjnius** para acceso USB en Android:

```python
# Android USB Detection
try:
    from jnius import autoclass
    from jnius import cast
    
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    UsbManager = autoclass('android.hardware.usb.UsbManager')
    Context = autoclass('android.content.Context')
    
    def get_android_usb_devices():
        context = PythonActivity.mActivity
        usb_manager = context.getSystemService(Context.USB_SERVICE)
        devices = usb_manager.getDeviceList()
        return list(devices.values())
except ImportError:
    # No es Android, usar detección normal
    pass
```

### 4. **Servicio en Segundo Plano**
Para que RabbitMQ/SocketIO funcionen con la app en background:

Crear `src/fiscalberryservice/android.py`:
```python
from jnius import autoclass
from android.broadcast import BroadcastReceiver

PythonService = autoclass('org.kivy.android.PythonService')
service = PythonService.mService

def start_service():
    """Inicia el servicio de Fiscalberry en background"""
    pass
```

Configurar en buildozer.spec:
```ini
services = fiscalberryservice:./src/fiscalberryservice/android.py
```

### 5. **Librerías Incompatibles**
Remover o condicionar:
- ❌ `pywin32` - Solo Windows
- ❌ `pyautogui` - No funciona en Android
- ⚠️ `pika` - Verificar compatibilidad con Android

### 6. **Testing en Android**
1. Compilar APK: `buildozer android debug`
2. Instalar: `adb install bin/fiscalberry-*.apk`
3. Ver logs: `adb logcat | grep python`

## 📦 Dependencias Android

### Recipes necesarias en python-for-android:
- `hostpython3` ✅
- `python3` ✅
- `kivy` ✅
- `pyjnius` ✅ (para USB y servicios)
- `openssl` ✅ (para conexiones seguras)
- `requests` ✅
- `python-socketio` ⚠️ (verificar recipe)
- `pika` ⚠️ (verificar recipe)

### Alternativas si pika no funciona:
- Usar `paho-mqtt` (mejor soporte Android)
- Crear adaptador MQTT ↔ RabbitMQ en el servidor

## 🎨 Interfaz GUI Android

### Optimizaciones necesarias:
1. **Densidad de pantalla**: Usar `dp` en lugar de `px`
2. **Orientación**: Soportar landscape y portrait
3. **Teclado virtual**: Ajustar layouts cuando aparece
4. **Permisos en runtime**: Solicitar USB permission al conectar

### Ejemplo de solicitud de permiso USB:
```python
from android.permissions import request_permissions, Permission
from android.permissions import check_permission

def request_usb_permission():
    if not check_permission(Permission.USB_PERMISSION):
        request_permissions([Permission.USB_PERMISSION])
```

## 🚀 Fases de Implementación

### **Fase 1: Preparación** ✅ ACTUAL
- [x] Crear rama `fiscalberry-android`
- [ ] Actualizar buildozer.spec con permisos
- [ ] Documentar cambios necesarios

### **Fase 2: Adaptación de Código**
- [ ] Adaptar printer_detector.py para Android USB
- [ ] Condicionar imports incompatibles (pywin32)
- [ ] Crear servicio Android para background
- [ ] Adaptar Configberry si es necesario

### **Fase 3: Primera Compilación**
- [ ] Instalar buildozer en Linux/WSL
- [ ] Compilar primer APK debug
- [ ] Resolver errores de compilación

### **Fase 4: Testing**
- [ ] Instalar en PC Android
- [ ] Probar detección de impresoras USB
- [ ] Verificar conexión RabbitMQ/SocketIO
- [ ] Probar interfaz GUI

### **Fase 5: Optimización**
- [ ] Mejorar performance en Android
- [ ] Optimizar batería (servicios en background)
- [ ] Ajustar UI para tablets
- [ ] Crear APK release firmado

## 🔍 Comandos Útiles

### Buildozer (compilación):
```bash
# Instalar buildozer (Ubuntu/WSL)
sudo apt install python3-pip python3-venv
pip install buildozer cython

# Compilar APK debug
buildozer android debug

# Compilar y desplegar
buildozer android debug deploy run logcat

# Limpiar build
buildozer android clean
```

### ADB (deployment):
```bash
# Instalar APK
adb install -r bin/fiscalberry-*.apk

# Ver logs en tiempo real
adb logcat | grep python

# Ver logs de la app
adb logcat | grep Fiscalberry
```

## ⚠️ Consideraciones Importantes

1. **Buildozer solo funciona en Linux**: Usar WSL en Windows o VM Ubuntu
2. **Primera compilación tarda mucho**: Descarga NDK, SDK, recipes (~2GB)
3. **Permisos USB**: Usuario debe aceptar manualmente la primera vez
4. **Batería**: Servicios en background consumen batería (optimizar con WorkManager)
5. **Impresoras**: Verificar compatibilidad USB OTG en la PC Android

## 📚 Referencias

- [Buildozer Documentation](https://buildozer.readthedocs.io/)
- [Python for Android](https://python-for-android.readthedocs.io/)
- [Kivy Android Guide](https://kivy.org/doc/stable/guide/packaging-android.html)
- [Pyjnius Documentation](https://pyjnius.readthedocs.io/)

---

**Próximo paso**: Actualizar buildozer.spec con permisos y comenzar adaptación de código.
