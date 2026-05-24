"""Esquema unificado de metricas (normaliza todas las plataformas a la misma forma)."""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field


class Plataforma(StrEnum):
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


class MotivoOmision(StrEnum):
    """Por que una plataforma configurada NO aporto datos a un resumen."""

    sin_credenciales = "sin_credenciales"  # no hay adaptador (credenciales insuficientes)
    presupuesto_agotado = "presupuesto_agotado"  # se agoto el rate-limit de la plataforma
    error_api = "error_api"  # el adaptador respondio None/[] por fallo de la API


class Cobertura(BaseModel):
    """Que plataformas RESPONDIERON vs. se OMITIERON al armar un resumen.

    Hace explicito, dentro de la respuesta, que los ceros de una plataforma
    omitida no son datos reales. `ok` y `omitidas` son disjuntos y juntos cubren
    todas las plataformas que la cuenta tiene configuradas; `motivo` mapea cada
    plataforma omitida a un `MotivoOmision`.
    """

    ok: list[Plataforma] = Field(default_factory=list)
    omitidas: list[Plataforma] = Field(default_factory=list)
    motivo: dict[str, MotivoOmision] = Field(default_factory=dict)

    @property
    def completa(self) -> bool:
        """True si no se omitio ninguna plataforma configurada."""
        return not self.omitidas


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
    # cobertura: que plataformas respondieron vs. se omitieron (y por que). Opcional
    # para no romper consumidores existentes; las fuentes lo rellenan cuando aplica.
    cobertura: Cobertura | None = None


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
