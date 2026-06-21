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

# Ejecutor de la llamada a `claude`. Misma firma que el de traducción/insumos
# (`(prompt, dir_permitido) -> salida`), pero puede devolver dos formas:
#   - `str`: solo el texto `result` (se parsea con `json_llm`, camino histórico).
#   - `tuple[str, dict | None]`: `(texto_result, structured_output)`, cuando el run usó
#     `--json-schema` y trajo la salida estructurada YA validada. Si la hay, se usa directa.
SalidaEjecutor = str | tuple[str, "dict | None"]
Ejecutor = Callable[[str, str], SalidaEjecutor]

# Tope de caracteres de titulo+resumen al prompt (protege contra notas larguísimas).
_MAX_CHARS = 600

# El prompt vive en la Prompts de Texto como documento EDITABLE (pestaña «Prompts», doc
# `prompt/clasificar-marca`): el equipo lo ajusta sin tocar código. Las variables
# {{MARCAS}}, {{MARCA_FALLBACK}} y {{NOTICIA}} se sustituyen aquí al componer la llamada. La
# INICIAL del paquete (`prompts_inicial/prompt/clasificar-marca.md`) es la ÚNICA fuente del
# texto: no hay copia duplicada en código (el test inicial↔código garantiza que existe).
_PROMPT_ID = "prompt/clasificar-marca"


def _plantilla() -> str:
    """Cuerpo EFECTIVO del prompt (publicado > store del equipo > INICIAL del paquete).

    Import diferido de `libprompts` (evita ciclos). `cuerpo_efectivo` ya cae a la inicial cuando
    el doc no está en el store; `cuerpo_inicial` es la red final si la lectura del store
    revienta (NUNCA lanza). "" solo si faltara la inicial (camino inalcanzable: lo cubre el
    test inicial↔código), y se avisa.
    """
    from .. import libprompts

    try:
        cuerpo = (libprompts.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- best-effort: caemos a la inicial del paquete
        cuerpo = ""
    cuerpo = cuerpo or libprompts.cuerpo_inicial(_PROMPT_ID).strip()
    if not cuerpo:
        _log.warning("clasificar_marca: %s no está en la Prompts ni en la inicial.", _PROMPT_ID)
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

    # Esquema raíz: la salida estructurada debe ser `{"marca": <una de las candidatas>}`.
    # El enum acota a las ids candidatas, así una marca fuera de lista no valida y cae al
    # fallback (mismo criterio que el parse de texto).
    esquema = {
        "type": "object",
        "properties": {"marca": {"type": "string", "enum": sorted(ids)}},
        "required": ["marca"],
    }

    correr = ejecutor or _con_esquema(esquema)
    try:
        with tempfile.TemporaryDirectory(prefix="keni-clasif-marca-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> fallback
        _log.warning("clasificar_marca: fallo al llamar a claude: %s", e)
        return fallback

    texto, estructurado = _desempaquetar(salida)
    # Salida estructurada YA validada por `--json-schema`: úsala directa si trae candidata.
    if isinstance(estructurado, dict):
        marca = str(estructurado.get("marca") or "").strip()
        if marca in ids:
            return marca
    # Fallback robusto: parsea el texto libre `result` (camino histórico, ante ausencia o
    # invalidez de la salida estructurada).
    data = json_llm.extraer_json(texto, dict)
    if isinstance(data, dict):
        marca = str(data.get("marca") or "").strip()
        if marca in ids:
            return marca
    _log.info(
        "clasificar_marca: sin marca válida en la respuesta (%r) -> fallback %s",
        (texto or "")[:120], fallback,
    )
    return fallback


def _desempaquetar(salida: SalidaEjecutor) -> tuple[str, dict | None]:
    """Normaliza la salida del ejecutor a `(texto, structured_output)`.

    Acepta tanto la forma histórica (`str` = solo texto) como la nueva
    (`tuple[str, dict | None]`), para no romper los ejecutores que solo devuelven texto.
    """
    if isinstance(salida, tuple):
        texto, estructurado = salida
        return str(texto or ""), (estructurado if isinstance(estructurado, dict) else None)
    return str(salida or ""), None


def _con_esquema(esquema: dict) -> Ejecutor:
    """Ejecutor real con `--json-schema`: devuelve `(texto, structured_output)`.

    Reutiliza el subproceso `claude -p` de traducción (acumula métricas). Pasa el esquema raíz
    para que la salida estructurada venga validada; `claude` la entrega en `structured_output`.
    """
    def _ej(prompt: str, carpeta: str) -> tuple[str, dict | None]:
        from .traducir import _ejecutar_claude_json_estructurado

        return _ejecutar_claude_json_estructurado(prompt, carpeta, json_schema=esquema)

    return _ej
