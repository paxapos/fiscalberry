"""
Enlaces a las guías de paxapos/documentation (doc.paxapos.com) para los casos
que el asistente no resuelve solo (#184): otra subred, IP desconocida, driver
del fabricante, cable directo sin router.

Las guías viven allá, no dentro de la app. Todos los enlaces están acá para
poder corregirlos en un solo lugar. Las guías específicas del asistente
(paxapos/documentation#117 a #125) todavía no están publicadas: mientras
tanto cada caso apunta a la página existente más cercana. Cuando se publiquen,
se cambia solo este diccionario.
"""

BASE = "https://doc.paxapos.com/user-guide"

# Páginas publicadas hoy (verificadas en el repo paxapos/documentation).
_IMPRESORAS = f"{BASE}/impresoras"
_PROBLEMAS = f"{_IMPRESORAS}#que-hacer-si-algo-no-sale-bien-problemas-comunes"
_DRIVERS = f"{BASE}/biblioteca-de-drivers"
_NO_IMPRIME = f"{BASE}/troubleshooting-semantico#error-impresora-comandera"

GUIDE_OTHER_NETWORK = "otra_red"                 # documentation#124 (hoja FEED y otra subred)
GUIDE_OTHER_NETWORK_KNOWN = "otra_red_marca"     # documentation#117/#118/#119 según la marca
GUIDE_NOT_FOUND = "no_aparece"                   # documentation#121 (instalación guiada)
GUIDE_USB_DRIVER = "usb_driver"                  # documentation#120 (colas de Windows y USB)
GUIDE_DIRECT_CABLE = "cable_directo"             # documentation#124
GUIDE_PRINT_FAILED = "no_imprime"

GUIDES = {
    GUIDE_OTHER_NETWORK: _PROBLEMAS,
    GUIDE_OTHER_NETWORK_KNOWN: _PROBLEMAS,
    GUIDE_NOT_FOUND: _PROBLEMAS,
    GUIDE_USB_DRIVER: _DRIVERS,
    GUIDE_DIRECT_CABLE: _PROBLEMAS,
    GUIDE_PRINT_FAILED: _NO_IMPRIME,
}


def guide_url(key):
    """URL de la guía, o "" si la clave no existe."""
    return GUIDES.get(key, "")


def open_guide(key, opener=None):
    """Abre la guía en el navegador. Devuelve False si no se pudo."""
    url = guide_url(key)
    if not url:
        return False
    if opener is None:
        import webbrowser
        opener = webbrowser.open
    try:
        return bool(opener(url))
    except Exception:
        return False
