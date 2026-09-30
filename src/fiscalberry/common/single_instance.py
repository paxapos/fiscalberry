"""
Candado de instancia única por máquina, y activación de la instancia viva.

Dos fiscalberry corriendo a la vez en el mismo equipo (servicio viejo + versión
nueva, o servicio + arranque manual) comparten el mismo config.ini y por lo
tanto el mismo uuid: sus clientes MQTT usan el mismo client id, el broker
desconecta al que estaba conectado en cada connect del otro y ambos quedan en
un loop infinito de reconexión mutua (decenas de miles de desconexiones por
hora contra el broker, y la cola de impresión nunca procesa estable).

Cada sistema usa su mecanismo, y los dos los libera el kernel al morir el
proceso (aunque sea con kill -9 o desde el Administrador de tareas), así que
un crash no deja un candado huérfano que impida arrancar después:

- Linux: lockfile con flock() en el mismo directorio del config.ini.
- Windows: mutex con nombre fijo `Local\\FiscalberrySingleInstance`. El
  instalador (installer/fiscalberry.iss) busca ese mismo nombre para saber si
  Fiscalberry sigue abierto antes de pisar los archivos.

Activación: el acceso directo y el arranque con Windows lanzan un proceso
nuevo aunque ya haya uno corriendo en la bandeja. Ese proceso no arranca: le
pide a la instancia viva que muestre su ventana y termina. En Windows el pedido
es un evento con nombre (`Local\\FiscalberryShowWindow`); en Linux, un socket
Unix al lado del lockfile.

En plataformas sin ninguno de los dos mecanismos el candado se desactiva en
silencio: es mejor arrancar sin protección que no arrancar.
"""

import os
import socket
import sys
import threading
import time

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger()

try:
    import fcntl
except ImportError:  # Windows: sin flock, se usa el mutex
    fcntl = None

LOCK_FILE_NAME = "fiscalberry.lock"
ACTIVATION_SOCKET_NAME = "fiscalberry.sock"

WINDOWS_MUTEX_NAME = "Local\\FiscalberrySingleInstance"
WINDOWS_SHOW_EVENT_NAME = "Local\\FiscalberryShowWindow"

# Pedido que viaja por el socket de activación en Linux.
SHOW_WINDOW_REQUEST = b"show\n"

# Referencia viva al candado tomado. En Linux es el file object del lockfile
# (si se garbage-collectea, el fd se cierra y el kernel libera el flock aunque
# el proceso siga corriendo); en Windows, el handle del mutex.
_lock_file = None
_listener = None


def _is_windows():
    return sys.platform == "win32"


def _lock_file_path():
    from fiscalberry.common.Configberry import Configberry
    config_dir = os.path.dirname(Configberry().getConfigFIle())
    return os.path.join(config_dir, LOCK_FILE_NAME)


def _activation_socket_path():
    return os.path.join(os.path.dirname(_lock_file_path()), ACTIVATION_SOCKET_NAME)


def _lock_wait_seconds():
    """
    Segundos a esperar si el candado está tomado (FISCALBERRY_LOCK_WAIT).

    La usa el relanzamiento post-actualización: el proceso viejo todavía puede
    estar muriendo cuando el nuevo arranca, y sin esta espera el reemplazo se
    pierde porque el binario nuevo aborta al no conseguir el candado.
    """
    try:
        return max(0.0, float(os.environ.get("FISCALBERRY_LOCK_WAIT") or 0))
    except ValueError:
        return 0.0


# --------------------------------------------------------------------------
# Windows: Win32 vía ctypes, detrás de una clase chica para poder simularla
# --------------------------------------------------------------------------

ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0x00000000
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
# Permite que la instancia viva pase al frente cuando la activa otro proceso.
# Sin esto Windows solo hace parpadear el botón de la barra de tareas.
ASFW_ANY = -1


class _Win32Api:
    """
    Las pocas llamadas a kernel32/user32 que hacen falta.

    Los tests la reemplazan por un doble: así se prueba la lógica del candado
    y de la activación sin Windows.
    """

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.WinDLL("user32", use_last_error=True)

        k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL,
                                     wintypes.LPCWSTR]
        k32.CreateEventW.restype = wintypes.HANDLE
        k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k32.OpenEventW.restype = wintypes.HANDLE
        k32.SetEvent.argtypes = [wintypes.HANDLE]
        k32.SetEvent.restype = wintypes.BOOL
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        u32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        u32.AllowSetForegroundWindow.restype = wintypes.BOOL

        self._k32 = k32
        self._u32 = u32

    def create_mutex(self, name):
        """Devuelve (handle, ya_existia)."""
        handle = self._k32.CreateMutexW(None, False, name)
        ya_existia = self._ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        return handle, ya_existia

    def create_event(self, name):
        # Auto-reset: cada SetEvent despierta una sola espera y vuelve solo a
        # no señalado.
        return self._k32.CreateEventW(None, False, False, name)

    def open_event(self, name):
        return self._k32.OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, False, name)

    def set_event(self, handle):
        return bool(self._k32.SetEvent(handle))

    def wait(self, handle, timeout_ms):
        return self._k32.WaitForSingleObject(handle, int(timeout_ms))

    def close_handle(self, handle):
        if handle:
            self._k32.CloseHandle(handle)

    def allow_set_foreground_window(self):
        # El DWORD de ASFW_ANY es (DWORD)-1.
        self._u32.AllowSetForegroundWindow(ASFW_ANY & 0xFFFFFFFF)


