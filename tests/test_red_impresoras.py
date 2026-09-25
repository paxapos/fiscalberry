# coding=utf-8
"""
Impresoras de red y redes de la PC (#175), sin red real.

Las salidas de Windows (GetAdaptersAddresses, GetIpNetTable) se arman en
memoria con los mismos structs que lee el código: así se prueba el parser de
verdad, con VPN, Hyper-V, máscaras raras y adaptadores desconectados. El
barrido TCP usa sockets reales en 127.0.0.x (Linux atiende todo 127/8) y
fakes para los timeouts.
"""

import ctypes
import socket
import struct
import threading
import time

import pytest

from fiscalberry.common import network_discovery as nd
from fiscalberry.common.printer_setup import TCP_NO_RESPONSE, TCP_OK, TCP_REFUSED


def adaptador(ip="192.168.1.27", prefix=24, name="Ethernet", kind=nd.ADAPTER_PHYSICAL,
              gateways=("192.168.1.1",), up=True, **kw):
    return nd.NetworkAdapter(name=name, address=ip, prefix=prefix, gateways=gateways,
                             kind=kind, up=up, **kw)


# ---------------------------------------------------------------------------
# Adaptadores: qué se barre y qué no
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre,descripcion,tipo,esperado", [
    ("Ethernet", "Intel(R) Ethernet Connection I219-V", nd.IF_TYPE_ETHERNET, nd.ADAPTER_PHYSICAL),
    ("Wi-Fi", "Realtek RTL8821CE 802.11ac PCIe Adapter", nd.IF_TYPE_WIFI, nd.ADAPTER_PHYSICAL),
    ("vEthernet (Default Switch)", "Hyper-V Virtual Ethernet Adapter", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VIRTUAL),
    ("vEthernet (WSL)", "Hyper-V Virtual Ethernet Adapter #2", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VIRTUAL),
    ("Ethernet 2", "VirtualBox Host-Only Ethernet Adapter", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VIRTUAL),
    ("VMware Network Adapter VMnet8", "VMware Virtual Ethernet Adapter for VMnet8", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VIRTUAL),
    ("Ethernet 3", "TAP-Windows Adapter V9", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VPN),
    ("OficinaVPN", "WireGuard Tunnel", nd.IF_TYPE_PROP_VIRTUAL, nd.ADAPTER_VPN),
    ("Ethernet 4", "Cisco AnyConnect Secure Mobility Client Virtual Miniport Adapter", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VPN),
    ("Ethernet 5", "Fortinet SSL VPN Virtual Ethernet Adapter", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VPN),
    ("Loopback Pseudo-Interface 1", "Software Loopback Interface 1", nd.IF_TYPE_LOOPBACK, nd.ADAPTER_LOOPBACK),
    ("Conexión de red Bluetooth", "Bluetooth Device (Personal Area Network)", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VIRTUAL),
    ("Túnel", "Microsoft Teredo Tunneling Adapter", nd.IF_TYPE_TUNNEL, nd.ADAPTER_VPN),
    ("docker0", "", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VIRTUAL),
    ("wg0", "", nd.IF_TYPE_ETHERNET, nd.ADAPTER_VPN),
    ("lo", "", nd.IF_TYPE_LOOPBACK, nd.ADAPTER_LOOPBACK),
])
def test_clasificacion_de_adaptadores(nombre, descripcion, tipo, esperado):
    assert nd.classify_adapter(nombre, descripcion, tipo) == esperado


def test_la_placa_de_una_pc_virtual_de_hyper_v_es_fisica():
    """Así se ve la placa de red de un runner de GitHub (una VM de Azure)."""
    assert nd.classify_adapter("Ethernet", "Microsoft Hyper-V Network Adapter",
                               nd.IF_TYPE_ETHERNET) == nd.ADAPTER_PHYSICAL


def test_un_switch_externo_de_hyper_v_con_gateway_es_la_red_real():
    externo = ("vEthernet (Externo)", "Hyper-V Virtual Ethernet Adapter")
    assert nd.classify_adapter(*externo, nd.IF_TYPE_ETHERNET, has_gateway=True) == nd.ADAPTER_PHYSICAL
    assert nd.classify_adapter(*externo, nd.IF_TYPE_ETHERNET, has_gateway=False) == nd.ADAPTER_VIRTUAL
    # Una VPN con gateway sigue siendo VPN.
    assert nd.classify_adapter("VPN", "TAP-Windows Adapter V9", nd.IF_TYPE_ETHERNET,
                               has_gateway=True) == nd.ADAPTER_VPN


