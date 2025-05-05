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
version.regex = __version__ = ['"](.*)['"]
version.filename = %(source.dir)s/fiscalberry/__init__.py

# (list) Application requirements
# Comma-separated list of recipes or pure-Python packages.
# IMPORTANT: Verify each requirement. Check if python-for-android recipes exist for non-pure-Python libs.
# Remove unnecessary dependencies (like pika if not used on mobile, pywin32,).
requirements = hostpython3,python3,kivy[base],python-escpos[image,qrcode,usb,serial],python-socketio[client],requests,platformdirs,pyjnius


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
# Add permissions required by your app and its dependencies (e.g., python-escpos)
android.permissions = INTERNET, FOREGROUND_SERVICE, ACCESS_NETWORK_STATE
# Example for storage (adjust based on need and target API/scoped storage):
# android.permissions = INTERNET, FOREGROUND_SERVICE, ACCESS_NETWORK_STATE, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE
# Example for Bluetooth (needed for BT printers, requires API level checks in code):
# android.permissions = INTERNET, FOREGROUND_SERVICE, ACCESS_NETWORK_STATE, BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_SCAN, BLUETOOTH_CONNECT
# Example for coarse location (sometimes needed for BT scanning on newer Android):
# android.permissions = INTERNET, FOREGROUND_SERVICE, ACCESS_NETWORK_STATE, ..., ACCESS_COARSE_LOCATION

# (list) features (adds uses-feature tags to manifest)
# Uncomment if using python-escpos with USB printers
# android.features = android.hardware.usb.host

# (int) Target Android API, should be as high as possible.
android.api = 35

# (int) Minimum API your APK / AAB will support.
android.minapi = 28

# (int) Android NDK API to use. Should usually match android.minapi.
android.ndk_api = 28

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

#
# Python for android (p4a) specific
#

# (str) python-for-android branch to use, defaults to master
# p4a.branch = master

# (str) The directory in which python-for-android should look for your own build recipes (if any)
p4a.local_recipes = my_recipes

#
# iOS specific - Not relevant for Android build
#
# [...]

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1