_win32 = None


def _win32_api():
    global _win32
    if _win32 is None:
        _win32 = _Win32Api()
    return _win32


class _WindowsMutexLock:
    """El candado es la EXISTENCIA del mutex, no su propiedad."""

    def __init__(self, api):
        self.api = api
        self.handle = None

    def try_acquire(self):
        handle, ya_existia = self.api.create_mutex(WINDOWS_MUTEX_NAME)
        if not handle:
            raise OSError("CreateMutexW falló")
        if ya_existia:
            # El handle apunta al mutex de la OTRA instancia: hay que cerrarlo,
            # o esta instancia lo mantendría vivo después de que la otra muera.
            self.api.close_handle(handle)
            return False
        self.handle = handle
        return True

    def release(self):
        self.api.close_handle(self.handle)
        self.handle = None

    def describe(self):
        return WINDOWS_MUTEX_NAME


class _FlockLock:
    def __init__(self, path):
        self.path = path
        self.file = None

    def open(self):
        self.file = open(self.path, "w")

    def try_acquire(self):
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        self.file.truncate(0)
        self.file.write(str(os.getpid()))
        self.file.flush()
        return True

    def give_up(self):
        self.file.close()
        self.file = None

    def release(self):
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()
        except OSError:
            pass
        self.file = None

    def describe(self):
        return self.path


# Indirección para que los tests puedan controlar el paso del tiempo.
_sleep = time.sleep
_monotonic = time.monotonic


def _esperar_candado(lock, espera):
    """Reintenta tomar el candado durante `espera` segundos."""
    limite = _monotonic() + espera
    while True:
        if lock.try_acquire():
            return True
        if _monotonic() >= limite:
            return False
        logger.debug("single_instance: candado ocupado, reintentando...")
        _sleep(0.5)


def _nuevo_candado():
    """El candado que corresponde a esta plataforma, o None si no hay."""
    if _is_windows():
        try:
            return _WindowsMutexLock(_win32_api())
        except Exception as e:
            logger.warning("single_instance: sin acceso a la API de Windows (%s), "
                           "candado deshabilitado", e)
            return None
    if fcntl is None:
        logger.debug("single_instance: plataforma sin fcntl, candado deshabilitado")
        return None

    lock = _FlockLock(_lock_file_path())
    try:
        lock.open()
    except OSError as e:
        # No poder crear el lockfile no debe impedir arrancar.
        logger.warning("single_instance: no se pudo crear %s (%s), candado deshabilitado",
                       lock.path, e)
        return None
    return lock


def acquire_single_instance_lock():
    """
    Intenta tomar el candado de instancia única. Es re-entrante: el entry point
    lo toma al arrancar y ServiceController.start() lo vuelve a pedir.

    Si la variable de entorno FISCALBERRY_LOCK_WAIT trae un número de segundos,
    reintenta durante ese lapso en vez de rendirse al primer intento.

    Returns:
        bool: True si esta instancia puede arrancar (candado tomado, o
              plataforma sin candado). False si YA HAY otra instancia corriendo
              en esta máquina: el llamador debe abortar el arranque.
    """
    global _lock_file
    if _lock_file is not None:
        return True

    lock = _nuevo_candado()
    if lock is None:
        return True

    try:
        tomado = _esperar_candado(lock, _lock_wait_seconds())
    except OSError as e:
        logger.warning("single_instance: no se pudo tomar el candado (%s), "
                       "candado deshabilitado", e)
        return True

    if not tomado:
        if hasattr(lock, "give_up"):
            lock.give_up()
        logger.error(
            "Ya hay otro Fiscalberry corriendo en esta maquina (lock: %s). "
            "Dos instancias con el mismo config.ini pelean por el mismo client id MQTT "
            "y la cola de impresion deja de funcionar. Deteniendo esta instancia; "
            "si queres reiniciar el servicio, para primero el que esta corriendo "
            "(ej: systemctl stop fiscalberry).",
            lock.describe(),
        )
        return False

    _lock_file = lock
    logger.debug("single_instance: candado tomado (%s, pid %s)", lock.describe(), os.getpid())
    return True