@pytest.mark.parametrize("mascara,prefijo", [
    ("255.255.255.0", 24), ("255.255.254.0", 23), ("255.255.0.0", 16),
    ("255.255.255.252", 30), ("255.255.255.255", 32), ("0.0.0.0", 0),
    ("255.255.0.255", None), ("255.0.255.0", None), ("no-es-mascara", None),
])
def test_prefijo_desde_mascara(mascara, prefijo):
    assert nd.prefix_from_netmask(mascara) == prefijo


def test_plan_de_un_24_barre_las_254_direcciones():
    plan = nd.plan_sweep(adaptador())
    assert len(plan.hosts) == 254
    assert plan.hosts[0] == "192.168.1.1" and plan.hosts[-1] == "192.168.1.254"
    assert not plan.partial and not plan.note


def test_plan_de_un_22_se_barre_entero():
    plan = nd.plan_sweep(adaptador("10.0.5.9", 22))
    assert len(plan.hosts) == 1022 and not plan.partial


def test_una_red_grande_se_barre_parcial_y_se_avisa():
    plan = nd.plan_sweep(adaptador("10.1.20.33", 16))
    assert plan.partial
    assert plan.hosts[0] == "10.1.20.1" and len(plan.hosts) == 254
    assert "muy grande" in plan.note and "/16" in plan.note


@pytest.mark.parametrize("ip,prefix,texto", [
    ("169.254.10.20", 16, "169.254"),
    ("192.168.1.27", 31, "/31"),
    ("192.168.1.27", 32, "/32"),
    ("192.168.1.27", None, "máscara"),
])
def test_mascaras_no_soportadas_se_informan_y_no_se_fuerzan(ip, prefix, texto):
    plan = nd.plan_sweep(adaptador(ip, prefix, raw_netmask="255.255.0.255" if prefix is None else ""))
    assert plan.hosts == ()
    assert texto in plan.unsupported


# ---- GetAdaptersAddresses simulado --------------------------------------------

class MemoriaWindows:
    """Arma en memoria la lista enlazada que devuelve GetAdaptersAddresses."""

    def __init__(self):
        self._vivos = []

    def _guardar(self, obj):
        self._vivos.append(obj)
        return obj

    def wstr(self, texto):
        buf = ctypes.create_string_buffer((texto + "\0").encode("utf-16-le"))
        return ctypes.addressof(self._guardar(buf))

    def sockaddr(self, ip):
        crudo = struct.pack("<HH4s8x", 2, 0, socket.inet_aton(ip))
        buf = self._guardar(ctypes.create_string_buffer(crudo, len(crudo)))
        return nd._SOCKET_ADDRESS(ctypes.addressof(buf), len(crudo))

    def unicasts(self, direcciones):
        anterior = None
        for ip, prefijo in reversed(direcciones):
            u = self._guardar(nd._UNICAST())
            u.Address = self.sockaddr(ip)
            u.OnLinkPrefixLength = prefijo
            if anterior is not None:
                u.Next = ctypes.pointer(anterior)
            anterior = u
        return ctypes.pointer(anterior) if anterior is not None else None

    def gateways(self, ips):
        anterior = None
        for ip in reversed(ips):
            g = self._guardar(nd._GATEWAY())
            g.Address = self.sockaddr(ip)
            if anterior is not None:
                g.Next = ctypes.pointer(anterior)
            anterior = g
        return ctypes.pointer(anterior) if anterior is not None else None

    def lista(self, adaptadores):
        anterior = None
        for datos in reversed(adaptadores):
            a = self._guardar(nd._ADAPTER())
            a.FriendlyName = self.wstr(datos["nombre"])
            a.Description = self.wstr(datos.get("descripcion", ""))
            a.IfType = datos.get("tipo", nd.IF_TYPE_ETHERNET)
            a.OperStatus = 1 if datos.get("conectado", True) else 2
            a.Flags = 0x4 if datos.get("dhcp", True) else 0
            a.Ipv4Metric = datos.get("metrica", 25)
            mac = bytes.fromhex(datos.get("mac", "001122334455"))
            a.PhysicalAddressLength = len(mac)
            for i, b in enumerate(mac):
                a.PhysicalAddress[i] = b
            uni = self.unicasts(datos.get("ips", []))
            if uni is not None:
                a.FirstUnicastAddress = uni
            gw = self.gateways(datos.get("gateways", []))
            if gw is not None:
                a.FirstGatewayAddress = gw
            if anterior is not None:
                a.Next = ctypes.pointer(anterior)
            anterior = a
        return anterior


