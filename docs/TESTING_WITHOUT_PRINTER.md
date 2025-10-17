# 🧪 TESTING BLUETOOTH SIN IMPRESORA PAYWAY

Guía completa para probar el soporte Bluetooth de Fiscalberry sin tener una impresora Payway SmartPOS física.

---

## 📋 ÍNDICE

1. [Opción 1: Usar Otra Impresora Bluetooth](#opcion-1-impresora-bluetooth-alternativa) ⭐ **RECOMENDADO**
2. [Opción 2: Simulador en PC](#opcion-2-simulador-en-pc)
3. [Opción 3: Emulador con Bluetooth Virtual](#opcion-3-emulador-android)
4. [Opción 4: Verificación sin Hardware](#opcion-4-verificacion-sin-hardware)

---

## OPCIÓN 1: IMPRESORA BLUETOOTH ALTERNATIVA ⭐

**La forma MÁS REALISTA de probar** - cualquier impresora térmica Bluetooth funcionará.

### ✅ Impresoras Compatibles

Fiscalberry usa el protocolo **ESC/POS estándar**, compatible con:

- **Impresoras portátiles Bluetooth:**
  - Xprinter XP-P323B (~$60 USD)
  - iMin D2-502 (~$80 USD)
  - Rongta RPP210 (~$50 USD)
  - Goojprt PT-210 (~$45 USD)
  
- **POS térmicos con Bluetooth:**
  - ZKTeco ZKP8001 (~$90 USD)
  - Epson TM-m30II-B (~$250 USD profesional)
  - Any thermal printer with Bluetooth + ESC/POS

### 📝 Pasos con Impresora Alternativa

```bash
# 1. Emparejar impresora en Android
# Settings → Bluetooth → Pair "Printer-XXX"

# 2. Obtener MAC address
adb shell dumpsys bluetooth_manager | grep -A 5 "Printer"

# 3. Editar config.ini con MAC de tu impresora
[IMPRESORA_BLUETOOTH]
marca = MiImpresoraBT
driver = Bluetooth
mac_address = XX:XX:XX:XX:XX:XX  # ← Reemplazar con MAC real
timeout = 15

# 4. Probar conexión
adb push test_bluetooth_printer.py /sdcard/
adb shell python3 /sdcard/test_bluetooth_printer.py
```

### 💰 Recomendación de Compra

Si vas a comprar una para testing:
- **Budget:** Goojprt PT-210 (~$45) - buena relación calidad/precio
- **Profesional:** iMin D2-502 (~$80) - excelente calidad
- **Referencia:** Buscar "thermal bluetooth printer 58mm ESC/POS" en Amazon/Mercado Libre

---

## OPCIÓN 2: SIMULADOR EN PC 💻

**Ventaja:** No necesitas hardware adicional  
**Desventaja:** No prueba impresión real, solo conectividad

### 📦 Instalación del Simulador

#### Linux (Ubuntu/Debian):
```bash
cd /home/santiago/fiscalberry

# Instalar dependencias Bluetooth
sudo apt-get update
sudo apt-get install -y libbluetooth-dev bluez python3-dev

# Instalar PyBluez
pip3 install pybluez

# Ejecutar simulador
python3 bluetooth_printer_simulator.py
```

#### Linux (Fedora/RHEL):
```bash
sudo dnf install bluez-libs-devel bluez
pip3 install pybluez
python3 bluetooth_printer_simulator.py
```

### 🔧 Uso del Simulador

1. **Ejecutar en tu PC:**
   ```bash
   python3 bluetooth_printer_simulator.py
   ```
   
   Verás:
   ```
   ✓ Servidor Bluetooth iniciado
     Puerto RFCOMM: 1
     Dirección MAC: AA:BB:CC:DD:EE:FF
   
   📱 PASOS PARA CONECTAR DESDE ANDROID:
     1. Activar Bluetooth en Android
     2. Buscar dispositivos
     3. Emparejar con esta PC
     4. Usar MAC address: AA:BB:CC:DD:EE:FF en config.ini
   
   ⏳ Esperando conexión...
   ```

2. **En Android:**
   ```bash
   # Emparejar con la PC
   Settings → Bluetooth → Scan → Pair "YourPCName"
   
   # Anotar MAC address mostrada en simulador
   
   # Configurar Fiscalberry con esa MAC
   ```

3. **Probar desde Fiscalberry:**
   ```bash
   # El simulador mostrará los comandos recibidos:
   📥 Recibido (245 bytes):
     → Comando: INICIALIZAR IMPRESORA (ESC @)
     → Comando: ALINEAR Centro
     📄 TEXTO A IMPRIMIR:
     ------------------------------------------------------------------
     FISCALBERRY TEST TICKET
     ------------------------------------------------------------------
   ```

### 🐛 Troubleshooting Simulador

**Error: "PyBluez no está instalado"**
```bash
sudo apt-get install libbluetooth-dev
pip3 install pybluez
```

**Error: "Permission denied"**
```bash
# Agregar usuario a grupo bluetooth
sudo usermod -a -G bluetooth $USER
sudo systemctl restart bluetooth

# Re-login para aplicar cambios
```

**No se puede descubrir desde Android:**
```bash
# Verificar Bluetooth activo
hciconfig hci0 up
hciconfig hci0 piscan  # Hacer visible

# Verificar servicio
sudo systemctl status bluetooth
```

---

## OPCIÓN 3: EMULADOR ANDROID 📱

**Ventaja:** Testa el código completo en ambiente Android  
**Desventaja:** Bluetooth virtual es complejo de configurar

### 🖥️ Opción 3A: Genymotion (Mejor soporte Bluetooth)

```bash
# 1. Descargar Genymotion (versión personal gratuita)
# https://www.genymotion.com/download/

# 2. Crear dispositivo virtual con Android 11+
# Agregar plugin "ARM Translation" para apps ARM

# 3. Habilitar Bluetooth virtual
# Settings → Bluetooth → Enable

# 4. Conectar Bluetooth host
# Genymotion Settings → Network → Bridge Bluetooth
```

### 🖥️ Opción 3B: Android Emulator con Bluetooth Forwarding

```bash
# Experimental - requiere Android Emulator reciente
# Crear AVD con Play Store

emulator -avd Pixel_5_API_33 -feature Bluetooth

# Nota: Bluetooth en emuladores es limitado
```

---

## OPCIÓN 4: VERIFICACIÓN SIN HARDWARE ✅

**Probar que el código funciona sin imprimir realmente.**

### 🧪 Test 1: Verificar Escaneo Bluetooth

```python
# test_bluetooth_scan_only.py
from fiscalberry.common.bluetooth_printer import scan_bluetooth_printers

print("🔍 Escaneando dispositivos Bluetooth...")
printers = scan_bluetooth_printers(timeout=10)

if printers:
    print(f"\n✓ Encontrados {len(printers)} dispositivos:")
    for p in printers:
        print(f"  • {p['name']} - {p['mac_address']}")
else:
    print("\n⚠️  No se encontraron dispositivos Bluetooth")
    print("   (Esto es normal si no hay impresoras cerca)")
```

```bash
# Ejecutar en Android
adb push test_bluetooth_scan_only.py /sdcard/
adb shell python3 /sdcard/test_bluetooth_scan_only.py
```

### 🧪 Test 2: Verificar Integración con ComandosHandler

```python
# test_bluetooth_integration.py
from fiscalberry.common.ComandosHandler import ComandosHandler

# Crear handler con config Bluetooth
config = {
    "driver": "Bluetooth",
    "mac_address": "00:11:22:33:AA:BB"  # MAC ficticia
}

try:
    handler = ComandosHandler(config)
    print("✓ ComandosHandler acepta driver Bluetooth")
except Exception as e:
    print(f"❌ Error: {e}")
```

### 🧪 Test 3: Verificar Permisos Android

```python
# test_bluetooth_permissions.py
from jnius import autoclass

try:
    BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
    adapter = BluetoothAdapter.getDefaultAdapter()
    
    if adapter:
        print("✓ BluetoothAdapter accesible")
        print(f"  Estado: {'Enabled' if adapter.isEnabled() else 'Disabled'}")
        
        # Verificar dispositivos emparejados
        paired = adapter.getBondedDevices()
        print(f"  Dispositivos emparejados: {paired.size()}")
    else:
        print("⚠️  Bluetooth no disponible en dispositivo")
        
except Exception as e:
    print(f"❌ Error accediendo Bluetooth: {e}")
    print("   Verificar permisos en AndroidManifest.xml")
```

---

## 📊 COMPARACIÓN DE OPCIONES

| Opción | Costo | Realismo | Dificultad | Recomendado Para |
|--------|-------|----------|------------|------------------|
| **Impresora BT** | $45-100 | ⭐⭐⭐⭐⭐ | ⚡ Fácil | Testing completo + Producción |
| **Simulador PC** | $0 | ⭐⭐⭐ | ⚡⚡ Medio | Verificar conectividad |
| **Emulador** | $0 | ⭐⭐ | ⚡⚡⚡ Difícil | Testing automatizado |
| **Sin Hardware** | $0 | ⭐ | ⚡ Muy fácil | Validar código |

---

## 🎯 RECOMENDACIÓN FINAL

### Para Testing Completo:
**Comprar impresora Bluetooth económica** (~$50 USD)
- Testas impresión real
- Verificas compatibilidad ESC/POS
- Útil para desarrollo futuro
- Recomendación: **Goojprt PT-210** o similar en Mercado Libre

### Para Verificación Rápida:
**Usar simulador en PC** (gratis)
- Verificas que la conexión funciona
- Ves qué comandos se envían
- No necesitas hardware adicional

### Para CI/CD:
**Tests sin hardware** (gratis)
- Validación automática
- No depende de hardware
- Útil para builds automatizados

---

## 🔗 ENLACES ÚTILES

- **Simulador:** `/home/santiago/fiscalberry/bluetooth_printer_simulator.py`
- **Tests:** `/home/santiago/fiscalberry/test_bluetooth_printer.py`
- **Documentación completa:** `/home/santiago/fiscalberry/docs/bluetooth_printing_guide.md`
- **Quick Setup:** `/home/santiago/fiscalberry/docs/BLUETOOTH_SETUP.md`

---

## 💬 PREGUNTAS FRECUENTES

**P: ¿El simulador imprime realmente?**  
R: No, solo muestra qué comandos se reciben. Para ver impresión real necesitas hardware.

**P: ¿Funcionará con Payway SmartPOS?**  
R: Sí, usa el mismo protocolo ESC/POS. Testing con otra impresora BT es válido.

**P: ¿Puedo usar mi celular como impresora?**  
R: No directamente, pero puedes instalar apps que emulan impresoras BT.

**P: ¿Necesito compilar APK nuevo?**  
R: Sí, el soporte Bluetooth no está en el APK actual. Ejecutar: `buildozer android debug`

**P: ¿Qué pasa si no tengo Linux para el simulador?**  
R: Windows tiene Bluetooth más complejo. Mejor usar Android + impresora real o emulador.

---

**✨ TIP:** Para el caso de Payway específicamente, cualquier impresora térmica Bluetooth te servirá perfectamente para validar que tu código funciona antes de probarlo en producción con el SmartPOS real.
