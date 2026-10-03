"""
Candado de instancia única por máquina, y activación de la instancia que ya
está corriendo.

Dos fiscalberry corriendo a la vez en el mismo equipo (servicio viejo + versión
nueva, o servicio + arranque manual) comparten el mismo config.ini y por lo
tanto el mismo uuid: sus clientes MQTT usan el mismo client id, el broker
desconecta al que estaba conectado en cada connect del otro y ambos quedan en
un loop infinito de reconexión mutua (decenas de miles de desconexiones por
hora contra el broker, y la cola de impresión nunca procesa estable).

En Windows eso es lo normal y no la excepción: el instalador deja a Fiscalberry
arrancando con la sesión (clave Run) y además hay un acceso directo. Abrirlo
desde el acceso directo con la instancia del arranque ya corriendo levantaba un
segundo proceso completo.

Cómo se implementa el candado en cada plataforma:

- Linux: un lockfile con flock() en el mismo directorio del config.ini.
- Windows: un mutex con nombre (`Local\\FiscalberrySingleInstance`). El
  instalador de Inno Setup mira ese mismo nombre para esperar a que la app se
  cierre antes de reemplazar archivos (ver installer/fiscalberry.iss).

En los dos casos el sistema operativo lo libera al morir el proceso, aunque
muera de golpe, así que no quedan candados huérfanos que impidan arrancar
después de un crash.

Activación: cuando se abre Fiscalberry y ya hay una instancia viva, la nueva no
arranca otra: le pide a la existente que muestre su ventana y termina. En
Windows el pedido es un evento con nombre (`Local\\FiscalberryShowWindow`); en
Linux, un socket Unix al lado del lockfile.

Donde no hay forma de tomar el candado (Android, o si el sistema lo niega) se
desactiva en silencio: es mejor arrancar sin protección que no arrancar.
"""

import os
import sys
import threading
import time

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger()

try:
    import fcntl
except ImportError:  # Windows / Android: sin flock
    fcntl = None

LOCK_FILE_NAME = "fiscalberry.lock"
SOCKET_FILE_NAME = "fiscalberry.sock"

# Los dos nombres los usa también el instalador (installer/fiscalberry.iss):
# si se cambian acá, hay que cambiarlos allá. Un test verifica que coincidan.
WINDOWS_MUTEX_NAME = "Local\\FiscalberrySingleInstance"
WINDOWS_SHOW_EVENT_NAME = "Local\\FiscalberryShowWindow"

ACTIVATION_MESSAGE = b"show"

_ERROR_ACCESS_DENIED = 5
_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0
# AllowSetForegroundWindow(ASFW_ANY): deja que la instancia que ya corre traiga
# su ventana al frente. Windows solo se lo permite al proceso que recibió el
# último clic del usuario, que es esta instancia nueva, no la que está viva.
_ASFW_ANY = 0xFFFFFFFF

# Referencias vivas a lo que sostiene el candado. Si el file object del lock se
# garbage-collectea, el fd se cierra y el kernel libera el flock aunque el
# proceso siga corriendo; con el handle del mutex pasa lo mismo.
_lock_file = None
_mutex_handle = None


def _es_windows():
    return sys.platform == "win32"


# --------------------------------------------------------------------------
# API de Windows (aislada para poder reemplazarla en los tests)
# --------------------------------------------------------------------------

