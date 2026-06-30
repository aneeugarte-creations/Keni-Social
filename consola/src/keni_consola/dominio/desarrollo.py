"""Orquestador PURO del motor de auto-desarrollo (pipeline de fases estilo Nolan v2).

Decide QUÉ fase sigue según la complejidad y el estado, QUÉ modelo usa cada fase y CUÁNDO
se pausa para un checkpoint humano. NO toca BD, subprocess ni la cola: es lógica pura y
testeable. El `worker_dev` y la API consumen estas funciones para encadenar el pipeline.

Pipeline (Nolan v2): analyze → plan → build → review.
  - analyze (sonnet): entiende el problema y el repo.
  - plan    (opus):   diseña el cambio (qué tocar, qué tests) — la fase de más criterio.
  - build   (sonnet): implementa el cambio en el worktree siguiendo el plan.
  - review  (sonnet): revisa el diff y los tests antes del checkpoint humano.

Complejidad → forma del pipeline y checkpoints:
  - simple:   build → review            (sin discovery; checkpoint tras review).
  - standard: analyze→plan→build→review (checkpoint tras review).
  - complex:  analyze→plan→build→review (checkpoints tras plan y tras review).
"""

from __future__ import annotations

import re
from typing import Any

# Fases del pipeline.
FASE_ANALYZE = "analyze"
FASE_PLAN = "plan"
FASE_BUILD = "build"
FASE_REVIEW = "review"
FASES: tuple[str, ...] = (FASE_ANALYZE, FASE_PLAN, FASE_BUILD, FASE_REVIEW)

# Clase editorial de los prompts de desarrollo (semillas en `prompts_inicial/editorial/desarrollo/`).
CLASE_EDITORIAL = "desarrollo"

# Modelo por fase (Nolan v2): el diseño del cambio (plan) en opus; el resto, incluida la
# construcción, en sonnet.
MODELO_DEFECTO = "sonnet"
MODELO_FASE: dict[str, str] = {
    FASE_ANALYZE: "sonnet",
    FASE_PLAN: "opus",
    FASE_BUILD: "sonnet",
    FASE_REVIEW: "sonnet",
}

# Complejidades válidas (la estima el discovery; '' = aún sin estimar).
COMPLEJIDAD_DEFECTO = "standard"
COMPLEJIDADES: tuple[str, ...] = ("simple", "standard", "complex")

# Secuencia de fases por complejidad.
_PIPELINE: dict[str, tuple[str, ...]] = {
    "simple": (FASE_BUILD, FASE_REVIEW),
    "standard": (FASE_ANALYZE, FASE_PLAN, FASE_BUILD, FASE_REVIEW),
    "complex": (FASE_ANALYZE, FASE_PLAN, FASE_BUILD, FASE_REVIEW),
}

# Fases TRAS las cuales el pipeline se pausa esperando una decisión humana (checkpoint).
_CHECKPOINTS: dict[str, frozenset[str]] = {
    "simple": frozenset({FASE_REVIEW}),
    "standard": frozenset({FASE_REVIEW}),
    "complex": frozenset({FASE_PLAN, FASE_REVIEW}),
}


def _norm_complejidad(complejidad: str) -> str:
    """Complejidad normalizada a una conocida (defecto `standard` si viene vacía/ilegible)."""
    return complejidad if complejidad in COMPLEJIDADES else COMPLEJIDAD_DEFECTO


def requiere_discovery(complejidad: str) -> bool:
    """True si la sugerencia debe pasar por discovery antes de construir.

    Una `simple` toma el atajo (nueva → en_cola directo); el resto necesita discovery para
    fijar la complejidad y producir el SPEC. Una complejidad aún sin estimar ('') también
    pasa por discovery.
    """
    return complejidad != "simple"


def modelo_de(fase: str) -> str:
    """Modelo (sonnet/opus) que ejecuta la fase dada."""
    return MODELO_FASE.get(fase, MODELO_DEFECTO)


def pipeline_de(complejidad: str) -> tuple[str, ...]:
    """Secuencia de fases del pipeline para la complejidad dada."""
    return _PIPELINE[_norm_complejidad(complejidad)]


def primera_fase(complejidad: str) -> str:
    """Primera fase a ejecutar para la complejidad dada."""
    return pipeline_de(complejidad)[0]


def siguiente_fase(complejidad: str, fase_actual: str) -> str | None:
    """Fase que sigue a `fase_actual`, o None si el pipeline terminó.

    None significa que no hay más trabajo automático tras `fase_actual` (la última del
    pipeline para esa complejidad).
    """
    secuencia = pipeline_de(complejidad)
    if fase_actual not in secuencia:
        return None
    i = secuencia.index(fase_actual)
    return secuencia[i + 1] if i + 1 < len(secuencia) else None


