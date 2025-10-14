#!/bin/bash

# Script para compilar Fiscalberry APK en Linux
# Requiere: buildozer, python3, git

set -e  # Salir si hay error

echo "================================================"
echo "  Fiscalberry Android - Script de Compilación"
echo "================================================"
echo ""

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Función para imprimir con color
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Verificar que estamos en el directorio correcto
if [ ! -f "buildozer.spec" ]; then
    print_error "buildozer.spec no encontrado"
    print_error "Ejecuta este script desde el directorio raíz de Fiscalberry"
    exit 1
fi

print_success "Directorio correcto detectado"

# Verificar si buildozer está instalado
if ! command -v buildozer &> /dev/null; then
    print_warning "Buildozer no está instalado"
    echo ""
    echo "Instalando buildozer..."
    echo ""
    
    # Instalar dependencias
    sudo apt update
    sudo apt install -y git zip unzip openjdk-17-jdk python3-pip \
        autoconf libtool pkg-config zlib1g-dev libncurses5-dev \
        libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev \
        build-essential ccache libltdl-dev
    
    # Instalar buildozer y cython
    pip3 install --upgrade buildozer cython
    
    print_success "Buildozer instalado"
else
    print_success "Buildozer ya está instalado"
fi

# Verificar versión de Python
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
print_success "Python version: $PYTHON_VERSION"

# Verificar versión de Java
JAVA_VERSION=$(java -version 2>&1 | head -n 1)
print_success "Java: $JAVA_VERSION"

echo ""
echo "Opciones de compilación:"
echo "  1) Debug (rápido, permite depuración)"
echo "  2) Release (optimizado, requiere keystore)"
echo "  3) Limpiar y compilar Debug"
echo "  4) Solo limpiar cache"
echo ""
read -p "Selecciona una opción (1-4): " option

case $option in
    1)
        echo ""
        print_warning "Compilando APK Debug..."
        echo ""
        buildozer android debug
        ;;
    2)
        echo ""
        print_warning "Compilando APK Release..."
        echo ""
        print_warning "Asegúrate de tener configurado el keystore en buildozer.spec"
        buildozer android release
        ;;
    3)
        echo ""
        print_warning "Limpiando cache anterior..."
        buildozer android clean
        print_success "Cache limpiado"
        echo ""
        print_warning "Compilando APK Debug..."
        buildozer android debug
        ;;
    4)
        echo ""
        print_warning "Limpiando cache..."
        buildozer android clean
        print_success "Cache limpiado"
        exit 0
        ;;
    *)
        print_error "Opción inválida"
        exit 1
        ;;
esac

# Verificar si la compilación fue exitosa
if [ $? -eq 0 ]; then
    echo ""
    echo "================================================"
    print_success "COMPILACIÓN EXITOSA"
    echo "================================================"
    echo ""
    
    # Buscar el APK generado
    APK_PATH=$(find bin/ -name "*.apk" -type f 2>/dev/null | head -n 1)
    
    if [ -n "$APK_PATH" ]; then
        APK_SIZE=$(du -h "$APK_PATH" | cut -f1)
        print_success "APK generado: $APK_PATH"
        print_success "Tamaño: $APK_SIZE"
        echo ""
        
        echo "Para instalar en tu dispositivo Android:"
        echo ""
        echo "  1. Conecta el dispositivo por USB"
        echo "  2. Habilita 'Depuración USB' en Configuración > Opciones de desarrollador"
        echo "  3. Ejecuta: adb install -r $APK_PATH"
        echo ""
        echo "O copia el APK al dispositivo y ábrelo manualmente."
        echo ""
        
        # Ofrecer instalar automáticamente
        read -p "¿Deseas instalar el APK ahora? (s/n): " install_now
        if [ "$install_now" = "s" ] || [ "$install_now" = "S" ]; then
            if command -v adb &> /dev/null; then
                echo ""
                print_warning "Instalando APK..."
                adb install -r "$APK_PATH"
                
                if [ $? -eq 0 ]; then
                    print_success "APK instalado correctamente"
                    echo ""
                    read -p "¿Deseas ver los logs en tiempo real? (s/n): " show_logs
                    if [ "$show_logs" = "s" ] || [ "$show_logs" = "S" ]; then
                        echo ""
                        print_warning "Mostrando logs (Ctrl+C para salir)..."
                        echo ""
                        adb logcat | grep -E "python|Fiscalberry"
                    fi
                else
                    print_error "Error al instalar APK"
                fi
            else
                print_warning "ADB no encontrado. Instala con: sudo apt install adb"
            fi
        fi
    else
        print_warning "No se encontró el APK generado en bin/"
    fi
else
    echo ""
    echo "================================================"
    print_error "ERROR EN LA COMPILACIÓN"
    echo "================================================"
    echo ""
    echo "Revisa los logs arriba para más detalles."
    echo ""
    echo "Errores comunes:"
    echo "  - Falta alguna dependencia del sistema"
    echo "  - Error en requirements.txt o buildozer.spec"
    echo "  - Problema con NDK/SDK (se descargan automáticamente)"
    echo ""
    echo "Intenta limpiar el cache: ./build-android.sh -> opción 4"
    exit 1
fi
