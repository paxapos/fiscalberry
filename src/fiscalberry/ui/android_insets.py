# coding=utf-8
"""
Márgenes del sistema (barra de estado, barra de navegación, notch).

Desde Android 15 (API 35) el sistema fuerza el modo edge-to-edge: la app dibuja
DEBAJO de la barra de estado y de la de navegación, y es responsabilidad de la
app dejar ese espacio libre. Sin esto, el reloj y los íconos del celular tapan
la primera fila de la interfaz (botón "volver", títulos) y la barra de gestos
tapa la última.

Devuelve píxeles, que es la unidad en la que Kivy trabaja en Android.
"""

from fiscalberry.common.fiscalberry_logger import getLogger

logger = getLogger("GUI.Insets")

SIN_MARGENES = {"top": 0, "bottom": 0, "left": 0, "right": 0}


def _insets_por_window(activity):
    """
    Vía precisa: WindowInsets del sistema. Contempla notch y barra de gestos.

    Puede devolver None: getRootWindowInsets() necesita la vista ya adjunta y no
    siempre está disponible cuando Kivy consulta (corre en el hilo de SDL, no en
    el hilo de UI de Android).
    """
    from jnius import autoclass

    Build = autoclass("android.os.Build$VERSION")
    decor = activity.getWindow().getDecorView()
    insets = decor.getRootWindowInsets()
    if insets is None:
        return None

    if Build.SDK_INT >= 30:
        Type = autoclass("android.view.WindowInsets$Type")
        barras = insets.getInsets(Type.systemBars())
        return {
            "top": barras.top,
            "bottom": barras.bottom,
            "left": barras.left,
            "right": barras.right,
        }

    return {
        "top": insets.getSystemWindowInsetTop(),
        "bottom": insets.getSystemWindowInsetBottom(),
        "left": insets.getSystemWindowInsetLeft(),
        "right": insets.getSystemWindowInsetRight(),
    }


def _insets_por_recursos(activity):
    """
    Respaldo: alturas declaradas en los recursos del sistema. Menos exacto que
    WindowInsets (no contempla notch), pero se puede leer desde cualquier hilo.
    """
    recursos = activity.getResources()

    def alto(nombre):
        ident = recursos.getIdentifier(nombre, "dimen", "android")
        return recursos.getDimensionPixelSize(ident) if ident > 0 else 0

    return {
        "top": alto("status_bar_height"),
        "bottom": alto("navigation_bar_height"),
        "left": 0,
        "right": 0,
    }


def get_system_insets():
    """
    Márgenes a respetar, en píxeles. En escritorio (o ante cualquier problema)
    devuelve ceros: la UI queda como antes, nunca rota.
    """
    try:
        from jnius import autoclass
    except ImportError:
        return dict(SIN_MARGENES)  # Escritorio

    try:
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        if activity is None:
            return dict(SIN_MARGENES)

        try:
            margenes = _insets_por_window(activity)
            if margenes and margenes.get("top"):
                logger.debug(f"Márgenes por WindowInsets: {margenes}")
                return margenes
        except Exception as e:
            logger.debug(f"WindowInsets no disponible, se usan los recursos: {e}")

        margenes = _insets_por_recursos(activity)
        logger.debug(f"Márgenes por recursos: {margenes}")
        return margenes
    except Exception as e:
        logger.warning(f"No se pudieron obtener los márgenes del sistema: {e}")
        return dict(SIN_MARGENES)