class _ApiWindows:
    """Las pocas llamadas de kernel32/user32 que hacen falta, vía ctypes."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL,
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
        self._k32 = k32

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        u32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        u32.AllowSetForegroundWindow.restype = wintypes.BOOL
        self._u32 = u32

    def crear_mutex(self, nombre):
        """Devuelve (handle, ya_existia). handle puede ser None si existe."""
        handle = self._k32.CreateMutexW(None, False, nombre)
        error = self._ctypes.get_last_error()
        if not handle:
            if error == _ERROR_ACCESS_DENIED:
                # Existe y lo creó otro proceso con otra seguridad.
                return None, True
            raise OSError(error, "CreateMutexW falló")
        return handle, error == _ERROR_ALREADY_EXISTS

    def crear_evento(self, nombre):
        handle = self._k32.CreateEventW(None, False, False, nombre)
        if not handle:
            raise OSError(self._ctypes.get_last_error(), "CreateEventW falló")
        return handle

    def abrir_evento(self, nombre):
        return self._k32.OpenEventW(_EVENT_MODIFY_STATE, False, nombre) or None

    def senalizar(self, handle):
        return bool(self._k32.SetEvent(handle))

    def esperar(self, handle, milisegundos):
        return self._k32.WaitForSingleObject(handle, milisegundos) == _WAIT_OBJECT_0

    def cerrar(self, handle):
        if handle:
            self._k32.CloseHandle(handle)

    def permitir_primer_plano(self):
        self._u32.AllowSetForegroundWindow(_ASFW_ANY)


_api = None


def _api_windows():
    global _api
    if _api is None:
        _api = _ApiWindows()
    return _api


# --------------------------------------------------------------------------
# El candado
# --------------------------------------------------------------------------

def _lock_file_path():
    from fiscalberry.common.Configberry import Configberry
    config_dir = os.path.dirname(Configberry().getConfigFIle())
    return os.path.join(config_dir, LOCK_FILE_NAME)


def _socket_path():
    return os.path.join(os.path.dirname(_lock_file_path()), SOCKET_FILE_NAME)


def _espera_configurada():
    try:
        return max(0.0, float(os.environ.get("FISCALBERRY_LOCK_WAIT") or 0))
    except ValueError:
        return 0.0


def _avisar_ocupado(donde):
    logger.error(
        "Ya hay otro Fiscalberry corriendo en esta maquina (%s). "
        "Dos instancias con el mismo config.ini pelean por el mismo client id MQTT "
        "y la cola de impresion deja de funcionar. Deteniendo esta instancia; "
        "si queres reiniciar el servicio, para primero el que esta corriendo "
        "(ej: systemctl stop fiscalberry).",
        donde,
    )


def acquire_single_instance_lock():
    """
    Intenta tomar el candado de instancia única.

    Si la variable de entorno FISCALBERRY_LOCK_WAIT trae un número de segundos,
    reintenta durante ese lapso en vez de rendirse al primer intento. La usa el
    relanzamiento post-actualización: el proceso viejo todavía puede estar
    muriendo cuando el nuevo arranca, y sin esta espera el reemplazo se pierde
    porque el binario nuevo aborta al no conseguir el candado.

    Es re-entrante: si este proceso ya lo tiene, devuelve True.

    Returns:
        bool: True si esta instancia puede arrancar (candado tomado, o
              plataforma sin candado). False si YA HAY otra instancia corriendo
              en esta máquina: el llamador debe abortar el arranque.
    """
    if _es_windows():
        return _tomar_mutex(_espera_configurada())
    return _tomar_flock(_espera_configurada())


def _tomar_mutex(espera):
    global _mutex_handle
    if _mutex_handle is not None:
        return True

    try:
        api = _api_windows()
    except Exception as e:
        logger.warning("single_instance: sin acceso a la API de Windows (%s), "
                       "candado deshabilitado", e)
        return True

    limite = time.monotonic() + espera
    while True:
        try:
            handle, ya_existia = api.crear_mutex(WINDOWS_MUTEX_NAME)
        except OSError as e:
            logger.warning("single_instance: no se pudo crear el mutex (%s), "
                           "candado deshabilitado", e)
            return True

        if not ya_existia:
            _mutex_handle = handle
            logger.debug("single_instance: mutex tomado (%s, pid %s)",
                         WINDOWS_MUTEX_NAME, os.getpid())
            return True

        # Abrir un mutex que ya existe también devuelve un handle: hay que
        # soltarlo, o este proceso lo mantendría vivo después de que muera el
        # dueño y nadie más podría arrancar.
        api.cerrar(handle)
        if time.monotonic() >= limite:
            _avisar_ocupado(f"mutex {WINDOWS_MUTEX_NAME}")
            return False
        logger.debug("single_instance: mutex ocupado, reintentando...")
        time.sleep(0.5)


def _tomar_flock(espera):
    global _lock_file
    if fcntl is None:
        logger.debug("single_instance: plataforma sin fcntl, candado deshabilitado")
        return True
    if _lock_file is not None:
        return True

    path = _lock_file_path()
    try:
        lock_file = open(path, "w")
    except OSError as e:
        # No poder crear el lockfile no debe impedir arrancar.
        logger.warning("single_instance: no se pudo crear %s (%s), candado deshabilitado", path, e)
        return True

    limite = time.monotonic() + espera
    while True:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= limite:
                lock_file.close()
                _avisar_ocupado(f"lock: {path}")
                return False
            logger.debug("single_instance: candado ocupado, reintentando...")
            time.sleep(0.5)

    lock_file.truncate(0)
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    _lock_file = lock_file
    logger.debug("single_instance: candado tomado (%s, pid %s)", path, os.getpid())
    return True


def holds_single_instance_lock():
    """True si ESTE proceso tiene el candado."""
    return _mutex_handle is not None or _lock_file is not None


def release_single_instance_lock():
    """Libera el candado (también se libera solo al morir el proceso)."""
    global _lock_file, _mutex_handle
    if _mutex_handle is not None:
        try:
            _api_windows().cerrar(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None
    if _lock_file is not None:
        try:
            if fcntl is not None:
                fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN)
            _lock_file.close()
        except OSError:
            pass
        _lock_file = None


# --------------------------------------------------------------------------
# Activación de la instancia existente
# --------------------------------------------------------------------------

def notify_running_instance(timeout=3.0):
    """
    Le pide a la instancia que ya corre que muestre su ventana.

    Se reintenta durante `timeout` segundos: la otra instancia puede haber
    tomado el candado hace un instante y todavía no estar escuchando.

    Returns:
        bool: True si el pedido llegó.
    """
    try:
        if _es_windows():
            return _notificar_windows(timeout)
        return _notificar_posix(timeout)
    except Exception as e:
        logger.warning("No se pudo avisar a la instancia que ya corre: %s", e)
        return False


def _notificar_windows(timeout):
    api = _api_windows()
    try:
        api.permitir_primer_plano()
    except Exception as e:
        logger.debug("AllowSetForegroundWindow falló: %s", e)

    limite = time.monotonic() + timeout
    while True:
        handle = api.abrir_evento(WINDOWS_SHOW_EVENT_NAME)
        if handle:
            try:
                return api.senalizar(handle)
            finally:
                api.cerrar(handle)
        if time.monotonic() >= limite:
            return False
        time.sleep(0.2)


def _notificar_posix(timeout):
    import socket

    ruta = _socket_path()
    limite = time.monotonic() + timeout
    while True:
        cliente = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        cliente.settimeout(max(0.2, limite - time.monotonic()))
        try:
            cliente.connect(ruta)
            cliente.sendall(ACTIVATION_MESSAGE)
            return True
        except OSError:
            if time.monotonic() >= limite:
                return False
            time.sleep(0.2)
        finally:
            cliente.close()


class ActivationListener:
    """Hilo que atiende los pedidos de mostrar la ventana. Ver `stop()`."""

    def __init__(self, esperar_pedido, liberar, callback, nombre):
        self._esperar_pedido = esperar_pedido
        self._liberar = liberar
        self._callback = callback
        self._detener = threading.Event()
        self._hilo = threading.Thread(target=self._run, daemon=True, name=nombre)

    def start(self):
        self._hilo.start()
        return self

    def _run(self):
        try:
            while not self._detener.is_set():
                try:
                    hubo_pedido = self._esperar_pedido()
                except Exception as e:
                    if self._detener.is_set():
                        break
                    logger.warning("Activación: error esperando pedidos (%s); "
                                   "se deja de escuchar.", e)
                    break
                if hubo_pedido and not self._detener.is_set():
                    try:
                        self._callback()
                    except Exception as e:
                        logger.error("Activación: el pedido de mostrar la ventana "
                                     "falló: %s", e)
        finally:
            try:
                self._liberar()
            except Exception:
                pass

    def stop(self, timeout=2.0):
        self._detener.set()
        if self._hilo.is_alive() and self._hilo is not threading.current_thread():
            self._hilo.join(timeout)


def start_activation_listener(callback):
    """
    Empieza a atender los pedidos de "mostrá la ventana" de instancias nuevas.

    Solo escucha quien tiene el candado: en Linux escuchar implica reemplazar
    el socket, y hacerlo sin ser el dueño le robaría el canal a la instancia
    que sí corre.

    `callback` corre en un hilo aparte: si toca la interfaz, tiene que pasar
    al hilo de la UI por su cuenta.

    Returns:
        ActivationListener, o None si no se pudo (o no corresponde) escuchar.
    """
    if not holds_single_instance_lock():
        return None
    try:
        if _es_windows():
            return _escuchar_windows(callback)
        return _escuchar_posix(callback)
    except Exception as e:
        logger.warning("No se pudo escuchar pedidos de activación (%s): abrir "
                       "Fiscalberry otra vez no va a mostrar esta ventana.", e)
        return None


def _escuchar_windows(callback):
    api = _api_windows()
    evento = api.crear_evento(WINDOWS_SHOW_EVENT_NAME)
    return ActivationListener(
        esperar_pedido=lambda: api.esperar(evento, 500),
        liberar=lambda: api.cerrar(evento),
        callback=callback,
        nombre="fiscalberry-activacion",
    ).start()


def _escuchar_posix(callback):
    import socket

    ruta = _socket_path()
    # Si quedó un socket de una ejecución anterior que murió, es nuestro:
    # tenemos el candado, así que nadie más puede estar usándolo.
    try:
        os.unlink(ruta)
    except FileNotFoundError:
        pass

    servidor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        servidor.bind(ruta)
        servidor.listen(4)
        servidor.settimeout(0.5)
    except OSError:
        servidor.close()
        raise

    def esperar_pedido():
        try:
            conexion, _ = servidor.accept()
        except socket.timeout:
            return False
        with conexion:
            conexion.settimeout(1.0)
            try:
                datos = conexion.recv(len(ACTIVATION_MESSAGE))
            except OSError:
                return False
        return datos == ACTIVATION_MESSAGE

    def liberar():
        servidor.close()
        try:
            os.unlink(ruta)
        except OSError:
            pass

    return ActivationListener(
        esperar_pedido=esperar_pedido,
        liberar=liberar,
        callback=callback,
        nombre="fiscalberry-activacion",
    ).start()
