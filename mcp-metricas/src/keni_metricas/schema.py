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


class MetricaPieza(BaseModel):
    """Rendimiento REAL de UNA pieza ya publicada, identificada por su id de Metricool.

    A diferencia de `Pieza` (que describe una de las "mejores piezas" de un periodo,
    descubierta desde la lista de posts), esto es el rendimiento de un post CONCRETO
    que el equipo ya programo/publico desde la Consola: se busca por `id_post_metricool`
    (el id que devolvio el scheduler de Metricool al programar) para pintarlo en la
    tarjeta del tablero. `encontrado=False` cuando Metricool aun no tiene datos del
    post (recien publicado) o el id no aparece: la UI muestra "sin datos todavia" en
    vez de ceros falsos.
    """

    id_post: str
    plataforma: Plataforma
    encontrado: bool = False
    visualizaciones: int = 0
    interacciones: int = 0
    engagement_pct: float = 0.0
    url: str | None = None
    publicado: date | None = None
    fuente: str = "desconocida"


class EstadisticasNumericas(BaseModel):
    """Resumen estadistico de una serie de valores (engagement o visualizaciones).

    Todos los campos son `None` si no hay datos suficientes (n=0; la desviacion
    necesita n>=2). Asi la UI distingue "0" de "sin dato".
    """

    n: int
    media: float | None = None
    mediana: float | None = None
    p25: float | None = None
    p75: float | None = None
    minimo: float | None = None
    maximo: float | None = None
    desviacion: float | None = None


class DistribucionBucket(BaseModel):
    """Un tramo del histograma de engagement (cuantas piezas caen en [inicio, fin))."""

    etiqueta: str
    inicio: float
    # fin: None = tramo abierto superior ("10%+").
    fin: float | None = None
    n: int


class AnaliticaPiezas(BaseModel):
    """Analitica de las piezas/videos de un periodo: estadisticas + top/peores + distribucion.

    `cuenta` es `None` cuando agrega todas las marcas (tab "Todas"). Coste 0 de API:
    se construye sobre las piezas que `mejores_piezas` ya descarga del periodo.
    """

    cuenta: str | None
    rango: str
    periodo: Periodo
    total: int
    fuente: str = "desconocida"
    engagement: EstadisticasNumericas
    visualizaciones: EstadisticasNumericas
    top: list[Pieza] = Field(default_factory=list)
    peores: list[Pieza] = Field(default_factory=list)
    distribucion: list[DistribucionBucket] = Field(default_factory=list)


class PuntoSerie(BaseModel):
    """Un dia de la serie temporal: totales del dia."""

    fecha: date
    visualizaciones: int
    interacciones: int


class SerieDiaria(BaseModel):
    """Evolucion diaria de un periodo (suma de las cuentas en alcance).

    `puntos` vacio = la fuente activa no expone serie diaria (degradacion honesta).
    """

    cuenta: str | None
    rango: str
    periodo: Periodo
    fuente: str = "desconocida"
    puntos: list[PuntoSerie] = Field(default_factory=list)


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


# Tope de amplitud de un rango personalizado (dias). Acota el coste de API (Metricool
# pagina/serie por dia) y evita consultas absurdas; ~1 año cubre cualquier caso real.
MAX_DIAS_RANGO = 366

# Nombres de mes en es-MX para las etiquetas legibles (indice 1-12).
_MESES_ES: tuple[str, ...] = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_MESES_ABREV_ES: tuple[str, ...] = (
    "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic",
)


def _parsear_mes(token: str) -> tuple[date, date]:
    """`AAAA-MM` -> (primer dia, ultimo dia) de ese mes. Lanza ValueError si no es valido."""
    try:
        anio_s, mes_s = token.split("-")
        anio, mes = int(anio_s), int(mes_s)
        primero = date(anio, mes, 1)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Mes no valido: {token!r}. Usa 'mes:AAAA-MM'.") from e
    # ultimo dia: el dia antes del primero del mes siguiente.
    if mes == 12:
        ultimo = date(anio, 12, 31)
    else:
        ultimo = date(anio, mes + 1, 1) - timedelta(days=1)
    return primero, ultimo


