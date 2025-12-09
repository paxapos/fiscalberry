# Compilar APK
source venv.buildozer/bin/activate

# Limpiar build anterior
buildozer android clean

# Recompilar con el código corregido  
buildozer android debug

# Instalar en dispositivo
adb install -r bin/fiscalberry-*.apk

# Verificar logs
adb logcat -s python:* | grep -i permission

# Limpiar compilación
buildozer android clean

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


