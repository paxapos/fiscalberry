"""
Impresoras de red y redes de la PC (#175).

Encuentra solas las impresoras de red que están en el mismo rango que la PC
(escenario 1 de #170) y explica por qué no se encuentra una que está en otro
rango (detección del escenario 5; cambiarle la IP es trabajo de #178 y #182).
**Nunca modifica nada**: ni la red de la PC ni la impresora.

1. Adaptadores (`list_adapters`): en Windows, `GetAdaptersAddresses` con IPv4,
   máscara real, gateways y métrica. Se descartan loopback, VPN, Hyper-V,
   VirtualBox, VMware, WSL y demás adaptadores virtuales: barrer la red de una
   VPN mandaría miles de conexiones a la empresa de alguien.
2. Barrido (`tcp_sweep`): TCP 9100 a cada dirección del rango, con sockets no
   bloqueantes en paralelo y timeout corto. Un /24 tarda lo que el timeout
   (1,5 s), no 254 veces eso. Se puede cancelar en cualquier momento.
3. Señales (`snmp_query`, `read_arp_table`): SNMP v2c unicast a UDP 161
   (sysDescr, sysName, hrDeviceDescr) para mostrar el modelo, y la tabla ARP
   de Windows para la MAC. El firewall de Windows deja pasar la respuesta de
   un pedido que salió de la PC, sin reglas nuevas.
4. Clasificación (`diagnose_address`): con la máscara real, una dirección
   queda como misma subred, otra subred con IP de fábrica conocida, otra
   subred desconocida, apagada, puerto cerrado o inválida.

SAM4S usa por defecto el puerto 6001 (investigación de #180). No se barre
todo el rango en ese puerto: solo se prueba en los equipos que respondieron
en el 9100 con "puerto cerrado" (están vivos, pero no escuchan ahí). Si el
6001 contesta, se ofrece como impresora en ese puerto y la prueba en papel
decide. Ver docs/asistente-impresoras-busqueda.md.
"""

import errno
import ipaddress
import os
import selectors
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_setup import (
    DEFAULT_RAW_PORT,
    SetupValidationError,
    TCP_INVALID,
    TCP_NO_RESPONSE,
    TCP_OK,
    TCP_REFUSED,
    probe_tcp,
    validate_network_address,
)

logger = getLogger("NetworkDiscovery")


# -- IPs de fábrica (#180) ------------------------------------------------------

# La IP no identifica la marca: 192.168.123.100 la comparten Xprinter, Gprinter
# y la Hasar HTP-250 (una Gprinter con otra marca). Alcanza para decir "otra
# subred, marca conocida"; el adaptador de #182 se elige por fingerprint.
# 192.168.1.1 (Hasar fiscal, sin confirmar) NO va: es la IP típica del router.
FACTORY_ADDRESSES = {
    "192.168.192.168": ("Epson",),
    "192.168.123.100": ("Xprinter", "Gprinter", "Hasar HTP-250"),
}

# Puerto de impresión de SAM4S según sus manuales (#180, confianza media).
SAM4S_PORT = 6001


# -- Adaptadores ----------------------------------------------------------------

ADAPTER_PHYSICAL = "fisico"
ADAPTER_LOOPBACK = "loopback"
ADAPTER_VPN = "vpn"
ADAPTER_VIRTUAL = "virtual"

# IANA ifType
IF_TYPE_ETHERNET = 6
IF_TYPE_PPP = 23
IF_TYPE_LOOPBACK = 24
IF_TYPE_PROP_VIRTUAL = 53
IF_TYPE_WIFI = 71
IF_TYPE_TUNNEL = 131

_VPN_WORDS = (
    "vpn", "tap-windows", "tap adapter", "tap-win32", "wireguard", "wintun",
    "openvpn", "anyconnect", "fortinet", "forticlient", "globalprotect", "pangp",
    "sonicwall", "zerotier", "tailscale", "hamachi", "nordlynx", "juniper",
    "pulse secure", "check point", "checkpoint", "proton", "softether",
    "array networks", "f5 networks", "wan miniport",
)
# "Microsoft Hyper-V Network Adapter" es la placa de una PC virtual (así se
# ven los runners de GitHub): es física para esa PC. Los virtuales de un host
# Hyper-V son "Hyper-V Virtual Ethernet Adapter" y se llaman "vEthernet (...)".
_HYPERV_HOST_WORDS = ("vethernet", "hyper-v virtual")
_VIRTUAL_WORDS = _HYPERV_HOST_WORDS + (
    "virtualbox", "vmware", "virtual ethernet",
    "virtual adapter", "docker", "wsl", "npcap", "loopback", "bluetooth",
    "wi-fi direct", "kernel debug", "teredo", "isatap", "6to4", "parallels",
    "microsoft wi-fi direct", "host-only",
)
_LINUX_VIRTUAL_PREFIXES = ("docker", "br-", "veth", "virbr", "vmnet", "vboxnet",
                           "lxc", "lxd", "cni", "flannel", "podman", "ifb", "dummy")
_LINUX_VPN_PREFIXES = ("tun", "tap", "wg", "tailscale", "zt", "ppp", "ipsec")


