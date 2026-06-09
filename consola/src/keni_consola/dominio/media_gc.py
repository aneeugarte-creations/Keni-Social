"""Recoleccion de basura (GC) de MEDIA HUERFANA del almacen (Estudio de imagen, diseno §5).

PROBLEMA QUE RESUELVE
=====================
El Estudio de imagen genera N variantes por pieza; las NO elegidas quedan como objetos
sueltos en el almacen de media (`almacen_media`) y nadie las borra: el almacen crece sin
limite. Aqui un barrido CONSERVADOR localiza y borra los objetos HUERFANOS.

DEFINICION DE HUERFANO (conservadora; ante la duda, NO se borra)
================================================================
Un objeto del almacen es huerfano si y SOLO si cumple las DOS condiciones:
  1. NO es una REFERENCIA VIVA: ni el `imagen` (composite horneado) ni la `foto` cruda de
     ninguna publicacion (normales — TODOS los estados/marcas — ni comerciales), ni un recurso
     que alimente el render on-demand (miniatura/media_id de plantillas del estudio, activos de
     marca: logos, tipografías), ni un arte catalogado en la galería, Y
  2. es mas VIEJO que `antiguedad_horas` (def 24h): asi NO se borran las variantes recien
     generadas por el Estudio que el usuario aun esta revisando.

Con el render ON-DEMAND la imagen publicable se DERIVA de la receta (foto + copy_in +
plantilla/marca) y NO se persiste un composite por edicion; esos renders sin referencia son
huerfanos RECICLABLES (caché reconstruible). Por eso protegemos los ORIGINALES (foto, logos,
tipografías, plantillas), no los composites.

Las referencias vivas se calculan SIEMPRE sobre el catalogo completo (sin filtros de
estado/marca): un objeto referenciado por CUALQUIER pieza, en cualquier estado, se conserva.

GALERÍA DE ARTES (catalogo) — referencia viva (comprobacion DEFENSIVA y OPCIONAL)
====================================================================================
La galería de ARTES (`api/artes.py` / `repos.listar_media_catalogo`) cataloga objetos
que el equipo decide CONSERVAR para reutilizar en publicaciones. Un arte catalogado es una
referencia viva: el GC NO lo borra aunque ninguna publicacion lo use todavia. El GC NO
depende de forma DURA de ese repo: si existe en runtime sus objetos se anaden a las
referencias vivas; si la funcion se eliminara, el GC sigue funcionando sin tocar esa fuente
(no se importa a nivel de modulo nada propio de la galería; se consulta via `hasattr`).

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


def _fotos_de(filas: list[dict[str, Any]]) -> set[str]:
    """Nombres de objeto en el campo `foto` (foto cruda) de una lista de filas.

    CRÍTICO con el render on-demand: la imagen publicable se DERIVA de la receta y la `foto`
    cruda ya NO está horneada dentro de `imagen`. Si el GC borrara la `foto`, el render
    on-demand se quedaría sin original. Por eso la `foto` de toda pieza es referencia viva.
    """
    nombres: set[str] = set()
    for fila in filas:
        nombre = (fila.get("foto") or "").strip()
        if nombre:
            nombres.add(nombre)
    return nombres


def _refs_documento(doc: Any, acc: set[str]) -> None:
    """Acumula en `acc` los media_id referenciados por un documento de capas (recursivo)."""
    if not isinstance(doc, dict):
        return
    fondo = doc.get("fondo")
    if isinstance(fondo, dict) and fondo.get("tipo") == "imagen":
        mid = ((fondo.get("imagen") or {}) if isinstance(fondo.get("imagen"), dict) else {}).get("media_id")
        if isinstance(mid, str) and mid.strip():
            acc.add(mid.strip())

    def _capas(capas: Any) -> None:
        if not isinstance(capas, list):
            return
        for c in capas:
            if not isinstance(c, dict):
                continue
            tipo = c.get("tipo")
            if tipo == "imagen" and isinstance(c.get("objeto"), str) and c["objeto"].strip():
                acc.add(c["objeto"].strip())
            elif tipo == "logo" and c.get("tipo_logo") == "imagen" and isinstance(c.get("media_id"), str) and c["media_id"].strip():
                acc.add(c["media_id"].strip())
            elif tipo == "grupo":
                _capas(c.get("capas"))

    _capas(doc.get("capas"))


def _objetos_recursos_marca() -> set[str]:
    """Originales que alimentan el render on-demand: plantillas del estudio y activos de marca.

    DEFENSIVO y OPCIONAL (igual patrón que la galería de artes): si alguna fuente no existe
    en runtime, se omite sin fallar. Protege de borrado:
      - las MINIATURAS y los media_id (logo/fondo/foto de muestra) de las plantillas del estudio,
      - los `objeto` de los activos de marca (logos oficiales, tipografías).
    Los specs de marca guardan sus logos/fondos como activos de marca o en sus media_id; se
    cubren vía los activos. Sin esto, un GC activo podría borrar el logo/tipografía que el
    render necesita componer.
    """
    import json

    refs: set[str] = set()
    listar_plantillas = getattr(repos, "listar_plantillas_diseno", None)
    if listar_plantillas is not None:
        try:
            for p in listar_plantillas():
                mini = (p.get("miniatura") or "").strip()
                if mini:
                    refs.add(mini)
                doc_raw = p.get("documento") or ""
                if doc_raw:
                    try:
                        _refs_documento(json.loads(doc_raw), refs)
                    except (ValueError, TypeError):
                        pass
        except Exception:  # noqa: BLE001 -- fuente opcional: nunca tumba el GC
            pass
    listar_activos = getattr(repos, "listar_marca_activos", None)
    if listar_activos is not None:
        try:
            for a in listar_activos():
                objeto = (a.get("objeto") or "").strip()
                if objeto:
                    refs.add(objeto)
        except Exception:  # noqa: BLE001 -- fuente opcional: nunca tumba el GC
            pass
    return refs


def _objetos_catalogo_media() -> set[str]:
    """Objetos catalogados en la galería de artes, SI ese repo existe (comprobacion OPCIONAL).

    La galería de artes (`api/artes.py`) NO es una dependencia dura del GC. Si
    `repos.listar_media_catalogo` no existe en runtime, devuelve set vacio sin fallar. Si
    existe, sus `objeto` se suman a las referencias vivas. `hasattr` evita importar nada
    propio de la galería a nivel de modulo.
    """
    listar = getattr(repos, "listar_media_catalogo", None)
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
      - DEFENSIVO Y OPCIONAL: el `objeto` de la galería de artes SOLO si ese repo existe
        en runtime (ver `_objetos_catalogo_media`).

    Las publicaciones son la fuente de verdad de "media en uso"; la galería de artes anade
    los objetos que el equipo decidio conservar para reutilizar.
    """
    vivas: set[str] = set()
    publicaciones = repos.listar_publicaciones()
    comerciales = repos.listar_publicaciones_comerciales()
    vivas |= _imagenes_de(publicaciones)
    vivas |= _imagenes_de(comerciales)
    # Con render on-demand la FOTO cruda ya no está horneada en `imagen`: protégela también, o
    # el GC borraría el original del que el render compone.
    vivas |= _fotos_de(publicaciones)
    vivas |= _fotos_de(comerciales)
    # Originales que alimentan el render: plantillas del estudio (miniatura + media_id) y
    # activos de marca (logos, tipografías). Defensivo y opcional.
    vivas |= _objetos_recursos_marca()
    vivas |= _objetos_catalogo_media()
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

    # RE-VERIFICACION anti-TOCTOU: entre el calculo de `huerfanos()` y el borrado pudo
    # nacer una referencia nueva (una pieza que fija `imagen`/`foto` a uno de estos
    # objetos). Se recalcula el set de referencias JUSTO antes del bucle de borrado y se
    # re-comprueba cada objeto contra ese snapshot fresco: el que se volvio referenciado
    # se CONSERVA (y se descuenta de los huerfanos reportados).
    vivas_ahora = referencias_vivas()
    rescatados = [n for n in a_borrar if n in vivas_ahora]
    if rescatados:
        _log.info(
            "GC media: %d objeto(s) referenciados durante el barrido; se conservan.",
            len(rescatados),
        )
        a_borrar = [n for n in a_borrar if n not in vivas_ahora]
        conservados = total - len(a_borrar)

    borrados = 0
    for nombre in a_borrar:
        if nombre in vivas_ahora:  # defensa redundante (lista ya filtrada)
            continue
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
