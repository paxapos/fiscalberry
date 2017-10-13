# -*- coding: iso-8859-1 -*-
from ConectorDriverComando import ConectorDriverComando
import unicodedata
import importlib
import logging
import string
import types
from array import array


class ValidationError(Exception):
    pass


class FiscalPrinterError(Exception):
    pass


class ComandoException(RuntimeError):
    pass


def valid_utf8_bytes(s):
    """
    """
    if isinstance(s, unicode):
        s = s.encode('utf-8')
    bytearray = array('B', s)
    return str_skip_bytes(s, invalid_utf8_indexes(bytearray))


def str_skip_bytes(s, dels):
    """
    """
    if not dels:
        return s
    return ''.join(c for i, c in enumerate(s) if i not in dels)


def invalid_utf8_indexes(bytes):
    """
    """
    skips = []
    i = 0
    len_bytes = len(bytes)
    while i < len_bytes:
        c1 = bytes[i]
        if c1 < 0x80:
            # U+0000 - U+007F - 7 bits
            i += 1
            continue
        try:
            c2 = bytes[i + 1]
            if ((c1 & 0xE0 == 0xC0) and (c2 & 0xC0 == 0x80)):
                # U+0080 - U+07FF - 11 bits
                c = (((c1 & 0x1F) << 6) |
                     (c2 & 0x3F))
                if c < 0x80:
                    # Overlong encoding
                    skips.extend([i, i + 1])
                i += 2
                continue
            c3 = bytes[i + 2]
            if ((c1 & 0xF0 == 0xE0) and
                    (c2 & 0xC0 == 0x80) and
                    (c3 & 0xC0 == 0x80)):
                # U+0800 - U+FFFF - 16 bits
                c = (((((c1 & 0x0F) << 6) |
                       (c2 & 0x3F)) << 6) |
                     (c3 & 0x3f))
                if ((c < 0x800) or (0xD800 <= c <= 0xDFFF)):
                    # Overlong encoding or surrogate.
                    skips.extend([i, i + 1, i + 2])
                i += 3
                continue
            c4 = bytes[i + 3]
            if ((c1 & 0xF8 == 0xF0) and
                    (c2 & 0xC0 == 0x80) and
                    (c3 & 0xC0 == 0x80) and
                    (c4 & 0xC0 == 0x80)):
                # U+10000 - U+10FFFF - 21 bits
                c = (((((((c1 & 0x0F) << 6) |
                         (c2 & 0x3F)) << 6) |
                       (c3 & 0x3F)) << 6) |
                     (c4 & 0x3F))
                if (c < 0x10000) or (c > 0x10FFFF):
                    # Overlong encoding or invalid code point.
                    skips.extend([i, i + 1, i + 2, i + 3])
                i += 4
                continue
        except IndexError:
            pass
        skips.append(i)
        i += 1
    return skips


def formatText(text):
    text = valid_utf8_bytes(text)
    text = text.replace('á', 'a')
    text = text.replace('é', 'e')
    text = text.replace('í', 'i')
    text = text.replace('ó', 'o')
    text = text.replace('ú', 'u')
    text = text.replace('Á', 'A')
    text = text.replace('É', 'E')
    text = text.replace('Í', 'I')
    text = text.replace('Ó', 'O')
    text = text.replace('Ú', 'U')
    text = text.replace('Ä', 'A')
    text = text.replace('Ë', 'E')
    text = text.replace('Ï', 'I')
    text = text.replace('Ö', 'O')
    text = text.replace('Ü', 'U')
    text = text.replace('ä', 'a')
    text = text.replace('ë', 'e')
    text = text.replace('ï', 'i')
    text = text.replace('ö', 'o')
    text = text.replace('ü', 'u')
    text = text.replace('ñ', 'n')
    text = text.replace('Ñ', 'N')
    text = text.replace('\\', ' ')
    text = text.replace('\'', ' ')
    text = text.replace('º', ' ')
    text = text.replace('"', ' ')
    text = text.replace('|', ' ')
    text = text.replace('¿', ' ')
    text = text.replace('¡', ' ')
    text = text.replace('ª', ' ')

    return text


class ComandoInterface:
    """Interfaz que deben cumplir las impresoras fiscales."""

    DEFAULT_DRIVER = None

    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop("modelo", None)
        driver = kwargs.pop("driver", self.DEFAULT_DRIVER)

        # inicializo el driver
        self.conector = ConectorDriverComando(self, driver, **kwargs)

        # inicializo el traductor
        traductorModule = importlib.import_module(self.traductorModule)
        traductorClass = getattr(traductorModule, self.traductorModule[12:])
        self.traductor = traductorClass(self, *args)

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        raise Exception("NotImplementedException")

    def close(self):
        """Cierra la impresora"""
        self.conector.close()
