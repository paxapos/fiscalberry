"""
Runtime hook de PyInstaller: dejar sys.stdout / sys.stderr utilizables.

El .exe de la GUI se compila con `console=False` (sin ventana de consola) y en
esa modalidad PyInstaller deja `sys.stdout` y `sys.stderr` valiendo None.
Cualquier codigo que escriba ahi revienta con "AttributeError: 'NoneType'
object has no attribute 'write'": `traceback.print_exc()`,
`print(..., file=sys.stderr)`, un `logging.StreamHandler` o cualquier libreria
de terceros que suponga que hay una consola.

Este hook corre antes que cualquier import de la aplicacion y pone en su lugar
un stream que descarta lo que recibe, para que nada falle por el solo hecho de
no tener a donde escribir. Los logs de verdad los toma setup_file_logging(),
que va a archivo.
"""

import io
import sys


class _StreamNulo(io.TextIOBase):
    """Acepta todo lo que le escriban y no lo manda a ningun lado."""

    # Hay librerias que consultan sys.stdout.encoding antes de escribir; en
    # io.TextIOBase vale None y las rompe.
    encoding = "utf-8"
    errors = "replace"

    def writable(self):
        return True

    def write(self, texto):
        return len(texto)

    def flush(self):
        pass


for _nombre in ("stdout", "stderr"):
    if getattr(sys, _nombre, None) is None:
        setattr(sys, _nombre, _StreamNulo())
