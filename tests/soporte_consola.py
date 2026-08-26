# coding=utf-8
"""
Herramientas para probar qué pasa cuando no hay consola.

Casi todo acá tiene que correr en un intérprete aparte. `fiscalberry_logger` se
configura una sola vez, al importarse, así que el estado de `sys.stdout` y
`sys.stderr` tiene que estar puesto ANTES de ese import: dentro del proceso de
pytest —que sí tiene consola, y ya importó el módulo— no se puede reproducir.
"""

import os
import subprocess
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(RAIZ, "src")
HOOK = os.path.join(RAIZ, "build_tools", "pyi_rth_consola.py")

TIEMPO_LIMITE = 120

# Lo que PyInstaller hace con un binario compilado con `console=False`, y
# también `pythonw`: no hay a dónde escribir.
SIN_CONSOLA = """
sys.stderr = None
sys.stdout = None
"""

# Lo que hace Kivy al importarse (kivy/logger.py: `sys.stderr =
# ProcessingStream("stderr", Logger.warning)`). Es la pieza que convierte un
# handler de logging roto en un cuelgue fatal: todo lo que se escriba a stderr
# vuelve a entrar al logging, que vuelve a fallar, que vuelve a escribir a
# stderr.
KIVY_TOMA_STDERR = """
class _ProcessingStream(io.TextIOBase):
    def __init__(self, destino): self.destino = destino
    def write(self, texto):
        if texto.strip(): self.destino(texto)
        return len(texto)
sys.stderr = _ProcessingStream(logging.getLogger("kivy").warning)
"""

# Devolver la consola real para poder contarle a pytest cómo fue.
VOLVER_A_LA_CONSOLA = """
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__
"""


def en_proceso_aparte(codigo, comprobar=True):
    """
    Corre el fragmento en un intérprete limpio y devuelve el CompletedProcess.

    Con `comprobar`, un código de salida distinto de cero es un fallo del test
    con toda la salida a la vista: si el proceso se muere, el test tiene que
    decir por qué y no pasar de largo.
    """
    preludio = f"import io, json, logging, os, sys\nsys.path.insert(0, {SRC!r})\n"
    resultado = subprocess.run(
        [sys.executable, "-c", preludio + codigo],
        capture_output=True, text=True, timeout=TIEMPO_LIMITE,
    )
    if comprobar:
        assert resultado.returncode == 0, (
            f"el proceso murió con código {resultado.returncode}\n"
            f"--- stdout ---\n{resultado.stdout[-2000:]}\n"
            f"--- stderr ---\n{resultado.stderr[-2000:]}"
        )
    return resultado


def veredicto(resultado):
    """
    Lee el JSON que el proceso hijo dejó en su última línea de stdout.

    Un hijo que no llegó a imprimirlo es un hijo que murió antes de tiempo, y
    eso tiene que romper el test, no devolver un diccionario vacío.
    """
    lineas = [l for l in resultado.stdout.strip().splitlines() if l.startswith("{")]
    assert lineas, (
        "el proceso no dejó veredicto; probablemente murió antes\n"
        f"--- stdout ---\n{resultado.stdout[-2000:]}\n"
        f"--- stderr ---\n{resultado.stderr[-2000:]}"
    )
    import json
    return json.loads(lineas[-1])


def binario_falso(carpeta, nombre, cuerpo):
    """
    Deja algo ejecutable que se comporta como un binario de Fiscalberry.

    `cuerpo` es el código Python que corre. Se envuelve en un lanzador nativo
    porque el updater invoca `[binario, "--selftest", ...]` y espera un
    ejecutable de verdad, no un guión de Python.
    """
    guion = carpeta / f"{nombre}.py"
    guion.write_text(f"import io, os, sys\nsys.path.insert(0, {SRC!r})\n{cuerpo}",
                     encoding="utf-8")

    if sys.platform == "win32":
        lanzador = carpeta / f"{nombre}.bat"
        lanzador.write_text(f'@echo off\r\n"{sys.executable}" "{guion}" %*\r\n',
                            encoding="utf-8")
    else:
        lanzador = carpeta / f"{nombre}.sh"
        lanzador.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{guion}" "$@"\n',
                            encoding="utf-8")
        lanzador.chmod(0o755)

    return str(lanzador)


# Un binario que no tiene stdout, como el .exe de la GUI compilado con
# `console=False`. Lo que escriba con print() no llega a ninguna parte.
GUI_SIN_STDOUT = """
class _Nulo(io.TextIOBase):
    encoding = "utf-8"
    def writable(self): return True
    def write(self, texto): return len(texto)
sys.stdout = _Nulo()
"""
