"""Rendimiento REAL por PIEZA del tablero, leido de Metricool por `id_post_metricool`.

PROBLEMA QUE RESUELVE
=====================
El tablero (`api/contenido.py`) muestra el estado editorial de cada pieza (copy/imagen/
revision/publicar) pero NO su rendimiento una vez publicada. Cuando el programador
empuja una pieza a Metricool guarda su `id_post_metricool` por plataforma
(`contenido_plataforma.id_post_metricool`). Aqui cerramos el bucle: con ese id se lee
el rendimiento REAL (visualizaciones, interacciones, engagement) desde la **API de
Metricool** —la fuente PAGADA— y se pinta en cada tarjeta, SIN adaptadores por red.

La lectura unifica sobre `keni_metricas.servicio.construir_metricas_pieza`, que va a la
fuente activa (Metricool en prod; muestra determinista en demo). No hay un adaptador
por plataforma: una sola lectura por (marca, red, id_post).

CACHE
=====
Golpear Metricool por cada tarjeta en cada apertura del tablero seria lento y costoso.
Se cachea por pieza en la tabla generica `metricas_cache` (tipo `pieza_contenido`,
clave `pieza:{marca}:{red}:{id_post}`), igual que el resto de metricas. La lectura es:

  - LAZY FILL con TTL: si la entrada no esta o es vieja (> `TTL_SEGUNDOS`), se recalcula
    al vuelo, se guarda y se devuelve. Si esta fresca, se devuelve la cacheada
    (instantaneo). Asi el rendimiento se actualiza solo cada pocas horas sin recalcular
    en cada render.
  - Degradacion honesta: si la fuente no encuentra el post (recien publicado) o falla,
    se devuelve `encontrado=False` (la UI muestra "sin datos todavia", nunca ceros).

Solo LECTURA de metricas; no muta el tablero. Conexion por operacion (via `repos`),
segura entre hilos como el resto.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from keni_metricas import servicio

from . import marcas, repos

_log = logging.getLogger("keni_consola.metricas_pieza")

# Tipo de entrada en `metricas_cache` para las piezas del tablero.
TIPO_PIEZA = "pieza_contenido"

# Frescura del rendimiento por pieza: pasado esto, la siguiente lectura recalcula.
# 4 h casa con la cadencia del daemon de metricas ("1 vez al dia importa"): el
# rendimiento de un post no cambia minuto a minuto.
TTL_SEGUNDOS = 4 * 60 * 60


def _ahora() -> datetime:
    return datetime.now()


def _clave(marca: str, red: str, id_post: str) -> str:
    return f"pieza:{marca}:{red}:{id_post}"


def _es_fresca(generado_en: str, ahora: datetime) -> bool:
    """True si `generado_en` (ISO) esta dentro del TTL respecto a `ahora`."""
    if not generado_en:
        return False
    try:
        ts = datetime.fromisoformat(generado_en)
    except ValueError:
        return False
    return (ahora - ts).total_seconds() < TTL_SEGUNDOS


def _calcular(marca: str, red: str, id_post: str) -> dict[str, Any]:
    """Lee el rendimiento crudo de una pieza desde la fachada de metricas.

    `marca` es el id de marca de la Consola (slug-guion): se traduce a `id_metricas`
    (guion_bajo) en la frontera, igual que el programador. Devuelve el dict de
    `MetricaPieza` (con `encontrado`/`fuente`). Best-effort: cualquier error de la
    fuente se degrada a `encontrado=False` sin romper el tablero.
    """
    id_metricas = marcas.id_metricas_de(marca)
    try:
        return servicio.construir_metricas_pieza(id_metricas, red, id_post)
    except Exception:  # noqa: BLE001 -- nunca rompe el tablero por una pieza
        _log.exception(
            "metricas_pieza: fallo al leer rendimiento de marca=%s red=%s id_post=%s.",
            marca, red, id_post,
        )
        return {
            "id_post": id_post,
            "plataforma": red,
            "encontrado": False,
            "visualizaciones": 0,
            "interacciones": 0,
            "engagement_pct": 0.0,
            "url": None,
            "publicado": None,
            "fuente": "desconocida",
        }


def rendimiento(marca: str, red: str, id_post: str) -> dict[str, Any]:
    """Rendimiento de UNA pieza desde cache (lazy fill + TTL). `{payload..., generado_en}`.

    Si la cache esta fresca devuelve la entrada cacheada; si falta o es vieja, recalcula,
    guarda y devuelve. El payload es el dict de `MetricaPieza` mas `generado_en` (cuando
    se leyo de Metricool, para que la UI muestre "actualizado hace X").
    """
    if not (marca and red and id_post):
        return {**_calcular(marca, red, id_post), "generado_en": ""}

    ahora = _ahora()
    clave = _clave(marca, red, id_post)
    entrada = repos.leer_metricas_cache(clave)
    if entrada is not None and _es_fresca(entrada["generado_en"], ahora):
        return {**entrada["payload"], "generado_en": entrada["generado_en"]}

    payload = _calcular(marca, red, id_post)
    generado_en = ahora.isoformat(timespec="seconds")
    # Solo cacheamos lo ENCONTRADO: un post recien publicado (encontrado=False) no debe
    # quedar pegado en cache; la proxima apertura reintenta hasta que Metricool lo tenga.
    if payload.get("encontrado"):
        repos.guardar_metricas_cache(
            clave,
            TIPO_PIEZA,
            "-",
            marca,
            payload,
            payload.get("fuente") or "muestra",
            generado_en,
        )
    return {**payload, "generado_en": generado_en if payload.get("encontrado") else ""}


def rendimiento_de_tablero(
    contenidos: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Mapa `contenido_plataforma.id -> rendimiento` para las filas con `id_post_metricool`.

    Recibe los items del tablero (ya con sus `plataformas`) y devuelve solo las filas
    publicadas que tienen `id_post_metricool`: cada una con su rendimiento (cacheado).
    Las filas sin id (no publicadas via Metricool) se omiten: la UI no pinta nada.
    Best-effort por pieza: un fallo de una no afecta a las demas.
    """
    salida: dict[str, dict[str, Any]] = {}
    for contenido in contenidos:
        marca = contenido.get("marca") or ""
        for plat in contenido.get("plataformas", []):
            id_post = plat.get("id_post_metricool") or ""
            red = plat.get("red") or ""
            if not id_post or not marca:
                continue
            salida[plat["id"]] = rendimiento(marca, red, id_post)
    return salida
