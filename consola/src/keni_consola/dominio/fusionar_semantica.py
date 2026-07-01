"""Fusionar SEMÁNTICAMENTE historias del MISMO evento con claude (Fase 2b).

El agrupar léxico (agrupar.asignar) une variantes claras del MISMO titular (url canónica o
título fuzzy ≥ umbral), pero NO une coberturas del mismo evento con titulares distintos
("Zelensky responde" vs "Rusia lanza misiles"). Esta capa, OPCIONAL y gateada, le pasa a Haiku el
lote de historias recientes de una marca y le pide AGRUPAR las que son del mismo evento; el daemon
fusiona cada grupo en una sola historia (n_fuentes real → mejor señal de tendencia/corroboración).

Este módulo es NEUTRO y PURO de I/O: solo construye el prompt, llama al ejecutor (inyectable en
tests) y parsea los grupos. Fusionar de verdad (reasignar items + borrar absorbidos + recalcular)
lo hace el daemon (`recolectar_daemon`), que es quien tiene los repos. BEST-EFFORT: ante cualquier
fallo devuelve `Fusiones([], [])` (no se fusiona ni etiqueta nada).

UNA PASADA del LLM (prompt `fusionar`) resuelve DOS agrupados del mismo lote, que antes eran dos
llamadas paralelas que leían los mismos titulares:
  - `grupos`: historias que son el MISMO HECHO concreto → el daemon las FUNDE en una.
  - `familias`: historias DISTINTAS de un mismo GRAN evento (cumbre, torneo, desastre…) → el daemon
    las ETIQUETA con `tema_macro` (no las funde); producción arma un carrusel del evento.

Los grupos pueden pasar por una VERIFICACIÓN por grupo (prompt `fusionar-verificar`, «Cotejar»),
GATEADA por `KENI_FUSION_COTEJAR` (def OFF): re-pregunta con SOLO esas historias y el grupo sale
confirmado, PARTIDO en subgrupos o descartado (fusionar por error es caro: infla la corroboración y
auto-produce piezas con fuentes que no hablan de lo mismo — pasó con «Shakira en la inauguración»
fundida con «alerta de la embajada» por el «Mundial»). Con Cotejar OFF los grupos de la pasada
principal se aceptan tal cual. Las familias NO se verifican (no se funden). La pasada principal y
Cotejar usan `config.fusion_modelo()` (sonnet); Subtema usa `config.subtema_modelo()` (haiku).
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from . import json_llm

_log = logging.getLogger("keni_consola.dominio.fusionar_semantica")

Ejecutor = Callable[[str, str], str]


class Fusiones(NamedTuple):
    """Salida de `proponer_fusiones`: dos agrupados del MISMO lote en una sola pasada del LLM.

    `grupos`: ids del MISMO hecho concreto (ya verificados) que el daemon FUNDE.
    `familias`: `{tema, ids}` de historias DISTINTAS del mismo gran evento que el daemon ETIQUETA.
    """

    grupos: list[list[str]]
    familias: list[dict[str, Any]]

# Cotas de tamaño del prompt.
_MAX_CLUSTERS = 40           # historias por lote que se mandan a Haiku
_MAX_CHARS_ITEM = 240        # recorte del titulo por historia


# La plantilla vive en la Prompts de Texto como prompt EDITABLE (pestaña «Prompts»). La lista
# JSON de historias se inserta en `{{HISTORIAS}}`. Si el store fallara, la red es la INICIAL del
# paquete (fuente única, sin texto duplicado aquí).
_PROMPT_ID = "prompt/fusionar"
_PROMPT_VERIFICACION_ID = "prompt/fusionar-verificar"
_PROMPT_SUBTEMA_ID = "prompt/fusionar-subtema"
_MARCA_HISTORIAS = "{{HISTORIAS}}"


def _plantilla(prompt_id: str = _PROMPT_ID) -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > inicial del paquete)."""
    from .. import libprompts

    try:
        cuerpo = (libprompts.cuerpo_efectivo(prompt_id) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar Fusionar sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libprompts.cuerpo_inicial(prompt_id).strip()


def _construir_prompt(payload_json: str, prompt_id: str = _PROMPT_ID) -> str:
    """Prompt de agrupación/verificación (plantilla editable + lista JSON de historias)."""
    plantilla = _plantilla(prompt_id)
    if _MARCA_HISTORIAS in plantilla:
        return plantilla.replace(_MARCA_HISTORIAS, payload_json)
    return f"{plantilla}\n\nHistorias:\n{payload_json}"


def _extraer_grupos(texto: str) -> list[list[str]]:
    """Extrae los grupos de ids del texto de Haiku (extractor compartido). [] si falla."""
    bruto = json_llm.extraer_lista(texto, claves=("grupos",))
    if bruto is None:
        return []
    grupos: list[list[str]] = []
    for g in bruto:
        if isinstance(g, list):
            ids = [str(x) for x in g if isinstance(x, (str, int))]
            if len(ids) >= 2:
                grupos.append(ids)
    return grupos


def _payload_clusters(clusters: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(validos, payload)` del lote: clusters con `{id, titulo}` (≤`_MAX_CLUSTERS`) y su payload JSON.

    El payload lleva `id`, `titulo` (truncado) y `tema_macro` (etiqueta de familia actual, para que el
    modelo REUTILICE verbatim una existente), nunca `resumen`. PURO. Fuente ÚNICA de la construcción
    del lote, compartida por `construir_prompt_fusion` (encolar) y `procesar_fusiones` (worker).
    """
    validos = [c for c in clusters if (c.get("id") and (c.get("titulo") or "").strip())][:_MAX_CLUSTERS]
    payload = [
        {
            "id": str(c["id"]),
            "titulo": json_llm.truncar_avisando(
                str(c.get("titulo", "")).strip(), _MAX_CHARS_ITEM,
                campo=f"titulo de {c['id']}", log=_log,
            )[0],
            # Etiqueta de familia ACTUAL del cluster (puede estar vacía): se manda para que el modelo
            # REUTILICE verbatim una etiqueta existente en vez de inventar un sinónimo.
            "tema_macro": str(c.get("tema_macro") or ""),
        }
        for c in validos
    ]
    return validos, payload


def construir_prompt_fusion(clusters: list[dict[str, Any]]) -> str:
    """Prompt de la pasada PRINCIPAL de fusión (plantilla + lista JSON del lote), o "" si <2 válidos.

    Lo usa el paso de Recolección para componer el prompt del JOB que ENCOLA por marca: el worker lo
    corre con `claude -p` (modelo `config.fusion_modelo()`) y su salida es la propuesta de grupos +
    familias que `procesar_fusiones` parsea y verifica. PURO.
    """
    validos, payload = _payload_clusters(clusters)
    if len(validos) < 2:
        return ""
    return _construir_prompt(json.dumps(payload, ensure_ascii=False))


def procesar_fusiones(
    salida: str,
    clusters: list[dict[str, Any]],
    *,
    ejecutor: Ejecutor | None = None,
    al_ejecutar: Callable[[str, str], None] | None = None,
) -> Fusiones:
    """Parsea la salida de la pasada PRINCIPAL y VERIFICA los grupos. PURO de repos.

    `salida` es el texto de la pasada principal (la corre el worker con `claude -p`, o `proponer_
    fusiones` en el camino síncrono). Devuelve `grupos` (mismo hecho, DISJUNTOS, ids del input, ≥2,
    VERIFICADOS) y `familias` (`{tema, ids}`, mismo gran evento, ≥2). La verificación («Cotejar»)
    re-pregunta cada grupo con `ejecutor` (`_ejecutar_haiku` por defecto). `al_ejecutar(prompt,
    salida)` recibe el prompt+salida REALES de cada llamada de VERIFICACIÓN (observabilidad).
    `Fusiones([], [])` ante <2 historias.
    """
    validos, payload = _payload_clusters(clusters)
    if len(validos) < 2:
        return Fusiones([], [])
    ids_validos = {str(c["id"]) for c in validos}
    correr = ejecutor or _ejecutar_haiku

    # GRUPOS (a fundir): disjuntos, solo ids del input, ≥2.
    vistos: set[str] = set()
    salida_grupos: list[list[str]] = []
    for grupo in _extraer_grupos(salida):
        limpio = [i for i in dict.fromkeys(grupo) if i in ids_validos and i not in vistos]
        if len(limpio) >= 2:
            vistos.update(limpio)
            salida_grupos.append(limpio)

    # FAMILIAS (a etiquetar, NO se funden): {tema, ids} con ids del input, sin repetir DENTRO, ≥2.
    familias: list[dict[str, Any]] = []
    for f in _extraer_familias(salida):
        ids = [i for i in dict.fromkeys(f["ids"]) if i in ids_validos]
        if len(ids) >= 2:
            familias.append({"tema": f["tema"], "ids": ids})

    # VERIFICACIÓN («Cotejar»), GATEADA por `KENI_FUSION_COTEJAR` (def OFF): con OFF los grupos de la
    # pasada principal se aceptan tal cual (ya salen disjuntos, ≥2 e ids del input: salida válida sin
    # sub-llamadas de cotejo). Con ON cada grupo se re-pregunta con un prompt enfocado (solo esas
    # historias) y el verificador confirma, PARTE en subgrupos o descarta; un grupo que no la supera NO
    # se funde (conservador). Las familias no se verifican. El parseo y los ejecutores de test no cambian.
    from .. import config

    if not config.fusion_cotejar_activo():
        return Fusiones(salida_grupos, familias)
    payload_por_id = {q["id"]: q for q in payload}
    confirmados: list[list[str]] = []
    for grupo in salida_grupos:
        confirmados.extend(_verificar_grupo(grupo, payload_por_id, correr, al_ejecutar))
    return Fusiones(confirmados, familias)


def proponer_fusiones(
    clusters: list[dict[str, Any]],
    *,
    ejecutor: Ejecutor | None = None,
    al_ejecutar: Callable[[str, str], None] | None = None,
) -> Fusiones:
    """En UNA pasada del LLM propone `grupos` (mismo hecho, a fundir) y `familias` (mismo gran
    evento, a etiquetar). PURO de repos.

    `clusters`: dicts con al menos `{id, titulo}` (y `tema_macro` opcional, que viaja en el payload
    para que las familias REUTILICEN una etiqueta existente). Los `grupos` salen VÁLIDOS, DISJUNTOS y
    VERIFICADOS (ids del input, sin repetir entre grupos, ≥2); las `familias` son `{tema, ids}` con
    ids válidos del input (≥2). `Fusiones([], [])` ante <2 historias o cualquier fallo de la llamada.

    `al_ejecutar(prompt, salida)`: callback OPCIONAL con el PROMPT y la SALIDA reales del LLM tras
    cada llamada (antes de parsear). El daemon lo usa para registrar la actividad IA de Fusionar con
    el LLM real; un fallo del callback no afecta a Fusionar (es observabilidad).

    Camino SÍNCRONO (corre la pasada principal con `ejecutor` y delega el parseo+verificación a
    `procesar_fusiones`). El camino ENCOLADO separa ambas: el worker corre la principal y el
    post-procesado llama a `procesar_fusiones`.
    """
    prompt = construir_prompt_fusion(clusters)
    if not prompt:
        return Fusiones([], [])
    correr = ejecutor or _ejecutar_haiku
    try:
        with tempfile.TemporaryDirectory(prefix="keni-fusion-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> no fusiona nada
        _log.warning("fusionar_semantica: falló la llamada a Haiku: %s", e)
        return Fusiones([], [])
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusionar_semantica: fallo en al_ejecutar.", exc_info=True)
    return procesar_fusiones(salida, clusters, ejecutor=ejecutor, al_ejecutar=al_ejecutar)


def _verificar_grupo(
    grupo: list[str],
    payload_por_id: dict[str, dict[str, Any]],
    correr: Ejecutor,
    al_ejecutar: Callable[[str, str], None] | None,
) -> list[list[str]]:
    """Verifica UN grupo propuesto; devuelve los subgrupos confirmados (subset, ≥2, disjuntos)."""
    # La verificación juzga "mismo HECHO concreto": solo {id, titulo}, sin `tema_macro` (un tema
    # compartido NO basta para fundir, así que no debe entrar como ruido en el prompt de Cotejar).
    payload = [{"id": payload_por_id[i]["id"], "titulo": payload_por_id[i]["titulo"]}
               for i in grupo if i in payload_por_id]
    if len(payload) < 2:
        return []
    prompt = _construir_prompt(
        json.dumps(payload, ensure_ascii=False), prompt_id=_PROMPT_VERIFICACION_ID
    )
    try:
        with tempfile.TemporaryDirectory(prefix="keni-fusion-verifica-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- conservador: sin verificación no se funde
        _log.warning("fusionar_semantica: falló la verificación del grupo (%s); se descarta.", e)
        return []
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusionar_semantica: fallo en al_ejecutar (verificación).", exc_info=True)
    miembros = set(grupo)
    vistos: set[str] = set()
    confirmados: list[list[str]] = []
    for g in _extraer_grupos(salida):
        limpio = [i for i in dict.fromkeys(g) if i in miembros and i not in vistos]
        if len(limpio) >= 2:
            vistos.update(limpio)
            confirmados.append(limpio)
    return confirmados


def _extraer_familias(texto: str) -> list[dict[str, Any]]:
    """Extrae las familias de macro-evento del texto de Haiku. [] si falla.

    Cada familia es `{"tema": "<etiqueta>", "ids": ["id1", "id2", ...]}`; descarta entradas mal
    formadas (sin lista de ids o con tema vacío). El extractor compartido tolera fences/prosa.
    """
    bruto = json_llm.extraer_lista(texto, claves=("familias",))
    if bruto is None:
        return []
    familias: list[dict[str, Any]] = []
    for f in bruto:
        if not isinstance(f, dict):
            continue
        tema = str(f.get("tema", "") or "").strip()
        crudo = f.get("ids")
        if not tema or not isinstance(crudo, list):
            continue
        ids = [str(x) for x in crudo if isinstance(x, (str, int))]
        if ids:
            familias.append({"tema": tema, "ids": ids})
    return familias


def _extraer_subtemas(texto: str) -> list[dict[str, Any]]:
    """Extrae los subtemas de un macro-evento del texto de Haiku. [] si falla.

    Cada subtema es `{"subtema": "<etiqueta>", "ids": ["id1", ...]}`; a diferencia de las
    familias, un subtema válido puede tener UN solo id (faceta con una sola historia).
    """
    bruto = json_llm.extraer_lista(texto, claves=("subtemas",))
    if bruto is None:
        return []
    subtemas: list[dict[str, Any]] = []
    for s in bruto:
        if not isinstance(s, dict):
            continue
        etiqueta = str(s.get("subtema", "") or "").strip()
        crudo = s.get("ids")
        if not etiqueta or not isinstance(crudo, list):
            continue
        ids = [str(x) for x in crudo if isinstance(x, (str, int))]
        if ids:
            subtemas.append({"subtema": etiqueta, "ids": ids})
    return subtemas


def proponer_subtemas(
    clusters: list[dict[str, Any]],
    *,
    ejecutor: Ejecutor | None = None,
    al_ejecutar: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Parte un MACRO-EVENTO ya etiquetado en SUBTEMAS coherentes (Haiku). PURO de repos.

    `clusters`: las historias de UNA familia de macro-evento (dicts con `{id, titulo}` y
    `subtema` opcional para reutilizar la etiqueta). Devuelve `[{"subtema": "<etiqueta>",
    "ids": [...]}, ...]` con cada id en UN solo subtema (disjuntos, del input). Un subtema
    puede tener un solo id. [] ante <2 historias o cualquier fallo (best-effort).

    Separa el evento por FACETA (partidos, incidentes, espectáculo…) para que cada carrusel
    sea de un tipo (un concierto no entra en el resumen de partidos) y la cadencia sea por
    subtema, no por el evento entero.
    """
    validos = [c for c in clusters if (c.get("id") and (c.get("titulo") or "").strip())][:_MAX_CLUSTERS]
    if len(validos) < 2:
        return []
    ids_validos = {str(c["id"]) for c in validos}

    payload = [
        {
            "id": str(c["id"]),
            "titulo": json_llm.truncar_avisando(
                str(c.get("titulo", "")).strip(), _MAX_CHARS_ITEM,
                campo=f"titulo de {c['id']}", log=_log,
            )[0],
            # Subtema ACTUAL del cluster (puede estar vacío): que Haiku REUTILICE la etiqueta.
            "subtema": str(c.get("subtema") or ""),
        }
        for c in validos
    ]
    # Subtema corre con SU PROPIO modelo (`config.subtema_modelo()`, def haiku): repartir ids por
    # faceta es una clasificación acotada, aparte de la pasada PRINCIPAL de Fusionar (sonnet).
    correr = ejecutor or _ejecutar_subtema
    prompt = _construir_prompt(
        json.dumps(payload, ensure_ascii=False), prompt_id=_PROMPT_SUBTEMA_ID
    )
    try:
        with tempfile.TemporaryDirectory(prefix="keni-subtema-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> no parte nada
        _log.warning("fusionar_semantica: falló la llamada a Haiku (subtema): %s", e)
        return []
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusionar_semantica: fallo en al_ejecutar (subtema).", exc_info=True)

    vistos: set[str] = set()
    subtemas: list[dict[str, Any]] = []
    for s in _extraer_subtemas(salida):
        # Solo ids del input, sin repetir entre subtemas (disjuntos), preservando orden.
        ids = [i for i in dict.fromkeys(s["ids"]) if i in ids_validos and i not in vistos]
        if ids:
            vistos.update(ids)
            subtemas.append({"subtema": s["subtema"], "ids": ids})
    return subtemas


def _ejecutar_haiku(prompt: str, dir_permitido: str) -> str:
    """Ejecutor real: el runner síncrono de `traduccion` con el modelo de la fusión.

    El modelo real lo decide `config.fusion_modelo()` (def sonnet). La fusión es una
    clasificación INLINE (agrupar ids por evento): se acota a NO agéntica —`max_turns=1` y
    `sin_tools=True` (sin `--add-dir`)— para que el modelo responda en un turno sin abrir un
    bucle de herramientas.
    """
    from .. import config
    from .traducir import _ejecutar_claude_json

    return _ejecutar_claude_json(
        prompt, dir_permitido, modelo=config.fusion_modelo(),
        max_turns=1, sin_tools=True,
    )


def _ejecutar_subtema(prompt: str, dir_permitido: str) -> str:
    """Ejecutor de Subtema: el runner síncrono con el modelo de Subtema (`config.subtema_modelo()`).

    Separado de `_ejecutar_haiku` (que usa `fusion_modelo`, sonnet): facetear un macro-evento en
    subtemas es una clasificación acotada y va con haiku por defecto, sin tocar el modelo de la
    fusión PRINCIPAL. No agéntica: `max_turns=1` y `sin_tools=True` (un turno, sin bucle de tools).
    """
    from .. import config
    from .traducir import _ejecutar_claude_json

    return _ejecutar_claude_json(
        prompt, dir_permitido, modelo=config.subtema_modelo(),
        max_turns=1, sin_tools=True,
    )


# --------------------------------------------------------------------------- #
# FUNDIR un grupo (mutación de repos, anti-TOCTOU) y etiquetar familias         #
# --------------------------------------------------------------------------- #


def _etiqueta_canonica(ids: list[str], por_id: dict[str, dict[str, Any]], propuesta: str) -> str:
    """Etiqueta ESTABLE de una familia de macro-evento: backstop determinista contra los sinónimos.

    Reúsa la `tema_macro` YA persistida que MÁS clusters de la familia comparten (así el mismo
    evento no se parte en «Mundial 2026» vs «Copa del Mundo 2026»: si Haiku agrupa ambos, gana la
    etiqueta dominante y se unifican). Cae a `propuesta` (la que propuso Haiku) solo si NINGÚN
    cluster de la familia traía etiqueta. Determinista: a empate de conteo, orden alfabético.
    """
    conteo: dict[str, int] = {}
    for i in ids:
        existente = str((por_id.get(i) or {}).get("tema_macro") or "").strip()
        if existente:
            conteo[existente] = conteo.get(existente, 0) + 1
    if not conteo:
        return propuesta
    return max(sorted(conteo), key=lambda e: conteo[e])


def _falta_subtema(ids: list[str], por_id: dict[str, dict[str, Any]]) -> bool:
    """True si algún cluster de la familia aún no tiene `subtema` (etiquetado incremental).

    Una familia con TODOS sus clusters ya faceteados no se reenvía a Haiku: re-proponer subtemas
    sobre una familia estable reescribiría la misma etiqueta y pagaría un Haiku por barrido.
    """
    return any(not str((por_id.get(i) or {}).get("subtema") or "").strip() for i in ids)


def _partir_en_subtemas(
    tema: str, ids: list[str], por_id: dict[str, dict[str, Any]],
    *, ejecutor: Ejecutor | None,
    al_ejecutar: Callable[[str, str], None] | None = None,
) -> int:
    """Parte una familia de macro-evento en SUBTEMAS (Haiku) y los persiste. Devuelve nº etiquetados.

    Cada subtema (faceta: «Partidos», «Espectáculo»…) agrupa los clusters de un tipo, para que el
    carrusel sea coherente y la cadencia sea por subtema. Best-effort: cualquier fallo (Haiku o
    persistencia) se loguea y devuelve lo que llevara, sin abortar el paso.

    `al_ejecutar(prompt, salida)` recibe el prompt+salida REALES de la llamada de subtema
    (observabilidad: el job de fusión lo usa para sellar su gasto bajo la etapa «Subtema»).
    """
    from .. import repos

    familia = [por_id[i] for i in ids if i in por_id]
    if len(familia) < 2:
        return 0
    try:
        grupos = proponer_subtemas(familia, ejecutor=ejecutor, al_ejecutar=al_ejecutar)
    except Exception:  # noqa: BLE001 -- un fallo de Haiku no aborta el etiquetado del evento
        _log.exception("fusionar_semantica: fallo proponiendo subtemas de «%s».", tema[:60])
        return 0
    etiquetados = 0
    for g in grupos:
        subtema = str(g.get("subtema") or "").strip()
        sub_ids = [str(i) for i in (g.get("ids") or []) if i]
        if not subtema or not sub_ids:
            continue
        try:
            etiquetados += repos.marcar_clusters_subtema(sub_ids, subtema) or 0
        except Exception:  # noqa: BLE001 -- persistir un subtema no aborta el paso
            _log.exception("fusionar_semantica: fallo al etiquetar el subtema «%s».", subtema[:60])
    return etiquetados


def _fusionar_grupo(
    ids: list[str],
    por_id: dict[str, dict[str, Any]],
    *,
    pesos: Any,
    eventos: list[dict[str, Any]] | None = None,
    breaking_peso: float,
    breaking_ventana_h: int,
    fuentes_baja: frozenset[str],
    perfil_activo: bool,
    ahora: datetime,
) -> bool:
    """Funde un grupo de historias en la CANÓNICA (más fuentes, desempate por score).

    Reasigna los items de las absorbidas a la canónica, borra las absorbidas (vacías) y recalcula
    + repuntúa la canónica (n_fuentes/score reales). Devuelve True si fusionó (≥2 historias).

    Salvaguardas:
      - ANTI-TOCTOU: antes de absorber, RE-LEE cada cluster absorbible; si entre la lectura del
        lote y ahora adquirió `publicacion_id` o dejó de ser `nuevo` (el pipeline lo promovió),
        NO se absorbe (se conserva intacto).
      - SIN ITEMS SUELTOS: los items se reasignan en LOTES de 500 HASTA VACIAR el cluster (antes el
        tope de 500 dejaba items colgando del cluster borrado si había más).
    """
    from .. import noticias_umbral, repos
    from . import agrupar

    clusters = [por_id[i] for i in ids if i in por_id]
    if len(clusters) < 2:
        return False
    canon = max(clusters, key=lambda c: (int(c.get("n_fuentes") or 0), float(c.get("score") or 0.0)))
    canon_id = str(canon["id"])
    absorbidas = 0
    for c in clusters:
        cid = str(c["id"])
        if cid == canon_id:
            continue
        # Re-verificación anti-TOCTOU: el absorbido pudo ser promovido entre lectura y fusionar.
        actual = repos.obtener_noticia_cluster(cid)
        if actual is None:
            continue
        if (actual.get("publicacion_id") or "") or (actual.get("estado") or "nuevo") != "nuevo":
            continue
        # Reasigna TODOS los items, por lotes, hasta vaciar (cota dura de seguridad: 100 lotes).
        for _ in range(100):
            lote = repos.items_de_cluster(cid, limite=500)
            if not lote:
                break
            repos.asignar_cluster_items({canon_id: [it["id"] for it in lote]})
        repos.borrar_noticia_cluster(cid)
        absorbidas += 1
    if not absorbidas:
        return False
    items = repos.items_de_cluster(canon_id, limite=500)
    if not items:
        return False
    base = repos.obtener_noticia_cluster(canon_id) or canon
    recalc = agrupar.recalcular(
        base, items,
        breaking_peso=breaking_peso,
        breaking_ventana_h=breaking_ventana_h,
        fuentes_baja_confianza=fuentes_baja,
        ahora=ahora,
    )
    palabras = noticias_umbral.palabras_relevancia(recalc.get("marca") or "", perfil_activo)
    recalc["score"], recalc["score_razon"], recalc["score_desglose"] = agrupar.puntuar_detalle(
        recalc, palabras_marca=palabras, eventos=eventos, ahora=ahora, pesos=pesos,
        breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
    )
    repos.upsert_noticia_cluster(recalc)
    return True


# --------------------------------------------------------------------------- #
# Marcador PERSISTIDO "fusión en curso" por marca (idempotencia del encolado)    #
# --------------------------------------------------------------------------- #
#
# El throttle/huella en memoria del barrido evita TRABAJO redundante (re-evaluar un lote que no
# cambió), pero NO sobrevive a un reinicio ni coordina barrido↔worker. Para no re-encolar una marca
# cuya fusión sigue EN VUELO (mismo papel que la columna `traduccion_encolada` de Traducir o el
# marcador `refresco_encolado_en` de Perfil), se persiste un sello ISO por marca en un JSON bajo el
# dir de datos (volumen compartido, escribible por el worker). Reapertura por TTL: un sello más viejo
# que el TTL se considera atascado (deploy/OOM) y NO bloquea (un barrido posterior re-encola).

_NOMBRE_CACHE_ENCOLADO = "fusion_encolada.json"


def _ruta_encolado() -> Path | None:
    """Ruta del JSON de marcas con fusión en curso (bajo el dir de datos). None si no se resuelve."""
    try:
        from .. import libprompts

        return libprompts.raiz() / _NOMBRE_CACHE_ENCOLADO
    except Exception:  # noqa: BLE001 -- sin dir de datos no hay marcador (el throttle igual frena)
        return None


def _cargar_encolado() -> dict[str, Any]:
    ruta = _ruta_encolado()
    if ruta is None or not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _guardar_encolado(data: dict[str, Any]) -> None:
    ruta = _ruta_encolado()
    if ruta is None:
        return
    try:
        from ..io_atomico import escribir_atomico

        ruta.parent.mkdir(parents=True, exist_ok=True)
        escribir_atomico(ruta, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:  # noqa: BLE001 -- el marcador es best-effort; un fallo no rompe la Recolección
        _log.warning("fusionar_semantica: no se pudo persistir el marcador de encolado.", exc_info=True)


def fusion_en_curso(marca: str, *, ahora: datetime | None = None, ttl_min: int) -> bool:
    """True si hay una fusión EN VUELO para `marca` (marcador dentro del TTL).

    Un marcador más viejo que `ttl_min` se considera ATASCADO (job interrumpido por deploy/OOM/error)
    y NO bloquea: el barrido re-encola (reapertura por TTL). Un marcador corrupto/ilegible tampoco
    bloquea (se re-encola). `marca` vacía nunca está en curso.
    """
    if not marca:
        return False
    sello = str(_cargar_encolado().get(marca) or "")
    if not sello:
        return False
    ref = ahora or datetime.now(UTC)
    try:
        edad_min = (ref - datetime.fromisoformat(sello)).total_seconds() / 60.0
    except (ValueError, TypeError):
        return False
    return edad_min < max(1, ttl_min)


def marcar_fusion_encolada(marca: str, *, ahora: datetime | None = None) -> None:
    """Sella la fusión de `marca` como EN CURSO (timestamp) AL ENCOLAR su job.

    Idempotencia entre barridos: mientras el marcador siga fresco (`fusion_en_curso`), el barrido NO
    re-encola la marca. Lo limpia el job al completar (`limpiar_fusion_encolada`) o el barrido si la
    admisión rechaza el encolado.
    """
    if not marca:
        return
    ref = ahora or datetime.now(UTC)
    cache = _cargar_encolado()
    cache[marca] = ref.isoformat()
    _guardar_encolado(cache)


def limpiar_fusion_encolada(marca: str) -> None:
    """Quita el marcador de fusión en curso de `marca` (job completado o encolado rechazado).

    La usa el worker al terminar la fusión (la marca vuelve a ser candidata) y el barrido cuando el
    encolado NO llegó a ocurrir (presupuesto/pausa), para reintentar sin esperar al TTL.
    """
    if not marca:
        return
    cache = _cargar_encolado()
    if marca in cache:
        del cache[marca]
        _guardar_encolado(cache)


# --------------------------------------------------------------------------- #
# Camino ENCOLADO (job del worker): orquesta la fusión de UNA marca             #
# --------------------------------------------------------------------------- #


def fusionar_marca(
    marca: str,
    recientes: list[dict[str, Any]],
    *,
    salida_principal: str,
    ejecutor: Ejecutor | None = None,
    al_ejecutar: Callable[[str, str], None] | None = None,
    al_ejecutar_subtema: Callable[[str, str], None] | None = None,
    ahora: datetime | None = None,
) -> dict[str, Any]:
    """Orquesta la fusión semántica de UNA marca a partir de la salida de la pasada principal.

    `recientes` es el lote de historias `nuevo` recientes de la marca (las que el barrido mandó a la
    pasada principal); `salida_principal` es la respuesta de esa pasada (la corre el worker con
    `claude -p`). Reproduce el bloque por-marca del paso inline:
      1. ANCLA DE AGENDA (determinista, sin LLM): una historia que nombra SIN ambigüedad un evento
         programado HEREDA su título como `tema_macro` (familia estable aunque caiga fuera del lote).
      2. `procesar_fusiones` parsea+VERIFICA los grupos y FUNDE cada uno (`_fusionar_grupo`,
         anti-TOCTOU sobre lo persistido).
      3. ETIQUETA las familias de macro-evento (NO las funde) reusando la etiqueta dominante, y las
         parte en SUBTEMAS (Haiku) si falta facetar alguna.
    Best-effort: un fallo por grupo/familia se loguea y no aborta. Devuelve `{grupos, fusionadas,
    familias, anclas}`.

    `al_ejecutar` recibe el prompt+salida de cada llamada de Cotejar (verificación de grupo) y
    `al_ejecutar_subtema` los de cada llamada de Subtema: el job de fusión los usa para sellar el
    gasto de esas sub-llamadas bajo su propia etapa («Cotejar»/«Subtema»), que de otro modo quedaría
    huérfano (el job solo registra el coste de la pasada principal, etapa «Fusionar»).
    """
    from .. import config, marcas, repos
    from . import agrupar

    ref = ahora or datetime.now(UTC)
    resultado = {"grupos": 0, "fusionadas": 0, "familias": 0, "anclas": 0}
    if len(recientes) < 2:
        return resultado

    maximo = config.fusion_semantica_max()
    breaking_peso = config.cluster_breaking_peso()
    breaking_ventana_h = config.cluster_breaking_ventana_h()
    fuentes_baja = config.fuentes_baja_confianza()
    perfil_activo = config.alguna_marca_con_etapa(config.ENV_PRIORIZAR_PERFIL_IA)
    pesos = config.score_pesos(marca)
    try:
        eventos = _eventos_de_marca(marca, ref)
    except Exception:  # noqa: BLE001 -- sin agenda legible la señal/ancla queda inerte
        _log.warning("fusionar_semantica: no se pudieron leer eventos de la marca %s.", marca)
        eventos = []

    lote = recientes[:maximo]
    por_id = {str(c["id"]): c for c in lote}

    # 1) ANCLA DE AGENDA: clave de familia determinista (la agenda es la verdad; el LLM solo etiqueta
    # lo NO agendado). Marca `ancladas_ids` para no dejar que el LLM las re-aglomere en una familia
    # más gruesa. Idempotente: solo (re)escribe las que aún no llevan ESA etiqueta.
    ancladas_ids: set[str] = set()
    por_evento: dict[str, list[dict[str, Any]]] = {}
    for c in recientes:
        titulo_ev = agrupar.evento_ancla(c, eventos, ahora=ref)
        if titulo_ev:
            por_evento.setdefault(titulo_ev, []).append(c)
    for titulo_ev, miembros in por_evento.items():
        for c in miembros:
            ancladas_ids.add(str(c["id"]))
        pendientes = [
            str(c["id"]) for c in miembros
            if str(c.get("tema_macro") or "").strip() != titulo_ev
        ]
        if pendientes:
            try:
                repos.marcar_clusters_tema_macro(pendientes, titulo_ev)
                resultado["anclas"] += 1
            except Exception:  # noqa: BLE001 -- persistir un ancla no aborta el paso
                _log.exception("fusionar_semantica: fallo al anclar el evento '%s'.", titulo_ev)
                continue
        # Refleja el ancla en memoria para que `_etiqueta_canonica` (abajo) lo respete.
        for c in miembros:
            c["tema_macro"] = titulo_ev

    # 2) GRUPOS (mismo hecho): parsea+verifica y funde cada uno.
    try:
        res = procesar_fusiones(salida_principal, lote, ejecutor=ejecutor, al_ejecutar=al_ejecutar)
    except Exception:  # noqa: BLE001 -- un fallo de parseo/verificación no aborta el resto del paso
        _log.exception("fusionar_semantica: fallo procesando las fusiones de %r.", marca)
        res = Fusiones([], [])
    for grupo in res.grupos:
        try:
            if _fusionar_grupo(
                grupo, por_id, pesos=pesos, eventos=eventos, breaking_peso=breaking_peso,
                breaking_ventana_h=breaking_ventana_h, fuentes_baja=fuentes_baja,
                perfil_activo=perfil_activo, ahora=ref,
            ):
                resultado["grupos"] += 1
                resultado["fusionadas"] += len(grupo) - 1
        except Exception:  # noqa: BLE001 -- un fusionado problemático no aborta el paso
            _log.exception("fusionar_semantica: fallo al fusionar un grupo de historias.")

    # 3) FAMILIAS de macro-evento (NO se funden): etiqueta + facetea.
    for familia in res.familias:
        tema_propuesto = str(familia.get("tema") or "").strip()
        ids = [str(i) for i in (familia.get("ids") or []) if i]
        if not tema_propuesto or len(ids) < 2:
            continue
        # La agenda ya etiquetó estas (determinista): NO dejes que el LLM las pise.
        if any(i in ancladas_ids for i in ids):
            continue
        tema = _etiqueta_canonica(ids, por_id, tema_propuesto)
        try:
            n = repos.marcar_clusters_tema_macro(ids, tema)
        except Exception:  # noqa: BLE001 -- persistir una etiqueta no aborta el paso
            _log.exception("fusionar_semantica: fallo al etiquetar el macro-evento '%s'.", tema)
            continue
        if n:
            resultado["familias"] += 1
        if _falta_subtema(ids, por_id):
            _partir_en_subtemas(tema, ids, por_id, ejecutor=ejecutor, al_ejecutar=al_ejecutar_subtema)

    if resultado["grupos"] or resultado["fusionadas"]:
        _log.info(
            "fusionar_semantica(%s): %d grupo(s), %d historia(s) absorbida(s).",
            marcas.etiqueta_de(marca) if marca else marca,
            resultado["grupos"], resultado["fusionadas"],
        )
    return resultado


def _eventos_de_marca(marca: str, ahora: datetime) -> list[dict[str, Any]]:
    """Eventos de la AGENDA de la marca en la ventana de encaje (ayer .. +7 días). Lectura de repos."""
    from datetime import timedelta

    from .. import repos

    if not marca:
        return []
    hoy = ahora.date()
    desde = (hoy - timedelta(days=1)).isoformat()
    hasta = (hoy + timedelta(days=7)).isoformat()
    return repos.listar_eventos_rota(desde=desde, hasta=hasta, marca=marca)


def construir_procesar_fusionar(marca: str, recientes: list[dict[str, Any]]):  # noqa: ANN201 -- Procesar
    """Callback de post-procesado del JOB de fusión semántica de UNA marca.

    El worker corre `claude -p` (modelo `config.fusion_modelo()`) con el prompt de
    `construir_prompt_fusion`; aquí tomamos esa `salida` como la pasada PRINCIPAL y orquestamos la
    fusión de la marca (`fusionar_marca`: ancla de agenda + grupos + familias + subtemas),
    persistiendo en repos. La verificación («Cotejar», solo si `KENI_FUSION_COTEJAR`) corre con
    `_ejecutar_haiku` (sonnet) y los subtemas con `_ejecutar_subtema` (haiku); sus callbacks sellan el
    gasto de cada sub-llamada bajo su etapa («Cotejar» / «Subtema») para que ese coste no quede
    invisible frente a la pasada principal («Fusionar»). Al
    terminar limpia el marcador de fusión en curso de la marca. Devuelve `{grupos, fusionadas,
    familias, anclas}`.
    """
    from .. import marcas
    from . import actividad_pool, traducir

    etiqueta_marca = marcas.etiqueta_de(marca) if marca else "sin marca"

    def _al_cotejar(prompt: str, salida: str) -> None:
        actividad_pool.registrar_actividad_pool(
            marca, f"Cotejar grupos — {etiqueta_marca}", etapa="Cotejar", prompt=prompt, salida=salida,
        )

    def _al_subtema(prompt: str, salida: str) -> None:
        actividad_pool.registrar_actividad_pool(
            marca, f"Subtema — {etiqueta_marca}", etapa="Subtema", prompt=prompt, salida=salida,
        )

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        # Descarta el residuo del acumulador del hilo ANTES de las sub-llamadas: la pasada principal
        # (que el worker ya contabilizó como «Fusionar») pudo acumular aquí; no debe contarse otra vez
        # en la primera sub-llamada.
        traducir.tomar_metricas_acumuladas()
        try:
            return fusionar_marca(
                marca, recientes, salida_principal=salida or "",
                al_ejecutar=_al_cotejar, al_ejecutar_subtema=_al_subtema,
            )
        finally:
            limpiar_fusion_encolada(marca)
            # Fusión TERMINADA (el job corrió): limpia su contador de intentos (vive aparte,
            # sobrevive a la purga) para no arrastrar reintentos a la próxima ventana de la marca.
            try:
                from ..pipeline_contenido import _intentos

                _intentos.reset(marca, _intentos.ETAPA_FUSIONAR)
            except Exception:  # noqa: BLE001 -- el reset es best-effort; la fusión ya completó
                pass

    return procesar
