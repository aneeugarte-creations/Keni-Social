"""PIPELINES · constantes compartidas + utilidades de presentación.

Hogar único de los catálogos/constantes del feed de Producción y de tres helpers que usan
varios módulos del paquete (`_red_nombre`, `_marca_nombre`, `_qa_fuente_de`). No depende de
los módulos de endpoint (`feed`/`problemas`/`detalle`) ni del motor de etapas: es la base.
"""

from __future__ import annotations

import json

from ... import marcas, redes
from ...estados import ORIGENES_AUTOGEN
from ...pipeline_contenido import (
    ORIGEN_PIPELINE,
    TIPO_ACTIVIDAD,
    VERDICTO_NO_VERIFICADO,
    VERDICTO_PROBLEMA,
)

# Orígenes de tema que el feed acepta como RUN: los del propio pipeline (ingesta del pool) y
# los del TABLERO que su etapa de copy redacta (`ORIGENES_AUTOGEN`: rss/radar/equipo/historia/
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

# Catálogo de etapas del pipeline (clave → nombre) en orden de flujo. Fusión y Editorial son el
# trabajo del POOL (dedup + encaje/score), DERIVADO de la historia (cluster), no de un toggle.
# Selección/Validación/Copy son TOGGLABLES por marca (activa = estado real; desactivada = "saltada").
# Aprobación es el gate humano. `estado_global` toma la primera no-{ok,saltada}.
_ETAPAS = (
    ("fusion", "Fusión"),
    ("editorial", "Editorial"),
    ("ci", "Selección"),
    ("qa", "Validación"),
    ("cd", "Copy"),
    ("arte", "Arte"),
    ("aprobacion", "Aprobación"),
)
# Claves válidas para el filtro `?etapa=` (la etapa donde la run está parada). Catálogo de
# `_ETAPAS`, sin duplicar la fuente de verdad.
_ETAPA_CLAVES = frozenset(clave for clave, _ in _ETAPAS)
# Etapas que SON una llamada a un LLM (la UI las marca "IA" y enseña prompt+proceso+resultado).
# Selección (crea el tema en BD) y Aprobación (humana) NO lo son.
_ETAPAS_IA = frozenset({"fusion", "editorial", "qa", "cd", "arte"})
# Prompt de la Biblioteca de Texto que usa cada etapa IA (código de etapa → id editable). Permite
# enseñar el PROMPT de entrada SIEMPRE, aunque la etapa aún no haya corrido (plantilla).
_PROMPT_POR_ETAPA = {
    "FUSION": "prompt/fusion",
    "EDITORIAL": "prompt/editorial",
    "QA": "prompt/validacion",
    "CD": "prompt/copy",
    "ARTE": "prompt/arte",
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
# Prefijos de etiqueta de la IA del POOL (lote por marca): "Fusión de historias" alimenta
# la etapa Fusión y "Encaje editorial" la etapa Editorial. Fuente única para el detalle
# (enlazar la generación) y la lista (evidencia de que el pool corrió: fix "Saltada").
_PREFIJO_POOL_FUSION = "Fusión"
_PREFIJO_POOL_EDITORIAL = "Encaje"
# Métricas a cero de un item sin generaciones correlacionadas (forma estable para la UI).
_METRICAS_CERO = {"items": 0, "tokens": 0, "coste_usd": 0.0, "duration_ms": 0}
# Tope de runs a MATERIALIZAR antes de filtrar/paginar en memoria. El tablero del equipo es
# pequeño en el piloto; esto acota el coste si el histórico de runs creciera mucho (se sirven los
# más recientes). `log()` no aplica aquí: la paginación reporta el `total` ya acotado a esto.
_UNIVERSO_MAX = 500

# Estados de plataforma que cuentan como "aprobado" para la etapa de Aprobación.
_ESTADOS_APROBADOS = frozenset({"aprobado", "programado", "publicado"})
# Estados de plataforma "en curso" de revisión humana (aún no aprobados).
_ESTADOS_EN_CURSO = frozenset({"en_curso", "en_revision"})


def _red_nombre(red: str) -> str:
    return "Web" if red == "web" else redes.nombre_por_id(red)


def _marca_nombre(marca: str) -> str:
    return marcas.etiqueta_de(marca) if marca else ""


def _qa_fuente_de(item: dict) -> dict:
    """Veredicto ESTRUCTURADO de la criba de la fuente (rediseño QPC), para la UI.

    Lee el veredicto persistido en el TEMA (`qa_veredicto`/`qa_hallazgos`):
      - `no_verificado` (⚠️): apta, no verificada a fondo; las piezas llevan el aviso.
      - `problema` (❗): algo de peso; NO se generó copy. `hallazgos` trae el detalle.
    `hallazgos` se parsea del JSON guardado (`{resumen, hallazgos:[...]}`); [] si vacío/ilegible.
    """
    veredicto = (item.get("qa_veredicto", "") or "").strip()
    resumen = ""
    hallazgos: list[dict] = []
    crudo = (item.get("qa_hallazgos", "") or "").strip()
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
        "veredicto": veredicto,
        "no_verificado": veredicto == VERDICTO_NO_VERIFICADO,
        "problema": veredicto == VERDICTO_PROBLEMA,
        "copy_omitido": veredicto == VERDICTO_PROBLEMA,
        "resumen": resumen,
        "hallazgos": hallazgos,
    }
