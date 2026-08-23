"""
El último paso: instalar lo que ya se bajó y se verificó.

Es lo único que cambia por plataforma, y cada una tiene su propia limitación:

- Linux/Raspberry: se puede reemplazar el archivo de un binario EN USO (el
  kernel mantiene vivo el inodo viejo mientras haya un fd abierto), así que el
  swap es un `os.replace` atómico.
- Windows: NO se puede. Hace falta que otro proceso haga el cambio cuando éste
  ya murió. Se usa el propio binario nuevo como ayudante, para no tener que
  distribuir un ejecutable extra.
- Android: el reemplazo lo hace el sistema y SIEMPRE requiere que el usuario
  acepte. No hay instalación silenciosa fuera de Play Store, y tampoco hay
  reversión automática.
- Source (Raspberry desde código): se reinstala el paquete con pip.
"""

import os
import shutil
import subprocess
import sys

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.updater import commit_guard, install_kind
from fiscalberry.common.updater.selftest import make_executable

logger = getLogger("Updater")

BACKUP_SUFFIX = ".fb-backup"
INCOMING_SUFFIX = ".fb-new"

# Cuánto espera el binario nuevo a que se libere el candado de instancia única
# tras relanzarse. El proceso viejo puede tardar en morir del todo.
RELAUNCH_LOCK_WAIT = "30"


class ApplyError(Exception):
    pass


def _bajo_systemd():
    """systemd define INVOCATION_ID para cada unidad que lanza."""
    return bool(os.environ.get("INVOCATION_ID"))


def _relanzar(binario):
    """
    Arranca el binario nuevo como proceso independiente y devuelve el control.

    Solo se usa cuando NADIE nos va a reiniciar. Bajo systemd no se llama: ahí
    alcanza con salir, y lanzar un hijo además provocaría dos instancias
    peleando por el mismo client id de MQTT.
    """
    entorno = dict(os.environ)
    entorno["FISCALBERRY_LOCK_WAIT"] = RELAUNCH_LOCK_WAIT
    kwargs = {"env": entorno, "close_fds": True}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    subprocess.Popen([binario], **kwargs)


def _preparar_swap(nuevo, destino, version, version_previa):
    """
    Deja el respaldo y la marca de confirmación. Común a Linux y Windows.

    El orden importa: primero se respalda, después se arma la marca, y recién
    al final se toca el binario vivo. Si el proceso muere en el medio, lo peor
    que pasa es revertir a un respaldo idéntico al binario actual.
    """
    backup = destino + BACKUP_SUFFIX
    try:
        shutil.copy2(destino, backup)
    except Exception as e:
        raise ApplyError(f"no se pudo respaldar el binario actual: {e}")

    commit_guard.arm(version, version_previa, destino, backup)
    return backup


# --------------------------------------------------------------------------
# Linux / POSIX empaquetado
# --------------------------------------------------------------------------

def apply_posix(nuevo, destino, version, version_previa):
    """
    Reemplaza el binario y pide reinicio.

    `os.replace` es atómico y en POSIX está permitido sobre un ejecutable en
    uso: el proceso actual sigue corriendo con el inodo viejo hasta que muere.
    """
    _preparar_swap(nuevo, destino, version, version_previa)

    entrante = destino + INCOMING_SUFFIX
    try:
        shutil.copy2(nuevo, entrante)
        make_executable(entrante)
        os.replace(entrante, destino)
    except Exception as e:
        # El binario vivo no se tocó; se limpia la marca para no revertir de más.
        commit_guard.clear()
        try:
            os.remove(entrante)
        except OSError:
            pass
        raise ApplyError(f"no se pudo reemplazar el binario: {e}")

    logger.info("Binario reemplazado por la versión %s. Reiniciando...", version)
    if not _bajo_systemd():
        try:
            _relanzar(destino)
        except Exception as e:
            logger.error("No se pudo relanzar automáticamente: %s. "
                         "Hay que abrir Fiscalberry de nuevo a mano.", e)
    return True


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------

