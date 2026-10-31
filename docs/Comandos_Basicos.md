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

## `reboot` — reiniciar la máquina

```json
{"reboot": true}
```

Ejecuta `reboot` del sistema operativo (requiere permisos de root). En equipos
donde no existe (Windows, Android) devuelve un `err` explícito.

## `restart` — reiniciar solo el servicio Fiscalberry

```json
{"restart": true}
```

- Con la GUI abierta (incluida Android) reinicia los servicios dentro del mismo proceso.
- Sin GUI, cierra el proceso a los 3 segundos y lo vuelve a levantar systemd
  (`Restart=always`).
- Si el equipo no corre bajo systemd ni con GUI, no hay quién lo vuelva a
  levantar: devuelve un `err` y no hace nada.

## `upgrade` — actualizar ahora, con versión fijada

```json
{"upgrade": true}                      // chequear ya (respeta el pin que tenga)
{"upgrade": {"version": "3.7.1"}}      // fijar esa versión y aplicarla
{"upgrade": {"version": "latest"}}     // quitar el pin y volver a seguir latest
```

La respuesta es inmediata (el chequeo corre en segundo plano, puede tardar
minutos si hay que descargar):

```json
{"rta": {"action": "upgrade",
         "rta": {"accepted": true, "current": "3.6.8", "target": "3.7.1"}}}
```

- `accepted: false` trae un `reason`; el caso típico es `"ya hay un chequeo en
  curso"`. Un pedido rechazado no cambia el pin. Reintentar más tarde.
- Una versión que no cumple `^\d+(\.\d+){1,3}$` (se acepta `v3.7.1`) devuelve
  `err` sin tocar nada.
- La versión fijada queda en `config.ini` (`[Updater] pinned_version = 3.7.1`) y
  **persiste**: los chequeos periódicos siguen esa versión y no saltan a la
  última. Para volver a seguir la última, `"latest"` (o borrar la clave a mano).
- Con un pin se consulta `releases/tags/v<versión>`, que incluye los
  prereleases: sirve para probar un build en un solo local.
- Mantiene las garantías de siempre: checksum `SHA256SUMS`, selftest del binario
  nuevo, no se aplica con impresiones pendientes (queda en `ocupado` y el
  periódico reintenta) y reversión automática si no arranca.
- Funciona aunque la auto-actualización esté desactivada
  (`[Updater] enabled = false`): el pedido remoto es explícito.
- El resultado final del chequeo queda en el log del updater.
