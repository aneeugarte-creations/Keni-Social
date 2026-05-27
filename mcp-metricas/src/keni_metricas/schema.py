"""Esquema unificado de metricas (normaliza todas las plataformas a la misma forma)."""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum

from keni_shared.metricas import engagement_pct
from pydantic import BaseModel, Field


class Plataforma(StrEnum):
    facebook = "facebook"
    instagram = "instagram"
    x = "x"
    tiktok = "tiktok"
    youtube = "youtube"


# Plataformas que exponen "alcance" (usuarios únicos). Solo Meta (FB/IG) lo da
# en su API de insights; YouTube/X/TikTok NO lo miden y lo reportan AUSENTE
# (None). Fuente única de esta clasificación (#138).
PLATAFORMAS_CON_ALCANCE: frozenset[Plataforma] = frozenset(
    {Plataforma.facebook, Plataforma.instagram}
)


class Cuenta(BaseModel):
    """Una marca/cuenta y las plataformas en las que tiene presencia configurada."""

    id: str
    nombre: str
    plataformas: list[Plataforma] = Field(default_factory=list)


class MetricaPlataforma(BaseModel):
    """Métricas normalizadas de UNA plataforma para un periodo.

    Semántica de agregación entre plataformas (#138) — qué se puede sumar y qué no:

    - `interacciones` es la ÚNICA magnitud comparable entre redes: es la misma
      cuenta (likes + comentarios + compartidos + …) en todas. Se AGREGA.
    - `visualizaciones` NO es homogénea entre redes: agrupa conceptos distintos
      (impresiones en FB/IG/X, reproducciones en YouTube/TikTok). Tiene sentido
      por plataforma, pero su suma cruzada es "peras con manzanas". El agregador
      la suma solo como total informativo SEGREGADO, y NO la usa como base de un
      engagement global (ver `agregador.py`).
    - `alcance` (usuarios únicos alcanzados) solo lo expone Meta (FB/IG). En
      YouTube/X/TikTok NO existe: se representa AUSENTE (`None`), nunca 0. Un 0
      sería un dato falso; `None` dice "esta plataforma no mide alcance" y queda
      EXCLUIDO del agregado en vez de hundir el total.
    - `engagement_pct` se calcula contra la base propia de cada plataforma, que
      sí es coherente dentro de ella.
    """

    plataforma: Plataforma
    visualizaciones: int
    # alcance (usuarios únicos): None = la plataforma NO lo mide (YouTube/X/TikTok),
    # distinto de 0 (Meta lo mide y dio 0). Ver docstring de la clase.
    alcance: int | None = None
    interacciones: int
    engagement_pct: float


def agregar_alcance(por_plataforma: list[MetricaPlataforma]) -> int | None:
    """Suma el alcance SOLO de las plataformas que lo miden (#138).

    Las plataformas que no miden alcance lo reportan AUSENTE (`None`) y quedan
    excluidas del total. Devuelve `None` si NINGUNA plataforma lo mide (ausencia
    de dato), para no inventar un 0 que hundiría el agregado.
    """
    valores = [m.alcance for m in por_plataforma if m.alcance is not None]
    return sum(valores) if valores else None