def classify_adapter(name, description="", if_type=IF_TYPE_ETHERNET, has_gateway=False):
    """
    Tipo de adaptador: solo los físicos se barren.

    Un "vEthernet" con gateway es un switch externo de Hyper-V: por ahí pasa
    la red real de la PC, así que cuenta como físico. El "Default Switch" y el
    de WSL no tienen gateway (son la NAT interna).
    """
    texto = f"{name} {description}".lower()
    if has_gateway and any(p in texto for p in _HYPERV_HOST_WORDS) \
            and not any(p in texto for p in _VPN_WORDS):
        return ADAPTER_PHYSICAL
    if if_type == IF_TYPE_LOOPBACK or name == "lo":
        return ADAPTER_LOOPBACK
    if if_type in (IF_TYPE_TUNNEL, IF_TYPE_PPP) or any(p in texto for p in _VPN_WORDS):
        return ADAPTER_VPN
    if name.lower().startswith(_LINUX_VPN_PREFIXES):
        return ADAPTER_VPN
    if if_type == IF_TYPE_PROP_VIRTUAL or any(p in texto for p in _VIRTUAL_WORDS):
        return ADAPTER_VIRTUAL
    if name.lower().startswith(_LINUX_VIRTUAL_PREFIXES):
        return ADAPTER_VIRTUAL
    return ADAPTER_PHYSICAL


@dataclass(frozen=True)
class NetworkAdapter:
    """Una dirección IPv4 de un adaptador de la PC."""

    name: str
    address: str
    prefix: Optional[int]
    description: str = ""
    gateways: tuple = ()
    metric: int = 0
    if_type: int = IF_TYPE_ETHERNET
    up: bool = True
    dhcp: Optional[bool] = None
    mac: str = ""
    kind: str = ADAPTER_PHYSICAL
    # Máscara que no es un prefijo (p. ej. 255.255.0.255): se informa tal cual.
    raw_netmask: str = ""

    @property
    def network(self):
        if self.prefix is None:
            return None
        return ipaddress.IPv4Network(f"{self.address}/{self.prefix}", strict=False)

    @property
    def link_local(self):
        return ipaddress.IPv4Address(self.address).is_link_local

    @property
    def usable(self):
        """¿Se barre? Físico, conectado y con una dirección de verdad."""
        return self.kind == ADAPTER_PHYSICAL and self.up and not self.link_local

    def contains(self, host):
        red = self.network
        try:
            return red is not None and ipaddress.IPv4Address(host) in red
        except ValueError:
            return False

    @property
    def label(self):
        return self.name or self.description or "adaptador"


def prefix_from_netmask(netmask):
    """Prefijo de una máscara (255.255.255.0 -> 24), o None si no es contigua."""
    try:
        valor = int(ipaddress.IPv4Address(netmask))
    except ValueError:
        return None
    prefijo = bin(valor).count("1")
    esperado = (0xFFFFFFFF << (32 - prefijo)) & 0xFFFFFFFF if prefijo else 0
    return prefijo if valor == esperado else None


# ---- Windows: GetAdaptersAddresses --------------------------------------------

import ctypes  # noqa: E402  (disponible en todas las plataformas)
from ctypes import POINTER, Structure, c_char_p, c_int32, c_uint8, c_uint32, c_uint64, c_void_p  # noqa: E402


class _SOCKET_ADDRESS(Structure):
    _fields_ = [("lpSockaddr", c_void_p), ("iSockaddrLength", c_int32)]


class _UNICAST(Structure):
    pass


_UNICAST._fields_ = [
    ("Length", c_uint32), ("Flags", c_uint32),
    ("Next", POINTER(_UNICAST)),
    ("Address", _SOCKET_ADDRESS),
    ("PrefixOrigin", c_int32), ("SuffixOrigin", c_int32), ("DadState", c_int32),
    ("ValidLifetime", c_uint32), ("PreferredLifetime", c_uint32), ("LeaseLifetime", c_uint32),
    ("OnLinkPrefixLength", c_uint8),
]


class _GATEWAY(Structure):
    pass


_GATEWAY._fields_ = [
    ("Length", c_uint32), ("Reserved", c_uint32),
    ("Next", POINTER(_GATEWAY)),
    ("Address", _SOCKET_ADDRESS),
]


class _ADAPTER(Structure):
    pass


# IP_ADAPTER_ADDRESSES_LH hasta Ipv4Metric: el resto no se usa, y como la
# memoria la reserva la API (no este struct), no hace falta declararlo.
_ADAPTER._fields_ = [
    ("Length", c_uint32), ("IfIndex", c_uint32),
    ("Next", POINTER(_ADAPTER)),
    ("AdapterName", c_char_p),
    ("FirstUnicastAddress", POINTER(_UNICAST)),
    ("FirstAnycastAddress", c_void_p),
    ("FirstMulticastAddress", c_void_p),
    ("FirstDnsServerAddress", c_void_p),
    ("DnsSuffix", c_void_p),
    ("Description", c_void_p),
    ("FriendlyName", c_void_p),
    ("PhysicalAddress", c_uint8 * 8),
    ("PhysicalAddressLength", c_uint32),
    ("Flags", c_uint32),
    ("Mtu", c_uint32),
    ("IfType", c_uint32),
    ("OperStatus", c_int32),
    ("Ipv6IfIndex", c_uint32),
    ("ZoneIndices", c_uint32 * 16),
    ("FirstPrefix", c_void_p),
    ("TransmitLinkSpeed", c_uint64),
    ("ReceiveLinkSpeed", c_uint64),
    ("FirstWinsServerAddress", c_void_p),
    ("FirstGatewayAddress", POINTER(_GATEWAY)),
    ("Ipv4Metric", c_uint32),
]

_AF_INET_WINDOWS = 2
_GAA_FLAGS = 0x2 | 0x4 | 0x8 | 0x80   # sin anycast/multicast/DNS, con gateways
_IP_ADAPTER_DHCP_ENABLED = 0x4
_IF_OPER_STATUS_UP = 1
_ERROR_BUFFER_OVERFLOW = 111
_ERROR_NO_DATA = 232


