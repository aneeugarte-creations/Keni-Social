"""Taller GREEN / brainstorming: lanzar la PROPUESTA de ideas evergreen + su post-procesado.

CONCEPTO: la IA NO genera contenido evergreen a ciegas. PROPONE una lista de IDEAS; una
persona las APRUEBA o las DESCARTA; y solo para las aprobadas se genera la pieza
(`flujo='evergreen'` en el tablero). Este modulo cubre el primer paso (proponer ideas):

  - `parsear_ideas`: dominio PURO. Saca las ideas del `{"ideas":[{"titulo","descripcion"}]}`
    que devuelve `claude -p` (tolera bloques ```json cercados y razonamiento alrededor), las
    sanea (titulo obligatorio, recortes, sin duplicados por titulo) y las devuelve como dicts.
  - `lanzar_propuesta`: compone el prompt (semilla `brainstorming-green` + editorial de marca +
    contexto opcional) y ENCOLA el job con el lanzador NEUTRO (`generar.lanzar`).
  - `construir_procesar_green_ideas`: el callback que corre en el WORKER al terminar: parsea la
    salida y crea las filas `green_ideas` (estado `propuesta`, origen `ia`), enlazadas al
    `generacion_id` del lote para trazabilidad.

La generacion de la PIEZA de una idea aprobada NO vive aqui: la dispara `api/green` con el
lanzador de copy existente (`generar.lanzar_copy`, `flujo='evergreen'`).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .. import biblioteca, repos
from ..estados import ESTADO_GREEN_PROPUESTA
from . import generar

_log = logging.getLogger("keni_consola.green")

# Prompt semilla que pide N ideas evergreen como JSON. Viaja en la biblioteca semilla.
PROMPT_BRAINSTORMING = "prompt/brainstorming-green"

# Topes defensivos: cuantas ideas importamos de una salida y longitudes maximas por campo.
MAX_IDEAS = 10
_MAX_TITULO = 200
_MAX_DESCRIPCION = 2000

# Bloque ```json ... ``` cercado (tolera "json"/"JSON" y espacios). Igual criterio que el
# resto del producto (`stream._RE_BLOQUE_JSON`).
_RE_BLOQUE_JSON = re.compile(r"```[ \t]*[jJ][sS][oO][nN]?[ \t]*\r?\n(.*?)```", re.DOTALL)


def _cargar_json_tolerante(s: str) -> Any | None:
    """`json.loads` tolerante: si el texto trae prefijo/sufijo, reintenta desde el 1er `[`/`{`."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        inicio = next((i for i, c in enumerate(s) if c in "[{"), -1)
        if inicio < 0:
            return None
        try:
            return json.loads(s[inicio:])
        except (json.JSONDecodeError, ValueError):
            return None


def _ideas_crudas(texto: str) -> list[Any] | None:
    """Saca la lista cruda de ideas del texto de claude (tolera fences y dict envoltorio).

    Acepta una lista JSON cruda o un objeto `{"ideas": [...]}` (o `items`), opcionalmente
    dentro de un bloque cercado ```json. Devuelve la lista (sin sanear) o None si no hay JSON.
    """
    if not isinstance(texto, str) or not texto.strip():
        return None
    s = texto.strip()
    cercados = re.findall(_RE_BLOQUE_JSON, s)
    candidatos = [c.strip() for c in cercados if c.strip()] or [s]
    for crudo in reversed(candidatos):  # el ULTIMO bloque suele ser el JSON final
        data = _cargar_json_tolerante(crudo)
        if data is None:
            continue
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for clave in ("ideas", "items"):
                if isinstance(data.get(clave), list):
                    return data[clave]
    return None


def parsear_ideas(salida: str) -> list[dict[str, str]]:
    """Parsea la salida de claude en una lista saneada de `{titulo, descripcion}`. PURO.

    Reglas: el `titulo` es OBLIGATORIO (se omite la idea sin titulo); `descripcion` es opcional.
    Se recortan longitudes, se ignoran entradas que no sean objeto y se DEDUPLICAN por titulo
    (case-insensitive). Tope de `MAX_IDEAS`. Devuelve [] si no hay JSON legible.
    """
    crudas = _ideas_crudas(salida)
    if not crudas:
        return []
    ideas: list[dict[str, str]] = []
    vistos: set[str] = set()
    for cruda in crudas:
        if not isinstance(cruda, dict):
            continue
        titulo = str(cruda.get("titulo", "") or "").strip()[:_MAX_TITULO]
        if not titulo:
            continue
        clave = titulo.lower()
        if clave in vistos:
            continue
        descripcion = str(cruda.get("descripcion", "") or "").strip()[:_MAX_DESCRIPCION]
        vistos.add(clave)
        ideas.append({"titulo": titulo, "descripcion": descripcion})
        if len(ideas) >= MAX_IDEAS:
            break
    return ideas


def lanzar_propuesta(
    *,
    marca: str,
    contexto: str = "",
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compone el prompt de brainstorming y ENCOLA el job que PROPONE ideas evergreen.

    El post-procesado (crear las filas `green_ideas`) corre en el worker via el spec
    `PROC_GREEN_IDEAS`. Devuelve el registro de generacion (para sondeo). `contexto` (opcional)
    es material del usuario (tono, temas a evitar, etc.) que se adjunta envuelto y anti-inyeccion.

    NOTA: el `generacion_id` que se enlaza en cada fila `green_ideas` queda "" en este camino:
    el id real lo crea `generar.lanzar` DESPUES de construir el spec, y el worker reconstruye el
    `procesar` solo desde el spec (no recibe el id). Es un enlace de trazabilidad opcional; las
    ideas se crean igual. Wirearlo requeriria que el worker inyecte el gen_id al `procesar`.
    """
    cuerpo = biblioteca.cuerpo_efectivo(biblioteca.prompt_base_de("green"))
    if cuerpo is None:
        raise biblioteca.BibliotecaError(
            "No está disponible el prompt de brainstorming. Reinstala la Consola."
        )
    prompt = generar.componer(
        cuerpo, biblioteca.editoriales_de_marca(marca, pipeline="green"), contexto, sin_emojis=True
    )
    # Import perezoso del jobspec para no acoplar; el spec NO lleva la generacion_id real (la
    # crea `generar.lanzar`), pero el worker la inyecta al reconstruir el procesar.
    from . import jobspec

    procesar_spec = jobspec.construir_green_ideas(marca=marca, autor=autor)
    return generar.lanzar(
        tipo="green-ideas",
        titulo="Ideas evergreen",
        marca=marca,
        prompt=prompt,
        procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
        procesar_spec=procesar_spec,
        autor=autor,
        # Brainstorming = SALIDA ESTRUCTURADA (se parsea a filas `green_ideas`; el usuario no ve
        # la salida cruda): bajo riesgo de exfiltración por el canal de salida. No se veta la web
        # por-callsite; queda la veta global `Bash Write Edit`.
    )


def construir_procesar_green_ideas(*, marca: str, generacion_id: str = ""):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del taller GREEN (worker).

    Parsea la salida de claude y crea una fila `green_ideas` por cada idea (estado `propuesta`,
    origen `ia`, enlazada a `generacion_id`). Devuelve un resumen `{ideas, ids}` para el registro.
    Si no hay ideas legibles, no crea nada (no es un error duro: el equipo puede reintentar).
    """

    def procesar(salida: str, _metricas: object) -> dict[str, Any]:
        ideas = parsear_ideas(salida or "")
        ids: list[str] = []
        for idea in ideas:
            fila = repos.crear_green_idea(
                marca=marca,
                titulo=idea["titulo"],
                descripcion=idea["descripcion"],
                estado=ESTADO_GREEN_PROPUESTA,
                origen="ia",
                generacion_id=generacion_id,
            )
            ids.append(fila["id"])
        if not ids:
            _log.info("taller green: claude no devolvió ideas legibles (marca=%s)", marca)
        return {"ideas": len(ids), "ids": ids}

    return procesar


__all__ = [
    "PROMPT_BRAINSTORMING",
    "construir_procesar_green_ideas",
    "lanzar_propuesta",
    "parsear_ideas",
]
