# 🚀 Guía de Compilación - Fiscalberry Android en Linux Mint

## 📋 Requisitos Previos

- **Linux Mint** (o Ubuntu 20.04+)
- **Python 3.8+**
- **Git**
- **Conexión a Internet** (para descargar NDK y SDK)
- **~10 GB de espacio libre** (para Android SDK, NDK, y builds)
- **4 GB RAM mínimo** (8 GB recomendado)

---

## 🔧 Paso 1: Preparar el Sistema

Abre una terminal y ejecuta:

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependencias necesarias
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip \
    autoconf libtool pkg-config zlib1g-dev libncurses5-dev \
    libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev \
    build-essential ccache libltdl-dev

# Verificar Python
python3 --version  # Debe ser 3.8 o superior

# Verificar Java
java -version  # Debe ser OpenJDK 17
```

---

## 📦 Paso 2: Instalar Buildozer

```bash
# Instalar Buildozer y Cython
pip3 install --upgrade buildozer cython

# Agregar al PATH si no está (agregar al ~/.bashrc)
echo 'export PATH=$PATH:~/.local/bin' >> ~/.bashrc
source ~/.bashrc

# Verificar instalación
buildozer --version
```

---

## 📂 Paso 3: Clonar o Navegar al Proyecto

```bash
# Si aún no tienes el proyecto
cd ~/Desktop
git clone https://github.com/paxapos/fiscalberry.git
cd fiscalberry

# Cambiar a la rama de Android
git checkout fiscalberry-android
```

---

## 🏗️ Paso 4: Compilar el APK

### Opción A: Usando el script automático (Recomendado)

```bash
# Dar permisos de ejecución al script
chmod +x build-android.sh

# Ejecutar el script
./build-android.sh

# Seleccionar opción:
# 1 = Compilar Debug (primera vez)
# 3 = Limpiar y recompilar (si hay errores)
```

### Opción B: Manualmente con buildozer

```bash
# Primera compilación (tarda 20-40 minutos)
buildozer android debug

# El APK estará en: bin/fiscalberry-*-debug.apk
```

---

## 📱 Paso 5: Instalar en Android

### Preparar el dispositivo Android:

1. **Habilitar Opciones de Desarrollador:**
   - Ve a `Configuración > Acerca del teléfono`
   - Toca 7 veces en "Número de compilación"

2. **Habilitar Depuración USB:**
   - Ve a `Configuración > Opciones de desarrollador`
   - Activa "Depuración USB"

3. **Conectar por USB:**
   - Conecta el dispositivo al PC
   - Acepta el diálogo de "Permitir depuración USB"

### Instalar el APK:

```bash
# Instalar ADB si no lo tienes
sudo apt install adb

# Verificar que el dispositivo está conectado
adb devices

# Instalar el APK
adb install -r bin/fiscalberry-*-debug.apk

# Ver logs en tiempo real (opcional)
adb logcat | grep -E "python|Fiscalberry"
```

### Alternativa - Instalación Manual:

1. Copia el APK del directorio `bin/` a tu dispositivo
2. En el dispositivo, abre el archivo APK
3. Permite la instalación de "fuentes desconocidas" si es necesario
4. Instala la app

---

## 🔍 Paso 6: Primera Ejecución y Permisos

Al abrir Fiscalberry por primera vez:

1. **La app solicitará permisos:**
   - ✅ Almacenamiento (para config.ini)
   - ✅ Red (para RabbitMQ/SocketIO)
   - ✅ USB (para impresoras)
   - ✅ Bluetooth (para impresoras BT)
   - ✅ Ubicación (requerido para Bluetooth en Android 10+)

2. **Conectar impresora USB:**
   - Conecta la impresora fiscal vía USB OTG
   - Android mostrará un diálogo "Permitir acceso a [dispositivo USB]"
   - Marca "Usar siempre para esta aplicación"
   - Toca "Aceptar"

3. **Adoptar comercio:**
   - La app mostrará el ID de cola de impresión
   - Visita el link de adopción
   - Completa la adopción en la web
   - La app se conectará automáticamente

---

## 🐛 Solución de Problemas

### Error: "buildozer: command not found"

```bash
# Reinstalar buildozer
pip3 install --upgrade --force-reinstall buildozer