def apply_windows(nuevo, destino, version, version_previa):
    """
    Windows no deja sobrescribir un .exe en uso, así que el cambio lo hace el
    propio binario nuevo desde una copia temporal, una vez que éste murió.

    Se usa el binario NUEVO como ayudante (y no el viejo) para que el código que
    hace el reemplazo sea siempre el más reciente.
    """
    import tempfile

    _preparar_swap(nuevo, destino, version, version_previa)

    ayudante = os.path.join(
        tempfile.mkdtemp(prefix="fb-apply-"), os.path.basename(destino))
    try:
        shutil.copy2(nuevo, ayudante)
    except Exception as e:
        commit_guard.clear()
        raise ApplyError(f"no se pudo preparar el ayudante de actualización: {e}")

    entorno = dict(os.environ)
    entorno["FISCALBERRY_LOCK_WAIT"] = RELAUNCH_LOCK_WAIT
    try:
        subprocess.Popen(
            [ayudante, "--apply-update",
             "--pid", str(os.getpid()),
             "--src", ayudante,
             "--dst", destino],
            env=entorno,
            close_fds=True,
            creationflags=0x00000008 | 0x00000200,
        )
    except Exception as e:
        commit_guard.clear()
        raise ApplyError(f"no se pudo lanzar el ayudante de actualización: {e}")

    logger.info("Ayudante lanzado; al cerrarse este proceso queda la versión %s.",
                version)
    return True


def run_apply_helper(pid, src, dst, timeout=120):
    """
    Modo ayudante (`--apply-update`): esperar a que muera el proceso viejo,
    reemplazar el ejecutable y volver a arrancarlo.

    Corre en un proceso aparte; su salida no la ve nadie, así que todo lo
    importante va al log de archivo.
    """
    import time

    logger.info("Ayudante de actualización: esperando a que termine el pid %s", pid)
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if not _proceso_vivo(pid):
            break
        time.sleep(0.5)
    else:
        logger.error("El proceso %s no terminó en %ss; se cancela el reemplazo.",
                     pid, timeout)
        commit_guard.clear()
        return 1

    # Margen para que Windows suelte del todo el archivo.
    time.sleep(1.0)

    for intento in range(1, 6):
        try:
            shutil.copy2(src, dst)
            break
        except Exception as e:
            logger.warning("Intento %d de reemplazar %s falló: %s", intento, dst, e)
            time.sleep(2.0)
    else:
        logger.error("No se pudo reemplazar %s. Se revierte la marca.", dst)
        commit_guard.clear()
        return 1

    logger.info("Ejecutable reemplazado. Relanzando %s", dst)
    try:
        _relanzar(dst)
    except Exception as e:
        logger.error("No se pudo relanzar tras actualizar: %s", e)
        return 1
    return 0


