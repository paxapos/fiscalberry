#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UDS Log Emitter — Canal IPC exclusivo para Android
===================================================
Permite que el Servicio Android (Proceso 2) envíe mensajes de log
a la UI Kivy (Proceso 1) mediante un Unix Domain Socket.

DISEÑO:
  - El socket vive en la carpeta privada del APK (/data/data/.../files/)
  - Permisos drwx------ → ninguna otra app puede acceder
  - Si la UI está cerrada (nadie escucha), los paquetes se descartan
    silenciosamente sin bloquear el Servicio
  - Zero I/O de disco, zero red, zero overhead

COMPATIBILIDAD: Android 5 (API 21) → Android 16+ (AF_UNIX desde Linux 2.0)
"""

import socket
import os
import logging

logger = logging.getLogger("UDSLogEmitter")

# Nombre abstracto del socket (con @ al inicio = sin archivo en disco)
# Esto evita tener que limpiar el archivo .sock manualmente
_SOCKET_NAME = "\0fiscalberry_logs"

# Socket global del emisor (Proceso 2 - Servicio)
_emitter_socket = None


def _get_socket_path():
    """
    Devuelve la ruta del socket en la carpeta privada del APK.
    Fallback a /tmp si no estamos en Android real.
    """
    try:
        # En Android, obtenemos el filesDir via pyjnius
        from jnius import autoclass
        PythonService = autoclass('org.kivy.android.PythonService')
        service = PythonService.mService
        if service:
            files_dir = service.getFilesDir().getAbsolutePath()
            return os.path.join(files_dir, "fb_logs.sock")
    except Exception:
        pass
    # Fallback para testing en desktop
    return "/tmp/fb_logs.sock"


def init_emitter():
    """
    Inicializa el socket emisor (llamar desde el Servicio al arrancar).
    Usa socket abstracto (@ prefix) para no dejar archivos en disco.
    """
    global _emitter_socket
    try:
        _emitter_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        logger.debug("UDS Emitter inicializado (socket abstracto)")
        return True
    except Exception as e:
        logger.warning(f"UDS Emitter no disponible: {e}")
        _emitter_socket = None
        return False


def emit(message: str):
    """
    Emite un mensaje al socket UDS.
    Si la UI no está escuchando, falla silenciosamente (sin excepción).
    """
    global _emitter_socket
    if _emitter_socket is None:
        return

    try:
        data = message.encode("utf-8", errors="replace")[:4096]  # Max 4KB por paquete
        _emitter_socket.sendto(data, _SOCKET_NAME)
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        # La UI no está escuchando → descartar silenciosamente
        pass
    except Exception as e:
        # Fallar en silencio siempre, los logs no deben bloquear el Servicio
        pass


def close_emitter():
    """Cierra el socket emisor (llamar en el finally del Servicio)."""
    global _emitter_socket
    if _emitter_socket:
        try:
            _emitter_socket.close()
        except Exception:
            pass
        _emitter_socket = None


# ──────────────────────────────────────────────────────────────────────────────
# Handler de Python logging para integración automática con el logger raíz
# ──────────────────────────────────────────────────────────────────────────────

class UDSHandler(logging.Handler):
    """
    Handler de Python logging que redirige todos los logs al socket UDS.
    Al agregarlo al logger raíz, todos los logger.debug/info/error existentes
    en el Servicio se reenvían automáticamente a la UI sin tocar cada línea.
    """
    def emit(self, record):
        try:
            msg = self.format(record)
            emit(msg)
        except Exception:
            pass  # Nunca propagar errores del handler de logging


# Formateador estándar para los mensajes que llegan a la UI
_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)


def attach_to_root_logger(level=logging.DEBUG):
    """
    Agrega el UDSHandler al logger raíz de Python.
    Llamar UNA sola vez desde service.py después de init_emitter().
    """
    handler = UDSHandler(level=level)
    handler.setFormatter(_formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    logger.debug("UDSHandler adjuntado al logger raíz")
