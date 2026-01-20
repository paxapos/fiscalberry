################APK################
//FUNCIONA CON API 26 EN ADELANTE

# Crear entorno virtual y activarlo
python3.12 -m venv venv.buildozer
source venv.buildozer/bin/activate
pip install buildozer cython
buildozer android debug


# Compilar APK
source venv.buildozer/bin/activate

# Limpiar build anterior
buildozer android clean

# Recompilar con el código corregido  
buildozer android debug

# Instalar en dispositivo
adb install -r bin/fiscalberry-*.apk

# Verificar logs
adb logcat -c && adb logcat -s python:*

# Actualizar dependencias
pip install --upgrade -r requirements.txt   
buildozer android clean

# Ejecutar aplicación en emulador
buildozer android deploy run

# Empaquetar para distribución
buildozer android release

# Reiniciar servidor ADB
adb kill-server
adb start-server



---------------------------------------------------------
################CLI################
//FUNCIONA HASTA PYTHON 3.14

# Cambiar al directorio del proyecto
cd /mnt/datos/repos/fiscalberry 

# Activar entorno virtual
source venv.cli/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar main.py
python -m fiscalberry.cli.main


---------------------------------------------------------
################GUI################
//FUNCIONA HASTA PYTHON 3.12

# Cambiar al directorio del proyecto
cd /mnt/datos/repos/fiscalberry 

# Crear entorno virtual y activarlo
python3.12 -m venv venv.gui

# Activar entorno virtual
source venv.gui/bin/activate  

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar fiscalberry_gui
venv.gui/bin/fiscalberry_gui 