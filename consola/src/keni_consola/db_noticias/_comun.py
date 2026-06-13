"""Persistencia — dominio noticias: helpers comunes (JSON de columnas, catálogo de tipos)."""
from __future__ import annotations

from .._db_comun import Any
from .._db_json import a_json_dict, a_json_lista, de_json_dict, de_json_lista


# --- JSON de columnas (serializadores compartidos) ------------------------ #
# Wrappers de dominio sobre `_db_json` (conservan el nombre por sus llamadores en
# `clusters.py` y el re-export de `__init__.py`). Semántica idéntica: dict/lista ->
# JSON `ensure_ascii=False`, str passthrough, neutro vacío ante ausente/malformado.
def _desglose_a_json(valor: Any) -> str:
    """Serializa `score_desglose` para la columna: dict -> JSON; str -> tal cual; resto -> ''."""
    return a_json_dict(valor)


def _desglose_a_dict(crudo: Any) -> dict[str, Any]:
    """Deserializa `score_desglose` (JSON) a dict; {} si está vacío o malformado. Best-effort."""
    return de_json_dict(crudo)


def _detalle_fuentes_a_json(valor: Any) -> str:
    """Serializa `fuentes_detalle` para la columna: lista -> JSON; str -> tal cual; resto -> ''."""
    return a_json_lista(valor)


def _detalle_fuentes_a_lista(crudo: Any) -> list[dict[str, Any]]:
    """Deserializa `fuentes_detalle` (JSON) a lista de dicts; [] si vacío o malformado."""
    return [d for d in de_json_lista(crudo) if isinstance(d, dict)]


# --- Tipos de fuente (catálogo) ------------------------------------------- #
# `fuentes_rss` es la ÚNICA tabla de fuentes (la fuente de verdad del motor de ingesta); la
# API la presenta como catálogo de tipo 'rss'. Esta allowlist deja la puerta a los tipos de
# aportación (idea/interna) que hoy producen items del tablero, no filas de fuente.
_TIPOS_FUENTE: tuple[str, ...] = ("rss", "idea", "interna")
