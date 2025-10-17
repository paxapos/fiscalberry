# 📱 Guía de Impresión Bluetooth en Fiscalberry Android

## 🎯 Para SmartPOS Payway y otras impresoras Bluetooth

---

## 📋 Requisitos Previos

1. **Dispositivo Android** con Bluetooth (Android 6.0+)
2. **Impresora Bluetooth** compatible con ESC/POS:
   - SmartPOS Payway
   - Impresoras térmicas Bluetooth
   - POS portátiles con Bluetooth
3. **Fiscalberry Android** instalado

---

## 🔧 Configuración Paso a Paso

### 1️⃣ Emparejar la Impresora

**Antes de usar Fiscalberry**, debes emparejar la impresora en Android:

1. Abre **Ajustes** de Android
2. Ve a **Bluetooth**
3. Enciende la impresora Bluetooth
4. Toca **Buscar dispositivos** o **Escanear**
5. Selecciona tu impresora (ej: "Payway Printer", "BT-Printer", etc.)
6. Introduce el PIN si lo solicita (generalmente `0000`, `1234`, o `1111`)
7. Espera a que aparezca como **"Emparejado"**

> ⚠️ **Importante:** La impresora DEBE estar emparejada antes de usarla con Fiscalberry.

---

### 2️⃣ Obtener la Dirección MAC

**Opción A: Desde Android**
1. Ajustes > Bluetooth
2. Toca el ícono ⚙️ junto a tu impresora emparejada
3. Busca **"Dirección del dispositivo"** o **"MAC Address"**
4. Anota la dirección (formato: `00:11:22:33:AA:BB`)

**Opción B: Desde Fiscalberry**
```bash
# Ejecutar desde terminal Android o adb shell
python3 test_bluetooth_printer.py
```
Esto escaneará automáticamente e imprimirá las direcciones MAC.

---

### 3️⃣ Configurar Fiscalberry

Edita el archivo `config.ini` y agrega:

```ini
[IMPRESORA_BLUETOOTH]
marca = PaywaySmartPOS
modelo = BT-Printer
driver = Bluetooth
mac_address = 00:11:22:33:AA:BB  # ← REEMPLAZA con tu MAC address
timeout = 15
```

**Parámetros:**

| Parámetro | Descripción | Obligatorio | Default |
|-----------|-------------|-------------|---------|
| `driver` | Debe ser `Bluetooth` | ✅ Sí | - |
| `mac_address` | Dirección MAC de la impresora | ✅ Sí | - |
| `timeout` | Tiempo de espera conexión (segundos) | ❌ No | 10 |

---

### 4️⃣ Probar la Conexión

**Desde la app Fiscalberry:**

1. Abre Fiscalberry
2. Ve a **Configuración** > **Impresoras**
3. Selecciona tu impresora Bluetooth
4. Presiona **"Imprimir Prueba"**

**Desde terminal/ADB:**

```bash
# Copiar script de prueba al dispositivo
adb push test_bluetooth_printer.py /sdcard/

# Ejecutar prueba
adb shell "cd /sdcard && python3 test_bluetooth_printer.py"
```

---

## 🐛 Solución de Problemas

### ❌ Error: "No se pudo conectar a la impresora"

**Causas comunes:**

1. **Impresora no emparejada**
   - Solución: Emparejar en Ajustes > Bluetooth

2. **Bluetooth desactivado**
   - Solución: Activar Bluetooth en Android

3. **Impresora apagada o sin batería**
   - Solución: Encender impresora y cargar batería

4. **MAC address incorrecta**
   - Solución: Verificar que la MAC en config.ini coincida exactamente
   - Formato correcto: `XX:XX:XX:XX:XX:XX` (mayúsculas, con `:`)

5. **Permisos no otorgados**
   - Solución: Verificar permisos en Ajustes > Apps > Fiscalberry > Permisos
   - Deben estar activados: Bluetooth, Ubicación

---

### ❌ Error: "Bluetooth no disponible"

**Soluciones:**

1. Verificar que el dispositivo Android tenga Bluetooth
2. Actualizar Fiscalberry a la última versión
3. Reinstalar la app si es necesario

---

### ❌ Error: "Timeout de conexión"

**Soluciones:**

