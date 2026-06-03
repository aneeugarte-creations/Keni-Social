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
    d = publicacion_a_dict(_pub(contenido="Ya hay copy", imagen="", falta_copy=True, falta_imagen=True))
    assert d["etapa_ia"] == "generando_arte"  # hay copy, falta imagen


def test_etapa_generando_copy_solo_si_no_hay_copy():
    d = publicacion_a_dict(_pub(contenido="", imagen="", falta_copy=False))
    assert d["etapa_ia"] == "generando_copy"


def test_etapa_en_revision_manda_sobre_contenido():
    d = publicacion_a_dict(_pub(contenido="copy", imagen="img.png", estado="en_revision"))
    assert d["etapa_ia"] == "lista_para_revisar"
