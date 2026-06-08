"""Comercial — api/comercial.py (_a_dict) + comercial.py.

Procedencia (#124): `fuente`/`es_muestra` marcan cifras de muestra (sinteticas) vs
reales.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

__all__ = [
    "EstadoComercial",
    "MetricaComercial",
    "ActualComercial",
    "SnapshotComercial",
    "PostSeleccionableComercial",
    "RespuestaPostsComercial",
    "PublicacionComercial",
    "RespuestaPublicacionesComercial",
    "RespuestaPublicacionComercial",
    "RespuestaRefrescarComercial",
]

EstadoComercial = Literal["activa", "pausada", "cerrada"]
MetricaComercial = Literal["interacciones", "visualizaciones", "alcance"]


class ActualComercial(TypedDict):
    """Valor actual de una pieza comercial (del ultimo snapshot)."""

    ts: str
    interacciones: int
    visualizaciones: int
    alcance: int
    engagement_pct: float


class SnapshotComercial(TypedDict):
    """Un punto de la serie temporal de una pieza comercial (acumulado).

    Ademas de las metricas "base" (interacciones/visualizaciones/alcance) lleva el
    desglose GRANULAR por pieza; cada uno es 0 cuando la fuente no lo expone (no se
    inventa), igual que `alcance` por pieza.
    """

    ts: str
    interacciones: int
    visualizaciones: int
    alcance: int
    likes: int
    comentarios: int
    compartidos: int
    guardados: int
    video_views: int
    tiempo_medio_vis_s: int
    clics_enlace: int
    seguidores_netos_atribuidos: int


class PostSeleccionableComercial(TypedDict):
    """Un post real de Metricool elegible para monitorizar (`GET /api/comercial/posts`)."""

    id: str
    red: str
    titulo: str
    publicado: str
    visualizaciones: int
    interacciones: int
    engagement_pct: float
    url: NotRequired[str | None]


class RespuestaPostsComercial(TypedDict):
    """Listado de posts seleccionables + procedencia (muestra vs real)."""

    posts: list[PostSeleccionableComercial]
    fuente: str
    es_muestra: bool


class PublicacionComercial(TypedDict):
    """Una pieza comercial monitoreada (`api/comercial._a_dict`).

    `fuente`/`es_muestra` (#124) marcan la procedencia de las cifras. `serie` solo
    viene en el detalle / al crear (`con_serie=True`), por eso es `NotRequired`.
    """

    id: str
    url: str
    id_post_metricool: str
    titulo: str
    marca: str
    marca_nombre: str
    cliente: str
    campania: str
    red: str
    red_nombre: str
    formato: str
    metrica_objetivo: MetricaComercial
    objetivo: int
    estado: EstadoComercial
    publicado: str
    notas: str
    aviso_en: str
    fecha_creacion: str
    fecha_actualizacion: str
    actual: ActualComercial
    progreso_pct: float
    alcanzado: bool
    fuente: str
    es_muestra: bool
    serie: NotRequired[list[SnapshotComercial]]


class RespuestaPublicacionesComercial(TypedDict):
    """Listado de `GET /api/comercial/publicaciones` con procedencia comun (#124)."""

    publicaciones: list[PublicacionComercial]
    fuente: str
    es_muestra: bool


class RespuestaPublicacionComercial(TypedDict):
    """Respuesta de los endpoints que devuelven UNA pieza comercial (`{publicacion}`)."""

    publicacion: PublicacionComercial


class RespuestaRefrescarComercial(TypedDict):
    """Respuesta de `POST /api/comercial/refrescar`: nº de piezas actualizadas."""

    actualizadas: int