# Agregar al PATH
export PATH=$PATH:~/.local/bin
```

### Error: "No Android SDK found"

Buildozer descargará el SDK automáticamente en la primera compilación. Esto es normal y puede tardar 10-20 minutos.

### Error: "Recipe for ... has no version specified"

```bash
# Limpiar cache y recompilar
buildozer android clean
buildozer android debug
```

### Error: Compilación falla con errores de NDK

```bash
# Limpiar completamente
rm -rf .buildozer
buildozer android debug
```

### La app no detecta la impresora USB

1. Verifica que el cable USB OTG funcione
2. Prueba con otra app USB (USB OTG Checker)
3. Revisa que diste permiso USB cuando lo pidió
4. Desconecta y vuelve a conectar la impresora

### La app se cierra cuando sale de primer plano

Esto es normal si no hay un servicio de segundo plano activo. Verifica en los logs:

```bash
adb logcat | grep "AndroidService"
```

---

## 📝 Archivos Importantes

```
fiscalberry/
├── buildozer.spec          # Configuración de compilación
├── build-android.sh        # Script de build automático
├── requirements.android.txt # Dependencias Python
├── bin/                    # APKs generados aquí
│   └── fiscalberry-*-debug.apk
├── .buildozer/             # Cache de compilación (muy grande)
└── src/
    ├── fiscalberry/
    │   ├── gui.py          # Entry point Android
    │   └── common/
    │       ├── printer_detector.py      # Detección USB Android
    │       └── android_permissions.py   # Gestión de permisos
    └── fiscalberryservice/
        └── android.py      # Servicio background
```

---

## 🎯 Comandos Útiles

```bash
# Compilación
buildozer android debug              # Compilar debug
buildozer android release           # Compilar release (requiere keystore)
buildozer android clean             # Limpiar cache

# Deployment
adb devices                         # Listar dispositivos conectados
adb install -r bin/*.apk           # Instalar/actualizar APK
adb uninstall com.paxapos.fiscalberry  # Desinstalar app

# Logs
adb logcat                          # Ver todos los logs
adb logcat | grep python            # Solo logs de Python
adb logcat | grep Fiscalberry       # Solo logs de Fiscalberry
adb logcat -c                       # Limpiar logs

# Info del dispositivo
adb shell getprop ro.build.version.release  # Versión de Android
adb shell pm list packages | grep fiscal     # Verificar si está instalado
```

---

## 📊 Tiempos Estimados

| Acción | Primera vez | Subsecuentes |
|--------|-------------|--------------|
| Instalar dependencias | 5-10 min | - |
| Instalar buildozer | 2-3 min | - |
| Primera compilación | 30-40 min | - |
| Compilaciones posteriores | 3-5 min | 3-5 min |
| Instalación en dispositivo | 1-2 min | 1-2 min |

**Total primera vez:** ~40-55 minutos  
**Total subsecuentes:** ~5-10 minutos

---

## ✅ Checklist Final

Antes de considerar la compilación exitosa:

- [ ] APK generado en `bin/`
- [ ] APK se instala sin errores
- [ ] App abre sin crashear
- [ ] Se solicitan permisos correctamente
- [ ] Config.ini se crea en la ubicación correcta
- [ ] Se detecta la impresora USB
- [ ] Se puede adoptar el comercio
- [ ] Conexión a RabbitMQ funciona
- [ ] Conexión a SocketIO funciona
- [ ] Se pueden enviar trabajos de impresión

---

## 🆘 Soporte

Si encuentras problemas:

1. **Revisa los logs:**
   ```bash
   adb logcat | grep -E "python|Fiscalberry|ERROR"
   ```

2. **Verifica el issue en GitHub:**
   https://github.com/paxapos/fiscalberry/issues

3. **Documentación:**
   - `docs/android_migration_plan.md`
   - `docs/android_changes_summary.md`

---

## 🎉 ¡Listo!

Una vez completados todos los pasos, tendrás Fiscalberry funcionando completamente en tu PC Android con soporte para:

- ✅ Impresoras USB fiscales
- ✅ Conexión a RabbitMQ
- ✅ SocketIO para comunicación
- ✅ Servicio en segundo plano
- ✅ Configuración persistente

**¡Buena suerte con la compilación!** 🚀
