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

## La pantalla: "Buscar impresoras" — #184

Código: `common/printer_search.py` (sin Kivy), `common/printer_wizard.py`,
`common/printer_guides.py`, `ui/printer_setup_screen.py` y
`ui/kv/printer_setup.kv`.

- Un solo botón **"Buscar impresoras"** corre red, USB/COM y colas de Windows
  en paralelo (`PrinterSearch`, un hilo por fuente) y muestra un solo listado
  que se va llenando: la red y el USB aparecen en ~2 s aunque las colas
  tarden. Nada corre en el hilo de Kivy: los resultados vuelven con `Clock`.
- Cada impresora es una fila grande con un nombre (el modelo si se conoce) y
  una frase sin jerga: "Conectada a la red", "Conectada por USB", "Conectada
  por cable USB", "Instalada en Windows". IP, puerto, driver, MAC y estado del
  spooler aparecen solo con **"Ver detalles"**.
- Una misma impresora vista por dos caminos se muestra una vez (reglas en
  `printer_search.py`); lo oculto (virtuales, fuera de línea, duplicados,
  COM de la placa) se ve con **"Mostrar todas (N más)"**.
- Las ya configuradas aparecen marcadas ("Ya está configurada como Caja") y
  no se vuelven a probar.
- Estados: buscando (con "Dejar de buscar", que deja lo encontrado), lista,
  vacío ("No encontramos impresoras…" con la guía), error por fuente (avisos
  debajo de la lista), probando, confirmar papel, problema (con "Probar de
  nuevo" y "Elegir otra impresora"), nombre, guardada ("Terminar" o "Agregar
  otra", que vuelve a la lista con la guardada marcada).
- **"Sé la dirección de la impresora"**: para una de red que no apareció. La
  dirección se diagnostica con la máscara real (#175). Si es de otra red, o
  es una IP de fábrica, se explica y se ofrece **"Ver la guía paso a paso"**.
  Si es la del router, se lo dice.
- Casos no automáticos (otra subred, impresora USB sin driver o con WinUSB,
  nada encontrado, prueba fallida): enlace a doc.paxapos.com. Todos los
  enlaces están en `printer_guides.py`; las guías específicas
  (paxapos/documentation#117 a #125) todavía no están publicadas y hoy apuntan
  a la página de impresoras y a la biblioteca de drivers.
- **Teclado**: Tab / Shift+Tab recorren botones e impresoras (recuadro azul),
  Enter o Espacio tocan, Escape vuelve atrás (y nunca cierra la app). Al
  llegar a cada paso el foco va a la acción principal, salvo en "¿salió el
  ticket?": un Enter por costumbre no puede confirmar el papel.
- Salir del asistente ("Configurar después", "Terminar", abrirlo de nuevo
  desde la bandeja) cancela la búsqueda y el subproceso de colas. Nada de
  esto toca el servicio MQTT.

### Recorrido E2E

Se probó con la app real bajo xvfb (Linux, `FISCALBERRY_PRINTER_WIZARD=1`),
el comercio vinculado y una impresora TCP falsa en la IP del contenedor que
responde DLE EOT: la búsqueda real la encontró en 2,6 s (1,5 s de barrido +
1 s de SNMP), el ticket llegó con su código, se confirmó el papel y recién ahí
apareció la sección en `config.ini`. Con el servicio MQTT sin poder conectar
(proxy), el asistente siguió respondiendo.

## Diagnóstico para soporte — #185

Código: `common/support_report.py` y `common/windows_privilege.py`.

Ante un error o aviso del asistente aparecen **"Copiar diagnóstico para
soporte"** (al portapapeles y a `diagnostico-impresoras.txt`, junto al
registro) y **"Ver registro"** (la pantalla de logs, que vuelve al asistente).

El reporte se arma **solo con campos permitidos**: versión e instalación,
sistema, nivel de privilegio, comercio (nombre, no el tenant), estado del
servicio, dónde quedó (paso, mensaje, guía), la última prueba (transporte,
identidad, DLE EOT, LPT, si se borró el trabajo de la cola, si se confirmó el
papel), la dirección escrita y su diagnóstico, la búsqueda (qué encontró cada
fuente, tiempos, avisos, ocultas y por qué), las redes de la PC, las
impresoras configuradas (claves de driver solamente) y el **recorrido paso a
paso** con tiempos relativos, que alcanza para reproducir dónde falló.

Lo identificable se reduce: MAC al fabricante (`00:26:AB:xx:xx:xx`), números de
serie a los últimos 4, id del equipo a 4 caracteres, IP pública oculta (las
privadas del local quedan: sin ellas no se entiende un problema de subred),
carpeta del usuario como `~`. Nunca entran credenciales MQTT, JWT,
contraseñas, tokens ni tickets: no se incluyen y, además, una pasada final
reemplaza por `[oculto]` todo valor del `config.ini` cuya clave sea sensible,
todo lo que parezca un JWT y lo que siga a `password=`, `token=`, `Bearer`.
Del registro entran solo advertencias y errores de los módulos del asistente.

**Privilegio** (`detect_privilege`, sin pedir nada): `TokenElevationType`
distingue administrador con UAC (token filtrado), ya elevado o "default"; en
el último caso `IsUserAnAdmin` separa administrador sin UAC de cuenta
estándar. #178 lo va a usar para no mostrar un cartel de UAC que la persona no
puede aprobar.

El escenario 5 (IP temporal, `dhcpstaticipcoexistence` antes y después,
fallback, diario de red) es de la fase 3: el reporte dice explícitamente que
no se usó.

Snapshots aprobados en `tests/snapshots/diagnostico_*.txt` (éxito, USB con
tapa abierta, cola trabada, nada encontrado, otra subred). Si un cambio es a
propósito: `FISCALBERRY_UPDATE_SNAPSHOTS=1 pytest tests/test_diagnostico_soporte.py`
y revisar el diff.

## Verificación en Windows real

La prueba del instalador (`build_tools/test-windows-installer.ps1`, workflow
"Instalador de Windows") corre `fiscalberry-gui.exe --discovery-report` sobre
el ejecutable instalado: lee `GetAdaptersAddresses`, `GetIpNetTable`,
SetupDi (usbprint y todos los USB) y los puertos COM de verdad, y lista las
colas con el subproceso `--list-printers` del exe instalado. Falla si alguna
sección revienta, si no hay al menos un adaptador físico con IPv4, si el
listado de colas tarda más de 5 s, si las colas PDF/XPS del runner no quedan
como virtuales y ocultas o si no se puede leer el nivel de privilegio. El runner no
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
