# Compilar APK

source venv.buildozer/bin/activate

# Limpiar build anterior

buildozer android clean

# Recompilar con el código corregido

buildozer android debug

# Instalar en dispositivo

adb install -r bin/fiscalberry-\*.apk

# Verificar logs

adb logcat -c && adb logcat -s python:\*

# Actualizar dependencias

pip install --upgrade -r requirements.txt  
pip freeze > requirements.txt
buildozer android clean

# Ejecutar aplicación en emulador

buildozer android deploy run

# Empaquetar para distribución

buildozer android release

# Reiniciar servidor ADB

adb kill-server
adb start-server

---

# Activar entorno virtual

source venv.cli/bin/activate

# Ejecutar main.py

python -m fiscalberry.cli.main

---

# Compilar versión CLI (Línea de Comandos)

# Desde el directorio principal (donde están los archivos .spec)

# 1. Activar el entorno virtual correspondiente

source venv.cli/bin/activate

# 2. Compilar con PyInstaller

pyinstaller fiscalberry-cli.spec

---

# Compilar versión GUI (Interfaz Gráfica)

# Desde el directorio principal (donde están los archivos .spec)

# 1. Activar el entorno virtual correspondiente

source venv.gui/bin/activate

# 2. Compilar con PyInstaller

pyinstaller fiscalberry-gui.spec

---

# Comandos remotos de control

Mensajes que manda Paxapos **sin `printerName`**; los ejecuta `ComandosHandler`
como comandos (no se imprimen). Todos devuelven `{"rta": ...}`, o `{"err": ...}`
si no se pudo cumplir.

Los comandos `reboot`, `restart` y `upgrade` solo se ejecutan si el valor es
exactamente `true`; cualquier otro (`false`, `"true"`, `1`, `null`) se ignora, se
loguea y responde un `err`.

## `reboot` — reiniciar la máquina

```json
{"reboot": true}
```

**Deshabilitado por defecto.** Se habilita solo desde el `config.ini` del propio
equipo:

```ini
[Paxaprinter]
remote_power_commands = true
```

Con la opción apagada (o ausente) responde un `err` claro y no hace nada.
Habilitado, ejecuta `reboot` del sistema operativo (requiere permisos de root). En
equipos donde no existe (Windows, Android) devuelve un `err` explícito.

## `restart` — reiniciar solo el servicio Fiscalberry

```json
{"restart": true}
```

Mismo requisito que `reboot`: `[Paxaprinter] remote_power_commands = true` en el
`config.ini` local; con la opción apagada responde un `err` y no hace nada.

- Con la GUI abierta (escritorio) reinicia los servicios dentro del mismo proceso.
- Sin GUI, cierra el proceso en forma ordenada a los 3 segundos (para que la
  respuesta alcance a salir) y lo vuelve a levantar systemd (`Restart=always`).
- Si el equipo no corre bajo systemd ni con GUI, no hay quién lo vuelva a
  levantar: devuelve un `err` y no hace nada. Es el caso de Android: el servicio
  corre en un proceso aparte, sin la App de Kivy, y no hay systemd, así que
  `restart` responde ese `err`.

## `upgrade` — buscar la última versión y aplicarla ya

```json
{"upgrade": true}
```

Hace en el momento el mismo chequeo que el updater hace cada 6 horas, contra el
último release publicado (`releases/latest`). No se puede elegir versión: el
equipo va a la que esté publicada como última.

La respuesta es inmediata (el chequeo corre en segundo plano y puede tardar
minutos si hay que descargar):

```json
{"rta": {"action": "upgrade",
         "rta": {"accepted": true, "current": "3.6.9"}}}
```

- `accepted: false` trae un `reason`; el caso típico es `"ya hay un chequeo en
  curso"` (el periódico o un pedido anterior). Reintentar más tarde.
- Mantiene las garantías de siempre: checksum `SHA256SUMS`, selftest del binario
  nuevo, no se aplica con impresiones pendientes (queda en `ocupado` y el
  periódico reintenta) y reversión automática si no arranca.
- Funciona aunque la auto-actualización esté desactivada
  (`[Updater] enabled = false`): el pedido remoto es explícito.
- El resultado final del chequeo queda en el log del updater.
