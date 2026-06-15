"""Encaje de MARCA con IA (Haiku) para historias SIN marca (Trends/agencias).

PROBLEMA QUE CIERRA: las noticias de Tendencias/agencias entran al pool sin marca
(`marca=''`). Si el encaje por vocabulario (`agrupar.marca_por_vocabulario`) no las
casa, quedan invisibles por marca y NUNCA se auto-promueven al feed: `crear_tema_de_cluster`
descarta los clusters sin marca (`if not marca: return None`). Esto pasa sobre todo con los
BREAKING (última hora) genéricos.

Este módulo asigna a una de las marcas CANDIDATAS con una sola llamada a `claude -p` (Haiku).
Es BEST-EFFORT: ante cualquier duda (la IA no devuelve una candidata válida) o fallo
(subproceso/timeout/JSON inválido) cae a la marca de NOTICIAS GENERALES (`fallback`), para que
ninguna historia quede varada sin marca.

Ejecutor inyectable (tests): `clasificar_marca(..., ejecutor=fake)`; sin él se usa el
subproceso real (reutiliza el de traducción, que acumula las métricas de coste del paso).
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable, Sequence

from . import json_llm

_log = logging.getLogger("keni_consola.dominio.clasificador_marca")

# Misma firma que el ejecutor de traducción/insumos: (prompt, dir_permitido) -> salida.
Ejecutor = Callable[[str, str], str]

# Tope de caracteres de titulo+resumen al prompt (protege contra notas larguísimas).
_MAX_CHARS = 600

# El prompt vive en la Biblioteca de Texto como documento EDITABLE (pestaña «Prompts», doc
# `prompt/clasificar-marca`): el equipo lo ajusta sin tocar código. Las variables
# {{MARCAS}}, {{MARCA_FALLBACK}} y {{NOTICIA}} se sustituyen aquí al componer la llamada. La
# INICIAL del paquete (`texto_inicial/prompt/clasificar-marca.md`) es la ÚNICA fuente del
# texto: no hay copia duplicada en código (el test inicial↔código garantiza que existe).
_PROMPT_ID = "prompt/clasificar-marca"


def _plantilla() -> str:
    """Cuerpo EFECTIVO del prompt (publicado > store del equipo > INICIAL del paquete).

    Import diferido de `libtexto` (evita ciclos). `cuerpo_efectivo` ya cae a la inicial cuando
    el doc no está en el store; `cuerpo_inicial` es la red final si la lectura del store
    revienta (NUNCA lanza). "" solo si faltara la inicial (camino inalcanzable: lo cubre el
    test inicial↔código), y se avisa.
    """
    from .. import libtexto

    try:
        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- best-effort: caemos a la inicial del paquete
        cuerpo = ""
    cuerpo = cuerpo or libtexto.cuerpo_inicial(_PROMPT_ID).strip()
    if not cuerpo:
        _log.warning("clasificar_marca: %s no está en la Biblioteca ni en la inicial.", _PROMPT_ID)
    return cuerpo


def clasificar_marca(
    titulo: str,
    resumen: str,
    candidatas: Sequence[tuple[str, str]],
    *,
    fallback: str,
    ejecutor: Ejecutor | None = None,
) -> str:
    """Id de marca para una historia sin marca. Best-effort: ante duda/fallo -> `fallback`.

    Parámetros:
        titulo, resumen: la historia a clasificar.
        candidatas: `[(id, nombre)]` entre las que elegir.
        fallback: id de la marca de noticias generales (catch-all). Si no está entre las
            candidatas se devuelve igualmente cuando la IA no acierta (decisión del llamante).
        ejecutor: `(prompt, dir) -> salida` inyectable (tests). None = subproceso real.
    """
    ids = {c[0] for c in candidatas}
    if not ids:
        return fallback
    titulo = (titulo or "").strip()[:_MAX_CHARS]
    resumen = (resumen or "").strip()[: max(0, _MAX_CHARS - len(titulo))]
    if not titulo and not resumen:
        return fallback

    lineas = "\n".join(f"- {cid} — {nombre}" for cid, nombre in candidatas)
    noticia = json.dumps({"titulo": titulo, "resumen": resumen}, ensure_ascii=False)
    prompt = (
        _plantilla()
        .replace("{{MARCAS}}", lineas)
        .replace("{{MARCA_FALLBACK}}", fallback)
        .replace("{{NOTICIA}}", noticia)
    )

    correr = ejecutor or _ejecutar
    try:
        with tempfile.TemporaryDirectory(prefix="keni-clasif-marca-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> fallback
        _log.warning("clasificar_marca: fallo al llamar a claude: %s", e)
        return fallback

    data = json_llm.extraer_json(salida, dict)
    if isinstance(data, dict):
        marca = str(data.get("marca") or "").strip()
        if marca in ids:
            return marca
    _log.info(
        "clasificar_marca: sin marca válida en la respuesta (%r) -> fallback %s",
        (salida or "")[:120], fallback,
    )
    return fallback


def _ejecutar(prompt: str, carpeta: str) -> str:
    """Ejecutor real: reutiliza el subproceso `claude -p` de traducción (acumula métricas)."""
    from .traducir import _ejecutar_claude_json

    return _ejecutar_claude_json(prompt, carpeta)
