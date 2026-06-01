"""Recoleccion de basura (GC) de MEDIA HUERFANA del almacen (Estudio de imagen, diseno §5).

PROBLEMA QUE RESUELVE
=====================
El Estudio de imagen genera N variantes por pieza; las NO elegidas quedan como objetos
sueltos en el almacen de media (`almacen_media`) y nadie las borra: el almacen crece sin
limite. Aqui un barrido CONSERVADOR localiza y borra los objetos HUERFANOS.

DEFINICION DE HUERFANO (conservadora; ante la duda, NO se borra)
================================================================
Un objeto del almacen es huerfano si y SOLO si cumple las DOS condiciones:
  1. NO esta referenciado por el campo `imagen` de ninguna publicacion (normales — en TODOS
     los estados y marcas — ni comerciales si estas tuvieran `imagen`), Y
  2. es mas VIEJO que `antiguedad_horas` (def 24h): asi NO se borran las variantes recien
     generadas por el Estudio que el usuario aun esta revisando.

Las referencias vivas se calculan SIEMPRE sobre el catalogo completo (sin filtros de
estado/marca): un objeto referenciado por CUALQUIER pieza, en cualquier estado, se conserva.

BIBLIOTECA DE MEDIOS (catalogo) — comprobacion DEFENSIVA y OPCIONAL
==================================================================
La biblioteca de medios (`api/biblioteca_media.py` / `repos.listar_media_biblioteca`) esta
EN PROCESO DE RETIRADA (AMX usa su propia biblioteca). El GC NO depende de ella: si el repo
existe en runtime, sus objetos catalogados se anaden a las referencias vivas como red de
seguridad; si el modulo/funcion se elimina, el GC sigue funcionando sin tocar esa fuente (no
se importa a nivel de modulo nada propio de biblioteca-media; se consulta via `hasattr`).

SEGURO POR DISENO
=================
  - Nunca borra un objeto referenciado o catalogado, ni uno reciente (umbral).
  - `limpiar` es ROBUSTO ante errores por objeto: si un borrado falla, loguea y sigue.
  - SIEMPRE loguea cuantos borro y cuantos conservo (sin caps silenciosos).
  - `dry_run` permite ver que se borraria sin tocar nada.

`referencias_vivas` y `huerfanos` son consultas de SOLO LECTURA; `limpiar` es la unica que
muta el almacen, y solo si `dry_run` es False.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .. import almacen_media, repos

_log = logging.getLogger("keni_consola.media_gc")


def _imagenes_de(filas: list[dict[str, Any]]) -> set[str]:
    """Nombres de objeto en el campo `imagen` de una lista de filas (vacios descartados)."""
    nombres: set[str] = set()
    for fila in filas:
        nombre = (fila.get("imagen") or "").strip()
        if nombre:
            nombres.add(nombre)
    return nombres


def _objetos_biblioteca_media() -> set[str]:
    """Objetos catalogados en biblioteca-media, SI ese repo existe (comprobacion OPCIONAL).

    La biblioteca de medios esta en retirada: NO es una dependencia dura del GC. Si
    `repos.listar_media_biblioteca` ya no existe (modulo eliminado), devuelve set vacio sin
    fallar. Si existe, sus `objeto` se suman como red de seguridad. `hasattr` evita importar
    nada propio de biblioteca-media a nivel de modulo.
    """
    listar = getattr(repos, "listar_media_biblioteca", None)
    if listar is None:
        return set()
    return {
        objeto
        for item in listar()
        if (objeto := (item.get("objeto") or "").strip())
    }


def referencias_vivas() -> set[str]:
    """Conjunto de nombres de objeto REFERENCIADOS (NO borrables).

    Une:
      - el `imagen` de TODAS las publicaciones normales (sin filtro de estado/marca),
      - el `imagen` de las publicaciones comerciales (HOY no tienen ese campo: el `.get`
        devuelve None y no aporta nada; se incluye por si se anade en el futuro),
      - DEFENSIVO Y OPCIONAL: el `objeto` de la biblioteca de medios SOLO si ese repo aun
        existe en runtime (esta en retirada; ver `_objetos_biblioteca_media`).

    Las publicaciones son la fuente de verdad de "media en uso". La biblioteca-media es una
    red de seguridad transitoria, no una dependencia dura.
    """
    vivas: set[str] = set()
    vivas |= _imagenes_de(repos.listar_publicaciones())
    vivas |= _imagenes_de(repos.listar_publicaciones_comerciales())
    vivas |= _objetos_biblioteca_media()
    return vivas


def huerfanos(antiguedad_horas: float = 24) -> list[str]:
    """Objetos HUERFANOS borrables: ni referenciados/catalogados ni recientes.

    Devuelve los nombres de objeto de `almacen_media.listar_objetos()` que NO estan en
    `referencias_vivas()` y cuyo mtime es mas viejo que `antiguedad_horas` (medido contra
    `time.time()`). Un umbral <= 0 se trata como 0 (todo lo no referenciado es candidato),
    pero el llamante (config) ya impone min 1h.
    """
    vivas = referencias_vivas()
    objetos = almacen_media.listar_objetos()
    corte = time.time() - max(antiguedad_horas, 0.0) * 3600.0
    return [
        nombre
        for (nombre, mtime) in objetos
        if nombre not in vivas and mtime < corte
    ]


def limpiar(antiguedad_horas: float = 24, dry_run: bool = False) -> dict[str, Any]:
    """Borra (o simula) los objetos huerfanos. Devuelve un resumen y loguea SIEMPRE.

    Resultado: `{borrados, conservados, dry_run, nombres}` donde `nombres` son los objetos
    huerfanos detectados (borrados o que se borrarian en `dry_run`). `conservados` es el
    total de objetos del almacen MENOS los huerfanos (lo que se mantiene: referenciados,
    catalogados o recientes).

    Robusto ante errores por objeto: si `borrar_objeto` falla para uno, loguea y sigue con
    los demas (ese objeto NO cuenta como borrado). En `dry_run` no toca el almacen.
    """
    total = len(almacen_media.listar_objetos())
    a_borrar = huerfanos(antiguedad_horas)
    conservados = total - len(a_borrar)

    if dry_run:
        _log.info(
            "GC media (DRY-RUN): %d huerfano(s) se borrarian, %d conservado(s) "
            "(umbral=%.1fh).",
            len(a_borrar), conservados, antiguedad_horas,
        )
        return {
            "borrados": 0,
            "conservados": conservados,
            "dry_run": True,
            "nombres": list(a_borrar),
        }

    borrados = 0
    for nombre in a_borrar:
        try:
            almacen_media.borrar_objeto(nombre)
            borrados += 1
        except Exception:  # noqa: BLE001 -- un fallo por objeto no debe abortar el barrido
            _log.exception("GC media: fallo al borrar el objeto huerfano %r.", nombre)
    _log.info(
        "GC media: %d huerfano(s) borrado(s), %d conservado(s) (umbral=%.1fh).",
        borrados, conservados, antiguedad_horas,
    )
    return {
        "borrados": borrados,
        "conservados": conservados,
        "dry_run": False,
        "nombres": list(a_borrar),
    }
