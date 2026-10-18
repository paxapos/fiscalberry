# coding=utf-8
"""
Impresión Win32Raw que VERIFICA que el ticket salió, y se repone sola cuando
Windows le cambia el puerto USB a la impresora.

El problema (visto en un comercio con Windows 11 e impresora Hasar USB):
  Win32Raw abre la impresora por el NOMBRE de la cola de Windows y escribe los
  bytes en el spooler. Fiscalberry nunca ve el puerto (USB001, USB002...).
  Cada tanto Windows vuelve a enumerar el dispositivo (microcorte, ahorro de
  energía USB, impresora sin número de serie USB) y le asigna un puerto NUEVO,
  pero la cola sigue apuntando al viejo, que ya no existe. Escribir en esa cola
  no da error: el trabajo queda trabado en la cola de Windows, Fiscalberry lo
  daba por "impreso OK" y el spooler durable lo descartaba. Ticket perdido.

Qué hace este módulo (todo "fail-open": si un chequeo no se puede hacer, se
imprime como siempre; nunca puede dejar de imprimir algo que antes imprimía):
  1. Antes de imprimir: si la cola apunta a un puerto USB muerto y el
     dispositivo apareció en otro puerto, mueve la cola a ese puerto (requiere
     permiso de "administrar impresora") o usa otra cola de la misma impresora
     que ya esté en el puerto vivo (la "Copia 1" que crea Windows).
  2. Después de imprimir: espera a que el trabajo salga de la cola de Windows.
     Si se traba (error, sin papel, offline, o no avanza), lo CANCELA (para que
     no salga duplicado cuando se arregle) y lanza PrinterProblem: el spooler
     lo reintenta y la pantalla muestra qué hacer.

Las funciones reciben `win32print`/`winreg` inyectables para poder testearlas
sin Windows.
"""

import re
import time

from fiscalberry.common.fiscalberry_logger import getLogger
from fiscalberry.common.printer_health import (
    PrinterProblem, SIN_PAPEL, TAPA_ABIERTA, PAPEL_TRABADO, NO_RESPONDE,
    IMPRESORA_CON_FALLA, CONEXION_PERDIDA, NO_ENCONTRADA, COLA_PAUSADA,
    NO_IMPRIME)

logger = getLogger()

# --- Constantes de winspool.h (se definen acá: no todas existen en pywin32) ---
PRINTER_STATUS_PAUSED = 0x00000001
PRINTER_STATUS_ERROR = 0x00000002
PRINTER_STATUS_PAPER_JAM = 0x00000008
PRINTER_STATUS_PAPER_OUT = 0x00000010
PRINTER_STATUS_PAPER_PROBLEM = 0x00000040
PRINTER_STATUS_OFFLINE = 0x00000080
PRINTER_STATUS_NOT_AVAILABLE = 0x00001000
PRINTER_STATUS_USER_INTERVENTION = 0x00100000
PRINTER_STATUS_DOOR_OPEN = 0x00400000

PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x00000400

JOB_STATUS_PAUSED = 0x00000001
JOB_STATUS_ERROR = 0x00000002
JOB_STATUS_PRINTING = 0x00000010
JOB_STATUS_OFFLINE = 0x00000020
JOB_STATUS_PAPEROUT = 0x00000040
JOB_STATUS_PRINTED = 0x00000080
JOB_STATUS_DELETED = 0x00000100
JOB_STATUS_BLOCKED_DEVQ = 0x00000200
JOB_STATUS_USER_INTERVENTION = 0x00000400
JOB_STATUS_COMPLETE = 0x00001000

JOB_STATUS_TRABADO = (JOB_STATUS_ERROR | JOB_STATUS_OFFLINE | JOB_STATUS_PAPEROUT
                      | JOB_STATUS_BLOCKED_DEVQ | JOB_STATUS_USER_INTERVENTION
                      | JOB_STATUS_PAUSED)
JOB_STATUS_TERMINADO = JOB_STATUS_PRINTED | JOB_STATUS_COMPLETE | JOB_STATUS_DELETED

JOB_CONTROL_DELETE = 5
PRINTER_ALL_ACCESS = 0x000F000C

# Interfaz de dispositivo de las impresoras USB (GUID_DEVINTERFACE_USBPRINT).
# usbmon guarda acá el número de puerto (USB001...) de cada dispositivo que vio
# alguna vez; "Control\Linked" = 1 solo mientras el dispositivo está presente.
USBPRINT_CLASS_KEY = (r"SYSTEM\CurrentControlSet\Control\DeviceClasses"
                      r"\{28d78fad-5a12-11d1-ae5b-0000f803a8c2}")

_PUERTO_USB = re.compile(r"^USB\d{3}$", re.IGNORECASE)

