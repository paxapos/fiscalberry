#!/bin/bash
set -e

# Activar entorno virtual
source venv.buildozer/bin/activate

# Compilar Fiscalberry APK
buildozer android debug

# Mostrar ubicación del APK generado
ls -lh bin/*.apk || true
