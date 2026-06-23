"""Bloqueo de imagen de STOCK sin licencia: nunca publicable hasta autorizar.

PURO (sin DB ni red): cubre el criterio único `dominio.licencia_imagen` y su efecto en la
derivación de "Falta imagen" (`dominio.piezas`), que es lo que mantiene la pieza fuera de
`programado`/`publicado` y con el badge activo mientras la foto sea stock no autorizada.
"""

from __future__ import annotations

from typing import Any

from keni_consola.dominio import licencia_imagen
from keni_consola.dominio.piezas import flags_falta_de_contenido, pieza_a_dict


def _pub(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "p1",
        "titulo": "T",
        "marca": "unotv",
        "red": "x",
        "contenido": "",
        "estado": "pendiente",
        "revision": "",
        "origen": "pipeline",
        "fecha_creacion": "",
        "fecha_actualizacion": "",
        "fecha_programada": "",
    }
    base.update(kw)
    return base


# --- es_stock_sin_autorizar (criterio único) -------------------------------- #


def test_stock_sin_autorizar_es_true():
    assert licencia_imagen.es_stock_sin_autorizar(
        {"imagen_origen": "stock", "imagen_autorizada": False}
    )


def test_stock_autorizado_no_bloquea():
    assert not licencia_imagen.es_stock_sin_autorizar(
        {"imagen_origen": "stock", "imagen_autorizada": True}
    )


def test_no_stock_nunca_bloquea():
    # Una imagen propia/IA/galería publica como siempre, autorizada o no.
    assert not licencia_imagen.es_stock_sin_autorizar(
        {"imagen_origen": "ia", "imagen_autorizada": False}
    )
    assert not licencia_imagen.es_stock_sin_autorizar(
        {"imagen_origen": "", "imagen_autorizada": False}
    )


def test_pieza_vacia_no_bloquea():
    assert not licencia_imagen.es_stock_sin_autorizar(None)
    assert not licencia_imagen.es_stock_sin_autorizar({})


def test_licenciada_nunca_bloquea_es_publicable():
    # Una foto LICENCIADA (AFP) tiene derechos: publicable directa, sin la autorización del stock.
    licenciada = {"imagen_origen": licencia_imagen.ORIGEN_LICENCIADA, "imagen_autorizada": True}
    assert not licencia_imagen.es_stock_sin_autorizar(licenciada)
    assert not licencia_imagen.bloquea_estado(licenciada, "programado")
    assert not licencia_imagen.bloquea_estado(licenciada, "publicado")


# --- bloquea_estado (solo programado/publicado) ----------------------------- #


def test_bloquea_solo_estados_publicables():
    sin_licencia = {"imagen_origen": "stock", "imagen_autorizada": False}
    assert licencia_imagen.bloquea_estado(sin_licencia, "programado")
    assert licencia_imagen.bloquea_estado(sin_licencia, "publicado")
    # Mover a borrador / en revisión NO se bloquea (la foto de stock vive ahí como ayuda visual).
    assert not licencia_imagen.bloquea_estado(sin_licencia, "borrador")
    assert not licencia_imagen.bloquea_estado(sin_licencia, "en_revision")
    assert not licencia_imagen.bloquea_estado(sin_licencia, None)


def test_no_bloquea_si_autorizada():
    ok = {"imagen_origen": "stock", "imagen_autorizada": True}
    assert not licencia_imagen.bloquea_estado(ok, "programado")
    assert not licencia_imagen.bloquea_estado(ok, "publicado")


# --- efecto en "Falta imagen" (dominio.piezas) ------------------------------ #


def test_stock_sin_autorizar_mantiene_falta_imagen():
    # Aunque la pieza tenga una `foto` adjunta, si es stock sin autorizar NO cuenta como imagen
    # real: sigue "Falta imagen" y no avanza/publica.
    pub = _pub(foto="stock123.jpg", imagen_origen="stock", imagen_autorizada=False)
    assert flags_falta_de_contenido(pub)["falta_imagen"] is True


def test_stock_autorizado_completa_la_imagen():
    pub = _pub(foto="stock123.jpg", imagen_origen="stock", imagen_autorizada=True)
    assert flags_falta_de_contenido(pub)["falta_imagen"] is False


def test_etapa_ia_de_stock_sin_autorizar_es_generando_arte():
    # La etapa serializada (la que prefiere el feed) mantiene "Falta imagen" para stock no autorizado.
    d = pieza_a_dict(
        _pub(
            estado="en_revision",
            contenido="copy #gol",
            copy_in="TITULAR",
            foto="stock123.jpg",
            imagen_origen="stock",
            imagen_autorizada=False,
        )
    )
    assert d["etapa_ia"] == "generando_arte"
    assert d["imagen_origen"] == "stock"
    assert d["imagen_autorizada"] is False
