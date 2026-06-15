"""Inmutabilidad de piezas `publicado`: lo que salió a redes no puede diferir de lo mostrado.

Una pieza ya publicada es READ-ONLY en lo editorial/visual (copy, imagen, foto, plantilla,
encuadre, carrusel, fecha…). Las escrituras OPERATIVAS (estado, id_post_metricool, preparado_en,
metadatos de revisión) siguen permitidas, y BORRAR también (limpiar errores). El guard vive en la
fachada `repos` (`verificar_publicacion_inmutable`) y la API lo traduce a 409.
"""

from __future__ import annotations

import pytest

from keni_consola import repos
from keni_consola.repos import PiezaPublicadaInmutable


def _publicada(entorno, **campos) -> dict:
    base = {"titulo": "T", "contenido": "Copy publicado", "estado": "publicado"}
    base.update(campos)
    return repos.crear_publicacion("unotv", "x", **base)


def test_publicada_no_admite_cambio_de_plantilla(entorno):
    """El caso del usuario: cambiar la plantilla de una pieza ya publicada se rechaza."""
    pub = _publicada(entorno)
    with pytest.raises(PiezaPublicadaInmutable):
        repos.actualizar_publicacion(pub["id"], {"plantilla_diseno_id": "pl-otra"})


def test_publicada_no_admite_cambio_de_copy_ni_imagen(entorno):
    pub = _publicada(entorno)
    with pytest.raises(PiezaPublicadaInmutable):
        repos.actualizar_publicacion(pub["id"], {"contenido": "Copy reescrito"})
    with pytest.raises(PiezaPublicadaInmutable):
        repos.actualizar_publicacion(pub["id"], {"imagen": "render/otra.png"})


def test_publicada_inmutable_por_contenido_plataforma(entorno):
    """El otro mutador (`actualizar_contenido_plataforma`, usado por edición de copy/imagen)
    también respeta la inmutabilidad."""
    pub = _publicada(entorno)
    with pytest.raises(PiezaPublicadaInmutable):
        repos.actualizar_contenido_plataforma(pub["id"], {"copy": "otra cosa"})


def test_publicada_permite_escrituras_operativas(entorno):
    """estado / id_post_metricool / preparado_en NO son contenido: el barrido y la
    reconciliación siguen pudiendo escribirlos en una pieza ya publicada."""
    pub = _publicada(entorno)
    actualizada = repos.actualizar_publicacion(
        pub["id"], {"id_post_metricool": "mc-123", "preparado_en": "2026-06-15T12:00:00"}
    )
    assert actualizada is not None
    assert actualizada["id_post_metricool"] == "mc-123"


def test_publicada_reescribir_mismo_valor_es_idempotente(entorno):
    """Re-escribir un campo congelado con el MISMO valor no rompe (comparación por valor)."""
    pub = repos.crear_publicacion(
        "unotv", "x", titulo="T", contenido="C", estado="programado",
        fecha_programada="2026-01-01T10:00",
    )
    repos.actualizar_publicacion(pub["id"], {"plantilla_diseno_id": "pl-1"})  # aún editable
    repos.actualizar_publicacion(pub["id"], {"estado": "publicado"})  # transición OK
    # Mismo valor de plantilla en una pieza ya publicada: no cambia nada -> no lanza.
    actualizada = repos.actualizar_publicacion(pub["id"], {"plantilla_diseno_id": "pl-1"})
    assert actualizada is not None


def test_publicada_se_puede_borrar(entorno):
    """Inmutable NO es indeleble: se permite borrar para limpiar errores."""
    pub = _publicada(entorno)
    assert repos.borrar_publicacion(pub["id"]) is True


def test_no_publicada_si_admite_edicion(entorno):
    """Una pieza que NO está publicada se edita con normalidad."""
    pub = repos.crear_publicacion(
        "unotv", "x", titulo="T", contenido="C", estado="programado",
        fecha_programada="2026-01-01T10:00",
    )
    actualizada = repos.actualizar_publicacion(pub["id"], {"plantilla_diseno_id": "pl-x"})
    assert actualizada is not None
    assert actualizada["plantilla_diseno_id"] == "pl-x"


def test_transicion_a_publicado_no_se_bloquea(entorno):
    """Marcar una pieza como `publicado` (incluso sellando su fecha real en el MISMO write) se
    permite: en el momento de la escritura la pieza AÚN no está publicada. Después ya es inmutable."""
    pub = repos.crear_publicacion(
        "unotv", "x", titulo="T", contenido="C", estado="programado",
        fecha_programada="2026-01-01T10:00",
    )
    actualizada = repos.actualizar_publicacion(
        pub["id"], {"estado": "publicado", "fecha_programada": "2026-01-01T10:05:00"}
    )
    assert actualizada is not None
    assert actualizada["estado"] == "publicado"
    # Y a partir de aquí, inmutable.
    with pytest.raises(PiezaPublicadaInmutable):
        repos.actualizar_publicacion(pub["id"], {"plantilla_diseno_id": "pl-z"})
