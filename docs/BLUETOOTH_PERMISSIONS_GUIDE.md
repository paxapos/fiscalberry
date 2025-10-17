# 🔓 GUÍA: OTORGAR PERMISOS BLUETOOTH EN ANDROID

## ⚠️ PROBLEMA IDENTIFICADO

Android 12+ (API 31+) requiere que los permisos de Bluetooth se soliciten **explícitamente en runtime** y el usuario los debe **aprobar manualmente**.

Los permisos críticos para Bluetooth son:
- `BLUETOOTH_CONNECT` (Android 12+)
- `BLUETOOTH_SCAN` (Android 12+)
- `ACCESS_FINE_LOCATION` (para escaneo)

---

## ✅ SOLUCIONES IMPLEMENTADAS

### 1. Código Actualizado
- ✅ `android_permissions.py`: Ahora usa `ActivityCompat.requestPermissions()` 
- ✅ `fiscalberry_app.py`: Solicita permisos de Bluetooth al iniciar
- ✅ `test_android_permissions.py`: Script de diagnóstico

### 2. Flujo Mejorado
Al iniciar Fiscalberry, ahora:
1. Detecta permisos faltantes
2. Muestra diálogo Android para aprobarlos
3. Si el usuario rechaza → muestra instrucciones en log
4. Si el usuario aprueba → Bluetooth funcional

---

## 📱 PASOS PARA PROBAR (DESPUÉS DE COMPILAR)

### Paso 1: Instalar APK Nuevo
```bash
cd /home/santiago/fiscalberry

# Esperar a que termine la compilación (15-20 min)
# Verás: "BUILD SUCCESSFUL"

# Instalar
adb install -r bin/fiscalberry-2.0.1-arm64-v8a_armeabi-v7a-debug.apk
```

### Paso 2: Ejecutar Test de Permisos
```bash
# Limpiar logs
adb logcat -c

# Ejecutar test de diagnóstico
adb push test_android_permissions.py /sdcard/
adb shell python3 /sdcard/test_android_permissions.py

# Resultado esperado:
# - Muestra qué permisos faltan
# - Intenta solicitarlos
# - Si falla, da instrucciones manuales
```

### Paso 3: Iniciar Fiscalberry y Aceptar Permisos
```bash
# Iniciar app
adb shell monkey -p com.paxapos.fiscalberry 1

# Ver logs en tiempo real
adb logcat -s python:* | grep -E "permiso|Bluetooth|BLUETOOTH"
```

**Cuando la app inicie:**
1. 📱 Aparecerá un diálogo: **"Allow Fiscalberry to connect to devices nearby?"**
2. ✅ **Presionar "ALLOW" o "PERMITIR"**
3. 🔄 Si no aparece, continuar con Paso 4

### Paso 4: Otorgar Permisos Manualmente (Si el Diálogo No Apareció)

#### Opción A: Via ADB (Más Rápido)
```bash
# Abrir configuración de permisos de Fiscalberry
adb shell am start -a android.settings.APPLICATION_DETAILS_SETTINGS \
  -d package:com.paxapos.fiscalberry

# En el celular/emulador:
# 1. Tap en "Permissions" o "Permisos"
# 2. Habilitar:
#    - Location → Allow all the time (o While using)
#    - Nearby devices → Allow
```

#### Opción B: Manual en el Dispositivo
```
Settings → Apps → Fiscalberry → Permissions → Enable:
  ✅ Location (Ubicación)
  ✅ Nearby devices (Dispositivos cercanos)
```

### Paso 5: Verificar Permisos Otorgados
```bash
# Verificar que los permisos se otorgaron
adb shell dumpsys package com.paxapos.fiscalberry | grep -A 20 "granted=true"

# Deberías ver:
# android.permission.BLUETOOTH_CONNECT: granted=true
# android.permission.BLUETOOTH_SCAN: granted=true
# android.permission.ACCESS_FINE_LOCATION: granted=true
```

### Paso 6: Probar Escaneo Bluetooth
```bash
# Reiniciar app para que tome los permisos
adb shell am force-stop com.paxapos.fiscalberry
adb shell monkey -p com.paxapos.fiscalberry 1

# Probar escaneo
adb push test_bluetooth_printer.py /sdcard/
adb shell python3 /sdcard/test_bluetooth_printer.py
```

---

## 🐛 TROUBLESHOOTING

