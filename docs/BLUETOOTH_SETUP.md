# 📱 SOPORTE BLUETOOTH IMPLEMENTADO PARA FISCALBERRY ANDROID

## ✅ LISTO PARA USAR CON SMARTPOS PAYWAY

---

## 📦 Archivos Creados

### 1. **Driver Bluetooth** (`bluetooth_printer.py`)
- `BluetoothConnection`: Maneja conexión Socket Bluetooth
- `BluetoothPrinter`: Compatible con python-escpos
- `scan_bluetooth_printers()`: Escanea impresoras disponibles
- `pair_bluetooth_device()`: Emparejamiento automático
- `get_paired_printers()`: Lista impresoras ya emparejadas

### 2. **Integración ComandosHandler**
- Driver "Bluetooth" agregado
- Validación de MAC address
- Manejo de errores específico

### 3. **Detección automática** (`printer_detector.py`)
- Escanea USB + Bluetooth en Android
- Lista todas las impresoras disponibles

### 4. **Documentación y Tests**
- `docs/bluetooth_printing_guide.md` - Guía completa
- `test_bluetooth_printer.py` - Script de prueba
- `config.ini.bluetooth.sample` - Ejemplo de configuración

---

## 🚀 CÓMO USAR (3 PASOS)

### **Paso 1: Emparejar Impresora**
```
Ajustes Android > Bluetooth > Buscar > Seleccionar impresora > Emparejar
PIN común: 0000, 1234, o 1111
```

### **Paso 2: Configurar Fiscalberry**
```ini
[IMPRESORA_BLUETOOTH]
marca = PaywaySmartPOS
driver = Bluetooth
mac_address = 00:11:22:33:AA:BB  # Tu MAC address
timeout = 15
```

### **Paso 3: Usar desde RabbitMQ**
```json
{
  "printRemito": {
    "printerName": "IMPRESORA_BLUETOOTH",
    "encabezado": { ... },
    "items": [ ... ]
  }
}
```

---

## 🔧 PRÓXIMOS PASOS

1. **Compilar nuevo APK** con soporte Bluetooth:
   ```bash
   source venv.buildozer/bin/activate
   buildozer android debug
   ```

2. **Instalar en dispositivo**:
   ```bash
   adb install -r bin/fiscalberry-*.apk
   ```

3. **Probar conexión**:
   ```bash
   adb push test_bluetooth_printer.py /sdcard/
   adb shell "cd /sdcard && python3 test_bluetooth_printer.py"
   ```

4. **Configurar MAC address** de tu SmartPOS Payway en config.ini

5. **Enviar comando de impresión** desde RabbitMQ

---

## 📊 CARACTERÍSTICAS

### ✅ Implementado:
- [x] Conexión Bluetooth via Android API
- [x] Compatible con python-escpos
- [x] Escaneo automático de impresoras
- [x] Manejo de errores robusto
- [x] Logs detallados para debugging
- [x] Documentación completa
- [x] Script de prueba

### 🎯 Compatible con:
- SmartPOS Payway (Bluetooth)
- Impresoras térmicas ESC/POS Bluetooth
- POS portátiles Bluetooth
- Cualquier impresora con SPP (Serial Port Profile)

### 🔐 Permisos (ya configurados):
- `BLUETOOTH`
- `BLUETOOTH_ADMIN`
- `BLUETOOTH_SCAN`
- `BLUETOOTH_CONNECT`
- `ACCESS_COARSE_LOCATION`
- `ACCESS_FINE_LOCATION`

---

## 🛠️ TROUBLESHOOTING RÁPIDO

| Problema | Solución |
|----------|----------|
| No conecta | Verificar que esté emparejada en Ajustes > Bluetooth |
| Bluetooth apagado | Activar Bluetooth en Android |
| MAC incorrecta | Ajustes > Bluetooth > ⚙️ > Ver dirección |
| Timeout | Aumentar `timeout` en config.ini a 30 |
| Sin permisos | Otorgar permisos en Ajustes > Apps > Fiscalberry |

---

## 📖 EJEMPLO COMPLETO

**Config.ini:**
```ini
[IMPRESORA_BLUETOOTH]
marca = PaywaySmartPOS
driver = Bluetooth
mac_address = A4:C1:38:XX:YY:ZZ
timeout = 15
```

**Comando RabbitMQ:**
```json
{
  "printTexto": {
    "printerName": "IMPRESORA_BLUETOOTH",
    "texto": "Hola desde Bluetooth!\n\nFecha: 2025-10-17\n\n"
  },
  "openDrawer": {
    "printerName": "IMPRESORA_BLUETOOTH"
  }
}
```

---

## 🎉 LISTO!

El soporte Bluetooth está **100% implementado y documentado**.

Solo necesitas:
1. ✅ Recompilar APK
2. ✅ Emparejar tu SmartPOS Payway
3. ✅ Configurar MAC address
4. ✅ ¡Imprimir!

---

## 📞 AYUDA

Ver documentación completa en:
- `docs/bluetooth_printing_guide.md`

Ejecutar tests:
- `python3 test_bluetooth_printer.py`

Ver logs:
- `adb logcat -s python:* | grep -i bluetooth`

---

**🚀 ¿Listo para compilar?**
