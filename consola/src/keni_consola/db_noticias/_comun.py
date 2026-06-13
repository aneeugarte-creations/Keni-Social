"""Persistencia — dominio noticias: helpers comunes (JSON de columnas, catálogo de tipos)."""
from __future__ import annotations

from .._db_comun import Any, json


# --- JSON de columnas (serializadores compartidos) ------------------------ #
def _desglose_a_json(valor: Any) -> str:
    """Serializa `score_desglose` para la columna: dict -> JSON; str -> tal cual; resto -> ''."""
    if isinstance(valor, dict):
        try:
            return json.dumps(valor, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""
    return valor if isinstance(valor, str) else ""


def _desglose_a_dict(crudo: Any) -> dict[str, Any]:
    """Deserializa `score_desglose` (JSON) a dict; {} si está vacío o malformado. Best-effort."""
    try:
        datos = json.loads(crudo or "{}")
    except (ValueError, TypeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _detalle_fuentes_a_json(valor: Any) -> str:
    """Serializa `fuentes_detalle` para la columna: lista -> JSON; str -> tal cual; resto -> ''."""
    if isinstance(valor, list):
        try:
            return json.dumps(valor, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""
    return valor if isinstance(valor, str) else ""


def _detalle_fuentes_a_lista(crudo: Any) -> list[dict[str, Any]]:
    """Deserializa `fuentes_detalle` (JSON) a lista de dicts; [] si vacío o malformado."""
    try:
        datos = json.loads(crudo or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(datos, list):
        return []
    return [d for d in datos if isinstance(d, dict)]


# --- Tipos de fuente (catálogo) ------------------------------------------- #
# `fuentes_rss` es la ÚNICA tabla de fuentes (la fuente de verdad del motor de ingesta); la
# API la presenta como catálogo de tipo 'rss'. Esta allowlist deja la puerta a los tipos de
# aportación (idea/interna) que hoy producen items del tablero, no filas de fuente.
_TIPOS_FUENTE: tuple[str, ...] = ("rss", "idea", "interna")
