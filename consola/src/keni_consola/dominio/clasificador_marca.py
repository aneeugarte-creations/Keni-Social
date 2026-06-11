"""Encaje de MARCA con IA (Haiku) para historias SIN marca (Trends/agencias).

PROBLEMA QUE CIERRA: las noticias de Tendencias/agencias entran al pool sin marca
(`marca=''`). Si el encaje por vocabulario (`clustering.marca_por_vocabulario`) no las
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

_PROMPT = (
    "Eres el editor que reparte las noticias entrantes entre las marcas de un grupo de "
    "medios. Clasifica la noticia en la marca que mejor le cuadre por TEMÁTICA.\n"
    "Marcas disponibles (id — nombre):\n{marcas}\n"
    "Si la noticia es de interés general y no encaja claramente en una temática específica "
    "(p. ej. deportes o videojuegos), elige la marca de noticias generales: «{fallback}».\n"
    'Responde SOLO con un JSON: {{"marca": "<id>", "confianza": <0..1>}}. El id debe ser '
    "uno de los listados.\n\n"
    "Noticia:\n{noticia}"
)


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
    prompt = _PROMPT.format(marcas=lineas, fallback=fallback, noticia=noticia)

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
    from .traduccion import _ejecutar_claude_json

    return _ejecutar_claude_json(prompt, carpeta)
