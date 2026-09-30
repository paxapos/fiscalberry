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

## Una sola instancia y la bandeja

El servicio de impresión vive en el mismo proceso que la ventana, así que dos
cosas no pueden pasar nunca: que haya dos Fiscalberry (usan el mismo client id
MQTT y se expulsan mutuamente del broker) y que cerrar la ventana corte la
impresión.

- **Instancia única**: la app crea el mutex `Local\FiscalberrySingleInstance`
  apenas arranca (`src/fiscalberry/common/single_instance.py`). Si ya existe,
  le pide a la instancia viva que muestre su ventana (evento
  `Local\FiscalberryShowWindow`) y termina con código 0.
- **Bandeja**: la "X" oculta la ventana; MQTT, websocket y spooler siguen. El
  ícono junto al reloj tiene "Abrir Fiscalberry" (también con clic) y "Salir
  (deja de imprimir)", que pide confirmación.
- **Arranque con Windows**: `HKCU\...\Run` lanza la app con `--minimized`,
  que arranca oculta en la bandeja.
- **Copias portables**: si existe la instalación del setup, un
  `fiscalberry-gui.exe` del zip abre la instalada y termina (nunca conviven dos
  versiones).

## Actualizaciones

El updater de la GUI (variante `windows-installer` en
`src/fiscalberry/common/updater/install_kind.py`) no reemplaza carpetas: baja
`FiscalberrySetup.exe` del release vigente, verifica su SHA256 y lo lanza así:

```text
FiscalberrySetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELAUNCH=1 /LOG=<logs>\instalador-<versión>.log
```

y enseguida cierra el proceso para liberar el mutex. El `.iss`:

- en `InitializeSetup`/`InitializeUninstall`, mientras exista el mutex, espera
  hasta 60 s si es silencioso; si es a mano, pide cerrar Fiscalberry desde la
  bandeja con opción de reintentar;
- borra `{app}\_internal` antes de copiar (`[InstallDelete]`), para no mezclar
  librerías de dos versiones;
- con `/RELAUNCH=1` vuelve a abrir la app con `--minimized` (entrada de `[Run]`
  sin `skipifsilent`).

Como es el mismo instalador, cada actualización deja al día `unins000.exe` y la
versión que muestra "Aplicaciones".

### Reversión

Antes de aplicar, el updater baja y verifica el `FiscalberrySetup.exe` de la
versión que está corriendo (release por tag) y lo guarda en
`<datos>\fiscalberry\rollback`. Si la versión nueva no llega a confirmar el
arranque (`commit_guard`, 3 intentos), se reinstala ese setup en silencio y la
versión nueva queda descartada en el equipo hasta que se publique otra.

Las versiones anteriores al instalador (3.6.x) no tienen setup en su release:
esa primera actualización no tiene reversión local, y queda en el log.

### Transición desde el zip portable

Las 3.6.x se actualizan con su updater viejo, que busca
`fiscalberry-windows-gui.zip`. Por eso el release sigue publicando el zip al
menos una versión más: así reciben el updater nuevo, que en la actualización
siguiente las migra a la instalación con `FiscalberrySetup.exe`. Después el zip
se retira del release y del readme.

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

[`build_tools/test-windows-installer.ps1`](../build_tools/test-windows-installer.ps1)
prueba el instalador de punta a punta en un runner de Windows:

1. instalación silenciosa (ejecutable, `unins000.exe` y arranque con Windows);
2. `--selftest` del binario instalado y versión en "Aplicaciones";
3. actualización silenciosa con la app "abierta" (el script crea el mutex): el
   setup tiene que esperar, instalar, conservar `unins000.exe` y relanzar con
   `--minimized`, sin dejar dos procesos;
4. desinstalación que borra la app y el arranque con Windows pero conserva
   `config.ini`.

Lo corren `.github/workflows/windows-installer.yml` (en cada push que toque el
instalador, la instancia única, la bandeja o el updater) y el job de Windows de
`build-release.yml`, que además publica `FiscalberrySetup.exe` con su entrada
en `SHA256SUMS`.