1. Aumentar el timeout en config.ini:
   ```ini
   timeout = 30
   ```

2. Acercar más la impresora al dispositivo Android

3. Reiniciar el Bluetooth:
   - Desactivar Bluetooth
   - Esperar 5 segundos
   - Activar Bluetooth

4. Desemparejar y volver a emparejar la impresora

---

### ⚠️ Impresión muy lenta

**Soluciones:**

1. **Interferencias Bluetooth**
   - Alejar de otros dispositivos Bluetooth
   - Alejar de WiFi 2.4GHz
   - Usar en área con menos dispositivos

2. **Batería baja de la impresora**
   - Cargar completamente la impresora

3. **Distancia excesiva**
   - Mantener máximo 5-10 metros de distancia
   - Sin obstáculos entre dispositivos

---

### 🔍 Logs de depuración

Para ver logs detallados:

```bash
# Habilitar logging DEBUG en config.ini
[SERVIDOR]
log_level = DEBUG

# Ver logs en tiempo real
adb logcat -s python:* | grep -i bluetooth
```

---

## 📊 Comparación de Conexiones

| Característica | Bluetooth | USB OTG | Red TCP/IP |
|----------------|-----------|---------|------------|
| **Cables** | ❌ No | ✅ Sí | ❌ No |
| **Alcance** | ~10 metros | Limitado | ~100 metros |
| **Velocidad** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Estabilidad** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Portabilidad** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **Batería impresora** | Necesaria | No necesaria | No necesaria |
| **Setup** | Medio | Fácil | Medio |
| **Recomendado para** | Movilidad | Fijo | Múltiples dispositivos |

---

## 💡 Mejores Prácticas

### ✅ Hacer:

- Mantener la impresora cerca del dispositivo Android (< 5 metros)
- Cargar la batería de la impresora regularmente
- Mantener el firmware de la impresora actualizado
- Probar la conexión antes de usarla en producción
- Tener papel térmico de repuesto

### ❌ No hacer:

- No usar con batería baja de la impresora
- No alejar más de 10 metros
- No usar cerca de muchos dispositivos WiFi/Bluetooth
- No cambiar la MAC address sin verificar
- No omitir el paso de emparejamiento

---

## 🔒 Seguridad

- Las conexiones Bluetooth pueden ser interceptadas
- Para entornos sensibles, considerar:
  - Usar red TCP/IP con VPN
  - USB OTG para conexión directa
  - Cifrado adicional a nivel de aplicación

---

## 📞 Soporte

Si tienes problemas:

1. Revisa esta guía completa
2. Ejecuta el script de prueba: `test_bluetooth_printer.py`
3. Revisa los logs: `adb logcat -s python:*`
4. Contacta soporte de Fiscalberry con:
   - Modelo de impresora
   - Versión de Android
   - Logs de error
   - Captura de pantalla

---

## 📝 Ejemplo de Configuración Completa

```ini
[SERVIDOR]
uuid = f8348685-xxxx-xxxx-xxxx-xxxxxxxxxxxx
sio_host = https://beta.paxapos.com
sio_password = 
log_level = INFO

[IMPRESORA_BLUETOOTH]
marca = PaywaySmartPOS
modelo = ThermalPrinter
driver = Bluetooth
mac_address = 00:11:22:33:AA:BB
timeout = 15

[Paxaprinter]
tenant = mi-comercio
site_name = Mi Comercio
alias = local-principal
rabbitmq_host = rabbitmq.restodigital.com.ar
rabbitmq_port = 5672
rabbitmq_user = fiscalberry
rabbitmq_password = fiscalberry123
rabbitmq_vhost = /

[RabbitMq]
host = rabbitmq.restodigital.com.ar
port = 5672
user = fiscalberry
password = fiscalberry123
vhost = /
queue = f8348685-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## 🎓 Recursos Adicionales

- **Documentación ESC/POS:** https://reference.epson-biz.com/modules/ref_escpos/
- **Python-escpos:** https://python-escpos.readthedocs.io/
- **Bluetooth Android:** https://developer.android.com/guide/topics/connectivity/bluetooth

---

**¿Funcionó todo correctamente? ⭐ ¡Excelente!**

**¿Tienes problemas? 🆘 Revisa la sección de solución de problemas o contacta soporte.**
