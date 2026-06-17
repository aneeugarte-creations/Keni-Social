"""PIPELINES · constantes compartidas + utilidades de presentación.

Hogar único de los catálogos/constantes del feed de Producción y de tres helpers que usan
varios módulos del paquete (`_red_nombre`, `_marca_nombre`, `_verificacion_fuente_de`). No depende de
los módulos de endpoint (`feed`/`problemas`/`detalle`) ni del motor de etapas: es la base.
"""

from __future__ import annotations

import json

from ... import marcas, redes
from ...estados import ORIGENES_AUTOGEN
from ...pipeline_contenido import (
    ORIGEN_PIPELINE,
    TIPO_ACTIVIDAD,
    VERIFICACION_RECHAZADO,
    VERIFICACION_REQUIERE_HUMANO,
    VERIFICACION_VERIFICADO,
)

# Orígenes de tema que el feed acepta como RUN: los del propio pipeline (recolección del pool) y
# los del TABLERO que su etapa Redactar redacta (`ORIGENES_AUTOGEN`: rss/radar/equipo/historia/
# import-calendario). Un tema de tablero solo se lista si la máquina lo TRABAJÓ (tiene
# generaciones del pipeline correlacionadas): el alta manual sin trabajo IA no es una run.
_ORIGENES_RUN = frozenset({ORIGEN_PIPELINE, *ORIGENES_AUTOGEN})
_TIPOS_TRABAJO_PIPELINE = frozenset({"pipeline", TIPO_ACTIVIDAD, "autogen"})

# Estado de etapa cuando su toggle está DESACTIVADO para la marca (1 toggle = 1 etapa): la etapa
# no se ejecuta y se pinta "Saltada" (no bloquea el estado global ni cuenta como fallo).
_ESTADO_SALTADA = "saltada"

# Tope por defecto de runs por página (alineado con el resto de la consola).
_LIMITE_DEF = 50
_LIMITE_MAX = 200

# Catálogo de etapas del pipeline (clave → nombre) en orden de flujo. Fusionar y Priorizar son el
# trabajo del POOL (dedup + encaje/score), DERIVADO de la historia (cluster), no de un toggle.
# Admitir/Verificar/Redactar son TOGGLABLES por marca (activa = estado real; desactivada = "saltada").
# Aprobar es el gate humano. `estado_global` toma la primera no-{ok,saltada}.
_ETAPAS = (
    ("fusionar", "Fusionar"),
    ("priorizar", "Priorizar"),
    ("admitir", "Admitir"),
    ("verificar", "Verificar"),
    ("redactar", "Redactar"),
    ("ilustrar", "Ilustrar"),
    ("aprobar", "Aprobar"),
)
# Claves válidas para el filtro `?etapa=` (la etapa donde la run está parada). Catálogo de
# `_ETAPAS`, sin duplicar la fuente de verdad.
_ETAPA_CLAVES = frozenset(clave for clave, _ in _ETAPAS)
# Etapas que SON una llamada a un LLM (la UI las marca "IA" y enseña prompt+proceso+resultado).
# Admitir (crea el tema en BD) y Aprobar (humana) NO lo son.
_ETAPAS_IA = frozenset({"fusionar", "priorizar", "verificar", "redactar", "ilustrar"})
# Prompt de la Prompts de Texto que usa cada etapa IA (código de etapa → id editable). Permite
# enseñar el PROMPT de entrada SIEMPRE, aunque la etapa aún no haya corrido (plantilla).
_PROMPT_POR_ETAPA = {
    "FUSIONAR": "prompt/fusionar",
    "PRIORIZAR": "prompt/priorizar",
    "VERIFICAR": "prompt/verificar",
    "REDACTAR": "prompt/redactar",
    "ILUSTRAR": "prompt/ilustrar",
}
# Valores válidos del filtro `?estado=` (el `estado_global` de la run).
_ESTADOS_GLOBAL = frozenset({"ok", "en_curso", "pendiente", "revisar", "fallo"})
# Valores válidos del filtro `?clase=` (qué mitad del feed unificado se quiere ver).
_CLASES = frozenset({"run", "actividad"})
# Estado de una generación/run de agente -> `estado_global` del item suelto (mismo chip
# que las runs). Lo que no casa (p. ej. un estado raro/legado) cae a "pendiente".
_ESTADO_ACTIVIDAD = {
    "completado": "ok",
    "error": "fallo",
    "ejecutando": "en_curso",
}
# Prefijos de etiqueta de la IA del POOL (lote por marca): "Fusionar historias" alimenta
# la etapa Fusionar y "Priorizar historias" la etapa Priorizar. Fuente única para el detalle
# (enlazar la generación) y la lista (evidencia de que el pool corrió: fix "Saltada").
_PREFIJO_POOL_FUSION = "Fusionar"
_PREFIJO_POOL_EDITORIAL = "Priorizar"
# Métricas a cero de un item sin generaciones correlacionadas (forma estable para la UI).
_METRICAS_CERO = {"items": 0, "tokens": 0, "coste_usd": 0.0, "duration_ms": 0}
# Tope de runs a MATERIALIZAR antes de filtrar/paginar en memoria. El tablero del equipo es
# pequeño en el piloto; esto acota el coste si el histórico de runs creciera mucho (se sirven los
# más recientes). `log()` no aplica aquí: la paginación reporta el `total` ya acotado a esto.
_UNIVERSO_MAX = 500

