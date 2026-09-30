# Fiscalberry AI Agent Instructions

## Project Overview

**Fiscalberry** is a multi-platform print server (Windows/Linux/Android) that translates JSON commands into printer-specific protocols via SocketIO/MQTT. It supports fiscal printers (Hasar/Epson) and ESC/POS receipt printers.

> ⚠️ **BRANCH v3.0.x**: This branch uses **MQTT protocol** (paho-mqtt) exclusively.  
> For AMQP (pika), use branch `v2.0.x`.

**Key Architecture Pattern**: Fiscalberry acts as a 3-in-1 system:

1. **Protocol**: Standardized JSON format for all printer commands
2. **Server**: SocketIO for management + **MQTT** for job queuing (RabbitMQ MQTT plugin)
3. **Driver**: Translates JSON → printer-specific commands (Hasar, Epson, ESC/POS)

## Critical Architecture Components

### Entry Points (3 Modes)

- **GUI Mode**: `src/fiscalberry/gui.py` → `FiscalberryApp` (Kivy-based, cross-platform)
- **CLI Mode**: `src/fiscalberry/cli.py` → `ServiceController` (headless servers/Raspberry Pi)
- **Android Service**: `src/fiscalberryservice/android.py` (background service)

### Core Services (Singleton Pattern)

```python
ServiceController  # Orchestrates SocketIO + MQTT lifecycle
├── FiscalberrySio  # SocketIO client for real-time management commands
└── RabbitMQProcessHandler → RabbitMQConsumer  # MQTT job queue processing
    └── ComandosHandler → Printer drivers
```

**CRITICAL**: `ServiceController` is a singleton - always access via existing instance, never instantiate directly in new code.

### Configuration System (`Configberry`)

- **File**: `config.ini` (INI format, environment-aware)
- **Priority Logic**: Local `config.ini` > SocketIO-provided config > Defaults
- **Adoption Flow**: App starts "unadopted" → SocketIO `start_rabbit` event → writes `[Paxaprinter]` section → becomes "adopted"
- **Listener Pattern**: Components register with `configberry.add_listener()` to react to config changes

### Print Job Flow

```
JSON Command (SocketIO/RabbitMQ)
  → ComandosHandler.runTraductor()
  → Driver-specific translation (Hasar/Epson/ESC/POS)
  → Printer (Serial/USB/Network/Bluetooth)
  → Response JSON back to client
```

## Android-Specific Architecture

### Build System

- **Tool**: Buildozer (Python-for-Android wrapper)
- **Build Command**: `buildozer android debug` (15-20 min compile time)
- **Custom Recipes**: `my_recipes/` for native dependencies (jpeg, kivy patches)
- **APK Output**: `bin/fiscalberry-{version}-{arch}-debug.apk`

### Permission System (Android 12+ Critical)

- **Runtime Permissions**: Bluetooth requires explicit user grant via `ActivityCompat.requestPermissions()`
- **Code Location**: `src/fiscalberry/common/android_permissions.py`
- **Pattern**: Always use dual-method approach (p4a + ActivityCompat fallback)

### Android Service Pattern

```python
# Main app starts service in background
from android import AndroidService  # OR jnius autoclass fallback
service.start(mActivity, '')  # Keeps RabbitMQ alive when app in background
```

## Printer Driver Architecture

### Driver Loading Pattern (ComandosHandler.py)

```python
# Dynamic driver instantiation based on config.ini [IMPRESORA] section
driver = config['driver'].lower()  # "hasar", "epson", "network", "bluetooth"
marca = config['marca']  # Printer brand/model

if driver == "hasar":
    from Traductores.TraductorFiscal import TraductorHasar
elif driver == "network":
    from escpos import printer
    driver_obj = printer.Network(host=config['host'], port=config['port'])
elif driver == "bluetooth":  # NEW: Android-specific
    from fiscalberry.common.bluetooth_printer import BluetoothPrinter
    driver_obj = BluetoothPrinter(mac_address=config['mac_address'])
```

**NEW PATTERN (Bluetooth)**: Uses Android BluetoothSocket via `jnius` → SPP UUID `00001101-...` → implements `escpos` interface.

### Printer Detection (Android)

- **USB**: Via `pyusb` + Android USB OTG permissions
- **Bluetooth**: Scans bonded devices + discovery via `BluetoothAdapter.getDefaultAdapter()`
- **Code**: `src/fiscalberry/common/printer_detector.py`

