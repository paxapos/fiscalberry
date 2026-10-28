# coding=utf-8
"""
Que el empaquetado no vuelva a dejar al ejecutable sin salida.

El arreglo del arranque sin consola tiene una parte que no vive en el código
sino en cómo se compila: un runtime hook que corre antes que nada y les da a
`sys.stdout` y `sys.stderr` algo escribible. Un `.spec` regenerado con
`pyi-makespec` vuelve a traer `runtime_hooks=[]` y se lleva el arreglo puesto
sin que nadie lo note hasta que un usuario no puede abrir el programa.

También hay una invariante de código: `logging.basicConfig()` sin decidir antes
si hay consola es justo lo que rompía la 3.6.4, y no puede reaparecer en otro
módulo.
"""

import ast
import os

import pytest

from soporte_consola import HOOK, RAIZ, SRC


SPECS = ["fiscalberry-gui.spec", "fiscalberry-cli.spec"]

# El único lugar donde se decide cómo se configura el logging del proceso.
DUENIO_DEL_LOGGING = os.path.join("fiscalberry", "common", "fiscalberry_logger.py")


def _arbol(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=ruta)


def _argumento(arbol, funcion, nombre):
    """El valor de un keyword de una llamada, tal como está escrito en el spec."""
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Name)
                and nodo.func.id == funcion):
            for kw in nodo.keywords:
                if kw.arg == nombre:
                    return ast.literal_eval(kw.value)
    return None


@pytest.mark.parametrize("spec", SPECS)
def test_el_spec_declara_el_runtime_hook(spec):
    hooks = _argumento(_arbol(os.path.join(RAIZ, spec)), "Analysis", "runtime_hooks")

    assert hooks, (
        f"{spec} se quedó sin runtime_hooks. Es lo que pasa al regenerar el "
        f"spec con pyi-makespec: hay que volver a poner el hook de consola.")
    assert any("pyi_rth_consola" in h for h in hooks), hooks


@pytest.mark.parametrize("spec", SPECS)
def test_el_hook_que_declara_el_spec_existe(spec):
    """Un hook que no está hace fallar la compilación, no el arranque."""
    hooks = _argumento(_arbol(os.path.join(RAIZ, spec)), "Analysis", "runtime_hooks")

    for hook in hooks:
        assert os.path.exists(os.path.join(RAIZ, hook)), hook


@pytest.mark.parametrize("spec", SPECS)
def test_un_ejecutable_sin_consola_no_puede_quedarse_sin_el_hook(spec):
    """
    La invariante que importa, escrita como tal: `console=False` significa que
    no hay stdout ni stderr, y entonces el hook es obligatorio. Si mañana la
    GUI pasa a tener consola, este test deja de exigirlo solo.
    """
    arbol = _arbol(os.path.join(RAIZ, spec))
    if _argumento(arbol, "EXE", "console") is not False:
        pytest.skip(f"{spec} compila con consola")

    hooks = _argumento(arbol, "Analysis", "runtime_hooks") or []
    assert any("pyi_rth_consola" in h for h in hooks), (
        f"{spec} compila con console=False y sin el hook de consola: el "
        f"ejecutable se cae al primer log")


def test_el_hook_no_depende_del_paquete():
    """
    El hook tiene que valerse solo.

    Corre antes que la aplicación y no hay a dónde reportar si falla: si
    importara `fiscalberry` y PyInstaller no hubiera empaquetado ese módulo,
    el ejecutable moriría en el arranque por culpa del propio arreglo.
    """
    importados = []
    for nodo in ast.walk(_arbol(HOOK)):
        if isinstance(nodo, ast.Import):
            importados += [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom):
            importados.append(nodo.module or "")

    assert importados, "algo se importa: io y sys"
    for modulo in importados:
        assert modulo.split(".")[0] in ("io", "sys"), (
            f"el hook importa {modulo!r}; solo puede usar la stdlib básica")


def _modulos_del_paquete():
    for base, _, archivos in os.walk(os.path.join(SRC, "fiscalberry")):
        for archivo in archivos:
            if archivo.endswith(".py"):
                yield os.path.join(base, archivo)


def test_solo_el_logger_configura_el_logging_del_proceso():
    """
    `logging.basicConfig()` instala un StreamHandler sobre `sys.stderr`, que en
    el ejecutable de Windows vale None. Decidir si hay consola es asunto de un
    solo módulo; en cualquier otro lado vuelve a meter el bug.
    """
    culpables = []
    for ruta in _modulos_del_paquete():
        if ruta.endswith(DUENIO_DEL_LOGGING):
            continue
        for nodo in ast.walk(_arbol(ruta)):
            if (isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "basicConfig"):
                culpables.append(f"{os.path.relpath(ruta, SRC)}:{nodo.lineno}")

    assert not culpables, (
        "estos módulos configuran el logging por su cuenta y pueden volver a "
        f"armar un handler sobre una consola que no existe: {culpables}")
