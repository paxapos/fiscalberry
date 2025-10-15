#!/bin/bash
# Script para instalar APK y ver logs en tiempo real
# Uso: ./install-and-log.sh

set -e

echo "=================================================="
echo "📱 Instalador y Monitor de Logs - Fiscalberry"
echo "=================================================="
echo ""

# Verificar que el emulador esté conectado
echo "🔍 Verificando dispositivos conectados..."
DEVICES=$(adb devices | grep -v "List of devices" | grep "device$" | wc -l)

if [ "$DEVICES" -eq 0 ]; then
    echo "❌ No hay dispositivos conectados"
    echo "💡 Inicia el emulador primero:"
    echo "   ~/Android/Sdk/emulator/emulator -avd Fiscalberry_Test &"
    exit 1
fi

echo "✅ Dispositivo(s) conectado(s): $DEVICES"
echo ""

# Buscar el APK más reciente
echo "🔍 Buscando APK en bin/..."
APK=$(ls -t bin/fiscalberry-*.apk 2>/dev/null | head -1)

if [ -z "$APK" ]; then
    echo "❌ No se encontró ningún APK en bin/"
    echo "💡 Compila primero con: buildozer android debug"
    exit 1
fi

echo "📦 APK encontrado: $APK"
APK_SIZE=$(du -h "$APK" | cut -f1)
echo "   Tamaño: $APK_SIZE"
echo ""

# Desinstalar versión anterior si existe
echo "🗑️  Desinstalando versión anterior (si existe)..."
adb uninstall com.paxapos.fiscalberry 2>/dev/null && echo "   ✓ Versión anterior desinstalada" || echo "   ℹ No había versión anterior"
echo ""

# Instalar nueva versión
echo "📲 Instalando nueva versión..."
if adb install -r "$APK"; then
    echo "✅ Instalación exitosa"
else
    echo "❌ Error en la instalación"
    exit 1
fi
echo ""

# Limpiar logs anteriores
echo "🧹 Limpiando logs anteriores..."
adb logcat -c
echo "✅ Logs limpiados"
echo ""

echo "=================================================="
echo "🚀 LANZANDO APLICACIÓN"
echo "=================================================="
echo ""
echo "Presiona Ctrl+C para detener el monitoreo de logs"
echo ""
sleep 2

# Iniciar la app
adb shell am start -n com.paxapos.fiscalberry/.MainActivity

echo ""
echo "📋 Monitoreando logs (filtrando Python, Kivy, Fiscalberry)..."
echo "=================================================="
echo ""

# Monitorear logs con colores
adb logcat | grep --color=auto -E "(python|Python|kivy|Kivy|fiscalberry|Fiscalberry|FATAL|ERROR|AndroidRuntime)"