def es_checkpoint(complejidad: str, fase: str) -> bool:
    """True si tras `fase` el pipeline pausa para un checkpoint humano."""
    return fase in _CHECKPOINTS.get(_norm_complejidad(complejidad), frozenset())


def estado_tras_fase(complejidad: str, fase: str) -> str:
    """Estado del kanban tras completar `fase`.

    `revision` si la fase es un checkpoint (espera decisión humana); en otro caso `building`
    (el pipeline sigue con la siguiente fase automáticamente).
    """
    return "revision" if es_checkpoint(complejidad, fase) else "building"


# --------------------------------------------------------------------------- #
# Composición de prompts (PURA: el cuerpo base se inyecta desde libprompts)     #
# --------------------------------------------------------------------------- #

# Anti prompt-injection: el texto del equipo (título/detalle/spec/plan) se envuelve para que
# el modelo lo trate como DATOS, no como instrucciones.
_INI = "<<<DATOS_SUGERENCIA"
_FIN = "DATOS_SUGERENCIA"


def _bloque(etiqueta: str, texto: str) -> str:
    """Bloque etiquetado y acotado con un dato de la sugerencia (vacío si no hay texto)."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    return f"## {etiqueta}\n{_INI}\n{texto}\n{_FIN}\n"


def componer_prompt(
    base: str, sugerencia: dict[str, Any], fase: str, *, nota: str = ""
) -> str:
    """Arma el prompt de una fase: el cuerpo `base` (clase `desarrollo`) + los datos de la sugerencia.

    `base` es el texto del prompt de la fase (lo carga el llamante desde la biblioteca de
    prompts). Se le adjunta el contexto acumulado de la sugerencia (título, detalle, SPEC del
    discovery, plan de la fase plan) envuelto anti-inyección. `nota` (opcional) es una indicación
    EFÍMERA del usuario para ESTE lanzamiento: se añade como bloque propio y el prompt avisa de
    que el humano la escribió a propósito para esta etapa. PURO: no lee ni escribe nada.
    """
    partes = [
        (base or "").strip(),
        f"# Fase actual: {fase}",
        _bloque("Título de la sugerencia", str(sugerencia.get("titulo", ""))),
        _bloque("Detalle", str(sugerencia.get("detalle", ""))),
        _bloque("Categoría", str(sugerencia.get("categoria", ""))),
        _bloque("SPEC (discovery)", str(sugerencia.get("spec", ""))),
        _bloque("Plan", str(sugerencia.get("plan", ""))),
    ]
    if (nota or "").strip():
        partes.append(_bloque("Nota del usuario para esta etapa", nota))
        partes.append(
            "El humano escribió la «Nota del usuario para esta etapa» a propósito al lanzar esta "
            "fase. Tenla en cuenta por encima del SPEC/plan previos."
        )
    return "\n\n".join(p for p in partes if p)


# --------------------------------------------------------------------------- #
# Parseo de salidas (PURO)                                                     #
# --------------------------------------------------------------------------- #

_RE_COMPLEJIDAD = re.compile(
    r"complejidad\s*[:=]\s*[\"']?(simple|standard|complex)\b", re.IGNORECASE
)


def parsear_discovery(salida: str) -> dict[str, str]:
    """Extrae `{spec, complejidad}` de la salida del discovery (PURO).

    `spec` es la salida completa (el SPEC markdown que escribió el modelo). `complejidad`
    sale de un marcador `complejidad: simple|standard|complex` (case-insensitive) en el texto;
    si no aparece uno reconocible, cae al defecto `standard`.
    """
    texto = (salida or "").strip()
    m = _RE_COMPLEJIDAD.search(texto)
    complejidad = m.group(1).lower() if m else COMPLEJIDAD_DEFECTO
    return {"spec": texto, "complejidad": complejidad}


def parsear_fase(salida: str, fase: str) -> dict[str, str]:
    """Extrae los campos a persistir de la salida de una fase (PURO).

    `plan` guarda la salida de la fase plan; `diff_resumen` la de build/review (el resumen
    del cambio que el modelo describe). Las demás fases no persisten texto propio.
    """
    texto = (salida or "").strip()
    if fase == FASE_PLAN:
        return {"plan": texto}
    if fase in (FASE_BUILD, FASE_REVIEW):
        return {"diff_resumen": texto}
    return {}
