"""Modelos (`TypedDict`) del subconjunto estable del contrato `/api/*`.

Cada `TypedDict` describe la forma EXACTA del JSON que emite el handler asociado
(verificado contra el handler y sus tests). Son solo tipos: no se instancian ni
validan en runtime; existen para derivar el TypeScript del frontend y para que el
guard detecte divergencias. Ver el docstring del paquete.

Convencion de campos OPCIONALES: se modelan con `NotRequired[...]` (clave que
puede no venir). Convencion de NULABLES: `X | None` (la clave viene pero su valor
puede ser `null`). Las dos cosas son distintas y se respetan tal cual en el TS.

Este paquete agrupa los modelos por DOMINIO en submodulos (`estado`, `limites`,
`metricas`, `publicaciones`, `comercial`, mas `_base` para los tipos
compartidos/auxiliares). Este `__init__` es un BARREL: re-exporta todos los modelos
y mantiene la superficie publica historica (un solo modulo `modelos`).

El orden de `MODELOS` (abajo) fija el orden en que aparecen las interfaces en el
`types.gen.ts`, para que la generacion sea estable y el diff sea minimo.
"""

from __future__ import annotations

# Tipos del `typing` re-exportados para preservar la superficie historica del modulo
# (estaban en su namespace y forman parte del `dir()` estable).
from typing import Literal, NotRequired, TypedDict

from ._base import (
    ErrorApi,
    MarcaDisponible,
    MetricasRun,
    Paginacion,
    RespuestaMensaje,
)
from .estado import (
    NivelEstado,
    RespuestaEstado,
    ResultadoEstado,
)
from .limites import (
    LimiteRed,
    RespuestaLimites,
)
from .metricas import (
    AnalisisDiario,
    AnaliticaPiezas,
    CeldaCrosstab,
    CeldaDesglose,
    CompararMetricas,
    ComparativaMetrica,
    ComparativaPorMarca,
    CorrelacionSeguidores,
    Crosstab,
    CuentaMetrica,
    DesgloseInteracciones,
    DistribucionBucket,
    EstadisticasNumericas,
    EstadoMetricas,
    HistoricoPieza,
    ItemCorrelacion,
    MarcaCobertura,
    MovimientoAnalisis,
    OpcionesMetricas,
    PeriodoMetricas,
    PiezaAnalisis,
    PiezaListado,
    PiezaMetrica,
    PiezaRendimiento,
    PiezasListado,
    PiezasRendimiento,
    PostEstrella,
    PuntoHistorico,
    PuntoSeguidores,
    PuntoSerie,
    RangoMetrica,
    RedCobertura,
    RedMetrica,
    ReporteMetricas,
    SerieSeguidores,
    SiguientePasoAnalisis,
    TendenciaDiaria,
    TotalComparativa,
    TotalMetricas,
    VelocidadPieza,
)
from .publicaciones import (
    EstadoPublicacion,
    EtapaIa,
    Publicacion,
    RespuestaColaAprobacion,
    RespuestaPublicacion,
    RespuestaPublicaciones,
    Revision,
)

