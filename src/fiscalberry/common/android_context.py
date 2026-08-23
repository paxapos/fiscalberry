# coding=utf-8
"""
Contexto de Android válido en CUALQUIERA de los dos procesos.

Fiscalberry corre en dos procesos Android: la UI (Activity) y el servicio de
impresión (Service). `PythonActivity.mActivity` es None en el proceso del
servicio, así que usarlo directamente revienta ahí con:

    AttributeError: 'NoneType' object has no attribute 'getSystemService'

Este helper devuelve la Activity si existe y, si no, el Service — ambos son
Context de Android y sirven igual para getSystemService(), getResources() o
getContentResolver().
"""

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("AndroidContext")


def get_android_context():
    """
    Context de Android, o None si no estamos en Android o no hay ninguno listo.
    El caller SIEMPRE debe contemplar el None.
    """
    try:
        from jnius import autoclass
    except ImportError:
        return None  # Escritorio

    for clase, atributo in (
        ("org.kivy.android.PythonActivity", "mActivity"),
        ("org.kivy.android.PythonService", "mService"),
    ):
        try:
            contexto = getattr(autoclass(clase), atributo)
            if contexto is not None:
                return contexto
        except Exception as e:
            logger.debug(f"Sin contexto desde {clase}: {e}")

    return None
