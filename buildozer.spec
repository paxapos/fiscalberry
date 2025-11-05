[app]

# (str) Title of your application
title = Fiscalberry

# (str) Package name
package.name = fiscalberry

# (str) Package domain (needed for android/ios packaging)
package.domain = com.paxapos

# (str) Source code directory (relative to spec file)
source.dir = src

# (str) Main python file to execute (relative to source.dir)
# Buildozer defaults to main.py, specify your actual entry point
source.main_py = fiscalberry/gui.py

# (list) Source files extensions to include
source.include_exts = py,png,jpg,kv,atlas,json,svg,pem,crt,ico # Add other extensions if needed (e.g., fonts, sounds)

# (list) List of inclusions using pattern matching (relative to source.dir)
# Include assets and the capabilities.json at the root of src
source.include_patterns = assets/*, capabilities.json

# (list) Source files to exclude (let empty to not exclude anything)
# source.exclude_exts = spec

# (list) List of directory to exclude (let empty to not exclude anything)
# source.exclude_dirs = tests, bin, venv

# (list) List of exclusions using pattern matching
# source.exclude_patterns = license,images/*/*.jpg

# (str) Application versioning
# version = x.x
# Optional: Use regex to get version from your code (e.g., __init__.py)
version.regex = VERSION = ['"](.*)['"]
version.filename = %(source.dir)s/fiscalberry/version.py

# (list) Application requirements
# Comma-separated list of recipes or pure-Python packages.
# IMPORTANT: Verify each requirement. Check if python-for-android recipes exist for non-pure-Python libs.
# Remove unnecessary dependencies (like pika if not used on mobile, pywin32,).
# NOTE: python-escpos extras expanded individually due to buildozer parsing limitations
# NOTE: kivy SIN [base] para forzar compilación desde source en lugar de usar wheels
# NOTE: Dependencias COMPLETAS verificadas del proyecto:
# - python-escpos: appdirs, argcomplete, importlib-resources, Pillow, python-barcode, PyYAML, qrcode, setuptools, six
# - python-socketio: python-engineio, bidict, simple-websocket, wsproto, h11
# - Kivy: filetype (para carga de imágenes)
# - Proyecto: requests (urllib3, certifi, idna, chardet), platformdirs, pyjnius, pika, pyserial, pyusb
requirements = hostpython3,python3,kivy,python-escpos,python-barcode,appdirs,argcomplete,importlib-resources,pyyaml,setuptools,six,qrcode,pillow,pyserial,pyusb,python-socketio[client],python-engineio,bidict,simple-websocket,wsproto,h11,requests,urllib3,certifi,idna,chardet,platformdirs,pyjnius,pika,filetype


# (str) Presplash of the application
presplash.filename = %(source.dir)s/fiscalberry/ui/assets/fiscalberry.png

# (str) Icon of the application
icon.filename = %(source.dir)s/fiscalberry/ui/assets/fiscalberry.png

# (list) Supported orientations
orientation = portrait

# (list) List of service to declare
# Ensure fiscalberryservice.android.py is correctly implemented for p4a services
services = fiscalberryservice:fiscalberryservice.android.py:foreground:sticky

#
# Android specific
#

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (string) Presplash background color
android.presplash_color = purple

# (list) Permissions
# Permisos necesarios para Fiscalberry Android:
# - INTERNET: Conexión a RabbitMQ, SocketIO y WebView
# - FOREGROUND_SERVICE: Servicio en segundo plano
# - ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE: Detectar conectividad y para WebView
# - WAKE_LOCK: Mantener el dispositivo activo durante impresión
# - READ/WRITE_EXTERNAL_STORAGE: Guardar configuración y logs
# - BLUETOOTH*: Para impresoras Bluetooth
# - ACCESS_COARSE_LOCATION: Requerido para escaneo Bluetooth en Android 10+
android.permissions = INTERNET,FOREGROUND_SERVICE,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,WAKE_LOCK,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_COARSE_LOCATION,ACCESS_FINE_LOCATION

# (list) features (adds uses-feature tags to manifest)
# Habilitar soporte para impresoras USB y Bluetooth
# NOTA: android.features no soportado en esta versión de buildozer, se agregará manualmente al AndroidManifest.xml
# android.features = android.hardware.usb.host,android.hardware.bluetooth

# (int) Target Android API, should be as high as possible.
android.api = 35

# (int) Minimum API your APK / AAB will support.
android.minapi = 28

# (int) Android NDK API to use. Should usually match android.minapi.
android.ndk_api = 28

android.sdkmanager_path = /home/vap/Android/Sdk/cmdline-tools/latest/bin/sdkmanager

# (bool) Automatically accept SDK license agreements. Useful for CI.
android.accept_sdk_license = True

# (str) Android entry point, default is ok for Kivy-based app
# android.entrypoint = org.kivy.android.PythonActivity

# (str) Full name including package path of the Java class that implements Android Activity
# android.activity_class_name = org.kivy.android.PythonActivity

# (str) Full name including package path of the Java class that implements Python Service
# android.service_class_name = org.kivy.android.PythonService

# (list) The Android archs to build for
# android.archs = arm64-v8a
android.archs = arm64-v8a, armeabi-v7a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

# (str) The format used to package the app for release mode (aab or apk). aab is recommended for Play Store.
android.release_artifact = apk
android.release = false

# (str) The format used to package the app for debug mode (apk).
android.debug_artifact = apk
android.debug = true

# ====== CONFIGURACIÓN PARA DEEP LINKS ======
# Esto permite que la app se abra desde links de la web

# (str) XML file for additional intent filters
# Este archivo se debe crear en: templates/AndroidManifest.tmpl.xml
android.manifest.intent_filters = templates/intent_filters.xml

# (str) Android app theme
# Opcional: usar tema Material Design
# android.theme = @android:style/Theme.Material.Light.DarkActionBar

# (str) Android logcat filters to use
# android.logcat_filters = *:S python:D

# ====== META-DATA PARA APP LINKS ======
# Esto mejora la vinculación automática sin necesidad de elegir navegador
# android.meta_data = asset_statements:@xml/assetlinks

#
# Python for android (p4a) specific
#

# (str) python-for-android branch to use, defaults to master
# p4a.branch = master

# (str) The directory in which python-for-android should look for your own build recipes (if any)
p4a.local_recipes = my_recipes

# (str) Bootstrap to use. Leave empty to let buildozer choose.
p4a.bootstrap = sdl2

# NOTA: La compilación desde source se fuerza en my_recipes/kivy/__init__.py

#
# iOS specific - Not relevant for Android build
#
# [...]

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