# Tiempos de espera del trabajo en la cola de Windows.
SEGUNDOS_SIN_AVANCE = 20     # en cola sin empezar a salir
SEGUNDOS_MAX_IMPRIMIENDO = 90  # tope aunque figure "imprimiendo"
SEGUNDOS_EN_ERROR = 4        # error sostenido antes de rendirse
INTERVALO_SONDEO = 0.25


def _win32print():
    import win32print
    return win32print


def _winreg():
    import winreg
    return winreg


def _puertos_de(info):
    return [p.strip() for p in (info.get("pPortName") or "").split(",") if p.strip()]


def _problema_por_estado_impresora(status):
    """Traduce el Status de la cola de Windows a un problema (o None)."""
    if status & PRINTER_STATUS_PAPER_OUT:
        return SIN_PAPEL
    if status & PRINTER_STATUS_DOOR_OPEN:
        return TAPA_ABIERTA
    if status & PRINTER_STATUS_PAPER_JAM:
        return PAPEL_TRABADO
    if status & (PRINTER_STATUS_OFFLINE | PRINTER_STATUS_NOT_AVAILABLE):
        return NO_RESPONDE
    if status & (PRINTER_STATUS_ERROR | PRINTER_STATUS_PAPER_PROBLEM
                 | PRINTER_STATUS_USER_INTERVENTION):
        return IMPRESORA_CON_FALLA
    return None


def leer_cola(printer_name, win32print=None):
    """PRINTER_INFO_2 de la cola (dict de pywin32)."""
    win32print = win32print or _win32print()
    h = win32print.OpenPrinter(printer_name)
    try:
        return win32print.GetPrinter(h, 2)
    finally:
        win32print.ClosePrinter(h)


