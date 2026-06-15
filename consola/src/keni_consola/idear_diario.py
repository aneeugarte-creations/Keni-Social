"""EVERGREEN DIARIO: reemite cada día UNA pieza green aprobada, al azar, para su hueco de las 8.

El plan editorial reserva una línea 'evergreen' (p. ej. UnoTV: evergreen:1). Su único ORIGEN
es el banco de contenido green (investigación/contenidos): piezas atemporales que el equipo
generó y APROBÓ. Este barrido la llena solo:

  - Si la marca tiene cupo 'evergreen' en su plan y HOY aún no se generó (ventana móvil de
    24 h, el MISMO conteo que la admisión), elige AL AZAR un contenido green aprobado del
    banco (categoría 'evergreen', excluyendo las reemisiones previas: `origen=
    'evergreen-diario'`) y lo DUPLICA: contenido nuevo + sus piezas por red en `aprobado`.
  - El programador (`auto_programar.barrer_aprobadas`, mismo bucle) las programa al siguiente
    hueco de su categoría — la franja evergreen de las 8:00 (hora CDMX).
  - Si el equipo ya creó un green hoy (cuenta como generado de la línea), el barrido NO añade
    otro: el automatismo rellena los días en los que nadie creó uno nuevo.

Gateado por el interruptor general (`KENI_MAQUINA`); no publica nada por sí mismo
(la publicación real sigue tras `KENI_PUBLICAR_REAL` y el gate humano ya ocurrió: el banco
está aprobado). Best-effort: un fallo se loguea y el siguiente barrido reintenta.
"""

from __future__ import annotations

import logging
import random

from . import config, marcas, repos

_log = logging.getLogger("keni_consola.idear_diario")

# Origen de las REEMISIONES del banco green: las excluye del propio pool (no se reemite una
# reemisión; siempre se parte del original) y las hace auditables en el tablero.
ORIGEN_EVERGREEN_DIARIO = "evergreen-diario"

# Estados de pieza que cuentan como "aprobada" para el banco: pasó el gate humano (aprobado)
# o ya salió alguna vez (programado/publicado tras aprobarse).
_ESTADOS_BANCO = ("aprobado", "programado", "publicado")


def _banco_de(marca: str) -> list[dict]:
    """Contenidos green APROBADOS de la marca: categoría 'evergreen', no-reemisión, con
    al menos una pieza por red en estado del banco. Best-effort: [] si algo falla."""
    try:
        items = repos.listar_contenido(clase="contenido", marca=marca)
    except Exception:  # noqa: BLE001 -- sin tablero legible, hoy no se reemite
        _log.exception("idear_diario: no se pudo leer el tablero (%s).", marca)
        return []
    banco: list[dict] = []
    for it in items:
        if (it.get("categoria") or "") != "evergreen":
            continue
        if (it.get("origen") or "") == ORIGEN_EVERGREEN_DIARIO:
            continue
        try:
            piezas = repos.listar_contenido_plataforma(it.get("id") or "")
        except Exception:  # noqa: BLE001 -- un item ilegible no tumba el barrido
            continue
        aprobadas = [p for p in piezas if (p.get("estado") or "") in _ESTADOS_BANCO]
        if aprobadas:
            banco.append({**it, "_piezas": aprobadas})
    return banco


def _reemitir(original: dict) -> dict | None:
    """Duplica un contenido green del banco: contenido nuevo + piezas en `aprobado`.

    Las piezas nacen `aprobado` (el gate humano ya ocurrió en el original); el barrido de
    aprobadas del programador las lleva al hueco evergreen (8:00). None si falla.
    """
    try:
        nuevo = repos.crear_contenido(
            clase="contenido",
            flujo="evergreen",
            categoria="evergreen",
            origen=ORIGEN_EVERGREEN_DIARIO,
            titulo=original.get("titulo") or "",
            descripcion=original.get("descripcion") or "",
            marca=original.get("marca") or "",
            tipo_contenido=original.get("tipo_contenido") or "ia",
            formato=original.get("formato") or "foto",
        )
        for p in original.get("_piezas") or []:
            repos.crear_contenido_plataforma(
                contenido_id=nuevo["id"],
                red=p.get("red") or "",
                estado="aprobado",
                copy=p.get("copy") or "",
                copy_in=p.get("copy_in") or "",
                imagen=p.get("imagen") or "",
                imagen_fuente=p.get("imagen_fuente") or "",
                foto=p.get("foto") or "",
                video=p.get("video") or "",
                veredicto=p.get("veredicto") or "",
                falta_revision=False,
                evergreen=True,
            )
        return nuevo
    except Exception:  # noqa: BLE001 -- el siguiente barrido reintenta
        _log.exception("idear_diario: fallo la reemisión de %s.", original.get("id"))
        return None


def barrer() -> int:
    """Un barrido: por marca con línea evergreen en su plan, reemite UNA si hoy falta.

    Idempotente dentro de la ventana: el duplicado cuenta como generado de la línea, así que
    el siguiente barrido ve el cupo lleno y no añade otro. Devuelve cuántas reemitió.
    """
    if not config.maquina_activa():
        return 0
    from .pipeline_contenido import _ingesta

    reemitidos = 0
    for marca in marcas.ids():
        plan = config.plan_dia(marca)
        if plan.get("evergreen", 0) <= 0:
            continue
        restantes = _ingesta.cupos_categoria_restantes(marca) or {}
        if restantes.get("evergreen", 0) <= 0:
            continue  # hoy ya hay green (del equipo o de una reemisión previa)
        banco = _banco_de(marca)
        if not banco:
            continue  # sin banco aprobado: no se inventa nada
        elegido = random.choice(banco)
        if _reemitir(elegido) is not None:
            reemitidos += 1
            _log.info(
                "idear_diario: reemitida «%s» (%s) hacia su hueco de las 8.",
                (elegido.get("titulo") or "")[:60], marca,
            )
    return reemitidos