## Developer Workflows

### Local Development Setup

```bash
# Create virtual environments (2 separate envs for GUI vs CLI)
python3 -m venv venv.cli
source venv.cli/bin/activate
pip install -r requirements.cli.txt

# OR for GUI development
python3 -m venv venv.kivy
source venv.kivy/bin/activate
pip install -r requirements.kivy.txt

# Run modes
python src/fiscalberry/cli.py          # CLI mode
python src/fiscalberry/gui.py          # GUI mode
```

### Android Build & Deploy

**⚙️ Prerequisitos:**

- Python 3.8+ (preferiblemente 3.11 o 3.12)
- Android SDK/NDK (se instala automáticamente por Buildozer)
- Java JDK 11 o superior
- Git, zip, unzip, autoconf, libtool, pkg-config

**📦 Setup inicial (solo primera vez):**

```bash
# 1. Crear entorno virtual dedicado para buildozer
python3 -m venv venv.buildozer
source venv.buildozer/bin/activate

# 2. Instalar buildozer y Cython
pip install --upgrade pip
pip install buildozer cython==0.29.36

# 3. Verificar configuración
buildozer android debug --verbose  # Primera vez descarga SDK/NDK (~2-3 GB)
```

**🔨 Comandos de compilación:**

```bash
# Activar entorno buildozer
source venv.buildozer/bin/activate

# BUILD LIMPIO (cuando cambias requirements.txt o buildozer.spec)
buildozer android clean             # Limpia compilaciones anteriores
buildozer android debug             # Compila APK debug (15-20 min primera vez)

# BUILD INCREMENTAL (cambios en código Python solamente)
buildozer android debug             # ~2-5 min si solo cambió código Python

# BUILD RELEASE (para producción)
buildozer android release           # Genera APK sin firmar
# Para firmar: jarsigner -verbose -sigalg SHA1withRSA -digestalg SHA1 \
#   -keystore my-release-key.keystore bin/fiscalberry-*.apk alias_name

# USAR SCRIPT AUTOMATIZADO (recomendado)
./build.android.sh                  # Script con logs y validaciones
```

**📱 Instalación en dispositivo:**

```bash
# Conectar dispositivo por USB (activar "Depuración USB" en opciones de desarrollador)

# Instalar APK
adb install -r bin/fiscalberry-2.0.1-arm64-v8a_armeabi-v7a-debug.apk

# Verificar instalación
adb shell pm list packages | grep fiscalberry
# Output esperado: package:com.paxapos.fiscalberry

# Iniciar app desde terminal
adb shell am start -n com.paxapos.fiscalberry/.FiscalberryActivity
```

**🐛 Debugging Android:**

```bash
# Ver logs en tiempo real (Python + Android)
adb logcat -s python:* MainActivity:* SDL:*

# Ver solo errores de Python
adb logcat -s python:E

# Ver config.ini en el dispositivo
adb shell run-as com.paxapos.fiscalberry cat files/app/config.ini

# Ver logs de Fiscalberry
adb shell run-as com.paxapos.fiscalberry cat files/app/logs/fiscalberry.log

# Limpiar datos de la app (resetear configuración)
adb shell pm clear com.paxapos.fiscalberry

# Enviar archivo config.ini al dispositivo
adb push config.ini /sdcard/
adb shell run-as com.paxapos.fiscalberry cp /sdcard/config.ini files/app/config.ini
```

**⚠️ Troubleshooting común:**

| Problema                       | Solución                                                         |
| ------------------------------ | ---------------------------------------------------------------- |
| `Command failed: ./gradlew...` | Limpiar build: `buildozer android clean && rm -rf .buildozer`    |
| `Recipe not found: kivy`       | Verificar `buildozer.spec`: `requirements = kivy==2.3.0,...`     |
| `Permission denied` en build   | `chmod +x .buildozer/android/platform/build-*/build/...`         |
| APK no inicia                  | Ver logcat: `adb logcat -s python:*` buscar errores de import    |
| `AAPT out of memory`           | En `buildozer.spec`: `android.gradle_dependencies = ...` reducir |
| Cambios no reflejados          | Forzar rebuild: `buildozer android clean` antes de compilar      |

**📊 Tiempos de compilación esperados:**