def _utf16_at(ptr, limite=512):
    """Texto UTF-16 terminado en cero (WCHAR* de Windows) en cualquier plataforma."""
    if not ptr:
        return ""
    datos = bytearray()
    for i in range(limite):
        par = ctypes.string_at(ptr + 2 * i, 2)
        if par == b"\x00\x00":
            break
        datos += par
    return datos.decode("utf-16-le", errors="replace")


def _ipv4_de_sockaddr(socket_address):
    """IPv4 de un SOCKET_ADDRESS (sockaddr_in), o None si es de otra familia."""
    if not socket_address.lpSockaddr or socket_address.iSockaddrLength < 8:
        return None
    crudo = ctypes.string_at(socket_address.lpSockaddr, 8)
    familia = struct.unpack("<H", crudo[:2])[0]
    if familia != _AF_INET_WINDOWS:
        return None
    return socket.inet_ntoa(crudo[4:8])


def parse_windows_adapters(first):
    """Recorre la lista de IP_ADAPTER_ADDRESSES y arma NetworkAdapter."""
    adaptadores = []
    nodo = first
    while nodo:
        a = nodo.contents
        nombre = _utf16_at(a.FriendlyName)
        descripcion = _utf16_at(a.Description)
        gateways = []
        gw = a.FirstGatewayAddress
        while gw:
            ip = _ipv4_de_sockaddr(gw.contents.Address)
            if ip:
                gateways.append(ip)
            gw = gw.contents.Next
        mac = ":".join(f"{b:02X}" for b in list(a.PhysicalAddress)[:min(a.PhysicalAddressLength, 8)])
        tipo = int(a.IfType)
        uni = a.FirstUnicastAddress
        while uni:
            ip = _ipv4_de_sockaddr(uni.contents.Address)
            if ip:
                prefijo = int(uni.contents.OnLinkPrefixLength)
                adaptadores.append(NetworkAdapter(
                    name=nombre,
                    description=descripcion,
                    address=ip,
                    prefix=prefijo if 0 <= prefijo <= 32 else None,
                    gateways=tuple(gateways),
                    metric=int(a.Ipv4Metric),
                    if_type=tipo,
                    up=int(a.OperStatus) == _IF_OPER_STATUS_UP,
                    dhcp=bool(a.Flags & _IP_ADAPTER_DHCP_ENABLED),
                    mac=mac,
                    kind=classify_adapter(nombre, descripcion, tipo, bool(gateways)),
                ))
            uni = uni.contents.Next
        nodo = a.Next
    return adaptadores


def windows_adapters(iphlpapi=None):
    """Adaptadores IPv4 de Windows (GetAdaptersAddresses, sin admin)."""
    api = iphlpapi or ctypes.WinDLL("iphlpapi")
    tamano = c_uint32(16 * 1024)
    for _ in range(4):
        buffer = ctypes.create_string_buffer(tamano.value)
        rc = api.GetAdaptersAddresses(_AF_INET_WINDOWS, _GAA_FLAGS, None, buffer,
                                      ctypes.byref(tamano))
        if rc == 0:
            return parse_windows_adapters(ctypes.cast(buffer, POINTER(_ADAPTER)))
        if rc == _ERROR_NO_DATA:
            return []
        if rc != _ERROR_BUFFER_OVERFLOW:
            raise OSError(rc, f"GetAdaptersAddresses devolvió {rc}")
    raise OSError(_ERROR_BUFFER_OVERFLOW, "GetAdaptersAddresses: la lista no entra en memoria")


# ---- Linux (desarrollo): ioctl + /proc ------------------------------------------

_SIOCGIFFLAGS = 0x8913
_SIOCGIFADDR = 0x8915
_SIOCGIFNETMASK = 0x891B
_IFF_UP = 0x1
_IFF_LOOPBACK = 0x8


def _linux_gateways(route_text):
    """{interfaz: [gateway]} desde /proc/net/route."""
    gateways = {}
    for linea in route_text.splitlines()[1:]:
        partes = linea.split()
        if len(partes) < 3 or partes[1] != "00000000":
            continue
        try:
            gw = socket.inet_ntoa(struct.pack("<I", int(partes[2], 16)))
        except (ValueError, struct.error):
            continue
        gateways.setdefault(partes[0], []).append(gw)
    return gateways


def linux_adapters(sys_net="/sys/class/net", route_file="/proc/net/route"):
    """Adaptadores en Linux. Solo para desarrollar el asistente fuera de Windows."""
    import fcntl

    try:
        with open(route_file, encoding="utf-8") as fh:
            gateways = _linux_gateways(fh.read())
    except OSError:
        gateways = {}

    adaptadores = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for nombre in sorted(os.listdir(sys_net)):
            ifreq = struct.pack("256s", nombre.encode()[:15])
            try:
                flags = struct.unpack("H", fcntl.ioctl(sock, _SIOCGIFFLAGS, ifreq)[16:18])[0]
                ip = socket.inet_ntoa(fcntl.ioctl(sock, _SIOCGIFADDR, ifreq)[20:24])
                mascara = socket.inet_ntoa(fcntl.ioctl(sock, _SIOCGIFNETMASK, ifreq)[20:24])
            except OSError:
                continue  # sin IPv4
            try:
                with open(os.path.join(sys_net, nombre, "address"), encoding="utf-8") as fh:
                    mac = fh.read().strip().upper()
            except OSError:
                mac = ""
            tipo = IF_TYPE_LOOPBACK if flags & _IFF_LOOPBACK else IF_TYPE_ETHERNET
            prefijo = prefix_from_netmask(mascara)
            adaptadores.append(NetworkAdapter(
                name=nombre, address=ip, prefix=prefijo,
                gateways=tuple(gateways.get(nombre, ())),
                if_type=tipo, up=bool(flags & _IFF_UP), mac=mac,
                kind=classify_adapter(nombre, "", tipo, bool(gateways.get(nombre))),
                raw_netmask="" if prefijo is not None else mascara,
            ))
    finally:
        sock.close()
    return adaptadores


