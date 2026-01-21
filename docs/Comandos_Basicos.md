***************************************
################APK################
***************************************

### Primeros Pasos


# 1. Crear entorno virtual dedicado para buildozer
python3.12 -m venv venv.buildozer

# 2. Activar entorno virtual
source venv.buildozer/bin/activate

# 3. Instalar dependencias de compilación
pip install buildozer cython

# 4. Primera compilación (descarga NDK/SDK automáticamente)
buildozer android debug


### Comandos de Compilación


# Activar entorno (siempre antes de compilar)
source venv.buildozer/bin/activate

# Compilar APK debug
buildozer android debug

# Compilar APK release (para distribución)
buildozer android release

# Limpiar build y recompilar desde cero
buildozer android clean && buildozer android debug


### Instalación en Dispositivo


# Instalar APK en dispositivo conectado
adb install -r bin/fiscalberry-*.apk

# Compilar, instalar y ejecutar en un solo comando
buildozer android deploy run


### Utilidades ADB


# Reiniciar servidor ADB (si no detecta dispositivo)
adb kill-server && adb start-server

# Ver logs de Python en tiempo real
adb logcat -c && adb logcat -s "python:*"

# Ver TODOS los logs del dispositivo
adb logcat

# Filtrar logs por errores
adb logcat *:E


***************************************
################CLI################
***************************************

### Primeros Pasos


# 1. Ir al directorio del proyecto
cd /mnt/datos/repos/fiscalberry

# 2. Crear entorno virtual
python3.12 -m venv venv.cli

# 3. Activar entorno virtual
source venv.cli/bin/activate

# 4. Instalar dependencias
pip install -r requirements.txt


### Ejecutar Fiscalberry CLI


# Activar entorno (siempre antes de ejecutar)
source venv.cli/bin/activate

# Ejecutar fiscalberry
python -m fiscalberry.cli.main


### Actualizar Dependencias


source venv.cli/bin/activate
pip install --upgrade -r requirements.txt


***************************************
################GUI################
***************************************

### Primeros Pasos


# 1. Ir al directorio del proyecto
cd /mnt/datos/repos/fiscalberry

# 2. Crear entorno virtual con Python 3.12
python3.12 -m venv venv.gui

# 3. Activar entorno virtual
source venv.gui/bin/activate

# 4. Instalar dependencias (incluye Kivy)
pip install -r requirements.txt


### Ejecutar Fiscalberry GUI


# Opción 1: Usando el script instalado
source venv.gui/bin/activate
fiscalberry_gui

# Opción 2: Ruta completa (sin activar venv)
venv.gui/bin/fiscalberry_gui

***************************************
#################DEBUG#################
***************************************

### Ver Logs en Tiempo Real

# CLI/GUI - Ver archivo de log actual
tail -f ~/.fiscalberry/fiscalberry.log

# Android - Ver logs de Python
adb logcat -c && adb logcat -s "python:*"


### Buscar Errores en Logs


# Buscar errores en el log
grep -i "error\|exception\|traceback" ~/.fiscalberry/fiscalberry.log

# Ver últimas 50 líneas del log
tail -n 50 ~/.fiscalberry/fiscalberry.log
