"""Esquema unificado de metricas (normaliza todas las plataformas a la misma forma)."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum

from pydantic import BaseModel, Field


class Plataforma(str, Enum):
    facebook = "facebook"
    instagram = "instagram"
    x = "x"
    tiktok = "tiktok"
    youtube = "youtube"


class Cuenta(BaseModel):
    """Una marca/cuenta y las plataformas en las que tiene presencia configurada."""

    id: str
    nombre: str
    plataformas: list[Plataforma] = Field(default_factory=list)


class MetricaPlataforma(BaseModel):
    plataforma: Plataforma
    visualizaciones: int
    alcance: int
    interacciones: int
    engagement_pct: float


class Periodo(BaseModel):
    desde: date
    hasta: date


class ResumenMetricas(BaseModel):
    cuenta: str
    rango: str
    periodo: Periodo
    visualizaciones: int
    alcance: int
    interacciones: int
    engagement_pct: float
    seguidores_netos: int
    variacion_vs_anterior: dict[str, float] = Field(default_factory=dict)
    por_plataforma: list[MetricaPlataforma] = Field(default_factory=list)
    fuente: str = "desconocida"


class Pieza(BaseModel):
    id: str
    plataforma: Plataforma
    titulo: str
    publicado: date
    visualizaciones: int
    interacciones: int
    engagement_pct: float
    url: str | None = None


# --- Rangos -----------------------------------------------------------------

RANGOS_DIAS: dict[str, int] = {"semana": 7, "7d": 7, "mes": 30, "30d": 30}


def resolver_rango(rango: str, hoy: date | None = None) -> tuple[date, date, int]:
    """Convierte un rango ('semana'|'mes'|'7d'|'30d') en (desde, hasta, dias)."""
    hoy = hoy or date.today()
    dias = RANGOS_DIAS.get((rango or "").lower().strip())
    if dias is None:
        validos = ", ".join(sorted(set(RANGOS_DIAS)))
        raise ValueError(f"Rango no valido: {rango!r}. Usa uno de: {validos}.")
    return hoy - timedelta(days=dias - 1), hoy, dias
