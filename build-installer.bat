@echo off
REM Script para compilar el instalador de Fiscalberry en Windows
REM Requiere: Python 3.11+, PyInstaller, Inno Setup 6

echo ============================================
echo Fiscalberry - Build Windows Installer
echo ============================================
echo.

REM Verificar que estamos en el directorio correcto
if not exist "installer.iss" (
    echo ERROR: No se encontro installer.iss
    echo Ejecuta este script desde la raiz del proyecto
    pause
    exit /b 1
)

REM Paso 1: Compilar ejecutables con PyInstaller
echo [1/3] Compilando ejecutables con PyInstaller...
set PYTHONPATH=src
pyinstaller fiscalberry-gui.spec
if errorlevel 1 (
    echo ERROR: Fallo la compilacion de GUI
    pause
    exit /b 1
)

pyinstaller fiscalberry-cli.spec
if errorlevel 1 (
    echo ERROR: Fallo la compilacion de CLI
    pause
    exit /b 1
)

REM Paso 2: Verificar que Inno Setup este instalado
echo.
echo [2/3] Verificando Inno Setup...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo ERROR: Inno Setup 6 no esta instalado
    echo Descargalo desde: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

REM Paso 3: Compilar instalador
echo.
echo [3/3] Creando instalador con Inno Setup...
%ISCC% installer.iss
if errorlevel 1 (
    echo ERROR: Fallo la creacion del instalador
    pause
    exit /b 1
)

echo.
echo ============================================
echo EXITO: Instalador creado en ./installer/
echo ============================================
dir installer\*.exe
echo.
pause
