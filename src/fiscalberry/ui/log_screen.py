#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LogScreen — Pantalla de Registro de Actividades
================================================

Android: recibe logs del Servicio (Proceso 2) via Unix Domain Socket.
         Los logs viven en RAM (deque), sin disco, sin archivo.
Desktop: comportamiento original (lee el archivo .txt de Kivy).
"""

from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty
from kivy.clock import Clock
import platform
import os
import subprocess
import threading
from collections import deque

# Detección de plataforma (reutilizable en todo el módulo)
_IS_ANDROID = 'ANDROID_STORAGE' in os.environ or 'ANDROID_ARGUMENT' in os.environ

# Socket abstracto (debe coincidir con uds_log_emitter.py)
_SOCKET_NAME = "\0fiscalberry_logs"

# Buffer en RAM compartido entre el thread listener y el hilo principal de Kivy
# maxlen=200 → cuando se llena, la línea más antigua se descarta automáticamente
_log_buffer = deque(maxlen=200)

# Flag para detener el thread al salir de la pantalla
_listener_running = False


def _uds_listener_thread():
    """
    Thread daemon que escucha el Unix Domain Socket y acumula mensajes en RAM.
    Corre solo en Android. Si el Servicio no está emitiendo, bloquea
    en recvfrom() sin consumir CPU (I/O wait).
    """
    import socket as _socket
    global _listener_running

    sock = None
    try:
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_DGRAM)
        sock.settimeout(1.0)  # Timeout para poder chequear _listener_running
        sock.bind(_SOCKET_NAME)

        while _listener_running:
            try:
                data, _ = sock.recvfrom(4096)
                msg = data.decode("utf-8", errors="replace")
                _log_buffer.appendleft(msg)  # Más recientes primero
            except _socket.timeout:
                continue  # Reintenta — verificar _listener_running
            except OSError:
                break

    except Exception:
        pass
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


class LogScreen(Screen):
    logs = StringProperty("")
    logFilePath = StringProperty("")

    def on_kv_post(self, base_widget):
        """Arranca el método de actualización según la plataforma."""
        if _IS_ANDROID:
            self._start_uds_listener()
            Clock.schedule_interval(self._update_from_buffer, 1)
        else:
            # Comportamiento original para CLI/GUI Desktop — sin cambios
            Clock.schedule_interval(self._update_from_file, 1)

    def on_leave(self):
        """Al salir de la pantalla, detener el listener para liberar el socket."""
        global _listener_running
        _listener_running = False

    # ──────────────────────────────────────────────────────────────────────
    # Android: UDS Listener
    # ──────────────────────────────────────────────────────────────────────

    def _start_uds_listener(self):
        """Inicia el thread listener del socket UDS."""
        global _listener_running, _log_buffer
        _listener_running = True
        _log_buffer.clear()
        t = threading.Thread(target=_uds_listener_thread, daemon=True)
        t.start()

    def _update_from_buffer(self, dt):
        """Lee el buffer in-memory y actualiza la UI (llamado por Clock cada 1s)."""
        if _log_buffer:
            self.logs = "\n".join(_log_buffer)
            if "scroll_view" in self.ids:
                self.ids.scroll_view.scroll_y = 1  # Scroll al inicio (más reciente)
        else:
            self.logs = "Esperando actividad del Servicio..."

    # ──────────────────────────────────────────────────────────────────────
    # Desktop: comportamiento original (sin cambios)
    # ──────────────────────────────────────────────────────────────────────

    def _update_from_file(self, dt):
        """Lee el archivo de logs de Kivy y actualiza la propiedad `logs`. (Desktop only)"""
        from fiscalberry.common.fiscalberry_logger import getLogFilePath
        log_path = getLogFilePath()
        self.logFilePath = log_path if log_path else ""

        if not self.logFilePath:
            self.logs = "No hay archivo de log configurado.\nLos logs se muestran solo en consola."
            return

        try:
            with open(self.logFilePath, "r") as log_file:
                log_data = log_file.read()
                self.logs = log_data
                if "scroll_view" in self.ids:
                    self.ids.scroll_view.scroll_y = 0
        except Exception as e:
            self.logs = f"Error al leer log: {e}"

    def open_log_file(self):
        """Abre el archivo de log en el editor predeterminado. Solo Desktop."""
        if _IS_ANDROID:
            return  # No aplica en Android

        if self.logFilePath:
            try:
                system = platform.system()
                if system == "Windows":
                    os.startfile(self.logFilePath)
                elif system == "Darwin":
                    subprocess.Popen(["open", self.logFilePath])
                else:
                    subprocess.Popen(["xdg-open", self.logFilePath])
            except FileNotFoundError:
                self.logs = f"Error: No se encontró el archivo de log en {self.logFilePath}"
            except OSError as e:
                self.logs = f"Error al abrir el log con la aplicación predeterminada: {e}"
            except Exception as e:
                self.logs = f"Error inesperado al abrir el log: {e}"
        else:
            self.logs = "No se ha encontrado la ruta del archivo de log."