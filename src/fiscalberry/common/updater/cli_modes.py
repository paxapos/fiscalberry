"""
Modos especiales de línea de comandos que atiende el propio ejecutable.

Se resuelven ANTES de cualquier otra cosa en los entry points, porque no son
arranques normales del programa:

- `--selftest`: lo ejecuta el updater sobre el binario NUEVO, antes de
  instalarlo. Tiene que ejercitar lo que suele romperse al empaquetar (imports
  que PyInstaller no detectó, Kivy, la base del spooler) y salir con código 0.
- `--apply-update`: solo Windows. El binario nuevo hace de ayudante y reemplaza
  al viejo una vez que éste murió.
- `--version`: útil para diagnosticar a distancia.
- `--discovery-report`: lo que ve el asistente de impresoras (redes, USB,
  puertos COM, colas), sin tocar nada. Lo usa la prueba del instalador.
"""

import os
import sys

MODES = ("--selftest", "--apply-update", "--version", "--discovery-report")


def _arg(argv, nombre, defecto=None):
    """Lee `--clave valor` sin arrastrar argparse a un arranque temprano."""
    if nombre in argv:
        i = argv.index(nombre)
        if i + 1 < len(argv):
            return argv[i + 1]
    return defecto


def handle_early_modes(argv=None):
    """
    Atiende los modos especiales. Si maneja alguno, termina el proceso.

    Devuelve False si no había ninguno y el arranque debe continuar normal.
    """
    argv = list(sys.argv if argv is None else argv)

    if "--version" in argv:
        from fiscalberry.version import VERSION
        print(VERSION)
        sys.exit(0)

    if "--apply-update" in argv:
        from fiscalberry.common.updater.appliers import run_apply_helper
        codigo = run_apply_helper(
            pid=_arg(argv, "--pid"),
            src=_arg(argv, "--src"),
            dst=_arg(argv, "--dst"),
            exe=_arg(argv, "--exe"),
        )
        sys.exit(codigo)

    if "--discovery-report" in argv:
        from fiscalberry.common.discovery_report import run
        sys.exit(run(ruta_reporte=_arg(argv, "--report")))

    if "--selftest" in argv:
        sys.exit(run_selftest(ruta_reporte=_arg(argv, "--report")))

    return False


def run_selftest(ruta_reporte=None):
    """
    Comprobación de que este binario sirve. Devuelve el código de salida.

    Importa a propósito los módulos pesados: el modo de falla clásico de un
    binario de PyInstaller es arrancar y morir en un import que el empaquetador
    no vio. Compilar no lo detecta; esto sí.
    """
    from fiscalberry.version import VERSION
    from fiscalberry.common.updater.selftest import selftest_report

    fallas = []

    # Kivy parsea sys.argv al importarse: "--selftest --report x" son opciones
    # que no conoce, y responde con sys.exit(2). El updater ya lanza el
    # selftest con KIVY_NO_ARGS=1, pero corrido a mano (soporte, CI) moría sin
    # escribir el reporte.
    os.environ.setdefault("KIVY_NO_ARGS", "1")

    def probar(descripcion, fn):
        try:
            fn()
        except (Exception, SystemExit) as e:
            # SystemExit también: una librería que corta el proceso al
            # importarse es justamente una falla que el selftest tiene que ver.
            fallas.append(f"{descripcion}: {type(e).__name__}: {e}")

    def _imports_core():
        import fiscalberry.common.ComandosHandler  # noqa: F401
        import fiscalberry.common.EscPComandos  # noqa: F401
        import fiscalberry.common.fiscalberry_sio  # noqa: F401
        import fiscalberry.common.print_spooler  # noqa: F401
        import fiscalberry.common.rabbitmq.consumer  # noqa: F401
        import escpos.printer  # noqa: F401

    def _config():
        from fiscalberry.common.Configberry import Configberry
        Configberry().getConfigFIle()

    def _spooler_db():
        import sqlite3
        from fiscalberry.common.print_spooler import default_db_path
        con = sqlite3.connect(default_db_path())
        try:
            con.execute("SELECT 1")
        finally:
            con.close()

    def _updater():
        from fiscalberry.common.updater import service  # noqa: F401

    probar("imports del núcleo", _imports_core)
    probar("lectura de configuración", _config)
    probar("base del spooler", _spooler_db)
    probar("módulo de actualización", _updater)

    # La GUI solo se prueba en el binario de la GUI: en el CLI, Kivy puede no
    # estar empaquetado y su ausencia no es una falla.
    from fiscalberry.common.updater import install_kind
    if install_kind.is_gui():
        def _gui():
            import kivy  # noqa: F401
            from kivy.app import App  # noqa: F401
            import fiscalberry.ui.fiscalberry_app  # noqa: F401
            import fiscalberry.desktop.tray  # noqa: F401
            # El asistente se importa recién al construir la App: sin esto,
            # un módulo que PyInstaller no empaquetó aparecería con el local
            # ya actualizado.
            import fiscalberry.ui.printer_setup_screen  # noqa: F401
            import fiscalberry.common.printer_wizard  # noqa: F401
            import fiscalberry.common.printer_test  # noqa: F401
            import fiscalberry.common.network_discovery  # noqa: F401
            import fiscalberry.common.usb_discovery  # noqa: F401
            import fiscalberry.common.usbprint_driver  # noqa: F401
            import fiscalberry.common.discovery_report  # noqa: F401
            if sys.platform == "win32":
                # Backend que pystray carga dinámicamente: si PyInstaller no
                # lo empaquetó, la bandeja no aparece y la "X" cierra la app.
                import pystray._win32  # noqa: F401
        probar("módulos de la interfaz", _gui)

    if fallas:
        lineas = [f"SELFTEST FALLO -> {f}" for f in fallas]
        codigo = 1
    else:
        lineas = [selftest_report(VERSION)]
        codigo = 0

    _publicar_resultado(lineas, ruta_reporte)
    return codigo


def _publicar_resultado(lineas, ruta_reporte=None):
    """
    Deja el resultado del selftest donde el proceso padre pueda leerlo.

    Por stdout, como siempre, pero eso solo alcanza en el binario de consola:
    el .exe de la GUI se compila con `console=False` y ahí `print()` no escribe
    en ningún lado, así que el padre leía la salida vacía y daba por fallado
    todo selftest de la GUI en Windows —o sea, esa GUI no podía actualizarse
    nunca—. Por eso el padre además pasa `--report <archivo>` y el resultado
    de verdad se lee de ahí.
    """
    for linea in lineas:
        print(linea)

    if not ruta_reporte:
        return

    try:
        with open(ruta_reporte, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lineas))
    except Exception:
        # Si no se puede escribir el reporte queda el stdout; nunca hacer
        # fallar al selftest por esto.
        pass