def _proceso_vivo(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if os.name == "nt":
        try:
            salida = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
            return str(pid) in (salida.stdout or b"").decode("latin-1", "replace")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# Android
# --------------------------------------------------------------------------

def apply_android(apk_path, version, version_previa):
    """
    Lanza el instalador del sistema con el APK ya descargado y verificado.

    Limitaciones que NO son nuestras y conviene tener presentes:
    - El usuario tiene que aceptar. No existe instalación silenciosa sideload.
    - La firma del APK debe coincidir con la instalada, o Android rechaza.
    - No hay reversión automática: si la versión nueva no abre, hay que ir al
      local. Por eso acá no se arma la marca de commit_guard: no habría quién
      la resuelva.
    """
    try:
        from fiscalberry.common.android_context import get_android_context
    except Exception as e:
        raise ApplyError(f"no se pudo acceder a las APIs de Android: {e}")

    contexto = get_android_context()
    if contexto is None:
        raise ApplyError("no hay contexto de Android disponible")

    if not _apk_es_compatible(contexto, apk_path, version):
        raise ApplyError("el APK descargado no pasó la verificación local")

    try:
        _instalar_con_package_installer(contexto, apk_path)
    except Exception as e:
        raise ApplyError(f"no se pudo abrir el instalador de Android: {e}")

    logger.info("Instalador de Android abierto para la versión %s. "
                "Falta que el usuario acepte.", version)
    return True


def _instalar_con_package_installer(contexto, apk_path):
    """
    Instala vía PackageInstaller en vez de un Intent con FileProvider.

    Se elige esta API a propósito: la alternativa (ACTION_VIEW con content://)
    obliga a declarar un FileProvider en el manifest y un recurso de rutas, y
    tocar el manifest de p4a es justo lo que más veces rompió el build de
    Android. PackageInstaller no necesita nada de eso, solo el permiso
    REQUEST_INSTALL_PACKAGES que ya está en el .spec.

    El usuario igual tiene que aceptar: sin ser device owner no existe la
    instalación silenciosa, y no es algo que podamos sortear.
    """
    from jnius import autoclass

    Intent = autoclass("android.content.Intent")
    PendingIntent = autoclass("android.app.PendingIntent")
    SessionParams = autoclass("android.content.pm.PackageInstaller$SessionParams")
    BuildVersion = autoclass("android.os.Build$VERSION")

    installer = contexto.getPackageManager().getPackageInstaller()
    params = SessionParams(SessionParams.MODE_FULL_INSTALL)
    session_id = installer.createSession(params)
    session = installer.openSession(session_id)

    try:
        salida = session.openWrite("fiscalberry.apk", 0, -1)
        try:
            with open(apk_path, "rb") as fh:
                while True:
                    trozo = fh.read(256 * 1024)
                    if not trozo:
                        break
                    salida.write(bytearray(trozo), 0, len(trozo))
            session.fsync(salida)
        finally:
            salida.close()

        # El PendingIntent que recibe el resultado debe ser MUTABLE: el sistema
        # le agrega extras al confirmar. Con FLAG_IMMUTABLE, commit() falla.
        FLAG_MUTABLE = 0x02000000
        flags = FLAG_MUTABLE if BuildVersion.SDK_INT >= 31 else 0
        intent = Intent(contexto.getPackageName() + ".APK_INSTALL_RESULT")
        pending = PendingIntent.getBroadcast(contexto, session_id, intent, flags)
        session.commit(pending.getIntentSender())
    except Exception:
        try:
            session.abandon()
        except Exception:
            pass
        raise


def _apk_es_compatible(contexto, apk_path, version_esperada):
    """
    Antes de molestar al usuario, comprobar que el APK sirve.

    Se mira la versión y la firma. Si la firma no coincide con la de la app
    instalada, Android va a rechazar la actualización igual: mejor detectarlo
    acá y dejarlo en el log que mostrar un error críptico del sistema.
    """
    try:
        from jnius import autoclass

        PackageManager = autoclass("android.content.pm.PackageManager")
        pm = contexto.getPackageManager()
        GET_SIGNATURES = 64

        info = pm.getPackageArchiveInfo(apk_path, GET_SIGNATURES)
        if info is None:
            logger.error("El APK descargado no se pudo leer.")
            return False

        nombre_version = info.versionName
        if version_esperada and nombre_version and nombre_version != version_esperada:
            logger.error("El APK dice ser %s pero se esperaba %s.",
                         nombre_version, version_esperada)
            return False

        instalado = pm.getPackageInfo(contexto.getPackageName(), GET_SIGNATURES)
        firmas_apk = {s.toCharsString() for s in (info.signatures or [])}
        firmas_inst = {s.toCharsString() for s in (instalado.signatures or [])}
        if firmas_apk and firmas_inst and not (firmas_apk & firmas_inst):
            logger.error(
                "La firma del APK no coincide con la de la app instalada: "
                "Android rechazaría la actualización. Se descarta.")
            return False
        return True
    except Exception as e:
        # No poder verificar no debería bloquear para siempre; se avisa fuerte.
        logger.warning("No se pudo verificar el APK localmente (%s). Se continúa.", e)
        return True


# --------------------------------------------------------------------------
# Instalación desde código (Raspberry)
# --------------------------------------------------------------------------

def apply_source(tarball_url, version, version_previa):
    """
    Reinstala el paquete con pip desde el tarball del release.

    Acá no hay binario que respaldar, así que la reversión es reinstalar el
    tarball de la versión anterior. La verificación se hace DESPUÉS de instalar
    (no hay forma de probar el paquete sin instalarlo) y si falla se revierte
    en el acto.
    """
    if not _pip_install(tarball_url):
        raise ApplyError("pip no pudo instalar la versión nueva")

    ok, detalle = _selftest_modulo(version)
    if not ok:
        logger.error("La versión %s no pasa el selftest tras instalarse (%s). "
                     "Volviendo a %s.", version, detalle, version_previa)
        previo = tarball_url.replace(f"v{version}", f"v{version_previa}")
        if not _pip_install(previo):
            logger.critical(
                "No se pudo revertir a %s. El servicio puede quedar inestable; "
                "hace falta intervención manual.", version_previa)
        raise ApplyError("la versión nueva no pasó el selftest; se revirtió")

    logger.info("Paquete actualizado a %s. Reiniciando...", version)
    return True


def _pip_install(origen):
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", origen],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    except Exception as e:
        logger.error("pip falló: %s", e)
        return False
    if proc.returncode != 0:
        logger.error("pip devolvió %s: %s", proc.returncode,
                     (proc.stdout or b"")[-800:].decode("utf-8", "replace"))
        return False
    return True


def _selftest_modulo(version_esperada):
    from fiscalberry.common.updater.selftest import OK_MARKER
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "fiscalberry.cli.main", "--selftest"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    except Exception as e:
        return False, str(e)
    salida = (proc.stdout or b"").decode("utf-8", "replace")
    if proc.returncode != 0:
        return False, f"código {proc.returncode}: {salida[-300:]}"
    if f"{OK_MARKER} {version_esperada}" not in salida:
        return False, f"marca ausente: {salida[-300:]}"
    return True, "ok"


# --------------------------------------------------------------------------
# Reversión (la decide commit_guard, la ejecuta la plataforma)
# --------------------------------------------------------------------------

def rollback(pendiente):
    """Restaura el binario respaldado. Devuelve True si quedó restaurado."""
    if not pendiente.backup_exists():
        logger.error("No hay respaldo en %s: no se puede revertir.", pendiente.backup)
        commit_guard.clear()
        return False

    destino = pendiente.target
    try:
        if os.name == "nt":
            # Mismo problema que al instalar: el .exe está en uso. El respaldo
            # hace de ayudante y se reemplaza a sí mismo sobre el destino.
            entorno = dict(os.environ)
            entorno["FISCALBERRY_LOCK_WAIT"] = RELAUNCH_LOCK_WAIT
            subprocess.Popen(
                [pendiente.backup, "--apply-update",
                 "--pid", str(os.getpid()),
                 "--src", pendiente.backup,
                 "--dst", destino],
                env=entorno, close_fds=True,
                creationflags=0x00000008 | 0x00000200)
            logger.warning("Reversión a %s lanzada; este proceso debe cerrarse.",
                           pendiente.previous_version)
            return True

        shutil.copy2(pendiente.backup, destino + INCOMING_SUFFIX)
        make_executable(destino + INCOMING_SUFFIX)
        os.replace(destino + INCOMING_SUFFIX, destino)
    except Exception as e:
        logger.critical("Falló la reversión a %s: %s", pendiente.previous_version, e)
        return False

    commit_guard.clear()
    try:
        os.remove(pendiente.backup)
    except OSError:
        pass
    logger.warning("Revertido a la versión %s.", pendiente.previous_version)
    return True


def apply_for_kind(kind, **kwargs):
    """Despacha al applier que corresponde a esta instalación."""
    if kind == install_kind.ANDROID:
        return apply_android(kwargs["apk_path"], kwargs["version"],
                             kwargs["version_previa"])
    if kind == install_kind.SOURCE:
        return apply_source(kwargs["tarball_url"], kwargs["version"],
                            kwargs["version_previa"])
    if kind in (install_kind.WINDOWS_GUI, install_kind.WINDOWS_CLI):
        return apply_windows(kwargs["nuevo"], kwargs["destino"],
                             kwargs["version"], kwargs["version_previa"])
    return apply_posix(kwargs["nuevo"], kwargs["destino"],
                       kwargs["version"], kwargs["version_previa"])
