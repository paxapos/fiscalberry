# Hasar, SAM4S y SerForce por Ethernet (#180)

Investigación para el escenario 5 del asistente: una impresora de red que quedó
con su IP de fábrica, en otra subred que la PC. Sus datos van a la tabla de IPs
de fábrica de #175, al transporte USB de #183 y a los adaptadores de #182.

**Qué tan firme es cada dato.** Todo sale de documentación pública: manuales de
las marcas, de los fabricantes originales (OEM) y de integradores. Desde el
entorno de trabajo no se pudo abrir la mayoría de los PDF, así que varios datos
se tomaron del extracto que muestra el buscador. **Nada se probó con hardware.**
Cada dato lleva su confianza, y la
[verificación con hardware](#verificación-con-hardware) dice qué hay que
confirmar antes de escribir un adaptador.

- **Alta**: documento oficial de la marca o del fabricante del modelo.
- **Media**: documento del OEM aplicado al modelo con marca, o de un integrador.
- **Baja**: un solo resultado, avisos de venta o inferencia.

## Resumen

- **"Serferoce" es, casi seguro, SerForce.** No existe ninguna marca
  "Serferoce". SerForce vende comanderas en Argentina: la TP85E (USB, Ethernet y
  RS-232) y la TP85U (solo USB), a través de STEC, Santich, Megatone y otros.
  Hay que confirmarlo con quien abrió la issue.
- **La Hasar HTP-250 es, muy probablemente, una Gprinter GP-80250N con la marca
  de Hasar.** Su manual de instalación USB/RS-232 hace elegir el driver
  "GP-80250N SERIES", y su IP de fábrica (192.168.123.100) es la de Gprinter. De
  las tres marcas, es la única que ya se puede cargar en la tabla de #175.
- **192.168.123.100 no identifica una marca.** La usan Xprinter, Gprinter y, por
  lo tanto, la HTP-250. Con la IP alcanza para clasificar el caso como "otra
  subred, marca conocida", pero el adaptador se elige por fingerprint, como ya
  exige #182.
- **SAM4S (GIANT-100, ELLIX) no publica su IP de fábrica**, y sus manuales dan el
  **puerto 6001** como predeterminado. Si no escucha también en el 9100, el
  barrido de #175 no la encuentra y el asistente no la puede agregar: hoy solo
  acepta la IP y usa el 9100. No entra en la tabla hasta verificarla.
- **SerForce no tiene documentación de red pública.** Se desconocen el OEM, la IP
  y el puerto: hace falta un equipo.
- **Las fiscales Hasar 2G (SMH/PT-250F, SMH/PT-1000F) quedan fuera del
  asistente.** No hablan ESC/POS y Fiscalberry v3 no tiene driver fiscal (el
  readme todavía menciona la SMH/PT-250F).
- **Adaptador viable en papel: uno solo, Gprinter (incluye la HTP-250)**, sujeto a
  la verificación con hardware. SAM4S y SerForce siguen con la guía manual.

## Matriz

| Modelo | Qué es | IP de fábrica | Puerto de impresión | USB (#183) | DLE EOT | Escenario 5 |
|---|---|---|---|---|---|---|
| Hasar HTP-250 (comandera: Ethernet, USB y RS-232) | Gprinter GP-80250N (media) | **192.168.123.100** (alta); máscara sin publicar | 9100, por ser Gprinter (baja) | Probable clase Impresora (`usbprint`): el instalador la agrega en un puerto USB de Windows (baja) | Probable: Gprinter declara ESC/POS con monitoreo de estado (baja) | **Candidata** (adaptador Gprinter) |
| SAM4S GIANT-100 (USB, serie y Ethernet; la SAM4S que más se ofrece en Argentina) | SAM4S, fabricada por ShinHeung | No publicada: se lee en el autotest | **6001** según SAM4S (media); 9100 según un integrador (baja) | Dos modos: COM virtual con el driver de SAM4S, o USB (media) | Documentado en el manual de comandos de SAM4S (media) | No por ahora |
| SAM4S ELLIX 30/35/40/45/50 | SAM4S | No publicada | 6001 (media) | Sin datos | Mismo manual de comandos (media) | No por ahora |
| SerForce TP85E | OEM desconocido | Desconocida | Desconocido | Desconocido | Desconocido | No por ahora |
| SerForce TP85U (solo USB) | OEM desconocido | No aplica | No aplica | Desconocido | Desconocido | No aplica |
| Hasar SMH/PT-250F y SMH/PT-1000F (fiscales 2G) | Controladores fiscales | Un solo resultado dice 192.168.1.1 (baja) | Protocolo fiscal propio, no ESC/POS | No aplica | No aplica | **Fuera de alcance** |

"DLE EOT" dice si el juego de comandos lo documenta. Si también responde por red
y por USB se confirma con el equipo: algunas placas de red no devuelven datos.
No bloquea al asistente: si la impresora no contesta, `read_status` devuelve
`UNKNOWN_STATUS` y decide la confirmación del papel (#172).

## Por modelo

### Hasar HTP-250

- **OEM.** El manual de instalación USB/RS-232 de Hasar hace instalar el driver
  "GP-80250N SERIES" de Gprinter. Las especificaciones coinciden con la serie
  GP-80250: 250 mm/s, 203 dpi, 80 mm, corte automático y comandos ESC/POS.
- **Red.** Según el manual Ethernet de Hasar, la IP de fábrica es 192.168.123.100
  y la PC tiene que estar en 192.168.123.x para configurarla. La máscara y el
  gateway no figuran en los extractos: se leen en el autotest.
- **Cambio de IP (según el manual de Gprinter).** La herramienta "GPETHERNET"
  cambia la IP por el puerto serie (elige COM y velocidad) o por la red
  ("Configure Interface", con la PC en el **mismo segmento**). También tiene la
  opción "DHCP Client". Algunos modelos traen además un panel web en la IP de la
  impresora. No se encontró si el panel pide contraseña.
- **Autotest.** Se imprime encendiendo la impresora con FEED apretado. El manual
  de Gprinter menciona soltarlo a los 6 segundos para imprimir la hoja larga con
  la IP.
- **Restauración de la red de fábrica:** no documentada en lo encontrado.

Consecuencia para #182: cambiar la IP por red exige estar en el mismo segmento,
que es justamente lo que resuelve la IP temporal de #178. Si la impresora además
está conectada por cable serie, la herramienta de Gprinter cambia la IP por COM,
sin IP temporal ni UAC. Vale la pena confirmarlo con el equipo.

### SAM4S (GIANT-100 y ELLIX)

- **Puerto.** Los manuales de SAM4S (ELLIX35III y serie GIANT-100, "Installing an
  Ethernet Printer") dicen que el puerto predeterminado es el 6001. Un integrador
  (Saby) la configura en el 9100. Puede escuchar en los dos o ser configurable:
  hay que verlo en el autotest.
- **IP.** No se encontró la de fábrica. Se lee en el autotest (encender con FEED
  apretado).
- **Herramientas.** "GIANT Tool" (ShinHeung) para la GIANT-100, "ELLIXSet" para la
  familia ELLIX y panel web en algunos modelos ELLIX. Según Saby, la IP se cambia
  en la pestaña "TCP/IP Setting" ("Printer IP" y después "Network Config"), y la
  contraseña predeterminada es **0821**.
- **USB.** La guía del driver de Windows distingue el modo COM virtual ("SERIAL/VCOM
  CONNECTION"), cuyo driver instala el instalador de SAM4S, y el modo USB ("USB
  CONNECTION"). Falta ver si el COM virtual es CDC (`usbser.sys`, sin driver
  propio) y si el modo USB es clase Impresora.
- **DLE EOT.** Figura en el "SAM4S Printer Control Command Manual" (`DLE EOT n`,
  estado en tiempo real).

### SerForce TP85E y TP85U

- Los avisos de venta describen una comandera de 80 mm con Ethernet, RS-232 y USB
  (TP85E) o solo USB (TP85U): carga de papel frontal, doble cortador patentado,
  230 mm/s, 203 dpi y drivers para Windows, Linux, POSReady y OPOS.
- No se encontraron manual, IP de fábrica, puerto ni herramienta de
  configuración. El OEM tampoco: esas especificaciones las comparten varios
  fabricantes chinos.
- STEC la vende y tiene artículos de soporte para la Hasar 250, pero no se
  encontró ninguno de SerForce.

### Hasar fiscales 2G

La SMH/PT-250F y la SMH/PT-1000F son controladores fiscales con protocolo propio.
El asistente configura impresoras ESC/POS, así que no se las ofrece. La IP de
fábrica 192.168.1.1 sale de un solo resultado, sin confirmar. Si fuera cierta,
coincide con la IP típica del router: **no hay que agregarla a la tabla de
#175**.

## Tabla de IPs de fábrica para #175

| IP | Marcas | Qué hacer |
|---|---|---|
| 192.168.192.168 | Epson TM | Ya está en #175 |
| 192.168.123.100 | Xprinter, Gprinter y Hasar HTP-250 | Sumar Gprinter y la HTP-250 a esa entrada. La IP no elige el adaptador: lo elige el fingerprint |
| Sin datos | SAM4S y SerForce | No entran hasta verificar la IP con el equipo |
| 192.168.1.1 (sin confirmar) | Hasar fiscal 2G | No agregar: es la IP típica del router y el modelo está fuera de alcance |

## Riesgos y límites de soporte

1. **IP compartida.** Una impresora en 192.168.123.100 puede ser Xprinter, Gprinter
   o una HTP-250 (Gprinter con otra marca). Si el fingerprint no coincide
   exactamente, se va al fallback de #182: panel web y guía manual, sin escribir
   nada.
2. **SAM4S en el 6001.** Si no escucha en el 9100, ni el barrido de #175 ni el
   asistente la encuentran. `PrinterWizard.submit_address` ya acepta un puerto,
   pero la pantalla no lo muestra. Esto se decide en #175 después de la
   verificación: sumar el 6001 como señal de identificación y, si imprime por
   ahí, dejar elegir el puerto.
3. **Cambio de IP solo en el mismo segmento** (Gprinter y Xprinter). Confirma el
   diseño de #178. Según la guía de Xprinter, tampoco funciona a través de un
   router.
4. **Contraseñas de fábrica** (SAM4S 0821). Un adaptador no cambia ni guarda
   credenciales. Si el panel pide una contraseña distinta de la de fábrica, se va
   al fallback.
5. **Restauración desconocida.** Ningún modelo tiene documentado el reset de red.
   El `restore` de #182 se habilita por modelo recién cuando se haya probado.
6. **Firmware.** Los OEM cambian el firmware entre lotes sin cambiar el nombre.
   El match de #182 incluye la versión de firmware, y cada versión nueva se
   verifica antes de habilitarla.
7. **Fiscales.** Nunca se les manda ESC/POS. Si alguna escucha en el 9100, #175 no
   la tiene que clasificar como impresora del asistente.
8. **DLE EOT por red.** Si no contesta, el asistente sigue: decide la
   confirmación del papel.

## Verificación con hardware

Para cada equipo (HTP-250, SAM4S GIANT-100 y SerForce TP85E):

1. **Autotest** (encender con FEED apretado): foto del ticket completo con IP,
   máscara, gateway, DHCP, MAC, puertos y firmware. También una foto de la
   etiqueta.
2. **Reset de red** con el procedimiento del manual. Anotar la IP resultante.
3. **Puertos**, desde una PC en la misma subred:
   `nmap -Pn -p 80,443,515,631,6001,9100 <ip>` y `nmap -sU -p 161 <ip>`.
4. **Fingerprint**: título y cabecera `Server` del panel web
   (`curl -sI http://<ip>/`), `sysDescr` y `sysObjectID` por SNMP si responde, y
   `GS I` de ESC/POS:

   ```python
   import socket

   IP, PUERTO = "192.168.123.100", 9100

   def gs_i(n):
       """GS I n: identificación ESC/POS. None = la impresora no contesta."""
       with socket.create_connection((IP, PUERTO), timeout=3) as s:
           s.settimeout(2)
           s.sendall(b"\x1dI" + bytes([n]))
           try:
               return s.recv(256)
           except socket.timeout:
               return None

   for n in (1, 2, 3, 65, 66, 67):  # modelo, tipo, firmware; 65-67: firmware, fabricante, modelo
       print(f"GS I {n}:", gs_i(n))
   ```

   Si la impresora no soporta algún `n`, puede imprimir algún carácter suelto.
5. **DLE EOT por red** con el código de Fiscalberry, en tres estados: normal,
   tapa abierta y sin papel. Se corre desde la raíz del repo, con las
   dependencias instaladas. Cuando #183 esté listo, repetirlo por USB.

   ```python
   import sys
   sys.path.insert(0, "src")
   from fiscalberry.common.ComandosHandler import build_driver
   from fiscalberry.common.printer_test import read_status

   config = {"driver": "Network", "host": "192.168.123.100", "port": "9100", "timeout": "10"}
   print(read_status(build_driver(config).driver))
   # PrinterStatus(online=None, ...) = no contesta DLE EOT
   ```

6. **USB**: en el Administrador de dispositivos, ¿aparece como "Compatibilidad con
   impresión USB" (clase 07) o como puerto COM? Anotar el Id. de hardware
   (VID/PID) y si trae número de serie.
7. **Cambio de IP** con la herramienta oficial, capturando con Wireshark:
   protocolo (broadcast UDP, TCP o HTTP), puerto y autenticación. Probar si
   funciona desde otra subred.
8. **DHCP**: activarlo y ver si la impresora se reencuentra por MAC (tabla ARP) o
   por nombre.

## Lo que tiene que completar el equipo

La issue pide también el inventario de clientes y el hardware disponible. Eso no
está en ninguna documentación:

| Marca y modelo | Firmware | Clientes que la usan | ¿Hay un equipo para probar? |
|---|---|---|---|
| Hasar HTP-250 | | | |
| SAM4S GIANT-100 | | | |
| SerForce TP85E | | | |

## Issues propuestas

Todavía no están creadas:

1. **Adaptador Gprinter (incluye Hasar HTP-250).** Depende de #175, #178, #182 y de
   la verificación con hardware. `default_ips`: 192.168.123.100. `detect`: match
   exacto por `GS I`, panel web o SNMP, más la versión de firmware. `configure`:
   el mecanismo de la herramienta oficial, solo si se puede reproducir sin
   heurísticas; si no, el panel web. `verify`: IP nueva, 9100 y prueba física de
   #172. `restore`: el reset verificado.
2. **SAM4S y SerForce**: por ahora no hay adaptador viable. Siguen en #180 como
   verificación con hardware, o en una issue aparte si el equipo lo prefiere. Si
   la SAM4S resulta viable, el adaptador sale de ahí.

## Fuentes

Hasar HTP-250:
[instalación Ethernet](https://compania.grupohasar.com/wp-content/uploads/2020/07/Instalacion-Ethernet-HTP-250.pdf),
[instalación USB/RS-232](https://compania.grupohasar.com/wp-content/uploads/2020/07/Instalacion-USB-Serie-HTP-250.pdf),
[especificaciones técnicas](https://compania.grupohasar.com/wp-content/uploads/2020/07/Especificaciones-T%C3%A9cnicas-HTP250.pdf),
[STEC: cambiar la IP de la comandera Hasar 250](https://soporte.stec.com.ar/support/solutions/articles/43000463283-como-cambiar-la-direccion-ip-de-la-comandera-hasar-250).

Gprinter y Xprinter:
[GP Ethernet Printer Settings Manual](https://docplayer.net/100644505-Gp-ethernet-printer-settings-manual.html),
[Gprinter: modificar la IP](https://usermanual.wiki/Document/GP20Ethernet20Printer20Settings20Manual.1671206595.pdf),
[manual de instalación de Gprinter (CET)](https://cetuk.co.uk/wp-content/uploads/2021/12/GPrinter-Printer-Installation-Manual.pdf),
[manual de la GP-80250IVN](https://www.manualslib.com/manual/1140486/Gprinter-Gp-80250ivn.html),
[Xprinter: configurar la IP](https://filedn.com/l3YHTxXEORjSP7vqHLwob1f/Xprinter/Tech%20Docs/configure%20IP%20address%20printable.pdf).

SAM4S:
[ELLIX35III, Installing an Ethernet Printer](https://www.manualslib.com/manual/1629925/Sam4s-Ellix35iii.html?page=23),
[serie GIANT-100, Installing an Ethernet Printer](https://www.manualslib.com/manual/1257623/Sam4s-Giant-100-Series.html?page=24),
[Saby: cambiar la IP de una SAM4S](https://saby.ru/help/equipment/receipt_printer/sam4s_change_ip),
[SAM4S Printer Control Command Manual](https://postorg.com.ua/published/file/999628/SAM4S%20Printer%20Control%20Command%20Manual%20REV1_8.pdf),
[guía del driver de Windows](http://sam4s.com/files/DOWN/2023061617233_1.pdf),
[ELLIXSet](http://sam4s.co.kr/include/download.asp?path=board&file=000135_1.8.pdf),
[GIANT Tool](https://multidata-kassen.de/wp-content/uploads/GIANT-100_Firmware-Anleitung_v1.1.pdf),
[GIANT-100 en Argentina](https://www.zetek.com.ar/comanderastickeadoras/impresora-termica-sam4s-giant-100.html).

SerForce:
[TP85E en STEC](https://www.stec.com.ar/products/impresora-termica-serforce-tp85e-usb-y-ethernet-80mm),
[TP85E en Santich](https://santich.net/index.php?id_product=451&controller=product),
[TP85U en Santich](https://santich.net/index.php?id_product=450&controller=product),
[TP85E en Megatone](https://www.megatone.net/producto/impresora-termica-serforce-tp85e-usb-y-ethernet-80mm_MKT0953STC/).

Hasar fiscales 2G:
[manual de la SMH/PT-250F](https://www.grupohasar.com/wp-content/uploads/2018/09/SMH-PT-250F-Manual-del-Usuario.pdf),
[manual de la SMH/PT-1000F](https://www.grupohasar.com/wp-content/uploads/2019/01/Nuevo-manual-1000F.pdf),
[STEC: cambiar la IP de la controladora fiscal Hasar 250](https://soporte.stec.com.ar/support/solutions/articles/43000463339-cambiar-direccion-ip-controladora-fiscal-hasar-250).

ESC/POS:
[DLE EOT](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/dle_eot.html),
[GS I](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_ci.html).