SALIDA_WINDOWS = [
    {"nombre": "Ethernet", "descripcion": "Intel(R) Ethernet Connection I219-V",
     "ips": [("192.168.1.27", 24)], "gateways": ["192.168.1.1"], "metrica": 25,
     "mac": "A4BB6D112233"},
    {"nombre": "Wi-Fi", "descripcion": "Intel(R) Wi-Fi 6 AX201 160MHz", "tipo": nd.IF_TYPE_WIFI,
     "ips": [("10.0.0.15", 24), ("10.0.1.15", 23)], "gateways": ["10.0.0.1"], "metrica": 35},
    {"nombre": "vEthernet (Default Switch)", "descripcion": "Hyper-V Virtual Ethernet Adapter",
     "ips": [("172.29.160.1", 20)], "metrica": 5000},
    {"nombre": "VPN Oficina", "descripcion": "TAP-Windows Adapter V9",
     "ips": [("10.8.0.6", 24)], "metrica": 1},
    {"nombre": "Ethernet 2", "descripcion": "Realtek PCIe GbE Family Controller",
     "ips": [("169.254.33.7", 16)], "conectado": False, "dhcp": True},
    {"nombre": "Loopback Pseudo-Interface 1", "descripcion": "Software Loopback Interface 1",
     "tipo": nd.IF_TYPE_LOOPBACK, "ips": [("127.0.0.1", 8)]},
]


def test_parser_de_get_adapters_addresses():
    mem = MemoriaWindows()
    primero = mem.lista(SALIDA_WINDOWS)
    adaptadores = nd.parse_windows_adapters(ctypes.pointer(primero))

    por_ip = {a.address: a for a in adaptadores}
    assert set(por_ip) == {"192.168.1.27", "10.0.0.15", "10.0.1.15", "172.29.160.1",
                           "10.8.0.6", "169.254.33.7", "127.0.0.1"}
    eth = por_ip["192.168.1.27"]
    assert eth.name == "Ethernet"
    assert eth.description.startswith("Intel(R) Ethernet")
    assert eth.prefix == 24 and eth.gateways == ("192.168.1.1",)
    assert eth.metric == 25 and eth.dhcp is True and eth.up is True
    assert eth.mac == "A4:BB:6D:11:22:33"
    assert eth.kind == nd.ADAPTER_PHYSICAL and eth.usable

    # Dos direcciones en el mismo Wi-Fi, cada una con su máscara real.
    assert por_ip["10.0.1.15"].prefix == 23 and por_ip["10.0.1.15"].name == "Wi-Fi"
    assert por_ip["172.29.160.1"].kind == nd.ADAPTER_VIRTUAL
    assert por_ip["10.8.0.6"].kind == nd.ADAPTER_VPN
    assert por_ip["127.0.0.1"].kind == nd.ADAPTER_LOOPBACK
    desconectado = por_ip["169.254.33.7"]
    assert desconectado.up is False and not desconectado.usable

    usables = sorted(a.address for a in adaptadores if a.usable)
    assert usables == ["10.0.0.15", "10.0.1.15", "192.168.1.27"]


class IphlpapiFalso:
    """GetAdaptersAddresses que primero pide más memoria, como el real."""

    def __init__(self, primero, tamano=200_000):
        self.primero = primero
        self.tamano = tamano
        self.llamadas = 0

    def GetAdaptersAddresses(self, familia, flags, reservado, buffer, tamano):
        self.llamadas += 1
        assert familia == 2 and flags & 0x80  # IPv4 y con gateways
        pedido = ctypes.cast(tamano, ctypes.POINTER(ctypes.c_uint32))
        if ctypes.sizeof(buffer) < ctypes.sizeof(nd._ADAPTER) or self.llamadas == 1:
            pedido.contents.value = max(self.tamano, ctypes.sizeof(nd._ADAPTER))
            return 111  # ERROR_BUFFER_OVERFLOW
        ctypes.memmove(buffer, ctypes.addressof(self.primero), ctypes.sizeof(nd._ADAPTER))
        return 0


