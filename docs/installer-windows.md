# Instalador de Windows con Inno Setup

Este proyecto incluye un instalador profesional de Windows creado con [Inno Setup](https://jrsoftware.org/isinfo.php).

## 🎯 Características del Instalador

- ✅ **Instalación guiada** con wizard en español e inglés
- ✅ **Accesos directos** en menú inicio y escritorio (opcional)
- ✅ **Desinstalador integrado** en "Programas y características"
- ✅ **Detección de versiones anteriores** con opción de actualización
- ✅ **Configuración automática** (crea `config.ini` si no existe)
- ✅ **Incluye GUI y CLI** en una sola instalación

## 📦 Archivos Relacionados

- [`installer.iss`](file:///mnt/datos/repos/fiscalberry/installer.iss) - Script de Inno Setup
- [`build-installer.bat`](file:///mnt/datos/repos/fiscalberry/build-installer.bat) - Script para compilar localmente en Windows

## 🔧 Compilar Localmente (Windows)

### Requisitos

1. **Python 3.11+** instalado
2. **PyInstaller** instalado (`pip install pyinstaller`)
3. **Inno Setup 6** descargado desde [jrsoftware.org](https://jrsoftware.org/isdl.php)

### Pasos

```cmd
# Opción 1: Usar el script automatizado
build-installer.bat

# Opción 2: Manual
# 1. Compilar ejecutables
set PYTHONPATH=src
pyinstaller fiscalberry-gui.spec
pyinstaller fiscalberry-cli.spec

# 2. Compilar instalador
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

El instalador se generará en `./installer/fiscalberry-3.0.0-setup.exe`

## 🤖 Compilación Automática (GitHub Actions)

El instalador se compila automáticamente en GitHub Actions cuando:

1. **Creas un tag** que empiece con `v`:

   ```bash
   git tag v3.0.1
   git push origin v3.0.1
   ```

2. **Ejecutas manualmente** el workflow desde GitHub UI

El workflow:

- Compila ejecutables para Windows (GUI + CLI)
- Instala Inno Setup con Chocolatey
- Compila el instalador
- Lo sube como artefacto al release

## 📝 Personalización

### Cambiar la versión

Edita [`installer.iss`](file:///mnt/datos/repos/fiscalberry/installer.iss) línea 6:

```iss
#define MyAppVersion "3.0.1"
```

### Cambiar el icono

Reemplaza el archivo `src/fiscalberry/ui/assets/fiscalberry.ico`

### Modificar archivos incluidos

Edita la sección `[Files]` en `installer.iss`:

```iss
[Files]
Source: "dist\fiscalberry-gui.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "tu-archivo.txt"; DestDir: "{app}"; Flags: ignoreversion
```

### Agregar acciones post-instalación

Edita la sección `[Code]` en `installer.iss` para agregar lógica Pascal Script.

## 🌍 Idiomas Soportados

- 🇪🇸 Español (predeterminado)
- 🇬🇧 English

Para agregar más idiomas, edita la sección `[Languages]` en `installer.iss`.

## ⚠️ Notas Importantes

### Ejecutables One-File vs Carpeta

Actualmente, el script asume que PyInstaller genera **ejecutables únicos** (`.exe`).

Si tu configuración de PyInstaller genera **carpetas** (modo predeterminado), descomenta estas líneas en `installer.iss`:

```iss
; Comentar estas líneas:
; Source: "dist\fiscalberry-gui.exe"; DestDir: "{app}"; Flags: ignoreversion
; Source: "dist\fiscalberry-cli.exe"; DestDir: "{app}"; Flags: ignoreversion

; Descomentar estas líneas:
Source: "dist\fiscalberry-gui\*"; DestDir: "{app}\gui"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\fiscalberry-cli\*"; DestDir: "{app}\cli"; Flags: ignoreversion recursesubdirs createallsubdirs
```

Y actualiza las rutas de los ejecutables en `[Icons]`:

```iss
Name: "{group}\{#MyAppName}"; Filename: "{app}\gui\fiscalberry-gui.exe"
Name: "{group}\{#MyAppName} CLI"; Filename: "{app}\cli\fiscalberry-cli.exe"
```

## 🔍 Solución de Problemas

### Error: "Inno Setup no está instalado"

Descarga e instala Inno Setup 6 desde [jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)

### Error: "No se encontró installer.iss"

Ejecuta el script desde la raíz del proyecto, no desde subdirectorios.

### El instalador no incluye todos los archivos

Verifica que PyInstaller haya compilado correctamente. Revisa la carpeta `dist/` para confirmar que los ejecutables existen.

## 📚 Recursos

- [Documentación de Inno Setup](https://jrsoftware.org/ishelp/)
- [Ejemplos de scripts](https://jrsoftware.org/ishelp/index.php?topic=samples)
- [Pascal Scripting Reference](https://jrsoftware.org/ishelp/index.php?topic=scriptintro)
