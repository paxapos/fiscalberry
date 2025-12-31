@echo off
REM ============================================================
REM  FISCALBERRY CLI - Script de compilación para Windows
REM ============================================================
REM  Ejecutar este script desde la carpeta raíz de fiscalberry
REM  Requisitos: Python 3.8+ instalado y en el PATH
REM ============================================================

echo.
echo ============================================================
echo    FISCALBERRY CLI - Compilador para Windows
echo ============================================================
echo.

REM Verificar que Python está instalado
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en el PATH.
    echo         Instalalo desde https://python.org
    echo         IMPORTANTE: Marca la opcion "Add Python to PATH" al instalar
    pause
    exit /b 1
)

echo [INFO] Python encontrado:
python --version

echo.
echo [1/4] Creando entorno virtual...
if not exist "venv.cli" (
    python -m venv venv.cli
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual
        pause
        exit /b 1
    )
)

echo [2/4] Instalando dependencias...
REM Usar rutas completas en lugar de activar el venv
venv.cli\Scripts\python.exe -m pip install --upgrade pip -q
if errorlevel 1 (
    echo [ERROR] No se pudo actualizar pip
    pause
    exit /b 1
)

venv.cli\Scripts\pip.exe install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] No se pudieron instalar las dependencias
    pause
    exit /b 1
)

venv.cli\Scripts\pip.exe install pyinstaller -q
if errorlevel 1 (
    echo [ERROR] No se pudo instalar pyinstaller
    pause
    exit /b 1
)

echo [3/4] Compilando fiscalberry-cli.exe...
venv.cli\Scripts\pyinstaller.exe fiscalberry-cli.spec --clean -y
if errorlevel 1 (
    echo [ERROR] La compilacion fallo
    pause
    exit /b 1
)

echo [4/4] Limpiando archivos temporales...
if exist "build\fiscalberry-cli" rmdir /s /q build\fiscalberry-cli

echo.
echo ============================================================
echo    COMPILACION COMPLETADA!
echo ============================================================
echo.
echo El ejecutable esta en: dist\fiscalberry-cli.exe
echo.
echo Para ejecutar:
echo    dist\fiscalberry-cli.exe
echo.
pause
