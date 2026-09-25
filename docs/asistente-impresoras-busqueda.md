# Asistente de impresoras: búsqueda automática (fase 2)

Cómo encuentra Fiscalberry las impresoras sin que la persona escriba nada, en
los escenarios 1 a 4 de la épica #170. Todo corre **sin permisos de
administrador**, fuera del hilo de la interfaz, y **nunca modifica** la PC, la
red ni la impresora: no se crean colas, no se instalan ni reemplazan drivers y
no se cambia ninguna IP.

Cada buscador entrega `PrinterCandidate` (ver `common/printer_setup.py`), el
mismo objeto que prueba el ticket (#172) y guarda el servicio (#171). Nada se
guarda en `config.ini` hasta que la prueba sale bien **y** la persona confirma
el papel.

## Red (escenario 1 y detección del 5) — #175

Código: `src/fiscalberry/common/network_discovery.py`.

### Adaptadores

`list_adapters()` lee en Windows `GetAdaptersAddresses` (IPv4, con gateways):
nombre, descripción, dirección, **prefijo real** (`OnLinkPrefixLength`),
gateways, métrica, DHCP, MAC y estado. Cada dirección de cada adaptador es un
`NetworkAdapter`.

Solo se barren los adaptadores **físicos y conectados**. Se descartan y se
avisa en la pantalla:

| Tipo | Cómo se reconoce |
|---|---|
| Loopback | `IfType` 24 |
| VPN | `IfType` 131 (túnel) o 23 (PPP), o la descripción: TAP-Windows, WireGuard, Wintun, OpenVPN, AnyConnect, Fortinet, GlobalProtect, ZeroTier, Tailscale, Hamachi… |
| Virtual | `vEthernet` / "Hyper-V Virtual Ethernet Adapter" (Default Switch, WSL), VirtualBox Host-Only, VMware VMnet, Docker, Bluetooth PAN, Wi-Fi Direct… |

Dos excepciones pensadas a propósito:

- "Microsoft Hyper-V Network Adapter" es la placa de una **PC virtual** (así
  se ven los runners de GitHub y muchas VPS): para esa PC es física.
- Un `vEthernet` **con gateway** es un switch externo de Hyper-V: la red real
  de la PC pasa por ahí, así que se barre.

En Linux (solo para desarrollar con `FISCALBERRY_PRINTER_WIZARD=1`) se usan
`ioctl` y `/proc/net/route`.

### Qué se barre

`plan_sweep()` usa la máscara real:

- Hasta 1022 direcciones (/22 o menor): se barre el rango entero.
- Una red más grande (/21, /16, 10.0.0.0/8…): se barren las 254 direcciones
  vecinas a la PC y se avisa. **La clasificación sigue usando la máscara real.**
- 169.254.x.x (la PC no encontró el router), /31, /32 o una máscara que no es
  un prefijo: no se barre y se informa. No se fuerza ninguna máscara.

Además se prueban las **IPs de fábrica** que quedan fuera de los rangos de la
PC. Si una responde (hay una ruta hasta ella), se puede usar tal cual.

### Barrido TCP 9100

`tcp_sweep()` abre conexiones **no bloqueantes** en paralelo (hasta 256 a la
vez, el límite práctico de `select()` en Windows es 512) con un timeout de
1,5 s por tanda. Un /24 tarda ~1,5 s; con SNMP, ~2,5 s. El timeout no es más
corto porque Windows reintenta el SYN después de un RST: con menos de ~1 s un
"puerto cerrado" parece "nadie". Se cancela en cualquier momento (al salir del
asistente) y cierra todos los sockets.

Un equipo que **rechaza** el 9100 está vivo (las impresoras contestan RST;
las PCs con firewall no contestan nada).

### SAM4S y el puerto 6001

Los manuales de SAM4S dan el **6001** como puerto de impresión (#180, confianza
media). Decisión: **no** se barre todo el rango en el 6001 (duplicaría el
tráfico); se prueba solo en los equipos que rechazaron el 9100. Si el 6001
acepta, se ofrece como impresora de red en ese puerto y la prueba en papel
decide. Riesgo conocido: el 6001 también es el display `:1` de X11 en Linux
(casi nunca abierto por TCP hoy); si fuera eso, el ticket no sale y no se
guarda nada. **Sin verificar con hardware.**

### Señales para mostrar el modelo

- **SNMP v2c** unicast a UDP 161, comunidad `public`: `sysDescr`, `sysObjectID`,
  `sysName` y `hrDeviceDescr.1`, a todas las impresoras encontradas con un solo
  socket y 1 s de espera. El firewall de Windows deja pasar la respuesta sin
  reglas nuevas porque el pedido salió de la PC. `sysObjectID` 1248 = Epson.
- **Tabla ARP** (`GetIpNetTable`): la MAC de lo que se encontró. Se muestra solo
  el fabricante de la placa (`00:26:AB:xx:xx:xx`). Algunos prefijos de Epson y
  Star están en `MAC_VENDORS`: es una pista para la pantalla, no decide nada.
- **ICMP** (`IcmpSendEcho`, sin admin) solo como señal en `address_in_use()`.

### Clasificación de una dirección (`diagnose_address`)

`AddressDiagnosis.kind`:

| Valor | Cuándo |
|---|---|
| `misma_subred` | Está en el rango (máscara real) de un adaptador físico y el 9100 acepta |
| `otra_subred_alcanzable` | Fuera de los rangos, pero hay ruta y el 9100 acepta: se puede usar |
| `otra_subred_marca_conocida` | Fuera de los rangos, no responde y es una IP de fábrica (escenario 5) |
| `otra_subred_desconocida` | Fuera de los rangos, no responde (p. ej. 192.168.123.68 con la PC en 192.168.1.27/24) |
| `apagada` | En el rango, nadie responde |
| `puerto_cerrado` | Responde el equipo pero no el 9100 (`is_gateway` dice si es el router) |
| `invalido` | No es una IPv4 usable, o es la dirección de red o de broadcast |

La red de una VPN o de un adaptador virtual **no** cuenta como "la red de la
PC".

### IPs de fábrica

| IP | Marcas | Fuente |
|---|---|---|
| 192.168.192.168 | Epson TM | #175 |
| 192.168.123.100 | Xprinter, Gprinter, Hasar HTP-250 | #180 |

La IP no identifica la marca (tres comparten la misma). **192.168.1.1 no se
agrega**: es la IP típica del router (#180). SAM4S y SerForce no tienen IP de
fábrica publicada.

Sin una IP en el rango de la impresora, la PC no puede hablarle: por eso el
escenario 5 solo se **detecta** (cuando la persona escribe la dirección que
imprimió la hoja de autotest) y se ofrece la guía. Cambiarle la IP es #178
(IP temporal con UAC) y #182 (adaptadores por marca), en la fase 3.

### Conflictos de IP

`address_in_use()` junta evidencia de que alguien usa una dirección antes de
proponerla (lo usará el escenario 5): TCP 80/443/9100 (aceptar o rechazar =
hay alguien), la tabla ARP e ICMP. Devuelve `None` si no se pudo saber.

## USB directo y COM (escenarios 2 y 3) — #183

Código: `src/fiscalberry/common/usb_discovery.py` (búsqueda) y
`src/fiscalberry/common/usbprint_driver.py` (driver `UsbPrint`).

### Por qué no PyUSB

Una térmica de clase Impresora USB (0x07) usa `usbprint.sys`, que viene con
Windows y crea el puerto `USB00x` aunque no haya driver de impresora ni cola.
PyUSB/libusb exigiría reemplazar ese driver por WinUSB (Zadig, con admin), y
eso rompe la cola de Windows. **Nunca se hace.** El driver `Usb` (PyUSB) queda
solo para Linux y para equipos que ya exponen WinUSB.

### Búsqueda

- `SetupDiGetClassDevs` + `SetupDiEnumDeviceInterfaces` sobre
  `GUID_DEVINTERFACE_USBPRINT` `{28d78fad-5a12-11d1-ae5b-0000f803a8c2}`. De la
  ruta (`\\?\usb#vid_04b8&pid_0e15#<serie>#{guid}`) salen VID, PID y serie.
  Si la instancia tiene `&` (Windows la inventó) o el dispositivo es
  compuesto (`&mi_00`), no hay serie.
- El puerto `USB001` sale de la clave de registro de la interfaz (`Port
  Number` + `Base Name`): sirve para reconocer la cola de Windows que usa la
  misma impresora y no mostrarla dos veces.
- El modelo: primero el Device ID IEEE 1284 (`IOCTL_USBPRINT_GET_1284_ID`,
  `MFG:EPSON;MDL:TM-T20II`), después la descripción que reporta el bus
  (`DEVPKEY_Device_BusReportedDeviceDesc`), después la marca por VID.
- **COM** con `serial.tools.list_ports`: CDC (`usbser.sys`), CH340, PL2303,
  FTDI y CP210x aparecen con VID/PID. Los COM de Bluetooth no se abren nunca
  (abrirlos intenta conectar y puede colgar); los de la placa madre y los
  módems se ocultan por defecto. Velocidad: 9600.
- **Incompatibles**: con `SetupDiGetClassDevs("USB")` se revisan todos los
  USB. Una impresora (clase 07 o VID de una marca conocida) sin driver
  (`DN_HAS_PROBLEM`, sin servicio) o con WinUSB/libusb se muestra como "no se
  puede usar" con el enlace a la guía. No se toca su driver.

### Identidad

Se guarda VID/PID/serie, no la ruta: la ruta incluye el puerto físico. Sin
serie, la ruta forma parte de la identidad (dos térmicas iguales solo se
distinguen por el puerto) y se guarda; si la impresora se enchufa en otro
puerto y es la única con ese VID/PID, se la reencuentra igual. Si hay dos
iguales sin serie y ninguna está en la ruta guardada, el driver avisa en vez
de adivinar.

### Driver `UsbPrint`

- `CreateFile` + `WriteFile` / `ReadFile` / `DeviceIoControl` con E/S
  superpuesta y timeout: una impresora sin papel puede dejar un `WriteFile`
  colgado para siempre; al vencer se cancela con `CancelIoEx`.
- **Convive con el spooler**: si un trabajo de Windows tiene el dispositivo,
  `CreateFile` falla por "en uso" y se reintenta a los 0,25, 0,5, 1 y 2 s.
  Cada ticket abre y cierra (`EscposIO(autoclose=True)`), así que Fiscalberry
  tampoco lo retiene y la cola de Windows sigue funcionando.
- Estado real con DLE EOT (1, 2 y 4) si la impresora tiene endpoint de entrada;
  si no contesta, decide la confirmación del papel (#172).
- `IOCTL_USBPRINT_GET_LPT_STATUS` se registra en el resultado de la prueba
  (`lpt_status`) **solo como dato**: muchas térmicas devuelven siempre el
  mismo valor y bloquear por eso daría falsos "sin papel".
- Desenchufada (`ERROR_DEVICE_NOT_CONNECTED`, `ERROR_FILE_NOT_FOUND`,
  `ERROR_GEN_FAILURE`) = "no se encontró la impresora"; ocupada después de
  los reintentos = "Windows no dejó usar la impresora".
- Fuera de Windows, `build_driver` responde con un `DriverError` claro.

## Colas de Windows ya instaladas (escenario 4) — #174

Código: `src/fiscalberry/common/windows_queues.py`.

- `EnumPrinters(PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS, 2)`: nombre,
  puerto, driver, atributos, estado y servidor. (`printer_detector.py` usaba
  nivel 1, que trae solo el nombre; no se tocó.)
- **En un subproceso que se puede matar**: `fiscalberry-gui.exe
  --list-printers --report <json>` (en desarrollo, `python -m
  fiscalberry.common.windows_queues`). Una cola compartida caída
  (`\\servidor\cola`) puede colgar `EnumPrinters` más de 30 s y un hilo de
  Python no se cancela. Si no termina en 8 s se lo mata y se reintenta solo
  con las colas locales (5 s); si también vence, se explica sin congelar la
  pantalla. Al salir del asistente el subproceso se mata en el acto.
- Se ocultan por defecto (quedan con "Mostrar todas"): PDF, XPS, OneNote, fax
  (atributo o driver) y colas fuera de línea ("usar impresora sin conexión",
  `PRINTER_STATUS_OFFLINE`, servidor desconocido).
- Orden: locales listas (la predeterminada primero), locales con algún aviso,
  compartidas, ocultas. Duplicadas (la misma cola local y como conexión, o con
  otras mayúsculas) aparecen una sola vez.
- El estado del spooler se muestra en "Detalles" **como dato**: muchos puertos
  TCP/IP y drivers POS dicen "Lista" con la impresora apagada. La verdad la da
  el papel (#172); si no se confirma, el trabajo se borra de la cola.
- La selección es `Win32Raw(printer_name=...)`; una cola ya guardada se
  reconoce sin distinguir mayúsculas.
- El puerto (`USB001`, `COM3:`) sirve para no mostrar dos veces la misma
  impresora: si una cola usa `USB001`, la impresora usbprint de ese puerto se
  muestra solo con "Mostrar todas" (se prefiere la cola que ya usa el local).

## Verificación en Windows real

La prueba del instalador (`build_tools/test-windows-installer.ps1`, workflow
"Instalador de Windows") corre `fiscalberry-gui.exe --discovery-report` sobre
el ejecutable instalado: lee `GetAdaptersAddresses`, `GetIpNetTable`,
SetupDi (usbprint y todos los USB) y los puertos COM de verdad, y lista las
colas con el subproceso `--list-printers` del exe instalado. Falla si alguna
sección revienta, si no hay al menos un adaptador físico con IPv4, si el
listado de colas tarda más de 5 s o si las colas PDF/XPS del runner no quedan
como virtuales y ocultas. El runner no
tiene impresoras: el barrido y las impresoras se prueban con fakes y sockets
locales en `tests/test_red_impresoras.py`.

## Pendiente de hardware

- Escenario 1 en Windows 10 y 11 con cuenta estándar: una impresora Epson y una
  Xprinter/Gprinter por cable al router.
- Que el firewall de Windows no pida permiso la primera vez (no debería: son
  conexiones salientes y respuestas a pedidos propios).
- SNMP en las marcas del mercado (muchas térmicas no lo traen).
- SAM4S en el 6001.
- Escenario 2: una térmica USB clase 07 **sin driver ni cola** con cuenta
  estándar (Epson TM-T20 y una Xprinter/Gprinter), con y sin número de serie;
  que responda DLE EOT por usbprint; desenchufarla en medio de la prueba.
- Que una cola de Windows existente sobre `USB001` siga imprimiendo después de
  usar `UsbPrint` (y mientras el spooler imprime, que `UsbPrint` espere).
- Escenario 3: una impresora por CH340/PL2303/FTDI y una CDC, a 9600. Si
  alguna necesita otra velocidad, hay que sumar la detección de velocidad.
- Una impresora con WinUSB (Zadig) o sin driver: que aparezca como
  incompatible y que no se toque nada.
- Escenario 4: una cola USB (driver del fabricante) y una por puerto TCP/IP
  con la impresora apagada (el spooler dice "Lista": la prueba tiene que
  fallar y borrar el trabajo). Una PC con una cola compartida de otra PC
  apagada: el listado tiene que caer al reintento solo con las locales.
