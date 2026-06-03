"""`crear_borrador_en` deriva `falta_copy` del copy REAL, no lo hardcodea a False.

Regresión: el flag fijo en False creaba piezas "copy listo" con copy vacío (drift que mentía en
el label del feed y en el gate de auto-avance). Ahora un copy vacío => `falta_copy=True`.
"""

from __future__ import annotations

from keni_consola import repos
from keni_consola.dominio import publicaciones as dom


def _tema():
    return repos.crear_contenido(clase="contenido", titulo="Tema", marca="unotv", origen="pipeline")


def test_borrador_sin_copy_marca_falta_copy(entorno):
    pieza = dom.crear_borrador_en(_tema()["id"], "unotv", "x", contenido="")
    assert pieza is not None
    assert pieza["falta_copy"] is True
    # Y la etapa, derivada del contenido real, NO miente: sin copy => generando_copy.
    assert pieza["etapa_ia"] == "generando_copy"


def test_borrador_con_copy_no_falta(entorno):
    pieza = dom.crear_borrador_en(_tema()["id"], "unotv", "instagram", contenido="Hola mundo")
    assert pieza is not None
    assert pieza["falta_copy"] is False