def list_adapters(platform=None, windows=windows_adapters, linux=linux_adapters):
    """Todos los adaptadores IPv4 (incluidos los que no se barren, para informar)."""
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return windows()
    if platform.startswith("linux"):
        return linux()
    return []


# -- Qué se barre ----------------------------------------------------------------

# Más de esto (una red /21 o mayor) no se barre entera: se revisan las 254
# direcciones vecinas de la PC y se avisa.
MAX_SWEEP_HOSTS = 1022


@dataclass(frozen=True)
class SweepPlan:
    adapter: NetworkAdapter
    hosts: tuple = ()
    partial: bool = False
    unsupported: str = ""   # por qué no se barre (en palabras)

    @property
    def note(self):
        if self.unsupported:
            return self.unsupported
        if self.partial:
            vecina = ipaddress.IPv4Network(f"{self.adapter.address}/24", strict=False)
            return (f"La red de \"{self.adapter.label}\" es muy grande "
                    f"(/{self.adapter.prefix}): se revisaron solo las direcciones "
                    f"{vecina.network_address + 1} a {vecina.broadcast_address - 1}.")
        return ""


def plan_sweep(adapter, max_hosts=MAX_SWEEP_HOSTS):
    """Las direcciones a barrer de un adaptador, con la máscara real."""
    if adapter.link_local:
        return SweepPlan(adapter, unsupported=(
            f"\"{adapter.label}\" no recibió dirección de red (169.254.x.x): la "
            "computadora no encontró el router. Si la impresora está conectada "
            "directo a la computadora, sin router, seguí la guía."))
    if adapter.prefix is None:
        return SweepPlan(adapter, unsupported=(
            f"\"{adapter.label}\" tiene una máscara que no se puede usar "
            f"({adapter.raw_netmask or 'desconocida'}): no se revisó esa red."))
    if adapter.prefix >= 31:
        return SweepPlan(adapter, unsupported=(
            f"\"{adapter.label}\" tiene máscara /{adapter.prefix}: no hay otras "
            "direcciones en esa red."))
    red = adapter.network
    if red.num_addresses - 2 > max_hosts:
        red = ipaddress.IPv4Network(f"{adapter.address}/24", strict=False)
        return SweepPlan(adapter, tuple(str(h) for h in red.hosts()), partial=True)
    return SweepPlan(adapter, tuple(str(h) for h in red.hosts()))


# -- Barrido TCP --------------------------------------------------------------------

SWEEP_TIMEOUT = 1.5      # Windows reintenta el SYN tras un RST: menos, y "cerrado" parece "nadie"
SWEEP_CONCURRENCY = 256  # select() de Python en Windows admite hasta 512 sockets

_EN_CURSO = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY, 10035, 10036, 10037}
_RECHAZADO = {errno.ECONNREFUSED, errno.ECONNRESET, 10061, 10054}


def _resultado_de_errno(codigo):
    if codigo == 0:
        return TCP_OK
    if codigo in _RECHAZADO:
        return TCP_REFUSED
    return TCP_NO_RESPONSE


def tcp_sweep(hosts, port=DEFAULT_RAW_PORT, timeout=SWEEP_TIMEOUT, concurrency=SWEEP_CONCURRENCY,
              cancel=None, socket_factory=None, selector_factory=None, clock=time.monotonic):
    """
    {host: TCP_OK | TCP_REFUSED | TCP_NO_RESPONSE} para cada host en `port`.

    Conexiones no bloqueantes en paralelo (hasta `concurrency` a la vez): el
    barrido tarda ~`timeout` por tanda, no por host. `cancel` (threading.Event)
    lo corta; lo que no se llegó a probar queda afuera del resultado.
    """
    factory = socket_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    resultados = {}
    pendientes = list(dict.fromkeys(hosts))
    sel = (selector_factory or selectors.DefaultSelector)()
    abiertos = {}   # socket -> (host, límite)

    def cerrar(sock):
        try:
            sel.unregister(sock)
        except (KeyError, ValueError, OSError):
            pass
        try:
            sock.close()
        except OSError:
            pass

    try:
        while pendientes or abiertos:
            if cancel is not None and cancel.is_set():
                break
            while pendientes and len(abiertos) < concurrency:
                host = pendientes.pop(0)
                try:
                    sock = factory()
                    sock.setblocking(False)
                    codigo = sock.connect_ex((host, port))
                except OSError as e:
                    resultados[host] = TCP_NO_RESPONSE
                    logger.debug(f"Barrido: {host} no se pudo intentar: {e}")
                    continue
                if codigo in _EN_CURSO:
                    abiertos[sock] = (host, clock() + timeout)
                    sel.register(sock, selectors.EVENT_WRITE)
                else:
                    resultados[host] = _resultado_de_errno(codigo)
                    sock.close()
            if not abiertos:
                continue
            espera = max(0.0, min(limite for _, limite in abiertos.values()) - clock())
            for clave, _ in sel.select(min(espera, 0.1)):
                sock = clave.fileobj
                host, _ = abiertos.pop(sock)
                try:
                    codigo = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                except OSError as e:
                    codigo = e.errno or -1
                resultados[host] = _resultado_de_errno(codigo)
                cerrar(sock)
            ahora = clock()
            for sock, (host, limite) in list(abiertos.items()):
                if ahora >= limite:
                    del abiertos[sock]
                    resultados[host] = TCP_NO_RESPONSE
                    cerrar(sock)
    finally:
        for sock in list(abiertos):
            cerrar(sock)
        sel.close()
    return resultados


