# Instalador de Windows (Inno Setup)

La GUI de Windows se distribuye como `FiscalberrySetup.exe`, generado con
[Inno Setup 6](https://jrsoftware.org/isinfo.php) a partir de
[`installer/fiscalberry.iss`](../installer/fiscalberry.iss).

## Qué hace el instalador

- Se instala **por usuario** (`PrivilegesRequired=lowest`), sin cartel de UAC,
  en `%LOCALAPPDATA%\Programs\Fiscalberry`.
- Empaqueta la carpeta onedir completa de PyInstaller (`dist\fiscalberry-gui\`:
  el ejecutable y su `_internal\`).
- Crea el acceso en el menú Inicio y, opcionalmente, en el escritorio.
- Registra el arranque con Windows en `HKCU\...\Run` con `--minimized`.
- La versión sale de los metadatos del ejecutable (`GetFileVersion`), que a su
  vez se generan desde `src/fiscalberry/version.py`: no hay que editarla a mano.
- `config.ini` y los logs viven fuera de la carpeta de instalación
  (`%LOCALAPPDATA%\Fiscalberry\Fiscalberry`), así que desinstalar no borra la
  vinculación del comercio.

El CLI de Windows se sigue publicando como `fiscalberry-windows-cli.zip`.

## Compilar localmente

Requisitos: Python 3.11+, las dependencias de `requirements.kivy.txt`,
PyInstaller e Inno Setup 6.

```cmd
build-installer.bat
```

O a mano:

```cmd
set PYTHONPATH=src
pyinstaller --clean -y fiscalberry-gui.spec
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer\fiscalberry.iss
```

El resultado queda en `dist\FiscalberrySetup.exe`.

## CI

`.github/workflows/build-release.yml` compila el instalador en el job de
Windows, lo instala en silencio, corre `--selftest` sobre el binario instalado,
lo desinstala y publica `FiscalberrySetup.exe` en el release junto con su
entrada en `SHA256SUMS`.
