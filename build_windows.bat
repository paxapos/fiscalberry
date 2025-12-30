@echo off
REM ============================================================
REM  FISCALBERRY CLI - Script de compilación para Windows
REM ============================================================
REM  Ejecutar este script desde la carpeta raíz de fiscalberry
REM  Requisitos: Python 3.8+ instalado
REM ============================================================

echo.
echo ============================================================
echo    FISCALBERRY CLI - Compilador para Windows
echo ============================================================
echo.

REM Verificar que Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instalalo desde https://python.org
    pause
    exit /b 1
)

echo [1/4] Creando entorno virtual...
if not exist "venv.cli" (
    python -m venv venv.cli
)

echo [2/4] Activando entorno virtual e instalando dependencias...
call venv.cli\Scripts\activate.bat

pip install --upgrade pip -q
pip install -r requirements.cli.txt -q
pip install pyinstaller -q

echo [3/4] Compilando fiscalberry-cli.exe...
pyinstaller fiscalberry-cli.spec --clean -y

echo [4/4] Limpiando archivos temporales...
rmdir /s /q build\fiscalberry-cli 2>nul

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