# -- SNMP v2c (sin dependencias) -------------------------------------------------

OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_HR_DEVICE_DESCR = "1.3.6.1.2.1.25.3.2.1.3.1"
SNMP_OIDS = (OID_SYS_DESCR, OID_SYS_OBJECT_ID, OID_SYS_NAME, OID_HR_DEVICE_DESCR)
SNMP_PORT = 161
SNMP_TIMEOUT = 1.0

# Número de empresa (IANA) en sysObjectID -> marca.
SNMP_ENTERPRISES = {1248: "Epson", 11: "HP", 2435: "Brother", 1602: "Canon",
                    1347: "Kyocera", 367: "Ricoh", 253: "Xerox"}


def _ber_len(n):
    if n < 0x80:
        return bytes([n])
    cuerpo = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(cuerpo)]) + cuerpo


def _ber(tag, contenido):
    return bytes([tag]) + _ber_len(len(contenido)) + contenido


def _ber_int(valor):
    largo = max(1, (valor.bit_length() + 8) // 8)
    return _ber(0x02, valor.to_bytes(largo, "big", signed=True))


def _ber_oid(oid):
    partes = [int(p) for p in oid.split(".")]
    cuerpo = bytearray([40 * partes[0] + partes[1]])
    for p in partes[2:]:
        grupo = [p & 0x7F]
        p >>= 7
        while p:
            grupo.insert(0, 0x80 | (p & 0x7F))
            p >>= 7
        cuerpo += bytes(grupo)
    return _ber(0x06, bytes(cuerpo))


def encode_get_request(request_id, oids, community="public"):
    """GetRequest SNMP v2c."""
    varbinds = b"".join(_ber(0x30, _ber_oid(o) + b"\x05\x00") for o in oids)
    pdu = _ber(0xA0, _ber_int(request_id) + _ber_int(0) + _ber_int(0) + _ber(0x30, varbinds))
    return _ber(0x30, _ber_int(1) + _ber(0x04, community.encode()) + pdu)


def _ber_leer(datos, i):
    """(tag, contenido, siguiente índice)."""
    tag = datos[i]
    largo = datos[i + 1]
    i += 2
    if largo & 0x80:
        n = largo & 0x7F
        largo = int.from_bytes(datos[i:i + n], "big")
        i += n
    if i + largo > len(datos):
        raise ValueError("respuesta SNMP truncada")
    return tag, datos[i:i + largo], i + largo


def _decode_oid(contenido):
    partes = [contenido[0] // 40, contenido[0] % 40]
    valor = 0
    for b in contenido[1:]:
        valor = (valor << 7) | (b & 0x7F)
        if not b & 0x80:
            partes.append(valor)
            valor = 0
    return ".".join(str(p) for p in partes)


def decode_response(datos):
    """(request_id, error_status, {oid: valor}) de un GetResponse, o ValueError."""
    tag, mensaje, _ = _ber_leer(datos, 0)
    if tag != 0x30:
        raise ValueError("no es un mensaje SNMP")
    _, _version, i = _ber_leer(mensaje, 0)
    _, _comunidad, i = _ber_leer(mensaje, i)
    tag, pdu, _ = _ber_leer(mensaje, i)
    if tag != 0xA2:
        raise ValueError("no es un GetResponse")
    _, rid, i = _ber_leer(pdu, 0)
    _, estado, i = _ber_leer(pdu, i)
    _, _indice, i = _ber_leer(pdu, i)
    _, lista, _ = _ber_leer(pdu, i)
    valores = {}
    j = 0
    while j < len(lista):
        _, vb, j = _ber_leer(lista, j)
        _, oid, k = _ber_leer(vb, 0)
        tag, valor, _ = _ber_leer(vb, k)
        oid = _decode_oid(oid)
        if tag == 0x04:
            valores[oid] = valor.decode("utf-8", errors="replace").strip("\x00 \r\n")
        elif tag == 0x06:
            valores[oid] = _decode_oid(valor)
        elif tag in (0x02, 0x41, 0x42, 0x43):
            valores[oid] = int.from_bytes(valor, "big", signed=(tag == 0x02))
        # noSuchObject/noSuchInstance/NULL: no hay dato
    return int.from_bytes(rid, "big", signed=True), int.from_bytes(estado, "big"), valores


def snmp_query(hosts, oids=SNMP_OIDS, community="public", timeout=SNMP_TIMEOUT,
               cancel=None, socket_factory=None, clock=time.monotonic, port=SNMP_PORT):
    """
    {host: {oid: valor}} de los que contestaron. Un solo socket UDP para todos:
    se manda un pedido a cada uno y se juntan las respuestas hasta el timeout.
    Una impresora sin SNMP (o con otra comunidad) simplemente no aparece.
    """
    if not hosts:
        return {}
    factory = socket_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    sock = factory()
    resultados = {}
    try:
        sock.settimeout(0.1)
        ids = {}
        for n, host in enumerate(hosts, start=1):
            rid = 0x4642_0000 + n
            ids[rid] = host
            try:
                sock.sendto(encode_get_request(rid, oids, community), (host, port))
            except OSError as e:
                logger.debug(f"SNMP a {host} no se pudo mandar: {e}")
        limite = clock() + timeout
        while len(resultados) < len(ids) and clock() < limite:
            if cancel is not None and cancel.is_set():
                break
            try:
                datos, (origen, _) = sock.recvfrom(4096)
            except (socket.timeout, TimeoutError, BlockingIOError):
                continue
            except OSError:
                continue  # Windows: ICMP "puerto inalcanzable" de otro host
            try:
                rid, estado, valores = decode_response(datos)
            except (ValueError, IndexError):
                continue
            host = ids.get(rid)
            if host is not None and host == origen and estado == 0:
                resultados[host] = valores
    finally:
        sock.close()
    return resultados


def model_from_snmp(valores):
    """Texto corto con el modelo, a partir de lo que contestó SNMP."""
    for oid in (OID_HR_DEVICE_DESCR, OID_SYS_DESCR, OID_SYS_NAME):
        texto = str(valores.get(oid) or "").strip()
        if texto:
            return " ".join(texto.split())[:60]
    return ""


def brand_from_snmp(valores):
    oid = str(valores.get(OID_SYS_OBJECT_ID) or "")
    prefijo = "1.3.6.1.4.1."
    if oid.startswith(prefijo):
        try:
            return SNMP_ENTERPRISES.get(int(oid[len(prefijo):].split(".")[0]), "")
        except ValueError:
            return ""
    return ""


# -- Tabla ARP e ICMP (señales, sin admin) -------------------------------------------

# OUI -> marca. Solo los prefijos registrados que se pudieron confirmar; es una
# pista para la pantalla, nunca decide nada.
MAC_VENDORS = {
    "00:26:AB": "Epson", "64:EB:8C": "Epson", "A4:EE:57": "Epson", "AC:18:26": "Epson",
    "00:11:62": "Star Micronics",
}


class _MIB_IPNETROW(Structure):
    _fields_ = [("dwIndex", c_uint32), ("dwPhysAddrLen", c_uint32),
                ("bPhysAddr", c_uint8 * 8), ("dwAddr", c_uint32), ("dwType", c_uint32)]


_ERROR_INSUFFICIENT_BUFFER = 122
_ARP_INVALID = 2


def _mac_valida(mac):
    return mac and mac not in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF") \
        and not mac.startswith("01:00:5E")


def parse_ip_net_table(buffer):
    """{ip: mac} de un MIB_IPNETTABLE en memoria."""
    n = c_uint32.from_buffer_copy(buffer[:4]).value
    tabla = {}
    fila_tam = ctypes.sizeof(_MIB_IPNETROW)
    # El arreglo de filas arranca alineado a 4 después de dwNumEntries.
    for k in range(n):
        inicio = 4 + k * fila_tam
        fila = _MIB_IPNETROW.from_buffer_copy(buffer[inicio:inicio + fila_tam])
        if fila.dwType == _ARP_INVALID:
            continue
        ip = socket.inet_ntoa(struct.pack("<I", fila.dwAddr))
        mac = ":".join(f"{b:02X}" for b in list(fila.bPhysAddr)[:min(fila.dwPhysAddrLen, 8)])
        if _mac_valida(mac):
            tabla[ip] = mac
    return tabla


def windows_arp_table(iphlpapi=None):
    api = iphlpapi or ctypes.WinDLL("iphlpapi")
    tamano = c_uint32(0)
    for _ in range(4):
        buffer = ctypes.create_string_buffer(max(tamano.value, 4))
        rc = api.GetIpNetTable(buffer, ctypes.byref(tamano), False)
        if rc == 0:
            return parse_ip_net_table(buffer.raw)
        if rc == _ERROR_NO_DATA:
            return {}
        if rc != _ERROR_INSUFFICIENT_BUFFER:
            raise OSError(rc, f"GetIpNetTable devolvió {rc}")
    return {}


def linux_arp_table(path="/proc/net/arp"):
    tabla = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lineas = fh.read().splitlines()[1:]
    except OSError:
        return tabla
    for linea in lineas:
        partes = linea.split()
        if len(partes) >= 4 and _mac_valida(partes[3].upper()):
            tabla[partes[0]] = partes[3].upper()
    return tabla


def read_arp_table(platform=None):
    """{ip: MAC} que la PC ya conoce. Nunca lanza: es una señal, no un requisito."""
    platform = sys.platform if platform is None else platform
    try:
        if platform == "win32":
            return windows_arp_table()
        if platform.startswith("linux"):
            return linux_arp_table()
    except Exception as e:
        logger.debug(f"No se pudo leer la tabla ARP: {e}")
    return {}


def windows_icmp_echo(host, timeout=1.0, iphlpapi=None):
    """
    Ping con IcmpSendEcho (sin admin). True si respondió, False si no, None si
    no se pudo intentar. Es solo una señal: muchas impresoras no responden ping.
    """
    try:
        api = iphlpapi
        if api is None:
            api = ctypes.WinDLL("iphlpapi")
            # Sin esto ctypes trunca el HANDLE a 32 bits y no acepta un IPAddr
            # mayor a 2^31 (toda IP que termine en .128 o más).
            api.IcmpCreateFile.restype = c_void_p
            api.IcmpSendEcho.argtypes = [c_void_p, c_uint32, c_void_p, ctypes.c_uint16,
                                         c_void_p, c_void_p, c_uint32, c_uint32]
            api.IcmpSendEcho.restype = c_uint32
            api.IcmpCloseHandle.argtypes = [c_void_p]
        destino = struct.unpack("<I", socket.inet_aton(host))[0]
        handle = api.IcmpCreateFile()
        if not handle or handle == -1:
            return None
        try:
            datos = b"fiscalberry"
            respuesta = ctypes.create_string_buffer(64 + len(datos) + 8)
            n = api.IcmpSendEcho(handle, destino, datos, len(datos), None, respuesta,
                                 len(respuesta), int(timeout * 1000))
            if not n:
                return False
            estado = struct.unpack("<I", respuesta.raw[4:8])[0]
            return estado == 0
        finally:
            api.IcmpCloseHandle(handle)
    except Exception as e:
        logger.debug(f"ICMP a {host} no disponible: {e}")
        return None


# -- Diagnóstico de una dirección ----------------------------------------------------

KIND_SAME_SUBNET = "misma_subred"
KIND_ROUTED = "otra_subred_alcanzable"
KIND_OTHER_KNOWN = "otra_subred_marca_conocida"
KIND_OTHER_UNKNOWN = "otra_subred_desconocida"
KIND_HOST_OFF = "apagada"
KIND_PORT_CLOSED = "puerto_cerrado"
KIND_INVALID = "invalido"

PRINTABLE_KINDS = (KIND_SAME_SUBNET, KIND_ROUTED)


@dataclass(frozen=True)
class AddressDiagnosis:
    """Por qué una dirección sirve o no, en datos (la UI arma el texto)."""

    kind: str
    host: str = ""
    port: int = DEFAULT_RAW_PORT
    tcp: str = TCP_INVALID
    adapter: Optional[NetworkAdapter] = None
    local_networks: tuple = ()
    brands: tuple = ()
    is_gateway: bool = False
    error: str = ""

    @property
    def printable(self):
        return self.kind in PRINTABLE_KINDS

    def as_dict(self):
        return {
            "kind": self.kind, "host": self.host, "port": self.port, "tcp": self.tcp,
            "adapter": self.adapter.label if self.adapter else None,
            "local_networks": list(self.local_networks), "brands": list(self.brands),
            "is_gateway": self.is_gateway,
        }


def factory_brands(host):
    return FACTORY_ADDRESSES.get(str(host).strip(), ())


def diagnose_address(host, port=DEFAULT_RAW_PORT, adapters=None, probe=probe_tcp):
    """
    Clasifica una dirección con la máscara real de cada adaptador de la PC.

    Bloquea hasta 3 s (el diagnóstico TCP): llamarla fuera del hilo de Kivy.
    `adapters` son los de list_adapters(); los no barribles (VPN, virtuales)
    no cuentan como "la red de la PC".
    """
    try:
        host_ok, port_ok = validate_network_address(host, port)
    except SetupValidationError as e:
        return AddressDiagnosis(KIND_INVALID, host=str(host), tcp=TCP_INVALID, error=str(e))

    propios = [a for a in (adapters or ()) if a.usable and a.network is not None]
    redes = tuple(str(a.network) for a in propios)
    local = next((a for a in propios if a.contains(host_ok)), None)
    marcas = factory_brands(host_ok)

    if local is not None:
        red = local.network
        direccion = ipaddress.IPv4Address(host_ok)
        if red.prefixlen < 31 and direccion in (red.network_address, red.broadcast_address):
            return AddressDiagnosis(
                KIND_INVALID, host=host_ok, port=port_ok, adapter=local, local_networks=redes,
                error="Esa dirección es la de la red, no puede ser una impresora")

    tcp = probe(host_ok, port_ok)
    es_gateway = any(host_ok in a.gateways for a in propios)
    comunes = dict(host=host_ok, port=port_ok, tcp=tcp, adapter=local,
                   local_networks=redes, brands=marcas, is_gateway=es_gateway)

    if tcp == TCP_INVALID:
        return AddressDiagnosis(KIND_INVALID, **comunes)
    if tcp == TCP_OK:
        return AddressDiagnosis(KIND_SAME_SUBNET if local or not propios else KIND_ROUTED,
                                **comunes)
    if tcp == TCP_REFUSED:
        return AddressDiagnosis(KIND_PORT_CLOSED, **comunes)
    if local is not None or not propios:
        return AddressDiagnosis(KIND_HOST_OFF, **comunes)
    return AddressDiagnosis(KIND_OTHER_KNOWN if marcas else KIND_OTHER_UNKNOWN, **comunes)


def address_in_use(host, probe=probe_tcp, arp=None, icmp=None, ports=(80, 443, DEFAULT_RAW_PORT),
                   platform=None):
    """
    ¿Hay algún equipo usando esta dirección? Para detectar conflictos antes de
    proponer una IP (escenario 5). Devuelve (True/False/None, [evidencias]).

    TCP 80/443/9100 son evidencia (aceptar o rechazar = hay alguien); la tabla
    ARP e ICMP son señales. None = no se pudo saber (sin evidencia ni señales).
    """
    platform = sys.platform if platform is None else platform
    evidencias = []
    for puerto in ports:
        resultado = probe(host, puerto, timeout=1.0)
        if resultado in (TCP_OK, TCP_REFUSED):
            evidencias.append(f"tcp{puerto}:{resultado}")
    tabla = (arp or read_arp_table)()
    if host in tabla:
        evidencias.append("arp")
    if icmp is None and platform == "win32":
        icmp = windows_icmp_echo
    eco = icmp(host) if icmp else None
    if eco:
        evidencias.append("icmp")
    if evidencias:
        return True, evidencias
    # Sin respuestas: libre si al menos se pudo preguntar por ICMP.
    return (False if eco is False else None), evidencias


# -- Búsqueda completa -----------------------------------------------------------------

@dataclass(frozen=True)
class NetworkPrinter:
    """Algo que acepta conexiones en un puerto de impresión."""

    host: str
    port: int = DEFAULT_RAW_PORT
    adapter: Optional[NetworkAdapter] = None   # None = fuera de las redes de la PC
    model: str = ""
    brand: str = ""
    mac: str = ""
    factory_brands: tuple = ()
    snmp: dict = field(default_factory=dict)

    @property
    def same_subnet(self):
        return self.adapter is not None

    def candidate(self):
        from fiscalberry.common.printer_setup import PrinterCandidate
        return PrinterCandidate.network(self.host, self.port)

    @property
    def mac_short(self):
        """Solo el fabricante de la placa (OUI): el resto identifica al equipo."""
        return (self.mac[:8] + ":xx:xx:xx") if self.mac else ""


@dataclass
class NetworkSearchResult:
    adapters: list = field(default_factory=list)       # todos, para el diagnóstico
    plans: list = field(default_factory=list)
    printers: list = field(default_factory=list)
    notes: list = field(default_factory=list)          # avisos en palabras
    error: str = ""
    swept: int = 0
    seconds: float = 0.0
    cancelled: bool = False

    @property
    def usable_adapters(self):
        return [a for a in self.adapters if a.usable]


def _nota_adaptador_excluido(a):
    if a.kind == ADAPTER_VPN:
        return f"Se ignoró la conexión VPN \"{a.label}\"."
    if a.kind == ADAPTER_VIRTUAL:
        return f"Se ignoró el adaptador virtual \"{a.label}\"."
    return ""


def search_network(cancel=None, adapters=None, list_adapters_fn=list_adapters,
                   sweep=tcp_sweep, snmp=snmp_query, arp=read_arp_table,
                   factory=FACTORY_ADDRESSES, alt_port=SAM4S_PORT, clock=time.monotonic):
    """
    Barre las redes físicas de la PC y devuelve NetworkSearchResult. No lanza.

    Además de los rangos propios, prueba las IPs de fábrica que caen fuera de
    ellos: si una responde (hay una ruta hasta ella) se puede usar tal cual.
    Si no responde no se puede saber si está ahí: sin una IP en ese rango, la
    PC no llega (eso es el escenario 5, #178).
    """
    cancel = cancel or threading.Event()
    inicio = clock()
    resultado = NetworkSearchResult()
    try:
        resultado.adapters = list(adapters) if adapters is not None else list(list_adapters_fn())
    except Exception as e:
        logger.warning(f"No se pudieron leer los adaptadores de red: {e}")
        resultado.error = "No se pudo leer la configuración de red de la computadora."
        resultado.seconds = clock() - inicio
        return resultado

    for a in resultado.adapters:
        if a.up and a.kind in (ADAPTER_VPN, ADAPTER_VIRTUAL):
            nota = _nota_adaptador_excluido(a)
            if nota and nota not in resultado.notes:
                resultado.notes.append(nota)

    fisicos = [a for a in resultado.adapters if a.kind == ADAPTER_PHYSICAL and a.up]
    if not fisicos:
        resultado.notes.append("La computadora no está conectada a ninguna red por cable o Wi-Fi.")

    adaptador_de = {}
    for a in fisicos:
        plan = plan_sweep(a)
        resultado.plans.append(plan)
        if plan.note:
            resultado.notes.append(plan.note)
        for h in plan.hosts:
            adaptador_de.setdefault(h, a)

    propios = [a for a in fisicos if a.usable]
    fabrica = [ip for ip in factory if not any(a.contains(ip) for a in propios)]
    objetivos = list(adaptador_de) + [ip for ip in fabrica if ip not in adaptador_de]
    resultado.swept = len(objetivos)

    try:
        respuestas = sweep(objetivos, DEFAULT_RAW_PORT, cancel=cancel) if objetivos else {}
        encontrados = [(h, DEFAULT_RAW_PORT) for h in objetivos if respuestas.get(h) == TCP_OK]
        vivos = [h for h in objetivos if respuestas.get(h) == TCP_REFUSED]
        if alt_port and vivos and not cancel.is_set():
            alt = sweep(vivos, alt_port, cancel=cancel)
            encontrados += [(h, alt_port) for h in vivos if alt.get(h) == TCP_OK]

        datos_snmp = {}
        if encontrados and not cancel.is_set():
            try:
                datos_snmp = snmp(sorted({h for h, _ in encontrados}), cancel=cancel)
            except Exception as e:
                logger.debug(f"SNMP no disponible: {e}")
        macs = arp() if encontrados else {}

        for host, puerto in encontrados:
            valores = datos_snmp.get(host, {})
            mac = macs.get(host, "")
            resultado.printers.append(NetworkPrinter(
                host=host, port=puerto, adapter=adaptador_de.get(host),
                model=model_from_snmp(valores),
                brand=brand_from_snmp(valores) or MAC_VENDORS.get(mac[:8], ""),
                mac=mac, factory_brands=tuple(factory.get(host, ())), snmp=dict(valores),
            ))
    except Exception as e:
        logger.error(f"Error en el barrido de red: {e}", exc_info=True)
        resultado.error = "No se pudo revisar la red."

    resultado.printers.sort(key=lambda p: (not p.same_subnet, ipaddress.IPv4Address(p.host), p.port))
    resultado.cancelled = cancel.is_set()
    resultado.seconds = clock() - inicio
    logger.info("Búsqueda de red: %d direcciones en %.1f s, %d impresoras",
                resultado.swept, resultado.seconds, len(resultado.printers))
    return resultado
