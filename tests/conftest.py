# coding=utf-8
"""
Configuración compartida de pytest para los tests de Fiscalberry.

Agrega `src/` al sys.path para poder importar el paquete `fiscalberry`
sin necesidad de instalarlo en modo editable.
"""

import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
