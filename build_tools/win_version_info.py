# coding=utf-8
"""
Genera el recurso VERSIONINFO de los .exe de Windows.

Para qué sirve: un ejecutable sin metadatos de versión aparece en Windows como
un archivo anónimo —sin empresa, sin descripción, sin producto— tanto en el
diálogo de SmartScreen como en las propiedades del archivo. Eso lo hace ver
sospechoso al usuario y suma puntos en las heurísticas de los antivirus.

Por qué se genera en vez de mantenerse a mano: el archivo estático que había
declaraba la versión **2.1.0.0** cuando el producto ya iba por la 3.5.x. Un
ejecutable que dice ser una versión que no es no ayuda a que nadie confíe en
él, y mantener el número sincronizado a mano no funcionó. Ahora sale siempre
de `fiscalberry/version.py`, que es la única fuente de verdad.
"""

import os
import re

PLANTILLA = """# GENERADO AUTOMATICAMENTE por build_tools/win_version_info.py
# No editar a mano: se regenera en cada build a partir de version.py
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vers},
    prodvers={vers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Paxapos - Plus Abstracta SRL'),
        StringStruct(u'FileDescription', u'{descripcion}'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'{nombre}'),
        StringStruct(u'LegalCopyright', u'(c) Paxapos - Plus Abstracta SRL. Licencia MIT.'),
        StringStruct(u'OriginalFilename', u'{nombre}.exe'),
        StringStruct(u'ProductName', u'Fiscalberry'),
        StringStruct(u'ProductVersion', u'{version}'),
        StringStruct(u'Comments', u'Servidor de impresion de codigo abierto. https://github.com/paxapos/fiscalberry')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

DESCRIPCIONES = {
    "fiscalberry-gui": "Fiscalberry - Servidor de impresion (interfaz grafica)",
    "fiscalberry-cli": "Fiscalberry - Servidor de impresion (consola)",
}


def _tupla_de_version(version):
    """'3.5.2' -> (3, 5, 2, 0). Windows exige exactamente cuatro numeros."""
    numeros = [int(n) for n in re.findall(r"\d+", version)][:4]
    while len(numeros) < 4:
        numeros.append(0)
    return tuple(numeros)


def generar(nombre, version, destino=None):
    """
    Escribe el archivo de VERSIONINFO para `nombre` y devuelve su ruta.

    `nombre` es el del ejecutable sin extensión (ej. 'fiscalberry-cli').
    """
    destino = destino or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), f"version_info_{nombre}.txt")

    contenido = PLANTILLA.format(
        vers=_tupla_de_version(version),
        version=version,
        nombre=nombre,
        descripcion=DESCRIPCIONES.get(nombre, "Fiscalberry"),
    )
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(contenido)
    return destino
