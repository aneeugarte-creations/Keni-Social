"""Biblioteca de hashtags por marca, sacada de TODO el historial de publicaciones.

El POOL de candidatos que la etapa `sugerir_hashtags` ofrece al revisar una pieza: los
hashtags que cada marca usa de verdad (umbral >= 20 usos, ver `umbral` en el JSON), sacados
del historial real (Metricool). Los datos viven como semilla versionada en `datos/<marca>.json`
(los regenera `scripts/generar_biblioteca_hashtags.py`); este módulo solo los CARGA y los expone.

`conteo_por_red` fija CUÁNTOS hashtags sugerir por red (la mediana histórica entre los posts que
etiquetan; 0 en redes que apenas usan hashtags, p. ej. YouTube). `candidatos` da la lista (sin
'#') de la que la IA elige los relevantes al copy. `fijos` son la FIRMA de la marca (nombre/portal),
que van casi en cada post y la etapa inyecta SIEMPRE (no dependen del tema, así que no los elige la IA).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATOS = Path(__file__).resolve().parent / "datos"

# Cuántos sugerir cuando la red no aparece en `conteo_por_red` (red sin foto histórica): la
# mediana global entre los posts que etiquetan en el piloto.
CANTIDAD_DEFECTO = 5


@lru_cache(maxsize=None)
def biblioteca(marca: str) -> dict:
    """Biblioteca cargada de `datos/<marca>.json` (cacheada). {} si la marca no tiene archivo."""
    ruta = _DATOS / f"{marca}.json"
    if not ruta.is_file():
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return datos if isinstance(datos, dict) else {}


def candidatos(marca: str) -> list[str]:
    """Hashtags candidatos de la marca (tags en minúscula, SIN '#'), por frecuencia desc. [] si no hay."""
    hashtags = biblioteca(marca).get("hashtags") or []
    salida: list[str] = []
    for h in hashtags:
        tag = str((h or {}).get("tag") or "").strip().lower().lstrip("#")
        if tag:
            salida.append(tag)
    return salida


def fijos(marca: str) -> list[str]:
    """Hashtags FIJOS de la marca (su firma: nombre/portal/lema), en minúscula SIN '#'. [] si no hay.

    Van casi en cada post y NO dependen del tema, así que la etapa los inyecta SIEMPRE (la IA solo
    elige los temáticos). Salen del historial: muy adoptados o el handle de la marca.
    """
    crudos = biblioteca(marca).get("fijos") or []
    salida: list[str] = []
    for c in crudos:
        tag = str(c or "").strip().lower().lstrip("#")
        if tag:
            salida.append(tag)
    return salida


def cantidad_sugerida(marca: str, red: str) -> int:
    """CUÁNTOS hashtags sugerir para `marca`+`red` (0 ⇒ no sugerir). Default `CANTIDAD_DEFECTO`.

    Marca sin biblioteca ⇒ 0 (no hay pool del que sacar). Red conocida ⇒ su `conteo_por_red`
    (puede ser 0: la red no usa hashtags). Red desconocida en una marca con biblioteca ⇒ el
    default global.
    """
    biblio = biblioteca(marca)
    if not biblio:
        return 0
    conteo = biblio.get("conteo_por_red") or {}
    if red in conteo:
        try:
            return max(0, int(conteo[red]))
        except (TypeError, ValueError):
            return 0
    return CANTIDAD_DEFECTO
