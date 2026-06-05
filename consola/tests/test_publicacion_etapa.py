"""La etapa IA serializada refleja el CONTENIDO real, no los flags `falta_*` almacenados.

PURO (sin DB ni red): `publicacion_a_dict` solo transforma un dict usando catálogos y lógica
pura. El bug que cubre: los flags `falta_copy`/`falta_imagen` se desincronizan del contenido
(la tubería rellena copy/imagen sin tocar el flag), y el label del feed mentía.
"""

from __future__ import annotations

from typing import Any

from keni_consola.dominio.publicaciones import publicacion_a_dict


def _pub(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "p1",
        "titulo": "T",
        "marca": "unotv",
        "red": "x",
        "contenido": "",
        "estado": "pendiente",
        "veredicto": "",
        "origen": "pipeline",
        "fecha_creacion": "",
        "fecha_actualizacion": "",
        "fecha_programada": "",
    }
    base.update(kw)
    return base


def test_etapa_ignora_flag_copy_desincronizado():
    # Flag dice "falta copy" (stale) PERO el copy ya está: la etapa NO debe ser "generando_copy".
    # Pieza CON copy-in (lleva imagen) pero sin foto -> generando_arte (falta la foto real).
    d = publicacion_a_dict(
        _pub(contenido="Ya hay copy", copy_in="TITULAR", imagen="placa.png", falta_copy=True)
    )
    assert d["etapa_ia"] == "generando_arte"  # hay copy, lleva imagen, falta la foto real


def test_etapa_generando_copy_solo_si_no_hay_copy():
    d = publicacion_a_dict(_pub(contenido="", copy_in="TITULAR"))
    assert d["etapa_ia"] == "generando_copy"


def test_pieza_sin_foto_no_esta_lista_aunque_no_lleve_copy_in():
    # TODO post necesita una FOTO real: sin foto (ni copy-in) NO está lista -> "Falta imagen".
    # (Antes una pieza de solo texto se daba por lista sin foto; ya no.)
    d = publicacion_a_dict(_pub(contenido="Solo texto", copy_in="", imagen="", foto=""))
    assert d["etapa_ia"] == "generando_arte"


def test_pieza_sin_marca_con_imagen_subida_esta_lista():
    # En piezas SIN marca/placa, la imagen subida (bespoke) SÍ cuenta como foto real -> lista.
    d = publicacion_a_dict(_pub(marca="", contenido="copy", copy_in="", imagen="subida.png", foto=""))
    assert d["etapa_ia"] == "lista_para_revisar"


def test_placa_sola_no_cuenta_como_imagen():
    # La PLACA (campo imagen) es solo plantilla: con copy-in pero sin foto real -> falta imagen.
    d = publicacion_a_dict(_pub(contenido="copy", copy_in="TITULAR", imagen="placa.png", foto=""))
    assert d["etapa_ia"] == "generando_arte"


def test_con_foto_real_esta_lista():
    d = publicacion_a_dict(_pub(contenido="copy", copy_in="TITULAR", imagen="placa.png", foto="bg.png"))
    assert d["etapa_ia"] == "lista_para_revisar"


def test_etapa_en_revision_manda_sobre_contenido():
    d = publicacion_a_dict(_pub(contenido="copy", copy_in="TITULAR", estado="en_revision"))
    assert d["etapa_ia"] == "lista_para_revisar"
