"""Modelos (`TypedDict`) del subconjunto estable del contrato `/api/*`.

Cada `TypedDict` describe la forma EXACTA del JSON que emite el handler asociado
(verificado contra el handler y sus tests). Son solo tipos: no se instancian ni
validan en runtime; existen para derivar el TypeScript del frontend y para que el
guard detecte divergencias. Ver el docstring del paquete.

Convencion de campos OPCIONALES: se modelan con `NotRequired[...]` (clave que
puede no venir). Convencion de NULABLES: `X | None` (la clave viene pero su valor
puede ser `null`). Las dos cosas son distintas y se respetan tal cual en el TS.

El orden de `MODELOS` (abajo) fija el orden en que aparecen las interfaces en el
`types.gen.ts`, para que la generacion sea estable y el diff sea minimo.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

# --------------------------------------------------------------------------- #
# Estado (autodiagnostico del sistema) — api/estado.py                         #
# --------------------------------------------------------------------------- #

NivelEstado = Literal["ok", "aviso", "error"]


class ResultadoEstado(TypedDict):
    estado: NivelEstado
    nombre: str
    detalle: str
    icono: str


class RespuestaEstado(TypedDict):
    resultados: list[ResultadoEstado]
    resumen: str
    siguiente_paso: str


# --------------------------------------------------------------------------- #
# Configuracion — api/config.py                                                #
# --------------------------------------------------------------------------- #


class MarcaDisponible(TypedDict):
    id: str
    nombre: str


class CredencialesPresentes(TypedDict):
    meta: bool
    youtube: bool
    x: bool
    tiktok: bool


class RespuestaConfig(TypedDict):
    fuente: str
    fuentes_validas: list[str]
    marcas: list[str]
    marcas_disponibles: list[MarcaDisponible]
    credenciales_presentes: CredencialesPresentes


class CuerpoGuardarConfig(TypedDict):
    fuente: str
    marcas: list[str]


# --------------------------------------------------------------------------- #
# Limites de caracteres por red — api/limites.py / limites_plataforma.py       #
# --------------------------------------------------------------------------- #


class LimiteRed(TypedDict):
    """Limite de caracteres canonico de una red (fuente unica, `GET /api/limites`).

    `limite` es `null` si la red no tiene tope tecnico practico (Facebook/YouTube).
    """

    id: str
    nombre: str
    limite: int | None


class RespuestaLimites(TypedDict):
    """Respuesta de `GET /api/limites`: los limites por red, en orden fijo."""

    limites: list[LimiteRed]


# --------------------------------------------------------------------------- #
# Metricas — api/metricas.py                                                   #
# --------------------------------------------------------------------------- #


class RangoMetrica(TypedDict):
    id: str
    etiqueta: str


class OpcionesMetricas(TypedDict):
    marcas: list[MarcaDisponible]
    rangos: list[RangoMetrica]


class TotalMetricas(TypedDict):
    visualizaciones: int
    alcance: int
    interacciones: int
    engagement_pct: float


class CuentaMetrica(TypedDict):
    marca_id: str
    marca: str
    visualizaciones: int
    alcance: int
    interacciones: int
    engagement_pct: float


class ReporteMetricas(TypedDict):
    """Respuesta de `GET /api/metricas/reporte`."""

    rango: str
    etiqueta_rango: str
    marca: str
    # Procedencia: "muestra" (ficticios) o el nombre de la fuente real (p. ej.
    # "meta"). La UI pinta un badge de advertencia con esto.
    fuente: str
    total: TotalMetricas
    cuentas: list[CuentaMetrica]


class ComparativaMetrica(TypedDict):
    metrica: str
    a: float
    b: float
    diferencia: float
    variacion_pct: float


class ComparativaPorMarca(TypedDict):
    marca_id: str
    marca: str
    comparativa: list[ComparativaMetrica]


class TotalComparativa(TypedDict):
    metricas: list[ComparativaMetrica]


class CompararMetricas(TypedDict):
    """Respuesta de `GET /api/metricas/comparar`: comparativa A vs B."""

    marca: str
    rango_a: str
    rango_b: str
    etiqueta_a: str
    etiqueta_b: str
    # Procedencia de los datos comparados ("muestra" = ficticios; "muestra" si
    # cualquiera de los dos reportes lo es).
    fuente: str
    total: TotalComparativa
    por_marca: list[ComparativaPorMarca]


# --------------------------------------------------------------------------- #
# Respuestas genericas comunes                                                 #
# --------------------------------------------------------------------------- #


class RespuestaMensaje(TypedDict):
    mensaje: str


class ErrorApi(TypedDict):
    """Forma de error que devuelve el backend (uno u otro campo, en espanol)."""

    error: NotRequired[str]
    mensaje: NotRequired[str]


# Orden estable de las interfaces en el `types.gen.ts` generado. Cada `TypedDict`
# se exporta como `interface`; los `Literal` (p. ej. `NivelEstado`) viajan inline
# en los campos que los usan y NO necesitan listarse aqui.
MODELOS = [
    ResultadoEstado,
    RespuestaEstado,
    MarcaDisponible,
    CredencialesPresentes,
    RespuestaConfig,
    CuerpoGuardarConfig,
    LimiteRed,
    RespuestaLimites,
    RangoMetrica,
    OpcionesMetricas,
    TotalMetricas,
    CuentaMetrica,
    ReporteMetricas,
    ComparativaMetrica,
    ComparativaPorMarca,
    TotalComparativa,
    CompararMetricas,
    RespuestaMensaje,
    ErrorApi,
]
