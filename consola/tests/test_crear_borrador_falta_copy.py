"""`crear_borrador_en` deriva `falta_copy` del copy REAL: un copy vacío => `falta_copy=True`."""

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


def test_borrador_rellena_fila_vacia_preexistente(entorno):
    """El depósito RELLENA un placeholder vacío de la misma red (no duplica la fila).

    Los flujos que promueven un tema con media adjunta (usar noticia, cajón presidencia)
    pre-crean la fila por red SIN copy; el copy debe caer en ESA fila —conservando su media
    (foto/carrusel)— en vez de nacer como hermana duplicada de la misma red.
    """
    tema = _tema()
    hueco = repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="instagram", falta_copy=True, falta_imagen=False,
        foto="fotos/portada.jpg", carrusel='[{"tipo":"imagen","objeto":"s2.jpg"}]',
    )
    pieza = dom.crear_borrador_en(tema["id"], "unotv", "instagram", contenido="Copy generado")
    assert pieza is not None
    assert pieza["id"] == hueco["id"]  # misma fila: rellenada, no duplicada
    assert pieza["contenido"] == "Copy generado"
    assert pieza["falta_copy"] is False
    # La media adjunta del placeholder sobrevive al depósito.
    assert pieza["foto"] == "fotos/portada.jpg"
    assert pieza["carrusel"] == '[{"tipo":"imagen","objeto":"s2.jpg"}]'
    # Y no hay filas duplicadas de esa red en el tema.
    filas = [
        p for p in repos.listar_contenido_plataforma(tema["id"]) if p["red"] == "instagram"
    ]
    assert len(filas) == 1


def test_borrador_no_rellena_fila_con_trabajo(entorno):
    """Una fila de la misma red CON copy no se pisa: el depósito crea una nueva."""
    tema = _tema()
    ocupada = repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", copy="Trabajo humano", falta_copy=False
    )
    pieza = dom.crear_borrador_en(tema["id"], "unotv", "x", contenido="Otro copy")
    assert pieza is not None
    assert pieza["id"] != ocupada["id"]
    assert (
        repos.obtener_contenido_plataforma(ocupada["id"])["copy"] == "Trabajo humano"
    )
