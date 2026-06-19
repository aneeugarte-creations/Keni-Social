"""Catálogo de fuentes RSS sugeridas (inicial de onboarding), cargado desde datos.

El catálogo es DATOS, no lógica. El equipo da de alta las fuentes desde la UI
(`POST /api/rss/fuentes`), que acepta cualquier categoría de `CATEGORIAS_VALIDAS`.

Contrato de cada preset (04-fuentes-externas.md): id, nombre, url, categoria, marca_sugerida,
linea_sugerida, idioma, region, descripcion. Opcional: `intervalo_min`, `peso`.

API pública (módulo PURO: sin red, sin BD):
  - `listar_presets(categoria=None, marca=None)` -> list[dict]
  - `categorias()` -> list[str]  (las presentes en la inicial, en orden de aparición)
  - `obtener_preset(id)` -> dict | None
  - `CATEGORIAS_VALIDAS` -> tuple[str, ...]  (vocabulario editorial canónico, DESACOPLADO de la
    inicial: el equipo puede crear una fuente `gaming` aunque la inicial no traiga ninguna).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Vocabulario editorial canónico de categorías. Manda la cadencia de sondeo del motor
# (`config_noticias.ingesta_intervalo_categoria`) y la validación al crear fuentes a mano
# (`api.rss`). DESACOPLADO de las categorías presentes en la inicial: que la inicial no traiga
# una categoría no debe impedir que el equipo cree fuentes en ella. 'breaking' (la cadencia más
# agresiva) se añade en la capa API, no es de catálogo.
CATEGORIAS_VALIDAS: tuple[str, ...] = (
    # Redacción de noticias (marcas tipo UnoTV / Claro Sports / Nación Gamer).
    "mx",
    "regional",
    "internacional",
    "entretenimiento",
    "deportes",
    "futbol",
    "motor",
    "otros-deportes",
    "gaming",
    "negocios",
    "tendencias",
    # Temáticas de misión (Fundación): el contenido se clasifica por el pilar del que habla,
    # no por geografía. Cadencia evergreen (~30 min): son temas de cambio lento, no breaking.
    "ciencia-tech",
    "salud",
    "medio-ambiente",
    "cultura",
    "educacion",
    "impacto-social",
)

_RUTA_INICIAL = Path(__file__).resolve().parent / "fuentes_presets.json"


def _cargar() -> list[dict[str, Any]]:
    """Lee la inicial del paquete (`fuentes_presets.json`). Falla de forma visible si está corrupta."""
    datos = json.loads(_RUTA_INICIAL.read_text(encoding="utf-8"))
    if not isinstance(datos, list):
        raise ValueError("fuentes_presets.json debe ser una lista de presets")
    return datos


_PRESETS: list[dict[str, Any]] = _cargar()

# Índice por id para búsqueda O(1).
_PRESETS_POR_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in _PRESETS}

# Orden de presentación de categorías (de aparición en la inicial).
_CATEGORIAS: list[str] = []
_vistas: set[str] = set()
for _p in _PRESETS:
    _cat = _p["categoria"]
    if _cat not in _vistas:
        _CATEGORIAS.append(_cat)
        _vistas.add(_cat)
del _p, _cat, _vistas


# --------------------------------------------------------------------------- #
# API pública                                                                   #
# --------------------------------------------------------------------------- #


def listar_presets(
    categoria: str | None = None, marca: str | None = None
) -> list[dict[str, Any]]:
    """Lista de presets del catálogo, opcionalmente filtrada por `categoria` y `marca`.

    Filtro de `marca` (conservador, son sugerencias de catálogo): cuando se pasa una marca, se
    ocultan SOLO los presets cuya `marca_sugerida` declara OTRA marca; los presets sin marca
    sugerida (catálogo genérico) siempre se muestran. Con `marca=None` se devuelven todos.

    Devuelve una copia superficial de cada preset (sin mutar el catálogo).
    """
    presets = _PRESETS
    if categoria is not None:
        presets = [p for p in presets if p["categoria"] == categoria]
    if marca:
        presets = [
            p
            for p in presets
            if not (p.get("marca_sugerida") or "")
            or (p.get("marca_sugerida") or "") == marca
        ]
    return [dict(p) for p in presets]


def categorias() -> list[str]:
    """Categorías presentes en la inicial, en orden de aparición."""
    return list(_CATEGORIAS)


def obtener_preset(preset_id: str) -> dict[str, Any] | None:
    """Devuelve el preset por id, o None si no existe."""
    p = _PRESETS_POR_ID.get(preset_id)
    return dict(p) if p is not None else None