def test_windows_adapters_reintenta_con_el_tamano_que_pide_la_api():
    mem = MemoriaWindows()
    api = IphlpapiFalso(mem.lista(SALIDA_WINDOWS[:1]))
    adaptadores = nd.windows_adapters(api)
    assert api.llamadas == 2
    assert [a.address for a in adaptadores] == ["192.168.1.27"]


def test_windows_adapters_sin_adaptadores():
    class SinDatos:
        def GetAdaptersAddresses(self, *a):
            return 232  # ERROR_NO_DATA
    assert nd.windows_adapters(SinDatos()) == []


def test_windows_adapters_propaga_un_error_real():
    class Roto:
        def GetAdaptersAddresses(self, *a):
            return 87  # ERROR_INVALID_PARAMETER
    with pytest.raises(OSError):
        nd.windows_adapters(Roto())


def test_gateways_de_linux():
    texto = ("Iface\tDestination\tGateway \tFlags\n"
             "eth0\t00000000\t0101A8C0\t0003\n"
             "eth0\t0001A8C0\t00000000\t0001\n")
    assert nd._linux_gateways(texto) == {"eth0": ["192.168.1.1"]}


# ---------------------------------------------------------------------------
# Barrido TCP
# ---------------------------------------------------------------------------

@pytest.fixture
def impresora_local():
    """Una "impresora" escuchando en 127.0.0.2:<puerto libre>."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.2", 0))
    srv.listen(16)
    yield srv.getsockname()[1]
    srv.close()


def test_barrido_real_distingue_abierto_y_cerrado(impresora_local):
    r = nd.tcp_sweep(["127.0.0.2", "127.0.0.3"], impresora_local, timeout=1.0)
    assert r == {"127.0.0.2": TCP_OK, "127.0.0.3": TCP_REFUSED}


def test_un_24_se_barre_en_menos_de_5_segundos(impresora_local):
    hosts = [f"127.0.1.{i}" for i in range(1, 255)] + ["127.0.0.2"]
    inicio = time.monotonic()
    r = nd.tcp_sweep(hosts, impresora_local)
    assert time.monotonic() - inicio < 5
    assert len(r) == 255
    assert [h for h, v in r.items() if v == TCP_OK] == ["127.0.0.2"]


class SocketColgado:
    """connect en curso que nunca termina (host que no existe)."""

    creados = []

    def __init__(self):
        self.cerrado = False
        SocketColgado.creados.append(self)

    def setblocking(self, _):
        pass

    def connect_ex(self, _):
        return 115  # EINPROGRESS

    def fileno(self):
        return 10_000 + SocketColgado.creados.index(self)

    def close(self):
        self.cerrado = True


class SelectorMudo:
    def __init__(self):
        self.registrados = set()

    def register(self, s, _):
        self.registrados.add(s)

    def unregister(self, s):
        self.registrados.discard(s)

    def select(self, _timeout):
        return []

    def close(self):
        pass


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 0.05
        return self.t


def test_sin_respuesta_vence_por_timeout_y_cierra_los_sockets():
    SocketColgado.creados = []
    r = nd.tcp_sweep([f"10.0.0.{i}" for i in range(1, 11)], timeout=1.0, concurrency=4,
                     socket_factory=SocketColgado, selector_factory=SelectorMudo, clock=Reloj())
    assert set(r.values()) == {TCP_NO_RESPONSE} and len(r) == 10
    assert all(s.cerrado for s in SocketColgado.creados)


def test_el_barrido_se_cancela():
    SocketColgado.creados = []
    cancelar = threading.Event()
    reloj = Reloj()

    def reloj_que_cancela():
        if reloj.t > 0.3:
            cancelar.set()
        return reloj()

    r = nd.tcp_sweep([f"10.0.0.{i}" for i in range(1, 255)], timeout=10, concurrency=8,
                     cancel=cancelar, socket_factory=SocketColgado,
                     selector_factory=SelectorMudo, clock=reloj_que_cancela)
    assert len(r) < 254
    assert all(s.cerrado for s in SocketColgado.creados)


# ---------------------------------------------------------------------------
# SNMP
# ---------------------------------------------------------------------------

def respuesta_snmp(rid, valores, estado=0):
    """GetResponse v2c como lo mandaría una impresora."""
    def valor(v):
        if v is None:
            return b"\x80\x00"  # noSuchObject
        if isinstance(v, str) and v.startswith("oid:"):
            return nd._ber_oid(v[4:])
        return nd._ber(0x04, v.encode())
    vbs = b"".join(nd._ber(0x30, nd._ber_oid(o) + valor(v)) for o, v in valores.items())
    pdu = nd._ber(0xA2, nd._ber_int(rid) + nd._ber_int(estado) + nd._ber_int(0) + nd._ber(0x30, vbs))
    return nd._ber(0x30, nd._ber_int(1) + nd._ber(0x04, b"public") + pdu)


def test_pedido_snmp_bien_formado():
    pedido = nd.encode_get_request(0x46420001, [nd.OID_SYS_DESCR])
    # SEQUENCE, versión 1 (v2c), comunidad "public", GetRequest
    assert pedido[0] == 0x30
    assert b"\x02\x01\x01\x04\x06public\xa0" in pedido
    assert nd._ber_oid(nd.OID_SYS_DESCR) in pedido


def test_oid_con_numeros_grandes_ida_y_vuelta():
    oid = "1.3.6.1.4.1.1248.1.2.2.1.1.1.1.1"
    assert nd._decode_oid(nd._ber_oid(oid)[2:]) == oid


def test_decodifica_una_respuesta_con_huecos():
    datos = respuesta_snmp(7, {
        nd.OID_SYS_DESCR: "EPSON TM-T88V",
        nd.OID_SYS_OBJECT_ID: "oid:1.3.6.1.4.1.1248.1.1",
        nd.OID_HR_DEVICE_DESCR: None,
    })
    rid, estado, valores = nd.decode_response(datos)
    assert (rid, estado) == (7, 0)
    assert valores[nd.OID_SYS_DESCR] == "EPSON TM-T88V"
    assert nd.OID_HR_DEVICE_DESCR not in valores
    assert nd.brand_from_snmp(valores) == "Epson"
    assert nd.model_from_snmp(valores) == "EPSON TM-T88V"


@pytest.mark.parametrize("basura", [b"", b"\x30", b"\x02\x01\x00", b"\x30\x05\x02\x01\x01\x04\x10abc"])
def test_respuestas_rotas_no_revientan(basura):
    with pytest.raises((ValueError, IndexError)):
        nd.decode_response(basura)


def test_snmp_real_por_udp_local():
    agente = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    agente.bind(("127.0.0.1", 0))
    puerto = agente.getsockname()[1]

    def atender():
        datos, origen = agente.recvfrom(4096)
        # request-id: primer INTEGER dentro del PDU
        rid = int.from_bytes(datos[datos.index(b"\xa0") + 4:datos.index(b"\xa0") + 8], "big")
        agente.sendto(respuesta_snmp(rid, {nd.OID_SYS_DESCR: "Xprinter XP-80"}), origen)

    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()
    try:
        r = nd.snmp_query(["127.0.0.1", "127.0.0.9"], timeout=1.0, port=puerto)
    finally:
        hilo.join(2)
        agente.close()
    assert r == {"127.0.0.1": {nd.OID_SYS_DESCR: "Xprinter XP-80"}}


# ---------------------------------------------------------------------------
# Tabla ARP e ICMP
# ---------------------------------------------------------------------------

def tabla_arp(filas):
    buf = struct.pack("<I", len(filas))
    for ip, mac, tipo in filas:
        mac_b = bytes.fromhex(mac.replace(":", ""))
        buf += bytes(nd._MIB_IPNETROW(
            7, len(mac_b), (ctypes.c_uint8 * 8)(*mac_b),
            struct.unpack("<I", socket.inet_aton(ip))[0], tipo))
    return buf


def test_parser_de_la_tabla_arp_de_windows():
    buf = tabla_arp([
        ("192.168.1.50", "00:26:AB:12:34:56", 3),
        ("192.168.1.51", "00:00:00:00:00:00", 3),      # incompleta
        ("192.168.1.52", "64:EB:8C:00:00:01", 2),      # inválida
        ("192.168.1.255", "FF:FF:FF:FF:FF:FF", 4),     # broadcast
        ("224.0.0.22", "01:00:5E:00:00:16", 4),        # multicast
    ])
    assert nd.parse_ip_net_table(buf) == {"192.168.1.50": "00:26:AB:12:34:56"}


def test_icmp_con_api_falsa():
    class Icmp:
        def __init__(self, respuestas, estado=0):
            self.respuestas, self.estado, self.cerrado = respuestas, estado, False

        def IcmpCreateFile(self):
            return 42

        def IcmpSendEcho(self, h, destino, datos, n, opciones, respuesta, tam, timeout):
            assert destino == struct.unpack("<I", socket.inet_aton("192.168.1.200"))[0]
            ctypes.memmove(respuesta, struct.pack("<II", destino, self.estado), 8)
            return self.respuestas

        def IcmpCloseHandle(self, h):
            self.cerrado = True

    api = Icmp(1)
    assert nd.windows_icmp_echo("192.168.1.200", iphlpapi=api) is True and api.cerrado
    assert nd.windows_icmp_echo("192.168.1.200", iphlpapi=Icmp(0)) is False
    assert nd.windows_icmp_echo("192.168.1.200", iphlpapi=Icmp(1, estado=11010)) is False


# ---------------------------------------------------------------------------
# Diagnóstico de una dirección (el DTO)
# ---------------------------------------------------------------------------

def probe_fijo(respuesta):
    llamadas = []

    def probe(host, port):
        llamadas.append((host, port))
        return respuesta
    probe.llamadas = llamadas
    return probe


PC = [adaptador("192.168.1.27", 24),
      adaptador("10.8.0.6", 24, name="VPN", kind=nd.ADAPTER_VPN, gateways=())]


def test_misma_subred_y_responde():
    d = nd.diagnose_address("192.168.1.80", adapters=PC, probe=probe_fijo(TCP_OK))
    assert d.kind == nd.KIND_SAME_SUBNET and d.printable
    assert d.adapter.name == "Ethernet"


def test_misma_subred_apagada():
    d = nd.diagnose_address("192.168.1.80", adapters=PC, probe=probe_fijo(TCP_NO_RESPONSE))
    assert d.kind == nd.KIND_HOST_OFF and not d.printable


def test_puerto_cerrado():
    d = nd.diagnose_address("192.168.1.1", adapters=PC, probe=probe_fijo(TCP_REFUSED))
    assert d.kind == nd.KIND_PORT_CLOSED
    assert d.is_gateway  # es el router: la interfaz lo puede decir


def test_192_168_123_68_contra_192_168_1_27_es_otra_subred():
    d = nd.diagnose_address("192.168.123.68", adapters=PC, probe=probe_fijo(TCP_NO_RESPONSE))
    assert d.kind == nd.KIND_OTHER_UNKNOWN
    assert d.local_networks == ("192.168.1.0/24",)   # la VPN no cuenta
    assert d.brands == ()


@pytest.mark.parametrize("ip,marca", [("192.168.123.100", "Xprinter"),
                                      ("192.168.192.168", "Epson")])
def test_ip_de_fabrica_en_otra_subred_es_marca_conocida(ip, marca):
    d = nd.diagnose_address(ip, adapters=PC, probe=probe_fijo(TCP_NO_RESPONSE))
    assert d.kind == nd.KIND_OTHER_KNOWN
    assert marca in d.brands


def test_hasar_y_gprinter_comparten_la_ip_de_xprinter():
    assert set(nd.factory_brands("192.168.123.100")) == {"Xprinter", "Gprinter", "Hasar HTP-250"}
    # La IP típica del router no es una IP de fábrica (#180).
    assert nd.factory_brands("192.168.1.1") == ()


def test_otra_subred_pero_con_ruta_se_puede_usar():
    d = nd.diagnose_address("192.168.123.100", adapters=PC, probe=probe_fijo(TCP_OK))
    assert d.kind == nd.KIND_ROUTED and d.printable


def test_una_ip_de_fabrica_en_la_misma_subred_es_misma_subred():
    pc = [adaptador("192.168.192.10", 24)]
    d = nd.diagnose_address("192.168.192.168", adapters=pc, probe=probe_fijo(TCP_OK))
    assert d.kind == nd.KIND_SAME_SUBNET


def test_la_red_de_la_vpn_no_es_la_red_de_la_pc():
    d = nd.diagnose_address("10.8.0.50", adapters=PC, probe=probe_fijo(TCP_NO_RESPONSE))
    assert d.kind == nd.KIND_OTHER_UNKNOWN


@pytest.mark.parametrize("dato", ["", "impresora", "192.168.1", "999.1.1.1", "::1", "224.0.0.1"])
def test_datos_invalidos_no_llegan_a_la_red(dato):
    probe = probe_fijo(TCP_OK)
    d = nd.diagnose_address(dato, adapters=PC, probe=probe)
    assert d.kind == nd.KIND_INVALID and d.error
    assert probe.llamadas == []


def test_la_direccion_de_la_red_o_de_broadcast_no_es_una_impresora():
    probe = probe_fijo(TCP_OK)
    for ip in ("192.168.1.0", "192.168.1.255"):
        assert nd.diagnose_address(ip, adapters=PC, probe=probe).kind == nd.KIND_INVALID
    assert probe.llamadas == []


def test_mascara_de_verdad_no_24():
    """Con /23, 192.168.1.27 y 192.168.0.80 son la misma subred."""
    pc = [adaptador("192.168.1.27", 23)]
    d = nd.diagnose_address("192.168.0.80", adapters=pc, probe=probe_fijo(TCP_NO_RESPONSE))
    assert d.kind == nd.KIND_HOST_OFF
    pc = [adaptador("192.168.1.27", 25)]  # .1 a .126
    d = nd.diagnose_address("192.168.1.200", adapters=pc, probe=probe_fijo(TCP_NO_RESPONSE))
    assert d.kind == nd.KIND_OTHER_UNKNOWN


def test_sin_adaptadores_se_diagnostica_igual_por_tcp():
    assert nd.diagnose_address("192.168.1.80", adapters=[],
                               probe=probe_fijo(TCP_OK)).kind == nd.KIND_SAME_SUBNET
    assert nd.diagnose_address("192.168.1.80", adapters=[],
                               probe=probe_fijo(TCP_NO_RESPONSE)).kind == nd.KIND_HOST_OFF


def test_conflicto_de_ip():
    def probe(host, port, timeout=None):
        return TCP_REFUSED if port == 80 else TCP_NO_RESPONSE
    en_uso, evidencia = nd.address_in_use("192.168.1.80", probe=probe, arp=lambda: {},
                                          icmp=lambda h: None, platform="linux")
    assert en_uso is True and evidencia == ["tcp80:rechazado"]

    libre, evidencia = nd.address_in_use(
        "192.168.1.81", probe=lambda h, p, timeout=None: TCP_NO_RESPONSE,
        arp=lambda: {}, icmp=lambda h: False, platform="linux")
    assert libre is False and evidencia == []

    no_se, _ = nd.address_in_use(
        "192.168.1.82", probe=lambda h, p, timeout=None: TCP_NO_RESPONSE,
        arp=lambda: {}, icmp=None, platform="linux")
    assert no_se is None

    arp, evidencia = nd.address_in_use(
        "192.168.1.83", probe=lambda h, p, timeout=None: TCP_NO_RESPONSE,
        arp=lambda: {"192.168.1.83": "00:11:22:33:44:55"}, icmp=None, platform="linux")
    assert arp is True and evidencia == ["arp"]


# ---------------------------------------------------------------------------
# Búsqueda completa (escenario 1)
# ---------------------------------------------------------------------------

class Barrido:
    def __init__(self, por_puerto):
        self.por_puerto = por_puerto
        self.pedidos = []

    def __call__(self, hosts, port, cancel=None):
        self.pedidos.append((list(hosts), port))
        tabla = self.por_puerto.get(port, {})
        return {h: tabla.get(h, TCP_NO_RESPONSE) for h in hosts}


def test_una_impresora_en_la_misma_subred_aparece_sola():
    barrido = Barrido({9100: {"192.168.1.50": TCP_OK, "192.168.1.1": TCP_REFUSED}})
    r = nd.search_network(
        adapters=[adaptador()], sweep=barrido,
        snmp=lambda hosts, cancel=None: {"192.168.1.50": {nd.OID_SYS_DESCR: "TM-T20II"}},
        arp=lambda: {"192.168.1.50": "00:26:AB:01:02:03"})

    assert [(p.host, p.port) for p in r.printers] == [("192.168.1.50", 9100)]
    impresora = r.printers[0]
    assert impresora.model == "TM-T20II" and impresora.brand == "Epson"
    assert impresora.same_subnet and impresora.mac_short == "00:26:AB:xx:xx:xx"
    assert impresora.candidate().stable_id == "network:192.168.1.50:9100"
    hosts_9100 = barrido.pedidos[0][0]
    # Todo el /24 más las IPs de fábrica que quedan afuera.
    assert len(hosts_9100) == 254 + 2
    assert "192.168.123.100" in hosts_9100 and "192.168.192.168" in hosts_9100
    assert r.swept == 256 and not r.error


def test_vpn_e_hyperv_no_se_barren_y_se_avisa():
    barrido = Barrido({})
    r = nd.search_network(adapters=[
        adaptador("10.8.0.6", 24, name="VPN Oficina", kind=nd.ADAPTER_VPN),
        adaptador("172.29.160.1", 20, name="vEthernet", kind=nd.ADAPTER_VIRTUAL),
        adaptador("192.168.1.27", 24),
    ], sweep=barrido, snmp=lambda h, cancel=None: {}, arp=lambda: {})
    barridos = barrido.pedidos[0][0]
    assert not any(h.startswith(("10.8.0.", "172.29.")) for h in barridos)
    assert any("VPN Oficina" in n for n in r.notes)
    assert any("vEthernet" in n for n in r.notes)


def test_sam4s_en_el_6001_solo_en_equipos_vivos():
    barrido = Barrido({9100: {"192.168.1.60": TCP_REFUSED, "192.168.1.61": TCP_REFUSED},
                       6001: {"192.168.1.60": TCP_OK}})
    r = nd.search_network(adapters=[adaptador()], sweep=barrido,
                          snmp=lambda h, cancel=None: {}, arp=lambda: {})
    assert barrido.pedidos[1] == (["192.168.1.60", "192.168.1.61"], 6001)
    assert [(p.host, p.port) for p in r.printers] == [("192.168.1.60", 6001)]
    assert r.printers[0].candidate().driver_config["port"] == "6001"


def test_ip_de_fabrica_alcanzable_desde_otra_subred():
    barrido = Barrido({9100: {"192.168.123.100": TCP_OK}})
    r = nd.search_network(adapters=[adaptador()], sweep=barrido,
                          snmp=lambda h, cancel=None: {}, arp=lambda: {})
    impresora = r.printers[0]
    assert impresora.host == "192.168.123.100" and not impresora.same_subnet
    assert "Gprinter" in impresora.factory_brands


def test_sin_red_y_con_apipa_se_explica():
    r = nd.search_network(adapters=[adaptador("169.254.3.4", 16)], sweep=Barrido({}),
                          snmp=lambda h, cancel=None: {}, arp=lambda: {})
    assert any("169.254" in n for n in r.notes)
    assert r.printers == []

    r = nd.search_network(adapters=[], sweep=Barrido({}),
                          snmp=lambda h, cancel=None: {}, arp=lambda: {})
    assert any("no está conectada" in n for n in r.notes)


def test_si_no_se_pueden_leer_los_adaptadores_no_revienta():
    def roto():
        raise OSError(5, "acceso denegado")
    r = nd.search_network(list_adapters_fn=roto)
    assert r.error and r.printers == []


def test_un_error_en_el_barrido_queda_en_el_resultado():
    def barrido(*a, **k):
        raise RuntimeError("se cortó la red")
    r = nd.search_network(adapters=[adaptador()], sweep=barrido)
    assert r.error == "No se pudo revisar la red."


def test_varios_adaptadores_en_la_misma_red_no_duplican():
    barrido = Barrido({9100: {"192.168.1.50": TCP_OK}})
    r = nd.search_network(adapters=[adaptador("192.168.1.27", 24, name="Ethernet"),
                                    adaptador("192.168.1.30", 24, name="Wi-Fi")],
                          sweep=barrido, snmp=lambda h, cancel=None: {}, arp=lambda: {})
    assert len(barrido.pedidos[0][0]) == 254 + 2
    assert len(r.printers) == 1


def test_lista_de_adaptadores_por_plataforma():
    assert nd.list_adapters("win32", windows=lambda: ["w"], linux=lambda: ["l"]) == ["w"]
    assert nd.list_adapters("linux", windows=lambda: ["w"], linux=lambda: ["l"]) == ["l"]
    assert nd.list_adapters("darwin", windows=lambda: ["w"], linux=lambda: ["l"]) == []