def release_single_instance_lock():
    """Libera el candado (también se libera solo al morir el proceso)."""
    global _lock_file
    stop_activation_listener()
    if _lock_file is not None:
        try:
            _lock_file.release()
        except OSError:
            pass
        _lock_file = None


# --------------------------------------------------------------------------
# Activación: la instancia nueva le pide a la viva que muestre su ventana
# --------------------------------------------------------------------------

def request_activation(timeout=2.0):
    """
    Le pide a la instancia que está corriendo que muestre su ventana.

    Devuelve True si el pedido llegó. False no es grave: la otra instancia
    puede ser el CLI (sin ventana) o estar terminando de arrancar.
    """
    try:
        if _is_windows():
            return _request_activation_windows(_win32_api())
        return _request_activation_socket(_activation_socket_path(), timeout)
    except Exception as e:
        logger.debug("single_instance: no se pudo pedir la activación: %s", e)
        return False


def _request_activation_windows(api):
    handle = api.open_event(WINDOWS_SHOW_EVENT_NAME)
    if not handle:
        return False
    try:
        api.allow_set_foreground_window()
        return api.set_event(handle)
    finally:
        api.close_handle(handle)


def _request_activation_socket(path, timeout):
    if not hasattr(socket, "AF_UNIX"):
        return False
    cliente = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    cliente.settimeout(timeout)
    try:
        cliente.connect(path)
        cliente.sendall(SHOW_WINDOW_REQUEST)
        return True
    except OSError:
        return False
    finally:
        cliente.close()


class _WindowsActivationListener:
    """Hilo que espera el evento con nombre y avisa a la instancia viva."""

    POLL_MS = 500

    def __init__(self, api, callback):
        self.api = api
        self.callback = callback
        self._stop = threading.Event()
        self._thread = None
        self.handle = None

    def start(self):
        self.handle = self.api.create_event(WINDOWS_SHOW_EVENT_NAME)
        if not self.handle:
            raise OSError("CreateEventW falló")
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="fiscalberry-activation")
        self._thread.start()

    def _run(self):
        # Espera con timeout para poder detenerse: WaitForSingleObject infinito
        # no se puede interrumpir desde Python.
        while not self._stop.is_set():
            if self.api.wait(self.handle, self.POLL_MS) == WAIT_OBJECT_0:
                if self._stop.is_set():
                    break
                _llamar(self.callback)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.api.close_handle(self.handle)
        self.handle = None


class _SocketActivationListener:
    """Socket Unix al lado del lockfile, solo accesible por el usuario."""

    def __init__(self, path, callback):
        self.path = path
        self.callback = callback
        self._stop = threading.Event()
        self._thread = None
        self._server = None

    def start(self):
        # Quien llega acá tiene el flock, así que un socket existente es resto
        # de una instancia que murió sin limpiar.
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(self.path)
            os.chmod(self.path, 0o600)
            server.listen(4)
            server.settimeout(0.5)
        except OSError:
            server.close()
            raise
        self._server = server
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="fiscalberry-activation")
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                conexion, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conexion.settimeout(1.0)
                pedido = conexion.recv(64)
            except OSError:
                pedido = b""
            finally:
                conexion.close()
            if pedido.strip() == SHOW_WINDOW_REQUEST.strip():
                _llamar(self.callback)

    def stop(self):
        self._stop.set()
        if self._server is not None:
            self._server.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        try:
            os.unlink(self.path)
        except OSError:
            pass
        self._server = None


def _llamar(callback):
    try:
        callback()
    except Exception as e:
        logger.warning("single_instance: error atendiendo la activación: %s", e)


def start_activation_listener(callback):
    """
    Empieza a atender los pedidos de "mostrá la ventana" de otras instancias.

    Solo tiene sentido en la instancia que tiene el candado. `callback` se
    llama desde un hilo propio: si toca la interfaz, tiene que pasar al hilo
    principal (en Kivy, con @mainthread). Devuelve True si quedó escuchando.
    """
    global _listener
    if _listener is not None:
        return True
    try:
        if _is_windows():
            listener = _WindowsActivationListener(_win32_api(), callback)
        elif hasattr(socket, "AF_UNIX"):
            listener = _SocketActivationListener(_activation_socket_path(), callback)
        else:
            return False
        listener.start()
    except Exception as e:
        logger.warning("single_instance: no se pudo escuchar pedidos de activación: %s", e)
        return False
    _listener = listener
    return True


def stop_activation_listener():
    global _listener
    if _listener is not None:
        try:
            _listener.stop()
        except Exception:
            pass
        _listener = None
