# Asistente de impresoras: búsqueda de red, USB y COM

Cómo encuentra Fiscalberry las impresoras de red (#175), USB (#183,
escenario 2) y USB que aparecen como COM (#183, escenario 3). Las colas de
Windows ya instaladas (#174) están en `common/windows_queues.py`.

Las tres reglas que valen para todo:

- **Sin permisos de administrador** y fuera del hilo de la interfaz.
- **No se modifica nada**: ni la red de la PC ni la de la impresora, ni
  drivers ni colas. Nunca Zadig.
- Cada búsqueda entrega `PrinterCandidate` (`common/printer_setup.py`): lo
  que se prueba con el ticket (#172) y, si sale bien y se confirma en papel,
  se guarda. Nada se guarda antes.

Diseño portado de `feat/instalador-v3` (PR #189) y adaptado a esta rama.

## Red — #175

Código: `common/network_discovery.py`.

### Adaptadores

`list_adapters()` lee en Windows `GetAdaptersAddresses` (IPv4, con
gateways): nombre, descripción, dirección, **prefijo real**
(`OnLinkPrefixLength`), gateways, métrica, DHCP, MAC y estado.

Solo se barren los adaptadores **físicos y conectados**. Se ignoran, con un
aviso:

| Tipo | Cómo se reconoce |
|---|---|
| Loopback | `IfType` 24 |
| VPN | `IfType` 131 (túnel) o 23 (PPP), o la descripción: TAP-Windows, WireGuard, Wintun, OpenVPN, AnyConnect, Fortinet, GlobalProtect, ZeroTier, Tailscale, Hamachi… |
| Virtual | `vEthernet` / "Hyper-V Virtual Ethernet Adapter" (Default Switch, WSL), VirtualBox Host-Only, VMware VMnet, Docker, Bluetooth PAN, Wi-Fi Direct… |

Barrer la red de una VPN mandaría cientos de conexiones a la red de otra
empresa. Dos excepciones:

- "Microsoft Hyper-V Network Adapter" es la placa de una **PC virtual** (así
  se ven los runners de GitHub): para esa PC es física.
- Un `vEthernet` **con gateway** es un switch externo de Hyper-V: la red real
  pasa por ahí.

### Qué se barre

`plan_sweep()` usa la máscara real:

- Hasta 1022 direcciones (/22 o menor): el rango entero.
- Una red más grande: las 254 direcciones vecinas a la PC, con aviso. La
  clasificación sigue usando la máscara real.
- 169.254.x.x (la PC no encontró el router), /31, /32 o una máscara que no es
  un prefijo: no se barre y se informa. No se fuerza ninguna máscara.
- **La PC misma no se barre**: otro sistema POS o un servidor de impresión que
  escuche en el 9100 de esta computadora aparecería como impresora.

También se prueban las **IPs de fábrica** que quedan fuera de los rangos de la
PC: si una responde, hay una ruta hasta ella y se puede usar.

### Barrido

`tcp_sweep()`: conexiones no bloqueantes al 9100, hasta 256 a la vez, con
1,5 s de espera por tanda. Un /24 tarda ~1,5 s (con SNMP, ~2,5 s). La espera
no es más corta porque Windows reintenta el SYN después de un RST: con menos
de ~1 s un "puerto cerrado" parece "nadie". Se cancela en cualquier momento y
cierra todos los sockets.

**SAM4S y el 6001** (#180): no se barre todo el rango en el 6001. Se prueba
solo en los equipos que rechazaron el 9100 (están vivos pero no escuchan
ahí). Si acepta, se ofrece en ese puerto y la prueba en papel decide.

### Señales para mostrar el modelo

- **SNMP v2c** unicast (UDP 161, comunidad `public`): `sysDescr`,
  `sysObjectID`, `sysName`, `hrDeviceDescr`. Un solo socket para todas las
  encontradas, 1 s. El firewall de Windows deja pasar la respuesta sin reglas
  nuevas porque el pedido salió de la PC.
- **Tabla ARP** (`GetIpNetTable`): la MAC. Solo se muestra el fabricante de la
  placa (`00:26:AB:xx:xx:xx`).

Son pistas para la pantalla: no deciden nada.

### Diagnóstico de una dirección (`diagnose_address`)

Para cuando la persona escribe la dirección que imprimió la hoja de autotest.

| `kind` | Cuándo |
|---|---|
| `misma_subred` | En el rango (máscara real) de un adaptador físico y el puerto acepta |
| `otra_subred_alcanzable` | Fuera de los rangos, pero hay ruta y el puerto acepta: se puede usar |
| `otra_subred_marca_conocida` | Fuera de los rangos, no responde y es una IP de fábrica |
| `otra_subred_desconocida` | Fuera de los rangos y no responde (192.168.123.68 con la PC en 192.168.1.27/24) |
| `apagada` | En el rango, nadie responde |
| `puerto_cerrado` | El equipo responde pero no el puerto (`is_gateway` dice si es el router) |
| `invalido` | No es una IPv4 de un equipo, es la de red o broadcast, o es la de esta PC |

La red de una VPN o de un adaptador virtual no cuenta como la red de la PC.
Sin una IP en el rango de la impresora la PC no puede hablarle: el asistente
lo explica, no cambia nada.

### IPs de fábrica

| IP | Marcas |
|---|---|
| 192.168.192.168 | Epson TM |
| 192.168.123.100 | Xprinter, Gprinter, Hasar HTP-250 |

La IP no identifica la marca. 192.168.1.1 no se agrega: es la IP típica del
router. Evidencia y límites en `docs/investigacion-impresoras-red.md` (#180).

## USB directo y COM — #183

Código: `common/usb_discovery.py` (búsqueda) y `common/usbprint_driver.py`
(driver `UsbPrint`).

### Por qué no PyUSB

Una térmica de clase Impresora USB (0x07) usa `usbprint.sys`, que viene con
Windows y crea el puerto `USB00x` aunque no haya driver de impresora ni cola.
PyUSB/libusb exigiría reemplazar ese driver por WinUSB (Zadig, con admin), y
eso rompe la cola de Windows. El driver `Usb` (PyUSB) queda para Linux y para
equipos que ya exponen WinUSB.

### Búsqueda

- **usbprint**: `SetupDiGetClassDevs` + `SetupDiEnumDeviceInterfaces` sobre
  `GUID_DEVINTERFACE_USBPRINT` `{28d78fad-5a12-11d1-ae5b-0000f803a8c2}`. De
  la ruta (`\\?\usb#vid_04b8&pid_0e15#<serie>#{guid}`) salen VID, PID y serie.
  Si la instancia tiene `&` (Windows la inventó) o el dispositivo es compuesto
  (`&mi_00`), no hay serie.
- El puerto `USB001` sale de la clave de registro de la interfaz (`Port
  Number` + `Base Name`): sirve para reconocer la cola de Windows que usa la
  misma impresora.
- El modelo: Device ID IEEE 1284 (`IOCTL_USBPRINT_GET_1284_ID`), después la
  descripción que da el bus, después la marca por VID.
- **COM** con `serial.tools.list_ports`: CDC (`usbser.sys`), CH340, PL2303,
  FTDI y CP210x aparecen con VID/PID. Los COM de Bluetooth no se abren nunca
  (abrirlos intenta conectar y puede colgar); los de la placa madre y los
  módems se ocultan por defecto. Velocidad: 9600.
- **Incompatibles**: con `SetupDiGetClassDevs("USB")` se revisan todos los
  USB. Una impresora (clase 07 o VID de una marca conocida) sin driver o con
  WinUSB/libusb se informa como "no se puede usar"; su driver no se toca.

### Qué se guarda

| Caso | En `config.ini` | Identidad (`_setup_id`) |
|---|---|---|
| USB con número de serie | `idVendor`, `idProduct`, `serial_number` | `usb:vvvv:pppp:serie` |
| USB sin serie | `idVendor`, `idProduct`, `device_path` | `usb:vvvv:pppp@ruta` |
| COM con serie (adaptador) | `devfile`, `baudrate` | `serial:vvvv:pppp:serie` |
| COM sin serie (CH340, muchos PL2303) | `devfile`, `baudrate` | `serial:comN` |

Con serie no se guarda la ruta: incluye el puerto USB físico y cambia al
enchufarla en otro. Sin serie la ruta es lo único que distingue dos
impresoras iguales; si se cambia de puerto y es la única con ese VID/PID, el
driver la encuentra igual. Si hay dos iguales sin serie y ninguna está en la
ruta guardada, el driver avisa en vez de adivinar.

Con número de serie, la misma impresora vista por usbprint y por PyUSB tiene
la misma identidad: no se guarda dos veces.

### Driver `UsbPrint`

- `CreateFile` + `WriteFile` / `ReadFile` / `DeviceIoControl` con E/S
  superpuesta y timeout: una impresora sin papel puede dejar un `WriteFile`
  colgado para siempre; al vencer se cancela con `CancelIoEx` y se espera a
  que la cancelación termine antes de soltar el buffer.
- **Convive con el spooler**: si un trabajo de Windows tiene el dispositivo,
  `CreateFile` falla por "en uso" y se reintenta a los 0,25, 0,5, 1 y 2 s.
  Cada ticket abre y cierra (`EscposIO(autoclose=True)`), así que Fiscalberry
  tampoco lo retiene.
- Estado real con DLE EOT 1, 2 y 4 si la impresora tiene endpoint de entrada.
  Si no contesta, "no se sabe": decide la confirmación del papel (#172).
- `IOCTL_USBPRINT_GET_LPT_STATUS` se guarda en el resultado de la prueba
  (`ResultadoPrueba.lpt`) **solo como dato**: muchas térmicas devuelven
  siempre lo mismo.
- Desenchufada (`ERROR_DEVICE_NOT_CONNECTED`, `ERROR_FILE_NOT_FOUND`,
  `ERROR_GEN_FAILURE`) es "no se encontró la impresora"; ocupada después de
  los reintentos, "Windows no dejó usar la impresora".
- Fuera de Windows, `build_driver` responde con un error claro.

### COM: control de flujo

python-escpos abre el `Serial` con control de flujo DSR/DTR y sin límite de
escritura. Si la impresora o el cable no levantan DSR, pyserial no manda
nada y la escritura espera para siempre. La prueba del asistente le pone un
tope de 10 s (`ESPERA_ESCRITURA_SERIE`): falla con "tardó demasiado en
responder" en vez de colgarse. Lo guardado no cambia (`dsrdtr` sigue siendo el
de python-escpos); `dsrdtr = false` en `config.ini` ahora sí lo desactiva
(antes el texto "false" se tomaba como verdadero).

## Verificación en Windows real

La prueba del instalador (`installer/test_installer.ps1`) corre
`fiscalberry-gui.exe --discovery-report` con el ejecutable instalado: lee de
verdad `GetAdaptersAddresses`, `GetIpNetTable`, SetupDi (usbprint y todos los
USB), cfgmgr32 y los puertos COM, y lista las colas con el subproceso
`--list-printers` del exe instalado. Falla si alguna sección revienta, si
tarda más de 120 s, si no hay al menos un adaptador físico con IPv4 o si no
trae la lista de dispositivos USB. El runner no tiene impresoras: el barrido y
los dispositivos se prueban con sockets locales y APIs simuladas en
`tests/test_red_impresoras.py` y `tests/test_usb_directo.py`.

## Prueba con hardware

Pendiente (#186). Todo con una **cuenta estándar** de Windows 10 y 11, sin
permisos de administrador.

Hasta que esté la pantalla del asistente (#184) se puede correr desde la raíz
del repo, con las dependencias instaladas:

```python
import sys
sys.path.insert(0, "src")
from fiscalberry.common import network_discovery, usb_discovery, ticket_prueba

red = network_discovery.search_network()
usb = usb_discovery.search_usb()
print(red.notes, [(p.title, p.host, p.port) for p in red.printers])
print([d.title for d in usb.usbprint], [p.title for p in usb.serial], usb.incompatible)

candidato = (red.printers or usb.usbprint or usb.serial)[0].candidate()
r = ticket_prueba.probar(candidato, "Prueba")
print(r.exito_tecnico, r.problema, r.accion, r.estado_antes, r.lpt)
```

1. **Red, misma subred**: una Epson y una Xprinter/Gprinter por cable al
   router. Tienen que aparecer solas en menos de 5 s. Que el firewall de
   Windows no pida permiso la primera vez (son conexiones salientes).
2. **Red, otra subred**: la impresora con su IP de fábrica y la PC en otro
   rango. Escribir la IP: tiene que decir "otra subred, marca conocida".
3. **SNMP y SAM4S**: anotar qué marcas contestan SNMP. Una SAM4S en el 6001.
4. **USB clase 07 sin driver ni cola** (Epson TM-T20 y una
   Xprinter/Gprinter), con y sin número de serie:
   - que aparezca en la búsqueda y pase la prueba técnica y la de papel;
   - estado real: tapa abierta y sin papel antes de imprimir;
   - desenchufarla en medio de la prueba;
   - enchufarla en otro puerto USB y que siga imprimiendo lo guardado.
5. **Cola de Windows sobre `USB001`**: imprimir con `UsbPrint`, después
   imprimir desde Windows (página de prueba) y que salga. Mandar un trabajo
   largo desde Windows y, mientras sale, imprimir con `UsbPrint`: tiene que
   esperar y salir después.
6. **COM**: una impresora por CH340 o PL2303 y una CDC, a 9600. Anotar si
   pasa la prueba con `dsrdtr` por defecto; si falla por tiempo, repetir con
   `dsrdtr = false` en la sección y anotar el resultado.
7. **Incompatible**: una impresora pasada a WinUSB con Zadig (en una PC de
   prueba) o sin driver: tiene que aparecer como "no se puede usar" y su
   driver tiene que quedar como estaba.
