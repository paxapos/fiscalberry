# Compilar APK

source venv.buildozer/bin/activate

# Limpiar build anterior

buildozer android clean

# Recompilar con el código corregido

buildozer android debug

# Instalar en dispositivo

adb install -r bin/fiscalberry-\*.apk

# Verificar logs

adb logcat -c && adb logcat -s python:\*

# Actualizar dependencias

pip install --upgrade -r requirements.txt  
pip freeze > requirements.txt
buildozer android clean

# Ejecutar aplicación en emulador

buildozer android deploy run

# Empaquetar para distribución

buildozer android release

# Reiniciar servidor ADB

adb kill-server
adb start-server

---

# Activar entorno virtual

source venv.cli/bin/activate

# Ejecutar main.py

python -m fiscalberry.cli.main

---

# Compilar versión CLI (Línea de Comandos)

# Desde el directorio principal (donde están los archivos .spec)

# 1. Activar el entorno virtual correspondiente

source venv.cli/bin/activate

# 2. Compilar con PyInstaller

pyinstaller fiscalberry-cli.spec

---

# Compilar versión GUI (Interfaz Gráfica)

# Desde el directorio principal (donde están los archivos .spec)

# 1. Activar el entorno virtual correspondiente

source venv.gui/bin/activate

# 2. Compilar con PyInstaller

pyinstaller fiscalberry-gui.spec