- **Primera compilación**: 15-25 minutos (descarga SDK/NDK/dependencias)
- **Build limpio**: 8-15 minutos (tiene SDK pero recompila todo)
- **Build incremental**: 2-5 minutos (solo cambios en código Python)
- **Tamaño APK final**: ~40-45 MB (arquitecturas arm64-v8a + armeabi-v7a)

### Testing Printers Without Hardware

```bash
# Network simulator (TCP port 9100)
python3 bluetooth_simulator_simple.py  # Simulates ESC/POS printer

# Configure Fiscalberry to use simulator
# config.ini:
# [IMPRESORA_SIMULADOR]
# driver = Network
# host = localhost
# port = 9100
```

## Project-Specific Conventions

### Logging System

- **Centralized**: `fiscalberry_logger.py` returns configured loggers
- **Usage**: `logger = getLogger("Component.SubComponent")`
- **Output**: `logs/fiscalberry.log` + console (environment-aware)
- **Android**: Logs to `/data/data/com.paxapos.fiscalberry/files/app/logs/`

### Error Handling Pattern

```python
# ALWAYS publish errors to RabbitMQ for monitoring
from fiscalberry.common.rabbitmq.error_publisher import publish_error

try:
    # printer operation
except Exception as e:
    logger.error(f"Operation failed: {e}", exc_info=True)
    publish_error(error_message=str(e), error_type="PrinterError")
    raise  # Re-raise to caller
```

### JSON Protocol Pattern

```json
// Command format (SocketIO/RabbitMQ)
{
    "printTicket": {
        "encabezado": {"tipo_cbte": "T"},
        "items": [{"alic_iva": 21.0, "importe": 10, "ds": "PRODUCT", "qty": 2}]
    }
}

// Response format
{"ret": {"last_invoice": "12345", "status": "ok"}}  // Success
{"msg": ["Poco papel para comprobantes"]}  // Printer status message
```

### Threading Model

- **SocketIO**: Daemon thread via `FiscalberrySio.start()`
- **RabbitMQ**: Process in separate thread via `RabbitMQProcessHandler`
- **Print Queue**: Worker pool (3 workers) in `ComandosHandler.process_print_jobs()`
- **CRITICAL**: All service threads must be daemon=True to allow clean shutdown

### Kivy UI Pattern

- **Screens**: `ScreenManager` with `adopt`, `main`, `logs` screens
- **State Management**: Properties (`StringProperty`, `BooleanProperty`) auto-update UI
- **Config Sync**: `_on_config_change()` updates UI when config.ini changes
- **KV Files**: `src/fiscalberry/ui/kv/main.kv` (declarative layout)

## Critical Gotchas & Anti-Patterns

1. **NEVER block the main thread** in Kivy GUI - use `@mainthread` decorator for UI updates from background threads
2. **Android permissions**: Must request at runtime for API 23+, use `android_permissions.py` helper
3. **Config priority**: ALWAYS respect `config.ini` values over SocketIO (see `rabbitmq/process_handler.py` priority logic)
4. **Service lifecycle**: Call `_stop_services_only()` not `stop()` to avoid recursive shutdown in GUI
5. **Python version**: Project uses Python 3.x (NOT 2.7 despite old README mentions)
6. **Buildozer caching**: Run `buildozer android clean` when changing `requirements` or `buildozer.spec`
7. **RabbitMQ reconnection**: Handled automatically by `RabbitMQProcessHandler` with exponential backoff

## Key Files Reference

- **Architecture**: `service_controller.py`, `fiscalberry_sio.py`, `rabbitmq/consumer.py`
- **Printer Core**: `ComandosHandler.py`, `EscPComandos.py`, `FiscalberryComandos.py`
- **Android**: `android_permissions.py`, `bluetooth_printer.py`, `fiscalberryservice/android.py`
- **Config**: `Configberry.py`, `config.ini.sample`
- **Diagnostics**: `diagnostics/rabbitmq_check.py` (connection testing tool)
- **Build**: `buildozer.spec`, `setup.py`, `requirements*.txt`

## When Making Changes

- **Adding printer support**: Extend `ComandosHandler` driver switch + add translator class
- **New Android permissions**: Update `buildozer.spec` + `android_permissions.py` + request at runtime
- **Config changes**: Update `Configberry` + trigger listeners + test adoption flow
- **API changes**: Update both SocketIO handlers (`fiscalberry_sio.py`) AND RabbitMQ consumers
- **UI changes**: Edit `.kv` files + corresponding screen Python class + test on Android + Desktop

