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
echo Seleccione qué versión desea compilar:
echo 1. Fiscalberry CLI (Sin interfaz gráfica)
echo 2. Fiscalberry GUI (Con interfaz gráfica)
echo 3. Ambas (CLI y GUI)
echo.
set /p opcion="Opción (1/2/3): "

if "%opcion%"=="1" goto compile_cli
if "%opcion%"=="2" goto compile_gui
if "%opcion%"=="3" goto compile_both

echo [ERROR] Opción inválida.
pause
exit /b 1

:compile_cli
call :build_app cli requirements.txt fiscalberry-cli.spec fiscalberry-cli
if errorlevel 1 goto error_finish
goto finish

:compile_gui
call :build_app gui requirements.kivy.txt fiscalberry-gui.spec fiscalberry-gui
if errorlevel 1 goto error_finish
goto finish

:compile_both
call :build_app cli requirements.txt fiscalberry-cli.spec fiscalberry-cli
if errorlevel 1 goto error_finish
call :build_app gui requirements.kivy.txt fiscalberry-gui.spec fiscalberry-gui
if errorlevel 1 goto error_finish
goto finish

:build_app
set APP_TYPE=%1
set REQ_FILE=%2
set SPEC_FILE=%3
set APP_NAME=%4

echo.
echo ============================================================
echo    COMPILANDO %APP_NAME%
echo ============================================================
echo [1/4] Creando entorno virtual venv.%APP_TYPE%...

REM Verificar si el venv existe y es válido
if exist "venv.%APP_TYPE%\Scripts\python.exe" (
    echo [INFO] Entorno virtual ya existe y es válido
) else (
    REM Borrar venv corrupto si existe
    if exist "venv.%APP_TYPE%" (
        echo [INFO] Borrando entorno virtual corrupto...
        rmdir /s /q venv.%APP_TYPE%
    )
    
    echo [INFO] Creando nuevo entorno virtual...
    python -m venv venv.%APP_TYPE%
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual
        exit /b 1
    )
    
    REM Verificar que se creó correctamente
    if not exist "venv.%APP_TYPE%\Scripts\python.exe" (
        echo [ERROR] El entorno virtual no se creó correctamente
        exit /b 1
    )
)

echo [2/4] Instalando dependencias...
venv.%APP_TYPE%\Scripts\python.exe -m pip install --upgrade pip -q
if errorlevel 1 (
    echo [ERROR] No se pudo actualizar pip
    exit /b 1
)

venv.%APP_TYPE%\Scripts\pip.exe install -r %REQ_FILE% -q
if errorlevel 1 (
    echo [ERROR] No se pudieron instalar las dependencias
    exit /b 1
)

venv.%APP_TYPE%\Scripts\pip.exe install pyinstaller -q
if errorlevel 1 (
    echo [ERROR] No se pudo instalar pyinstaller
    exit /b 1
)

echo [3/4] Compilando %APP_NAME%.exe...
venv.%APP_TYPE%\Scripts\pyinstaller.exe %SPEC_FILE% --clean -y
if errorlevel 1 (
    echo [ERROR] La compilación falló
    exit /b 1
)

echo [4/4] Limpiando archivos temporales...
if exist "build\%APP_NAME%" rmdir /s /q build\%APP_NAME%

REM Salir exitosamente de la subrutina
exit /b 0

:error_finish
echo.
echo ============================================================
echo    [ERROR] LA COMPILACIÓN HA FALLADO
echo ============================================================
echo Revisa los mensajes anteriores para ver el error exacto.
echo.
pause
exit /b 1

:finish
echo.
echo ============================================================
echo    COMPILACION COMPLETADA!
echo ============================================================
echo.
echo Los ejecutables están en: dist\
echo.
pause
