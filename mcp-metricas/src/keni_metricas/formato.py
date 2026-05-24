"""Helpers de formato compartidos entre el reporte (Markdown) y el dashboard (HTML).

Centraliza los datos/strings comunes que estaban duplicados en `reporte.py` y
`dashboard.py` (DRY): el signo de un porcentaje, el mapa de motivos de omision y
la lista de partes `plataforma (motivo)` de una cobertura parcial. El render
final (Markdown vs. HTML) se queda en cada modulo; aqui solo viven los datos.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schema import Cobertura

# Etiquetas legibles para los motivos de omision de cobertura.
_MOTIVO_TEXTO: dict[str, str] = {
    "sin_credenciales": "sin credenciales",
    "presupuesto_agotado": "presupuesto agotado",
    "error_api": "error de API",
}


def signo(pct: float) -> str:
    """Devuelve el porcentaje con signo explicito (+/-)."""
    return f"+{pct}" if pct > 0 else f"{pct}"


def _cobertura_dict(cob: Cobertura | Mapping | None) -> dict | None:
    """Normaliza una `Cobertura` (modelo o dict) a un dict simple, o None."""
    if cob is None:
        return None
    if isinstance(cob, Mapping):
        return dict(cob)
    # Modelo Pydantic Cobertura -> dict JSON-serializable.
    return cob.model_dump(mode="json")


def partes_cobertura(
    cob: Cobertura | Mapping | None,
    etiqueta: Mapping[str, str] | None = None,
) -> list[str] | None:
    """Lista de partes `plataforma (motivo)` de una cobertura parcial.

    Devuelve None si respondio todo (o no aplica). `etiqueta` mapea opcionalmente
    el id de plataforma a un nombre legible (p. ej. el dashboard usa "Facebook"
    en vez de "facebook"); si se omite, se usa el id tal cual. El render final
    (Markdown vs. HTML) se construye en cada modulo a partir de estas partes.
    """
    d = _cobertura_dict(cob)
    if not d or not d.get("omitidas"):
        return None
    motivo = d.get("motivo") or {}
    etiqueta = etiqueta or {}
    partes = []
    for p in d["omitidas"]:
        nombre = etiqueta.get(p, p)
        texto = _MOTIVO_TEXTO.get(motivo.get(p, ""), motivo.get(p, "?"))
        partes.append(f"{nombre} ({texto})")
    return partes
