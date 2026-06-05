"""Helpers PUROS para el Carril Rápido de Breaking (Claro Sports).

Selecciona los temas del Radar que están marcados como `breaking=True` (señal acelerando
NOW), filtra por marca, ordena por señal descendente y anota el estado del borrador.

PROPÓSITO ÚNICO: superficie para el humano. Este módulo NUNCA auto-publica ni auto-aprueba;
sólo PROPONE temas urgentes para que el equipo los atienda con un tap.

CONTRATO
--------
  - `items_breaking(marca, geo)` → lista de temas breaking del snapshot (pure, sin red).
  - `clave_de_titulo(titulo)` → clave de dedup para cruzar con contenido.
  - `anotar_estado_borrador(items, marca)` → anota `estado_borrador`/`contenido_id`/
    `generacion_id` IN-PLACE leyendo el tablero. Best-effort: si falla, deja "ninguno".

Dependencias: `repos` y `generaciones` (lectura), `dominio.dedup` (clave).
Sin red, sin mutaciones (este módulo es de LECTURA).
"""

from __future__ import annotations

import logging
from typing import Any

from . import dedup

_log = logging.getLogger("keni_consola.dominio.breaking")

# Máximo de items breaking que se exponen al frontend por request.
MAX_ITEMS_BREAKING = 20


def items_breaking(marca: str, geo: str) -> list[dict[str, Any]]:
    """Temas breaking del snapshot del Investigador para `marca` y `geo`, por señal desc.

    Lee `repos.listar_radar_items` (el snapshot materializado por el daemon del Investigador).
    Sin snapshot (daemon OFF) o si `marca` está vacía → lista vacía (safe-by-default, sin red).
    Devuelve a lo sumo `MAX_ITEMS_BREAKING` temas. Best-effort: cualquier fallo devuelve `[]`.
    """
    if not marca:
        return []
    try:
        from .. import repos

        filas = repos.listar_radar_items(marca=marca, geo=geo)
    except Exception:  # noqa: BLE001
        _log.exception("breaking: no se pudo leer el snapshot (marca=%s, geo=%s)", marca, geo)
        return []

    resultado: list[dict[str, Any]] = []
    for fila in filas:
        if not fila.get("breaking"):
            continue
        titulo = (fila.get("titulo") or "").strip()
        if not titulo:
            continue
        resultado.append(dict(fila))

    # Ordenar por señal desc (tema que más acelera primero).
    resultado.sort(key=lambda t: -(int(t.get("senal") or 0)))
    return resultado[:MAX_ITEMS_BREAKING]


def clave_de_titulo(titulo: str) -> str:
    """Clave de dedup de un título (igual que el Investigador). "" si el título está vacío."""
    return dedup.clave(titulo)


def _borradores_breaking_de_marca(marca: str) -> list[dict[str, Any]]:
    """Lee el tablero de `marca` filtrando por `origen='breaking'`. Best-effort → []."""
    try:
        from .. import repos

        # `listar_contenido` no filtra por `origen`; post-filtramos en memoria (universo pequeño).
        todos = repos.listar_contenido(marca=marca, clase="contenido")
        return [it for it in todos if (it.get("origen") or "") == "breaking"]
    except Exception:  # noqa: BLE001
        _log.exception("breaking: no se pudo leer el tablero de borradores (marca=%s)", marca)
        return []


def _generacion_reciente_de(contenido_id: str) -> tuple[str, str]:
    """Devuelve `(gen_id, estado_gen)` de la generación más reciente del contenido.

    Escanea el almacén de generaciones buscando las que tienen `contenido_id` igual al
    pasado y devuelve la más reciente (fecha_inicio desc). Best-effort → ("", "").
    """
    if not contenido_id:
        return ("", "")
    try:
        from .. import generaciones

        todas = generaciones.listar(limite=None)  # ya ordenadas recientes primero
        for gen in todas:
            if (gen.get("contenido_id") or "") == contenido_id:
                return (gen.get("id") or "", gen.get("estado") or "")
    except Exception:  # noqa: BLE001
        _log.exception("breaking: no se pudo leer generaciones (contenido_id=%s)", contenido_id)
    return ("", "")


def anotar_estado_borrador(items: list[dict[str, Any]], marca: str) -> None:
    """Anota IN-PLACE `estado_borrador`, `contenido_id` y `generacion_id` en cada item.

    Cruza el título de cada tema (por clave de dedup) contra los contenidos con
    `origen='breaking'` de la marca. Una sola query al tablero (no N+1). Best-effort:
    si el cruce falla, todos quedan con `estado_borrador='ninguno'` sin lanzar excepción.

    Valores de `estado_borrador`:
      - `"ninguno"`:   no hay borrador creado para este tema.
      - `"generando"`: hay borrador y su generación de copy está ejecutando.
      - `"listo"`:     hay borrador con la generación completada (copy disponible).
    """
    # Valores por defecto para todos los items (defensa ante cualquier fallo parcial).
    for item in items:
        item.setdefault("estado_borrador", "ninguno")
        item.setdefault("contenido_id", "")
        item.setdefault("generacion_id", "")

    if not marca or not items:
        return

    borradores = _borradores_breaking_de_marca(marca)
    if not borradores:
        return

    # Construir mapa clave -> contenido para O(1) por item (dedup: gana el primero).
    mapa: dict[str, dict[str, Any]] = {}
    for borrador in borradores:
        titulo = (borrador.get("titulo") or "").strip()
        clave = clave_de_titulo(titulo)
        if clave and clave not in mapa:
            mapa[clave] = borrador

    for item in items:
        titulo_item = (item.get("titulo") or "").strip()
        clave = clave_de_titulo(titulo_item)
        if not clave:
            continue
        borrador = mapa.get(clave)
        if borrador is None:
            continue

        contenido_id = borrador.get("id") or ""
        item["contenido_id"] = contenido_id

        gen_id, estado_gen = _generacion_reciente_de(contenido_id)
        item["generacion_id"] = gen_id

        if estado_gen == "ejecutando":
            item["estado_borrador"] = "generando"
        elif gen_id:
            item["estado_borrador"] = "listo"
        else:
            # Borrador existe pero no se encontró generación asociada todavía.
            item["estado_borrador"] = "listo"
