[app]

# === FISCALBERRY ANDROID CLI (Headless - Sin UI) ===
# Versión sin Kivy para servicio puro en background

title = Fiscalberry CLI
package.name = fiscalberry_cli
package.domain = com.paxapos

source.dir = src
source.main_py = android_cli/main.py

# Extensiones (sin .kv - no hay UI)
source.include_exts = py,json,pem,crt,ico

source.include_patterns = assets/*, capabilities.json

version.regex = VERSION = ['"](.*)["']
version.filename = %(source.dir)s/fiscalberry/version.py

# === REQUIREMENTS SIN KIVY ===
# APK resultante: ~12-15 MB vs ~49 MB (UI version)
requirements = hostpython3,python3,pyjnius,pika,python-socketio[client],python-engineio,python-escpos,qrcode,pillow,pyserial,pyusb,requests,platformdirs,bidict,simple-websocket,wsproto,h11,urllib3,certifi,idna,chardet,python-barcode,appdirs,setuptools,six,pyyaml,importlib-resources,filetype,argcomplete

# Icon (mínimo requerido)
icon.filename = %(source.dir)s/fiscalberry/ui/assets/fiscalberry.png

orientation = portrait

# === SERVICE (CLI) ===
services = fiscalberryservice:android_cli.android_service.py:foreground:sticky

#
# Android specific
#

fullscreen = 0

# Permisos (mismos que UI version)
android.permissions = INTERNET,FOREGROUND_SERVICE,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,WAKE_LOCK,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_COARSE_LOCATION,ACCESS_FINE_LOCATION,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

# API levels (33 = máximo para NDK r25b)
android.api = 33
android.minapi = 22
android.ndk_api = 22

android.accept_sdk_license = True

# Archs
android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True
android.release_artifact = apk
android.release = false
android.debug_artifact = apk
android.debug = true
android.private_storage = True

#
# Python for android (p4a) specific
#

# Custom recipes (con fix SDL2 para webview)
p4a.local_recipes = my_recipes

# === BOOTSTRAP: webview (SIN SDL2/OpenGL) ===
# webview es para servicios headless sin UI
# Elimina ~15 MB de dependencias gráficas vs sdl2
p4a.bootstrap = webview

# Environment variables
p4a.extra_env = LDFLAGS=-Wl,--hash-style=both, CFLAGS=-fPIC

[buildozer]

log_level = 2
warn_on_root = 1