__all__ = [
    # Tipos del typing re-exportados.
    "Literal",
    "NotRequired",
    "TypedDict",
    # Estado.
    "NivelEstado",
    "ResultadoEstado",
    "RespuestaEstado",
    # Compartidos.
    "MarcaDisponible",
    # Limites.
    "LimiteRed",
    "RespuestaLimites",
    # Metricas.
    "RangoMetrica",
    "OpcionesMetricas",
    "TotalMetricas",
    "CuentaMetrica",
    "RedMetrica",
    "RedCobertura",
    "MarcaCobertura",
    "ReporteMetricas",
    "ComparativaMetrica",
    "ComparativaPorMarca",
    "TotalComparativa",
    "CompararMetricas",
    "PiezaAnalisis",
    "MovimientoAnalisis",
    "SiguientePasoAnalisis",
    "AnalisisDiario",
    "EstadoMetricas",
    "PeriodoMetricas",
    "EstadisticasNumericas",
    "PiezaMetrica",
    "DistribucionBucket",
    "AnaliticaPiezas",
    "PuntoSerie",
    "TendenciaDiaria",
    "PiezaRendimiento",
    "PiezasRendimiento",
    "PiezaListado",
    "PiezasListado",
    "PuntoHistorico",
    "VelocidadPieza",
    "HistoricoPieza",
    "PuntoSeguidores",
    "SerieSeguidores",
    "CeldaDesglose",
    "DesgloseInteracciones",
    "CeldaCrosstab",
    "Crosstab",
    "PostEstrella",
    "ItemCorrelacion",
    "CorrelacionSeguidores",
    # Compartidos / auxiliares.
    "Paginacion",
    "MetricasRun",
    # Publicaciones.
    "EstadoPublicacion",
    "EtapaIa",
    "Revision",
    "Publicacion",
    "RespuestaPublicaciones",
    "RespuestaPublicacion",
    "RespuestaColaAprobacion",
    # Respuestas genericas.
    "RespuestaMensaje",
    "ErrorApi",
    # Lista ordenada de modelos (orden estable del `types.gen.ts`).
    "MODELOS",
]


# Orden estable de las interfaces en el `types.gen.ts` generado. Cada `TypedDict`
# se exporta como `interface`; los `Literal` (p. ej. `NivelEstado`) viajan inline
# en los campos que los usan y NO necesitan listarse aqui.
MODELOS = [
    ResultadoEstado,
    RespuestaEstado,
    MarcaDisponible,
    LimiteRed,
    RespuestaLimites,
    RangoMetrica,
    OpcionesMetricas,
    TotalMetricas,
    CuentaMetrica,
    RedMetrica,
    RedCobertura,
    MarcaCobertura,
    ReporteMetricas,
    ComparativaMetrica,
    ComparativaPorMarca,
    TotalComparativa,
    CompararMetricas,
    # Análisis diario con narrativa (F6/#146).
    PiezaAnalisis,
    MovimientoAnalisis,
    SiguientePasoAnalisis,
    AnalisisDiario,
    # Estado del refresco de la cache de métricas (botón Actualizar + polling).
    EstadoMetricas,
    # Analítica de piezas (estadísticas + top/peores + distribución) y tendencia diaria.
    PeriodoMetricas,
    EstadisticasNumericas,
    PiezaMetrica,
    DistribucionBucket,
    AnaliticaPiezas,
    PuntoSerie,
    TendenciaDiaria,
    # Drill-down marca -> pieza (rendimiento por pieza publicada).
    PiezaRendimiento,
    PiezasRendimiento,
    # Listado completo de piezas del periodo + histórico por pieza + velocidad.
    PiezaListado,
    PiezasListado,
    PuntoHistorico,
    VelocidadPieza,
    HistoricoPieza,
    # Analíticas R2: seguidores, desglose, crosstab, correlación.
    PuntoSeguidores,
    SerieSeguidores,
    CeldaDesglose,
    DesgloseInteracciones,
    CeldaCrosstab,
    Crosstab,
    PostEstrella,
    ItemCorrelacion,
    CorrelacionSeguidores,
    # Envelope/auxiliares compartidos.
    Paginacion,
    MetricasRun,
    # Publicaciones (#101 ampliacion churn).
    Publicacion,
    RespuestaPublicaciones,
    RespuestaPublicacion,
    # Aprobacion de equipo (#9, Fase 3).
    RespuestaColaAprobacion,
    # Generaciones: DEFERIDAS (ver bloque arriba). Se mantienen a mano en types.ts.
    RespuestaMensaje,
    ErrorApi,
]


# Importar los submodulos enlaza sus nombres como atributos del paquete (`modelos._base`,
# `modelos.metricas`, ...). Se eliminan del namespace para preservar EXACTAMENTE la
# superficie publica historica (cuando `modelos` era un unico fichero): el `dir()` no
# debe ganar nombres de submodulo. Los modelos ya estan re-exportados arriba por nombre.
for _submodulo in ("_base", "config", "estado", "limites", "metricas", "publicaciones"):
    globals().pop(_submodulo, None)
del _submodulo
