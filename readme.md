
# ¿Para qué sirve?

Para enviar un JSON (mediante websocket), que fiscalberry lo reciba, lo transforme en un conjunto de comandos compatible con la impresora instalada, conecte con la impresora y responda al websocket con la respuesta que nos envió la impresora.

# Descargas

**Página de descargas: <https://github.com/paxapos/fiscalberry/releases/latest>**

Estos enlaces apuntan **siempre a la última versión publicada**; no hace falta
cambiarlos cuando sale una nueva.

| Sistema | Con interfaz gráfica | Solo consola |
| --- | --- | --- |
| Windows | [fiscalberry-windows-gui.zip](https://github.com/paxapos/fiscalberry/releases/latest/download/fiscalberry-windows-gui.zip) | [fiscalberry-windows-cli.zip](https://github.com/paxapos/fiscalberry/releases/latest/download/fiscalberry-windows-cli.zip) |
| Linux | [fiscalberry-linux-gui.tar.gz](https://github.com/paxapos/fiscalberry/releases/latest/download/fiscalberry-linux-gui.tar.gz) | [fiscalberry-linux-cli.tar.gz](https://github.com/paxapos/fiscalberry/releases/latest/download/fiscalberry-linux-cli.tar.gz) |
| Android | [fiscalberry-android-gui.apk](https://github.com/paxapos/fiscalberry/releases/latest/download/fiscalberry-android-gui.apk) | — |

Para verificar la descarga:
[SHA256SUMS](https://github.com/paxapos/fiscalberry/releases/latest/download/SHA256SUMS)

```sh
sha256sum -c SHA256SUMS --ignore-missing
```

Una vez instalado **no hace falta volver a descargar nada**: Fiscalberry se
actualiza solo. Ver [Actualización automática](#actualización-automática).

Los binarios de Linux se compilan en Ubuntu 22.04, así que corren en esa
versión y en cualquiera más nueva.

Para Raspberry pi (ARM) no hay binario precompilado (PyInstaller no hace
cross-compile a ARM): se instala desde código y se corre el CLI.
Ver [docs/INSTALACION_RASPBERRY.md](docs/INSTALACION_RASPBERRY.md).

# Como comenzar (solo developers del proyecto)

fiscalberry se puede instalar para usar con UI o solo consola (por ejemplo para ser ejecutado en una raspberry sin UI)

la forma mas simple es descargar el proyecto
y ejecutar asi:
pip install -e .
y luego podras ejecutar fiscalberry_gui o fiscalberry_cli como un comando mas

si lo queres  instalar en prod seria sin el -e
pip install .

la otra opcion mas para DEVs seria crear un virtual environment:

clonar repo
crear enviroment (1 para kivy y otro para modo cli, consola)
python3 -m venv .venv.kivy
python3 -m venv .venv.cli

luego activar el enviroment que se desea usar, por ejemplo modo solo consola:
source venv.cli/bin/activate

instalar requerimientos de modo consola
pip install -r requirements.cli.txt

ahora ya puede ejecutar:
python src/cli.py

lo mismo si se desea trabajar con interfaz kivy...


# Cómo publicar una nueva versión (release)

Los binarios (Linux, Windows y Android APK) los compila y publica
automáticamente GitHub Actions (`.github/workflows/build-release.yml`).

**El release se dispara cuando cambia la versión en `src/fiscalberry/version.py`
y se pushea a la rama `v3.0.x`.** Commitear sin cambiar la versión NO publica nada
(no se gasta CI). Tampoco se dispara desde `master`.

## Pasos

1. **Terminá y commiteá tus cambios** primero (el bump exige working tree limpio):

   ```sh
   git add -A
   git commit -m "feat: lo que hayas hecho"
   ```

2. **Bumpeá la versión** con `bump-my-version` (actualiza `version.py` + `setup.py`
   y crea un commit `chore(release): bump version X -> Y`). Elegí el tipo según el cambio:

   ```sh
   bump-my-version bump patch   # 3.1.0 -> 3.1.1  (fixes)
   bump-my-version bump minor   # 3.1.0 -> 3.2.0  (features nuevas)
   bump-my-version bump major   # 3.1.0 -> 4.0.0  (cambios incompatibles)
   ```

   > Instalación de la tool (una vez): `pipx install bump-my-version`
   > (o `pip install -r requirements.dev.txt` dentro de un venv).

3. **Pusheá** a la rama de release:

   ```sh
   git push origin v3.0.x
   ```

Listo. La Action detecta la nueva versión, compila los binarios y publica el
GitHub Release con el tag `vX.Y.Z` y los archivos adjuntos. **El tag lo crea la
Action**, no hace falta crearlo a mano.

## Notas importantes

- **Una versión = un release.** Si el tag `vX.Y.Z` ya existe, la Action se saltea
  la publicación (evita releases duplicados). Para publicar de nuevo, bumpeá a una
  versión nueva.
- `version.py` es la **única fuente de verdad** de la versión; no la edites a mano,
  usá `bump-my-version`.
- También se puede disparar manualmente desde la pestaña **Actions → Build and
  Release Fiscalberry → Run workflow** (`workflow_dispatch`).


# ¿Qué es?

Fiscalberry es un servidor de websockets desarrollado en Python pensado para que corra en una raspberry-pi (de ahí viene el nombre de este proyecto). **Pero funciona perfectamente en otros sistemas operativos.**
![fiscalberry JSON](http://alevilar.com/uploads/entendiendo%20fiscalberry.jpg)

# ¿Qué impresoras son compatibles?

Fiscalberry tiene drivers desarrollados para conectarse con 2 tipos de impresoras: Fiscales y Receipt.

Impresoras Fiscales compatibles: Hasar y Epson

Nueva versión con soporte para las últimas impresoras Fiscales de segunda generación (2gen) HASAR y EPSON <br>
Modelos compatibles (HASAR: SMH/PT-250F, EPSON: TM-T900FA)

Impresoras Receipt (de comandas) compatibles: las que soportan ESC/P

## Fiscalberry como servidor de impresión (print-server) de impresoras receipt (comanderas) y fiscales

Fiscalberry es un 3x1, actúa como: protocolo, servidor y driver facilitando al programador la impresión de tickets, facturas o comprobantes fiscales.

- _PROTOCOLO_: Siguiendo la estructura del JSON indicado, se podrá imprimir independientemente de la impresora conectada. Fiscalberry se encargará de conectarse y pelear con los códigos y comandos especiales de cada marca/modelo.
- _SERVIDOR_: gracias al servidor de websockets es posible conectar tu aplicación para que ésta fácilmente pueda enviar JSON's y recibir las respuestas de manera asíncrona.
- _DRIVER_: Es el encargado de transformar el JSON genérico en un conjunto de comandos especiales según marca y modelo de la impresora. Aquí es donde se adaptó el código del proyecto de Reingart (<https://github.com/reingart/pyfiscalprinter>) para impresoras Hasar y Epson.

Funciona en cualquier PC con cualquier sistema operativo que soporte Python.

La idea original fue pensada para que funcione en una raspberry pi, cuyo fin es integrar las fiscales al mundo de la Internet de las Cosas (IOT).

## ¿Para quienes está pensado?

Para los desarrolladores que desean enviar a imprimir mediante JSON (es decir, desde algún lugar de la red, internet, intranet, etc, etc) de una forma "estándar" y que funcione en cualquier impresora, marca y modelo.

## PROBALO

### Descargar

usando git

```sh
git clone https://github.com/paxapos/fiscalberry.git
```

o directamente el ZIP: <https://github.com/paxapos/fiscalberry/archive/master.zip>

### Instalar Dependencias

ATENCIÓN: Funciona con Python 2.7.* NO en Python 3!

probado bajo python 2.7.6 en Linux, Raspian, Ubuntu, Open Suse y Windows

Se necesitan varias dependencias:

```sh
sudo pip install -r requirements.txt

```

Si te encontras con el error "socket.gaierror:  Name or service not known"

A veces, en Linux (Open Suse), ser necesario poner el nombre del equipo (hostname) en el archivo /etc/hosts, si es que aún no lo tenías.
Generalmente el archivo hosts viene solo con la dirección "127.0.0.1 localhost",

para solucionarlo debés ejecutar el comando

```bash
hostname
```

y ver cuál es el nombre de la máquina para agregarlo al archivo /etc/hosts
127.0.0.1 nombre-PC localhost

### Iniciar el programa

```sh
sudo python server.py

# o iniciar como demonio linux
sudo python rundaemon.py
```

Ahora ya puedes conectarte en el puerto 12000
entrando a un browser y la dirección <http://localhost:12000>

## Conceptos básicos ¿Cómo funciona?

Supongamos que tenemos este JSON genérico:

```
{
    "ACCION_A_EJECUTAR": {
        PARAMETROS_DE_LA_ACCION
        ...
    }
}
```

Lo enviamos usando websockets a un host y puerto determinado (el servidor fiscalberry), éste lo procesa, envía a imprimir, y responde al cliente con la respuesta de la impresora. Por ejemplo, devolviendo el número del último comprobante impreso.

Otro ejemplo más concreto: queremos imprimir un ticket, esta acción en el protocolo fiscalberry se lo llama como acción "printTicket" y está compuesta de 2 parámetros obligatorios: "encabezado" e "items".

El "encabezado" indica el tipo de comprobante a imprimir (y también podría agregarle datos del cliente, que son opcionales).
Los ítems son una lista de productos a imprimir donde, en este ejemplo, tenemos una coca cola, con impuesto de 21%, importe $10, descripción del producto "COCA COLA" y la cantidad vendida es 2.

```json
{
    "printTicket": {
        "encabezado": {
            "tipo_cbte": "T",      // tipo tiquet *obligatorio
        },
        "items": [
            {
                "alic_iva": 21.0,  // impuesto
                "importe": 10,     // importe
                "ds": "COCA COLA", // descripcion producto
                "qty": 2.0         // cantidad
            }
        ]
    }
}
```

### JSON RESPUESTA

Existen 2 tipos de respuesta y siempre vienen con la forma de un JSON.

Aquellos que son una respuesta a un comando enviado, comienzan con "ret"
**_{"ret": ......}_**

Aquellos que son un mensaje directo de algun dispositivo conectado, vienen con "msg"

**_{"msg": ......}_**

```javascript
// ejemplo retorno de un mensaje cuando no hay papel
{"msg": ["Poco papel para comprobantes o tickets"]}
```

#### NOTA

Deberás enviar JSON válidos al servidor. Recomendamos usar la pagina <http://jsonlint.com/> para verificar como tu programa esta generando los JSON.

# Licencia

Fiscalberry se distribuye bajo licencia [MIT](LICENSE). Podés usarlo, modificarlo
y redistribuirlo —incluso en productos comerciales— conservando el aviso de copyright.

Las dependencias del proyecto son todas permisivas (MIT/BSD), con una excepción:
el extra `python-escpos[all]` arrastra `pycups`, que es GPLv2+. Solo lo usa el
driver CUPS; si necesitás empaquetar sin código GPL, instalá `python-escpos` sin
el extra `[all]` y usá el driver `LP` en su lugar.

# Actualización automática

Desde la 3.5.0 Fiscalberry se actualiza solo. Funciona en Linux, Windows,
Raspberry (instalación desde código) y Android.

## Cómo decide qué versión instalar

La regla no es "actualizar si hay algo más nuevo" sino **tener instalado
exactamente lo que dice el último release** de GitHub. La diferencia importa:
si una versión sale mala, **borrar ese release en GitHub hace que toda la flota
vuelva sola a la anterior**, sin tocar ningún dispositivo. Es el botón de pánico.

Los *prereleases* quedan afuera automáticamente, así que se pueden publicar
builds de prueba sin que los dispositivos los agarren.

## Qué verifica antes de instalar

1. **Checksum**: el release publica un `SHA256SUMS` y el archivo descargado
   tiene que coincidir. Si un release no lo trae, no se actualiza.
2. **Que el binario arranque**: se ejecuta el binario nuevo con `--selftest`
   (importa los módulos pesados, lee la config, abre la base del spooler) y
   solo se instala si sale limpio. Compilar no prueba que arranque.
3. **Que no haya impresiones pendientes**: nunca se actualiza con la cola
   ocupada. Actualizar con un ticket en vuelo es perder el ticket.

## Si la versión nueva no levanta

Antes de reemplazar el binario se guarda el anterior. Si la versión nueva no
llega a conectar el servicio en 3 arranques seguidos, **se revierte sola** al
binario que funcionaba. El local no queda sin imprimir.

## Diferencias por plataforma

| | Cómo se aplica | Automático |
| --- | --- | --- |
| Linux / Raspberry | Reemplazo atómico del binario, reinicia systemd | Sí |
| Windows | El binario nuevo hace de ayudante y se reemplaza tras cerrarse | Sí |
| Android | Abre el instalador del sistema | Requiere un toque del usuario |

En Android **no existe** la instalación silenciosa fuera de Play Store, ni la
reversión automática: son límites del sistema operativo.

## Configuración

En el `config.ini`, sección opcional:

```ini
[Updater]
enabled = true              ; false para desactivarlo
check_interval_hours = 6    ; mínimo efectivo: 10 minutos
```

## Comandos útiles

```sh
fiscalberry_cli --version    # qué versión es ésta
fiscalberry_cli --selftest   # ¿este binario arranca bien?
```