### ❌ "No aparece el diálogo de permisos"

**Causa:** Android ya decidió (rechazó anteriormente o configurado en manifest)

**Solución:**
```bash
# Resetear permisos de la app
adb shell pm reset-permissions-to-default com.paxapos.fiscalberry

# Desinstalar completamente
adb uninstall com.paxapos.fiscalberry

# Reinstalar
adb install -r bin/fiscalberry-*.apk

# Iniciar de nuevo
adb shell monkey -p com.paxapos.fiscalberry 1
```

### ❌ "Permission denied al escanear Bluetooth"

**Verificar permisos:**
```bash
adb shell dumpsys package com.paxapos.fiscalberry | grep permission

# Si BLUETOOTH_SCAN o BLUETOOTH_CONNECT = granted=false:
# → Ir a Settings y habilitarlos manualmente (Paso 4)
```

### ❌ "BluetoothAdapter is null"

**Causa:** Bluetooth no disponible en emulador o dispositivo sin BT

**Solución:**
- Usar dispositivo físico con Bluetooth
- O usar emulador Genymotion con soporte BT

### ❌ "ActivityCompat not found"

**Causa:** androidx.core no incluida en APK

**Verificar buildozer.spec:**
```ini
# Debería tener:
android.gradle_dependencies = androidx.core:core:1.6.0
```

Si falta, agregar y recompilar.

---

## 📊 COMANDOS ÚTILES DE DIAGNÓSTICO

### Ver todos los permisos de Fiscalberry
```bash
adb shell dumpsys package com.paxapos.fiscalberry | grep -E "permission|granted"
```

### Ver estado del Bluetooth
```bash
adb shell dumpsys bluetooth_manager
```

### Ver logs filtrados de permisos
```bash
adb logcat -s python:* | grep -i bluetooth
```

### Otorgar permisos via ADB (Android <= 10)
```bash
# Nota: En Android 11+ esto NO funciona, debe ser manual
adb shell pm grant com.paxapos.fiscalberry android.permission.BLUETOOTH_CONNECT
adb shell pm grant com.paxapos.fiscalberry android.permission.BLUETOOTH_SCAN
adb shell pm grant com.paxapos.fiscalberry android.permission.ACCESS_FINE_LOCATION
```

---

## ✅ CHECKLIST FINAL

Antes de intentar usar Bluetooth, verificar:

- [ ] APK compilado con código actualizado
- [ ] APK instalado en dispositivo Android 
- [ ] Fiscalberry iniciado al menos una vez
- [ ] Diálogo de permisos apareció y se aceptó (O permisos otorgados manualmente)
- [ ] `BLUETOOTH_CONNECT: granted=true` en dumpsys
- [ ] `BLUETOOTH_SCAN: granted=true` en dumpsys
- [ ] `ACCESS_FINE_LOCATION: granted=true` en dumpsys
- [ ] Bluetooth habilitado en dispositivo
- [ ] (Opcional) Impresora BT emparejada

---

## 🎯 RESUMEN RÁPIDO

```bash
# 1. Esperar compilación
tail -f build-bluetooth-permissions.log

# 2. Instalar
adb install -r bin/fiscalberry-*.apk

# 3. Iniciar y ACEPTAR permisos cuando aparezca el diálogo
adb shell monkey -p com.paxapos.fiscalberry 1

# 4. Si no aparece diálogo, otorgar manualmente:
adb shell am start -a android.settings.APPLICATION_DETAILS_SETTINGS \
  -d package:com.paxapos.fiscalberry
# → Permissions → Enable Location + Nearby devices

# 5. Verificar
adb shell dumpsys package com.paxapos.fiscalberry | grep BLUETOOTH

# 6. Probar
adb push test_bluetooth_printer.py /sdcard/
adb shell python3 /sdcard/test_bluetooth_printer.py
```

---

## 📞 SI NADA FUNCIONA

**Última opción:** Otorgar TODOS los permisos de una vez via Settings:

```
1. Settings → Apps → Fiscalberry
2. Permissions → Allow ALL
3. Restart app
```

O usar comando ADB:
```bash
adb shell am start -n com.android.settings/.applications.InstalledAppDetailsTop \
  -d package:com.paxapos.fiscalberry
```

---

**Última actualización:** Compilación en progreso...  
**Estado:** Esperando BUILD SUCCESSFUL para continuar con testing