def _parsear_rango_fechas(token: str) -> tuple[date, date]:
    """`AAAA-MM-DD_AAAA-MM-DD` -> (desde, hasta). Valida orden y cap de amplitud."""
    try:
        desde_s, hasta_s = token.split("_")
        desde = date.fromisoformat(desde_s)
        hasta = date.fromisoformat(hasta_s)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Rango no valido: {token!r}. Usa 'rango:AAAA-MM-DD_AAAA-MM-DD'."
        ) from e
    if hasta < desde:
        raise ValueError("Rango invalido: 'hasta' es anterior a 'desde'.")
    if (hasta - desde).days + 1 > MAX_DIAS_RANGO:
        raise ValueError(f"Rango demasiado amplio (maximo {MAX_DIAS_RANGO} dias).")
    return desde, hasta


def resolver_rango(rango: str, hoy: date | None = None) -> tuple[date, date, int]:
    """Convierte un rango en `(desde, hasta, dias)`.

    Acepta:
      - Rangos RODANTES ('semana'|'7d'|'mes'|'30d'): ventana de N dias que termina HOY.
      - Rango ANCLADO ('semana_cerrada'): ultima semana natural cerrada (lunes->domingo).
      - Mes concreto ('mes:AAAA-MM'): primer..ultimo dia de ese mes.
      - Rango personalizado ('rango:AAAA-MM-DD_AAAA-MM-DD'): fechas exactas (cap MAX_DIAS_RANGO).

    Como toda la cadena (fuentes, Metricool, historico) ya trabaja con `desde/hasta`,
    estos tokens fluyen sin tocar nada mas: el token string es tambien la clave de cache.
    """
    hoy = hoy or date.today()
    clave = (rango or "").lower().strip()
    if clave == RANGO_SEMANA_CERRADA:
        desde, hasta = semana_cerrada(hoy)
        return desde, hasta, (hasta - desde).days + 1
    if clave.startswith("mes:"):
        desde, hasta = _parsear_mes(clave[len("mes:"):])
        return desde, hasta, (hasta - desde).days + 1
    if clave.startswith("rango:"):
        desde, hasta = _parsear_rango_fechas(clave[len("rango:"):])
        return desde, hasta, (hasta - desde).days + 1
    dias = RANGOS_DIAS.get(clave)
    if dias is None:
        validos = ", ".join(sorted(RANGOS_VALIDOS))
        raise ValueError(
            f"Rango no valido: {rango!r}. Usa uno de: {validos}, o 'mes:AAAA-MM' / "
            f"'rango:AAAA-MM-DD_AAAA-MM-DD'."
        )
    return hoy - timedelta(days=dias - 1), hoy, dias


# Etiquetas legibles de los presets (las de tokens se calculan al vuelo).
_ETIQUETAS_PRESET: dict[str, str] = {
    "semana": "Última semana",
    "7d": "Últimos 7 días",
    "mes": "Último mes",
    "30d": "Últimos 30 días",
    RANGO_SEMANA_CERRADA: "Semana cerrada",
}


def etiqueta_rango(rango: str) -> str:
    """Etiqueta legible en es-MX de un rango (preset o token mes:/rango:).

    Ejemplos: 'mes:2026-05' -> 'Mayo 2026'; 'rango:2026-05-01_2026-05-31' ->
    '1–31 may 2026'; 'rango:2026-04-28_2026-05-03' -> '28 abr – 3 may 2026'.
    """
    clave = (rango or "").lower().strip()
    if clave.startswith("mes:"):
        primero, _ = _parsear_mes(clave[len("mes:"):])
        return f"{_MESES_ES[primero.month - 1].capitalize()} {primero.year}"
    if clave.startswith("rango:"):
        desde, hasta = _parsear_rango_fechas(clave[len("rango:"):])
        if desde.month == hasta.month and desde.year == hasta.year:
            return f"{desde.day}–{hasta.day} {_MESES_ABREV_ES[desde.month - 1]} {desde.year}"
        if desde.year == hasta.year:
            return (
                f"{desde.day} {_MESES_ABREV_ES[desde.month - 1]} – "
                f"{hasta.day} {_MESES_ABREV_ES[hasta.month - 1]} {desde.year}"
            )
        return (
            f"{desde.day} {_MESES_ABREV_ES[desde.month - 1]} {desde.year} – "
            f"{hasta.day} {_MESES_ABREV_ES[hasta.month - 1]} {hasta.year}"
        )
    return _ETIQUETAS_PRESET.get(clave, rango)