## Developer Panel (Separate Repository)

**Repository**: https://github.com/paxapos/fiscalberry-developer-panel  
**Integration**: Git submodule at `developer-panel/`  
**Purpose**: Web dashboard for monitoring errors across multiple Fiscalberry tenants

### Architecture

- **Framework**: FastAPI + WebSocket
- **Auth**: JWT-based authentication
- **Error Source**: Consumes from RabbitMQ queues: `{tenant}_errors`
- **Real-time**: WebSocket notifications for live error updates

### Quick Start

```bash
# Update panel to latest version
./scripts/sync-developer-panel.sh

# Test integration (starts RabbitMQ + Panel + Fiscalberry)
./scripts/test-developer-panel-integration.sh

# Run panel standalone
cd developer-panel
source venv/bin/activate
python main.py
# Access at: http://localhost:8000
# Login: dev1 / dev123
```

### Context & Integration

- **Message Format**: See `developer-panel/.fiscalberry-context.json`
- **Error Publisher**: `src/fiscalberry/common/rabbitmq/error_publisher.py`
- **Error Types**: COMMAND_EXECUTION_ERROR, TRANSLATOR_ERROR, PROCESSING_ERROR, JSON_PARSE_ERROR, PRINTER_ERROR, etc.
- **Documentation**:
  - `MIGRACION_DEVELOPER_PANEL.md` - Migration guide
  - `DEVELOPER_PANEL_WORKFLOW.md` - Development workflows
  - `DEVELOPER_PANEL_DOCS.md` - Error handling system docs

### Development Workflows

**Scenario 1: Panel-only changes**

```bash
cd developer-panel
git checkout -b feature/new-view
# Make changes, commit, push
git push origin feature/new-view
# Create PR in developer-panel repo
# After merge: cd .. && ./scripts/sync-developer-panel.sh
```

**Scenario 2: Fiscalberry changes affecting panel**

```bash
# 1. Update error_publisher.py with new error type
# 2. Document in DEVELOPER_PANEL_DOCS.md
# 3. Update panel to support new error type
cd developer-panel && git checkout -b feature/support-new-error
# 4. Create PRs in both repos with cross-references
```

**Scenario 3: Testing together**

```bash
./scripts/test-developer-panel-integration.sh
# This starts everything: RabbitMQ + Panel + Fiscalberry + test errors
```

### Key Notes

- **Submodule updates**: Always run `git submodule update --remote` after pulling Fiscalberry
- **Independent versioning**: Panel has its own release cycle
- **Standalone capable**: Can run without Fiscalberry for monitoring existing deployments
- **Multi-tenant**: Monitors multiple Fiscalberry instances/tenants from single dashboard

## External Dependencies

- **RabbitMQ + MQTT Plugin**: Message broker for job queue (host/port in config, default port 1883)
- **SocketIO Server**: Real-time bidirectional communication (adoption, management)
- **Printer Protocols**: Hasar/Epson fiscal, ESC/POS (via `python-escpos`)
- **Android APIs**: USB Host, Bluetooth (via `jnius`), Foreground Service

## MQTT Configuration (v3.0.x)

### RabbitMQ MQTT Plugin Setup

```bash
# Enable MQTT plugin on RabbitMQ server
rabbitmq-plugins enable rabbitmq_mqtt
```

### config.ini

```ini
[RabbitMq]
host = your-server.com
port = 1883              # MQTT port (NOT 5672 AMQP)
user = fiscalberry
password = your_password

[SERVIDOR]
uuid = 12345678-1234-1234-1234-123456789abc  # Topic for this device
```

### Key MQTT Differences from AMQP (v2.0.x)

| Aspect  | v2.0.x (AMQP)      | v3.0.x (MQTT)                    |
| ------- | ------------------ | -------------------------------- |
| Library | pika               | paho-mqtt                        |
| Port    | 5672               | 1883                             |
| Concept | Exchange + Queue   | Topic                            |
| ACK     | Manual (basic_ack) | Automatic (QoS 1)                |
| Session | N/A                | Persistent (clean_session=False) |

### MQTT Key Features

- **Persistent Session** (`clean_session=False`): RabbitMQ stores pending messages if client disconnects
- **QoS 1**: Automatic ACK when `on_message` callback completes without errors
- **Topic = UUID**: Each printer subscribes to its own UUID topic
