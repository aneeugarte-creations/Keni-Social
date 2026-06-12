"""Indicaciones del equipo (cajón `contexto` de los Insumos) → guía del copy.

En el cajón `contexto` (api/insumos.py) el equipo pega los lineamientos de
Coordinación Marketing / Temas Editoriales: "no usar X término", "hoy prioridad
al Mundial", correcciones, transmisiones. Esos ítems NUNCA se publican ni entran
al pool (`ingesta.noticia_item_de_insumo` los excluye y empujar responde 400),
pero la promesa del producto es que GUÍEN la generación: este módulo los lee
(los VIGENTES) y los compone como bloque de texto que `generar.componer_copy`
inyecta en TODOS los copys de la marca (lanzamientos reales Y previsualización
de la Biblioteca: "lo que lanzas es lo que previsualizas").

VIGENTE = ítem del cajón `contexto` con `tipo="contexto"`, de la marca pedida o
sin marca, con fecha en los últimos `VENTANA_DIAS` días. Las indicaciones son
operativas del día a día ("hoy prioridad a...", "esta semana no usar..."), así
que CADUCAN SOLAS por ventana: sin ese corte, una corrección puntual de hace un
mes seguiría mandando sobre todos los copys. No hay flag "descartado": descartar
una indicación = borrar su lote del cajón (DELETE), así que existir ya implica
no descartada. Tope `TOPE_ITEMS` (los más recientes) para no inflar el prompt.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from ..tiempo import hoy_utc

_log = logging.getLogger("keni_consola.indicaciones")

# Cajón de los insumos donde viven las indicaciones (ver api/insumos.py `_CAJONES`).
CAJON_CONTEXTO = "contexto"

# Ventana de vigencia en días: una indicación más vieja deja de mandar sola, sin
# que nadie tenga que limpiarla (las indicaciones del equipo son operativas, no
# línea editorial permanente — eso vive en los documentos editoriales por marca).
VENTANA_DIAS = 7

# Tope de ítems inyectados (los más recientes primero): protege el tamaño del
# prompt si el equipo vuelca muchas indicaciones en pocos días.
TOPE_ITEMS = 20

# Encabezado del bloque inyectado (delimitado y accionable para el modelo).
ENCABEZADO_INDICACIONES = "## Indicaciones del equipo (vigentes, OBLIGATORIAS)"


def _ddmm(fecha_iso: str) -> str:
    """`YYYY-MM-DD` → `DD/MM` para fechar cada indicación en el bloque. "" si no parsea."""
    try:
        f = date.fromisoformat((fecha_iso or "").strip())
    except ValueError:
        return ""
    return f.strftime("%d/%m")


def bloque_indicaciones(items: list[dict[str, Any]]) -> str:
    """Compone el bloque de prompt a partir de ítems de indicación. Función PURA.

    Lista de ítems entra (en el orden en que deben aparecer; `indicaciones_vigentes`
    ya los entrega más recientes primero), bloque de texto sale. Sin ítems (o sin
    ninguno con título útil) devuelve "" y el prompt del copy no cambia NI UN byte.
    """
    lineas: list[str] = []
    for item in items:
        titulo = str(item.get("titulo") or "").strip()
        if not titulo:
            continue
        resumen = str(item.get("resumen") or "").strip()
        texto = f"{titulo} — {resumen}" if resumen else titulo
        fecha = _ddmm(str(item.get("fecha") or ""))
        lineas.append(f"- {texto} ({fecha})" if fecha else f"- {texto}")
    if not lineas:
        return ""
    return (
        ENCABEZADO_INDICACIONES
        + "\n\nCúmplelas en TODAS las piezas; si chocan con la línea editorial, mandan estas indicaciones:\n\n"
        + "\n".join(lineas)
    )


def indicaciones_vigentes(marca: str, *, hoy: date | None = None) -> list[dict[str, Any]]:
    """Ítems VIGENTES del cajón `contexto` para `marca`, más recientes primero.

    Filtra: `tipo="contexto"` (el cajón es de guía, pero un ítem re-tipado a nota
    deja de ser indicación), marca del ítem == `marca` o vacía (una indicación sin
    marca dentro del cajón aplica a todas), y fecha del cajón dentro de la ventana
    de `VENTANA_DIAS`. Sin fecha parseable no hay vigencia que evaluar: se omite.
    Devuelve a lo sumo `TOPE_ITEMS`, ordenados (fecha, creado) descendente.
    """
    from .. import repos  # import local para mantener el módulo testeable sin BD

    _hoy = hoy or hoy_utc()
    corte = _hoy - timedelta(days=VENTANA_DIAS)
    marca_pedida = (marca or "").strip()
    vigentes: list[dict[str, Any]] = []
    for item in repos.listar_insumo_items(cajon=CAJON_CONTEXTO):
        if str(item.get("tipo") or "").strip().lower() != "contexto":
            continue
        marca_item = str(item.get("marca") or "").strip()
        if marca_item and marca_pedida and marca_item != marca_pedida:
            continue
        try:
            fecha = date.fromisoformat(str(item.get("fecha") or "").strip())
        except ValueError:
            continue
        if fecha < corte:
            continue
        vigentes.append(item)
    vigentes.sort(
        key=lambda it: (str(it.get("fecha") or ""), str(it.get("creado") or "")), reverse=True
    )
    return vigentes[:TOPE_ITEMS]


def bloque_para_marca(marca: str) -> str:
    """Bloque de indicaciones vigentes de `marca`, BEST-EFFORT: nunca rompe un copy.

    Si la BD no está disponible (preview en entornos sin Postgres, fallo puntual),
    el copy sale SIN indicaciones (con warning), igual que los adjuntos editoriales
    best-effort de `generar.adjuntos_copy`.
    """
    try:
        return bloque_indicaciones(indicaciones_vigentes(marca))
    except Exception:  # noqa: BLE001 -- las indicaciones son guía extra; nunca rompen el copy
        _log.warning(
            "indicaciones del equipo no disponibles; el copy de %s sale sin ellas",
            marca or "(sin marca)",
        )
        return ""