def agregar_engagement(
    por_plataforma: list[MetricaPlataforma], interacciones: int
) -> float | None:
    """Engagement global defendible: NO divide sobre bases de visualización
    heterogéneas (#138).

    - 0 plataformas → `None` (no hay nada que medir).
    - 1 plataforma  → su engagement (base homogénea, coherente).
    - >1 plataforma → `None`: sumar impresiones de unas con reproducciones de
      otras y dividir las interacciones entre ese total da un número sin
      significado. El engagement coherente vive por plataforma en `por_plataforma`.
    """
    if not por_plataforma:
        return None
    if len(por_plataforma) == 1:
        return engagement_pct(interacciones, por_plataforma[0].visualizaciones)
    return None


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
    """Resumen agregado de una cuenta sobre todas sus plataformas.

    Sobre la agregación entre plataformas heterogéneas (#138):

    - `visualizaciones`: suma de las visualizaciones de cada plataforma. Es un
      total INFORMATIVO (mezcla impresiones y reproducciones); el desglose real
      vive en `por_plataforma`. NO se usa como base de `engagement_pct` global.
    - `alcance`: suma SOLO de las plataformas que miden alcance (Meta). Es `None`
      si NINGUNA plataforma del resumen lo mide: ausencia de dato, no 0.
    - `engagement_pct`: `None` cuando el resumen combina plataformas con bases de
      visualización heterogéneas (no se divide sobre bases incomparables). Con una
      sola plataforma se conserva su engagement, que sí es coherente.
    """

    cuenta: str
    rango: str
    periodo: Periodo
    visualizaciones: int
    # alcance: None = ninguna plataforma del resumen mide alcance (no es 0 real).
    alcance: int | None = None
    interacciones: int
    # engagement_pct: None = no es comparable (bases de visualización heterogéneas).
    engagement_pct: float | None = None
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

# Rangos RODANTES: ventana de N dias que TERMINA hoy (incluido). El mapa da los
# dias de cada uno; `resolver_rango` los resuelve como (hoy-(N-1), hoy).
RANGOS_DIAS: dict[str, int] = {"semana": 7, "7d": 7, "mes": 30, "30d": 30}

# Rango ANCLADO al calendario: la ultima semana natural CERRADA (lunes->domingo
# inmediatamente anterior a la semana en curso, domingo incluido). A diferencia de
# "semana" (rodante, termina hoy), este NO depende del dia en que se corra: el
# lunes a las 10 da exactamente la semana que acaba de cerrar. Lo usa el reporte
# del lunes (issue #141). Son tambien 7 dias, pero su ventana no es relativa a hoy.
RANGO_SEMANA_CERRADA = "semana_cerrada"

# Todos los rangos validos como entrada (rodantes + anclados). El reporte de
# deportes y la API los validan contra este conjunto.
RANGOS_VALIDOS: tuple[str, ...] = (*RANGOS_DIAS.keys(), RANGO_SEMANA_CERRADA)


def semana_cerrada(hoy: date | None = None) -> tuple[date, date]:
    """Lunes->domingo de la ultima semana NATURAL cerrada (domingo incluido).

    Devuelve `(lunes, domingo)` de la semana inmediatamente anterior a la que
    contiene `hoy`. Ejemplo: cualquier dia de la semana del 25-31 may 2026 ->
    (2026-05-18, 2026-05-24). Independiente del dia en que se corra (issue #141).
    """
    hoy = hoy or date.today()
    lunes_de_esta_semana = hoy - timedelta(days=hoy.weekday())  # lunes=0 .. domingo=6
    domingo_cerrado = lunes_de_esta_semana - timedelta(days=1)
    lunes_cerrado = domingo_cerrado - timedelta(days=6)
    return lunes_cerrado, domingo_cerrado


def resolver_rango(rango: str, hoy: date | None = None) -> tuple[date, date, int]:
    """Convierte un rango en `(desde, hasta, dias)`.

    Rangos rodantes ('semana'|'7d'|'mes'|'30d'): ventana de N dias que termina
    HOY. Rango anclado ('semana_cerrada'): la ultima semana natural cerrada
    (lunes->domingo, domingo incluido), independiente del dia en que se corra.
    """
    hoy = hoy or date.today()
    clave = (rango or "").lower().strip()
    if clave == RANGO_SEMANA_CERRADA:
        desde, hasta = semana_cerrada(hoy)
        return desde, hasta, (hasta - desde).days + 1
    dias = RANGOS_DIAS.get(clave)
    if dias is None:
        validos = ", ".join(sorted(RANGOS_VALIDOS))
        raise ValueError(f"Rango no valido: {rango!r}. Usa uno de: {validos}.")
    return hoy - timedelta(days=dias - 1), hoy, dias