def puertos_usb(winreg=None):
    """
    Puertos USB de impresora que Windows conoce, desde el registro:
        {"USB001": {"vivo": bool, "descripcion": str, "dispositivo": str}}
    Vacío si no se puede leer (el llamador debe tomarlo como "no sé").
    """
    winreg = winreg or _winreg()
    puertos = {}
    try:
        clase = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, USBPRINT_CLASS_KEY)
    except OSError:
        return puertos
    try:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(clase, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(clase, sub + r"\#\Device Parameters") as dp:
                    numero = winreg.QueryValueEx(dp, "Port Number")[0]
                    try:
                        base = winreg.QueryValueEx(dp, "Base Name")[0] or "USB"
                    except OSError:
                        base = "USB"
                    try:
                        descripcion = winreg.QueryValueEx(dp, "Port Description")[0] or ""
                    except OSError:
                        descripcion = ""
            except OSError:
                continue
            vivo = False
            try:
                with winreg.OpenKey(clase, sub + r"\#\Control") as ctl:
                    vivo = bool(winreg.QueryValueEx(ctl, "Linked")[0])
            except OSError:
                pass  # sin "Control": el dispositivo no está conectado
            nombre = f"{base}{int(numero):03d}"
            # Si dos instancias reclaman el mismo número, gana la que está viva.
            if nombre in puertos and puertos[nombre]["vivo"] and not vivo:
                continue
            puertos[nombre] = {"vivo": vivo, "descripcion": descripcion,
                               "dispositivo": sub}
    finally:
        winreg.CloseKey(clase)
    return puertos


def _mover_cola_a_puerto(printer_name, puerto, win32print):
    """Cambia el puerto de la cola. Requiere permiso de administrar la impresora."""
    h = win32print.OpenPrinter(printer_name, {"DesiredAccess": PRINTER_ALL_ACCESS})
    try:
        info = win32print.GetPrinter(h, 2)
        info["pPortName"] = puerto
        # None = no tocar permisos; reescribirlos puede fallar sin ser necesario.
        info["pSecurityDescriptor"] = None
        win32print.SetPrinter(h, 2, info, 0)
    finally:
        win32print.ClosePrinter(h)


def _cola_alternativa(info, puerto, win32print):
    """Otra cola con el mismo driver que ya usa `puerto` (ej. 'X (Copia 1)')."""
    for p in win32print.EnumPrinters(2):
        nombre = p.get("pPrinterName")
        if (nombre and nombre != info.get("pPrinterName")
                and p.get("pDriverName") == info.get("pDriverName")
                and puerto.upper() in (x.upper() for x in _puertos_de(p))):
            return nombre
    return None


def preparar_cola(printer_name, win32print=None, winreg=None):
    """
    Chequeo previo a imprimir. Devuelve el nombre de la cola a usar (normalmente
    el mismo). Lanza PrinterProblem solo cuando es SEGURO que el trabajo no va a
    salir; ante cualquier duda devuelve `printer_name` y se imprime como siempre.
    """
    win32print = win32print or _win32print()
    try:
        info = leer_cola(printer_name, win32print)
    except Exception as e:
        # El driver de escpos dará su propio error (impresora inexistente).
        logger.debug("No se pudo leer la cola '%s': %s", printer_name, e)
        return printer_name

    if (info.get("Status", 0) & PRINTER_STATUS_PAUSED
            or info.get("Attributes", 0) & PRINTER_ATTRIBUTE_WORK_OFFLINE):
        raise PrinterProblem(
            COLA_PAUSADA,
            f"La cola '{printer_name}' está pausada o en 'usar sin conexión'")

    puertos = _puertos_de(info)
    if not puertos or not all(_PUERTO_USB.match(p) for p in puertos):
        return printer_name  # red, COM, puerto propio del fabricante: no aplica

    try:
        usb = puertos_usb(winreg)
    except Exception as e:
        logger.debug("No se pudieron leer los puertos USB: %s", e)
        return printer_name
    if not usb:
        return printer_name

    mios = [usb.get(p.upper()) for p in puertos]
    if any(m and m["vivo"] for m in mios):
        return printer_name

    # El puerto de la cola está muerto. ¿Apareció la misma impresora en otro?
    descripciones = {m["descripcion"].strip().lower() for m in mios
                     if m and m["descripcion"].strip()}
    candidatos = sorted(nombre for nombre, d in usb.items()
                        if d["vivo"] and d["descripcion"].strip().lower() in descripciones)

    if not candidatos:
        # No hay ningún dispositivo igual conectado: apagada o desenchufada.
        raise PrinterProblem(
            NO_RESPONDE,
            f"Cola '{printer_name}' en {','.join(puertos)}: el dispositivo USB no está conectado")

    if len(candidatos) > 1:
        # Dos impresoras iguales conectadas: no adivinamos cuál es.
        raise PrinterProblem(
            CONEXION_PERDIDA,
            f"Cola '{printer_name}' en {','.join(puertos)} (sin dispositivo); "
            f"hay varias iguales vivas: {candidatos}")

    nuevo = candidatos[0]
    try:
        _mover_cola_a_puerto(printer_name, nuevo, win32print)
        logger.warning(
            "Windows le cambió el puerto a la impresora '%s' (%s -> %s). "
            "Se corrigió la cola automáticamente.", printer_name, ",".join(puertos), nuevo)
        return printer_name
    except Exception as e:
        logger.warning("No se pudo mover la cola '%s' a %s (¿falta permiso de "
                       "administrar la impresora?): %s", printer_name, nuevo, e)

    alternativa = _cola_alternativa(info, nuevo, win32print)
    if alternativa:
        logger.warning(
            "Windows le cambió el puerto a la impresora '%s' (%s -> %s). Se imprime "
            "por la cola '%s', que ya está en el puerto nuevo.",
            printer_name, ",".join(puertos), nuevo, alternativa)
        return alternativa

    raise PrinterProblem(
        CONEXION_PERDIDA,
        f"Windows movió la impresora de {','.join(puertos)} a {nuevo} y la cola "
        f"'{printer_name}' quedó en el puerto viejo; no hay permiso para corregirla. "
        f"Correr scripts/windows/configurar_impresora_usb.ps1 como administrador.")


def _cancelar(win32print, h, job_id):
    try:
        win32print.SetJob(h, job_id, 0, None, JOB_CONTROL_DELETE)
        return True
    except Exception as e:
        logger.error("No se pudo cancelar el trabajo %s trabado en Windows (puede "
                     "salir duplicado cuando se arregle): %s", job_id, e)
        return False


def esperar_trabajo(printer_name, job_id, win32print=None, winreg=None,
                    reloj=time.monotonic, dormir=time.sleep):
    """
    Espera a que el trabajo `job_id` salga de la cola de Windows. Si queda
    trabado lo cancela y lanza PrinterProblem con la causa más probable.
    """
    win32print = win32print or _win32print()
    try:
        h = win32print.OpenPrinter(printer_name)
    except Exception as e:
        logger.debug("No se pudo abrir '%s' para verificar el trabajo: %s", printer_name, e)
        return

    try:
        inicio = reloj()
        error_desde = None
        while True:
            try:
                job = win32print.GetJob(h, job_id, 1)
            except Exception:
                return  # ya no está en la cola: salió hacia la impresora
            status = job.get("Status", 0) or 0
            if status & JOB_STATUS_TERMINADO:
                return

            ahora = reloj()
            if status & JOB_STATUS_TRABADO:
                error_desde = error_desde if error_desde is not None else ahora
                if ahora - error_desde >= SEGUNDOS_EN_ERROR:
                    break
            else:
                error_desde = None

            limite = (SEGUNDOS_MAX_IMPRIMIENDO if status & JOB_STATUS_PRINTING
                      else SEGUNDOS_SIN_AVANCE)
            if ahora - inicio >= limite:
                break
            dormir(INTERVALO_SONDEO)

        # Trabado: cancelarlo ANTES de reportar, para que no salga sumado al
        # reintento cuando la impresora vuelva.
        _cancelar(win32print, h, job_id)
        tipo, detalle = _diagnosticar(printer_name, job, win32print, winreg)
        raise PrinterProblem(tipo, detalle)
    finally:
        try:
            win32print.ClosePrinter(h)
        except Exception:
            pass


def _diagnosticar(printer_name, job, win32print, winreg):
    """Mejor explicación disponible para un trabajo que no salió."""
    job_status = job.get("Status", 0) or 0
    detalle = (f"Trabajo {job.get('JobId')} trabado en la cola '{printer_name}' "
               f"(status=0x{job_status:x}, '{job.get('pStatus') or ''}')")
    if job_status & JOB_STATUS_PAPEROUT:
        return SIN_PAPEL, detalle
    try:
        info = leer_cola(printer_name, win32print)
    except Exception:
        info = {}
    detalle += f"; cola status=0x{info.get('Status', 0):x} puerto={info.get('pPortName')}"
    por_estado = _problema_por_estado_impresora(info.get("Status", 0) or 0)

    puertos = _puertos_de(info)
    if puertos and all(_PUERTO_USB.match(p) for p in puertos):
        try:
            usb = puertos_usb(winreg)
        except Exception:
            usb = {}
        mios = [usb.get(p.upper()) for p in puertos]
        if usb and not any(m and m["vivo"] for m in mios):
            descripciones = {m["descripcion"].strip().lower() for m in mios
                             if m and m["descripcion"].strip()}
            otro = any(d["vivo"] and d["descripcion"].strip().lower() in descripciones
                       for d in usb.values())
            return (CONEXION_PERDIDA if otro else NO_RESPONDE), detalle + "; puerto USB muerto"

    if por_estado:
        return por_estado, detalle
    if job_status & JOB_STATUS_OFFLINE:
        return NO_RESPONDE, detalle
    if job_status & (JOB_STATUS_ERROR | JOB_STATUS_USER_INTERVENTION):
        return IMPRESORA_CON_FALLA, detalle
    if job_status & JOB_STATUS_PAUSED:
        return COLA_PAUSADA, detalle
    return NO_IMPRIME, detalle


def crear_driver_verificado(**kwargs):
    """Instancia el Win32Raw verificado (import diferido: escpos/pywin32)."""
    return _clase_verificada()(**kwargs)


_CLASE = None


def _clase_verificada():
    global _CLASE
    if _CLASE is not None:
        return _CLASE

    from escpos import printer as escpos_printer

    class Win32RawVerificado(escpos_printer.Win32Raw):
        """Win32Raw que no da por impreso lo que quedó trabado en Windows."""

        def open(self, job_name="fiscalberry", raise_not_found=True):
            self._fallo_escritura = None
            try:
                if self.printer_name:
                    self.printer_name = preparar_cola(self.printer_name)
                try:
                    super().open(job_name=job_name, raise_not_found=True)
                except Exception as e:
                    raise PrinterProblem(
                        NO_ENCONTRADA,
                        f"No se pudo abrir la cola '{self.printer_name}': {e}") from e
            except PrinterProblem as problema:
                # Si la apertura ocurre dentro de una acción de EscPComandos, la
                # excepción se traga ahí; close() la vuelve a lanzar.
                self._fallo_escritura = problema
                raise

        def _raw(self, msg):
            try:
                super()._raw(msg)
            except Exception as e:
                # EscPComandos atrapa los errores acción por acción y sigue:
                # sin esto, un ticket que no se pudo escribir quedaba "OK".
                if getattr(self, "_fallo_escritura", None) is None:
                    self._fallo_escritura = e  # la primera causa es la que importa
                raise

        def close(self):
            if self._device is False or self._device is None:
                fallo = getattr(self, "_fallo_escritura", None)
                self._fallo_escritura = None
                if isinstance(fallo, PrinterProblem):
                    raise fallo
                if fallo is not None:
                    raise PrinterProblem(
                        NO_ENCONTRADA, f"No se pudo escribir en '{self.printer_name}': {fallo}")
                return
            job_id = getattr(self, "current_job", None)
            nombre = self.printer_name
            fallo = getattr(self, "_fallo_escritura", None)
            self._fallo_escritura = None
            super().close()
            if fallo is not None:
                raise PrinterProblem(
                    NO_RESPONDE, f"Falló la escritura en '{nombre}': {fallo}")
            if job_id:
                try:
                    esperar_trabajo(nombre, job_id)
                except PrinterProblem:
                    raise
                except Exception as e:
                    logger.debug("No se pudo verificar el trabajo en Windows: %s", e)

        def __del__(self):
            # Escpos.__del__ llama a close(): no puede lanzar en el GC.
            try:
                super().close()
            except Exception:
                pass

    _CLASE = Win32RawVerificado
    return _CLASE