# Estados de plataforma que cuentan como "aprobado" para la etapa de Aprobar: la pieza ya pasó
# el gate humano (COLAPSO 2026-06: ya no hay estado de reposo `aprobado`; cuenta lo que salió).
_ESTADOS_APROBADOS = frozenset({"programado", "publicado"})
# Estados de plataforma "en curso" de revisión humana (aún no aprobados).
_ESTADOS_EN_CURSO = frozenset({"en_revision"})


def _red_nombre(red: str) -> str:
    return "Web" if red == "web" else redes.nombre_por_id(red)


def _marca_nombre(marca: str) -> str:
    return marcas.etiqueta_de(marca) if marca else ""


def _verificacion_fuente_de(item: dict) -> dict:
    """Verificacion ESTRUCTURADO de la verificación de la fuente (rediseño QPC), para la UI.

    Lee el verificacion persistido en el TEMA (`verificacion_fuente`/`verificar_hallazgos`):
      - `verificado` (✅): confirmada con fuentes; se auto-produjo.
      - `requiere_humano` (⚠️): la IA no pudo confirmar; NO se generó copy, a la mesa.
      - `rechazado` (❗): falso/sátira/legal; NO se generó copy. `hallazgos` trae el detalle.
    `hallazgos` se parsea del JSON guardado (`{resumen, hallazgos:[...]}`); [] si vacío/ilegible.
    """
    verificacion = (item.get("verificacion_fuente", "") or "").strip()
    resumen = ""
    hallazgos: list[dict] = []
    crudo = (item.get("verificar_hallazgos", "") or "").strip()
    if crudo:
        try:
            datos = json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            datos = None
        if isinstance(datos, dict):
            resumen = str(datos.get("resumen", "") or "")
            h = datos.get("hallazgos")
            if isinstance(h, list):
                hallazgos = [x for x in h if isinstance(x, dict)]
    return {
        "verificacion_fuente": verificacion,
        "verificado": verificacion == VERIFICACION_VERIFICADO,
        "requiere_humano": verificacion == VERIFICACION_REQUIERE_HUMANO,
        "rechazado": verificacion == VERIFICACION_RECHAZADO,
        "copy_omitido": verificacion in (VERIFICACION_REQUIERE_HUMANO, VERIFICACION_RECHAZADO),
        "resumen": resumen,
        "hallazgos": hallazgos,
    }
