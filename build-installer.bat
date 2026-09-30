@echo off
REM Compila FiscalberrySetup.exe en Windows (lo mismo que hace la CI).
REM Requiere: Python 3.11+ con requirements.kivy.txt, PyInstaller e Inno Setup 6.
REM El instalador empaqueta solo la GUI (onedir); el CLI se sigue publicando en zip.

echo ============================================
echo Fiscalberry - Build Windows Installer
echo ============================================
echo.

REM Verificar que estamos en el directorio correcto
if not exist "installer\fiscalberry.iss" (
    echo ERROR: No se encontro installer\fiscalberry.iss
    echo Ejecuta este script desde la raiz del proyecto
    pause
    exit /b 1
)

REM Paso 1: GUI onedir con PyInstaller (dist\fiscalberry-gui\)
echo [1/2] Compilando la GUI con PyInstaller...
set PYTHONPATH=src
pyinstaller --clean -y fiscalberry-gui.spec
if errorlevel 1 (
    echo ERROR: Fallo la compilacion de la GUI
    pause
    exit /b 1
)

REM Paso 2: instalador con Inno Setup
echo.
echo [2/2] Creando el instalador con Inno Setup...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo ERROR: Inno Setup 6 no esta instalado
    echo Descargalo desde: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

%ISCC% installer\fiscalberry.iss
if errorlevel 1 (
    echo ERROR: Fallo la creacion del instalador
    pause
    exit /b 1
)

echo.
echo ============================================
echo EXITO: dist\FiscalberrySetup.exe
echo ============================================
echo.
pause
