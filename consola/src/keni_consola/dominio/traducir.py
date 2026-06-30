"""Traducción + tropicalización MX de títulos/resúmenes extranjeros con Haiku.

Patrón SÍNCRONO POR LOTES: una sola llamada `claude -p --output-format json`
traduce TODOS los ítems de una vez (minimiza el nro de subprocesos). Mismo patrón
que `importador_calendario._ejecutar_claude_json` y `dominio.recibir_parse`, con
`--model` de `config.insumos_modelo()`.

API pública:
    traducir_items(items, *, ejecutor=None) -> list[dict]

`items` es una lista de dicts con al menos `{id, titulo, resumen}` en idioma extranjero.
Devuelve `[{id, titulo_es, resumen_es}]` traducidos y tropicalizados al español MX.

Ejecutor inyectable (tests): si `ejecutor` es None se usa el subproceso real
(`_ejecutar_claude_json`); en tests se pasa una función falsa para no llamar a `claude`.

BEST-EFFORT: ante cualquier fallo (subproceso, timeout, JSON inválido, etc.) devuelve
los ítems originales mapeados a `titulo_es`/`resumen_es` (sin romper el Radar).

Acotado por tamaño de prompt: si la lista es muy larga, se trunca el texto de cada ítem
para no superar el límite razonable de contexto de entrada (ver `_MAX_CHARS_ITEM`).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from typing import Any

from .. import config
from . import json_llm

_log = logging.getLogger("keni_consola.dominio.traducir")

# Timeout del subproceso. Haiku es rápido; 60 s es más que suficiente para un lote de 15 ítems.
_CLAUDE_TIMEOUT_S = 90

# Máximo de caracteres de titulo+resumen que se pasan al prompt POR ÍTEM.
# Protección contra prompts enormes (feeds con artículos larguísimos).
_MAX_CHARS_ITEM = 600

# Ejecutor de la llamada a `claude`. Misma firma que en recibir_parse
# (`(prompt, dir_permitido) -> salida`), pero puede devolver dos formas:
#   - `str`: solo el texto `result` (se parsea con `_extraer_traducciones`, camino histórico).
#   - `tuple[str, dict | None]`: `(texto_result, structured_output)`, cuando el run usó
#     `--json-schema` y trajo la salida estructurada YA validada. Si la hay, se usa directa.
SalidaEjecutor = str | tuple[str, "dict[str, Any] | None"]
Ejecutor = Callable[[str, str], SalidaEjecutor]


# --------------------------------------------------------------------------- #
# Ejecutor real                                                                 #
# --------------------------------------------------------------------------- #

# ACUMULADOR de métricas del ejecutor síncrono, POR HILO. El envelope JSON de `claude -p
# --output-format json` trae el coste real de cada llamada (tokens/coste/duración), pero los
# pasos del pool (fusión, encaje, traducción, insumos) lo descartaban: sus registros de
# actividad salían SIN métricas en Producción. Cada llamada SUMA aquí; quien registra la
# actividad lo recoge (y resetea) con `tomar_metricas_acumuladas()`. Thread-local: los pasos
# del daemon corren secuenciales en su hilo, así la atribución no se cruza con otros hilos
# (worker/insumos) que usan este mismo ejecutor.
_metricas_hilo = threading.local()


def _metricas_de_envelope(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Métricas del envelope de `claude -p --output-format json`, o None si no trae ninguna.

    Forma compatible con `generaciones.metricas`: `{tokens_in, tokens_out, cache_read,
    cache_creation, total_cost_usd, duration_ms, num_turns, modelo}`. Los tokens y la CACHÉ se
    prefieren de `modelUsage` (suma por modelo: capta multi-modelo y multi-turno, donde el `usage`
    de sesión solo refleja el último turno); fallback al `usage` agregado. El `modelo` sale de las
    claves de `modelUsage` (coma-separado) o de `model`. Sin esto, los pasos inline del pool
    (Fusionar/Macro/Traducir…) guardaban coste pero NO caché ni modelo, dejando el ledger con
    caché 0 y modelo vacío (tokens descuadrados frente al coste real). PURA y tolerante: campos
    ausentes/ilegibles se omiten.
    """
    if not isinstance(envelope, dict):
        return None
    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
    model_usage = envelope.get("modelUsage") if isinstance(envelope.get("modelUsage"), dict) else {}

    def _num(valor: object) -> int | float | None:
        return valor if isinstance(valor, (int, float)) and not isinstance(valor, bool) else None

    def _suma(campo_mu: str, campo_usage: str) -> int | None:
        # Preferir la suma por modelo de `modelUsage`; si no aporta, caer al `usage` agregado.
        total: int | None = None
        for uso in model_usage.values():
            n = _num(uso.get(campo_mu)) if isinstance(uso, dict) else None
            if n is not None:
                total = (total or 0) + int(n)
        if total is None:
            n = _num(usage.get(campo_usage))
            total = int(n) if n is not None else None
        return total

    out: dict[str, Any] = {}
    for destino, valor in (
        ("tokens_in", _suma("inputTokens", "input_tokens")),
        ("tokens_out", _suma("outputTokens", "output_tokens")),
        ("cache_read", _suma("cacheReadInputTokens", "cache_read_input_tokens")),
        ("cache_creation", _suma("cacheCreationInputTokens", "cache_creation_input_tokens")),
    ):
        if valor is not None:
            out[destino] = valor
    coste = _num(envelope.get("total_cost_usd"))
    if coste is not None:
        out["total_cost_usd"] = float(coste)
    for destino, fuente in (("duration_ms", envelope.get("duration_ms")), ("num_turns", envelope.get("num_turns"))):
        n = _num(fuente)
        if n is not None:
            out[destino] = int(n)
    modelos = [n for n in model_usage if isinstance(n, str) and n]
    modelo = ", ".join(modelos) if modelos else (
        envelope.get("model") if isinstance(envelope.get("model"), str) and envelope.get("model") else None
    )
    if modelo:
        out["modelo"] = modelo
    return out or None


def _acumular_metricas(metricas: dict[str, Any] | None) -> None:
    """Suma `metricas` al acumulador del hilo (no-op con None).

    Los campos numéricos se SUMAN entre las llamadas del paso; `modelo` (texto) se UNE
    (nombres distintos, coma-separados) porque sumar cadenas no tiene sentido.
    """
    if not metricas:
        return
    acc = getattr(_metricas_hilo, "acumulado", None)
    if acc is None:
        acc = {}
        _metricas_hilo.acumulado = acc
    for clave, valor in metricas.items():
        if clave == "modelo":
            vistos: list[str] = []
            for n in str(acc.get("modelo", "")).split(", ") + str(valor).split(", "):
                if n and n not in vistos:
                    vistos.append(n)
            acc["modelo"] = ", ".join(vistos)
        else:
            acc[clave] = acc.get(clave, 0) + valor


def tomar_metricas_acumuladas() -> dict[str, Any] | None:
    """Devuelve y RESETEA las métricas acumuladas del hilo desde la última toma (None si nada).

    Lo usa quien registra la actividad de un paso IA del pool justo después de ejecutarlo
    (p. ej. `recolectar_daemon._registrar_actividad_ia`): lo acumulado desde la toma anterior
    es el coste de ESE paso. Tomar también sirve para DESCARTAR restos entre pasos.
    """
    acc = getattr(_metricas_hilo, "acumulado", None)
    _metricas_hilo.acumulado = None
    return acc or None


def construir_argv_claude_json(
    prompt: str,
    dir_permitido: str,
    modelo: str | None,
    *,
    max_turns: int | None = None,
    sin_tools: bool = False,
    json_schema: dict[str, Any] | None = None,
) -> list[str]:
    """argv de `claude -p <prompt> --output-format json [...]`. PURO (no corre nada).

    Compone el comando que ejecuta `_ejecutar_claude_json`. Aislado para poder afirmarlo en
    tests sin lanzar el subproceso. `json_schema` (cuando viene) añade `--json-schema <json>`:
    `claude` valida su salida estructurada contra el esquema y la entrega en `structured_output`
    a nivel raíz del envelope. Validar la salida estructurada cuesta un turno extra (tool_use
    interno), así que con schema el tope de turnos sube a `>=2` salvo que el llamante pida más.

    `sin_tools=True`: la etapa no usa NINGUNA herramienta, así que emite `--tools ""` (cero
    tools) en vez de `--add-dir`. Sin esquemas de tool en el system prompt se ahorran ~17k
    tokens por llamada (clave en las etapas inline a ráfagas, donde la caché se enfría).
    """
    from . import stream  # import perezoso: evita ciclo importador<->dominio

    argv: list[str] = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
    ]
    if sin_tools:
        argv += stream.arg_sin_tools()
    else:
        argv += ["--add-dir", dir_permitido]
    argv += [*stream.arg_skip_permisos(), *stream.arg_excluir_secciones_dinamicas()]
    if json_schema is not None:
        argv += ["--json-schema", json.dumps(json_schema, ensure_ascii=False)]
        # La validación de la salida estructurada gasta un turno extra (tool_use interno):
        # no la ahogues con un tope de 1. Respeta un tope mayor que pida el llamante.
        if max_turns is not None and max_turns < 2:
            max_turns = 2
    if max_turns is not None:
        argv += ["--max-turns", str(max_turns)]
    if modelo:
        argv += ["--model", modelo]
    return argv


def _ejecutar_claude_json(
    prompt: str,
    dir_permitido: str,
    modelo: str | None = None,
    *,
    max_turns: int | None = None,
    sin_tools: bool = False,
) -> str:
    """Corre `claude -p` y devuelve solo el texto `result` (compat: ejecutor histórico).

    Atajo del camino sin esquema sobre `_ejecutar_claude_json_estructurado`: descarta la
    salida estructurada (que siempre es None sin `--json-schema`). Lo siguen usando los pasos
    que solo necesitan el texto libre (traducción, fusión, perfil editorial).
    """
    texto, _ = _ejecutar_claude_json_estructurado(
        prompt, dir_permitido, modelo, max_turns=max_turns, sin_tools=sin_tools
    )
    return texto


def _ejecutar_claude_json_estructurado(
    prompt: str,
    dir_permitido: str,
    modelo: str | None = None,
    *,
    max_turns: int | None = None,
    sin_tools: bool = False,
    json_schema: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Corre `claude -p ... --output-format json` y devuelve `(texto_result, structured_output)`.

    Síncrono, acotado por `_CLAUDE_TIMEOUT_S`. Hereda el entorno (incluido
    `CLAUDE_CODE_OAUTH_TOKEN`). `modelo=None` cae al de insumos (`KENI_INSUMOS_MODELO`);
    un llamante puede fijar el suyo (la fusión usa el de `KENI_FUSION_MODELO`). No tocar
    en tests: se inyecta un ejecutor falso.

    `json_schema` (opcional): cuando viene, `claude` valida su salida estructurada contra el
    esquema y la entrega en `structured_output` (objeto, a nivel RAÍZ del envelope, SEPARADO
    del texto libre `result`). Se devuelve como segundo elemento; es None si no se pidió
    esquema o si el run no lo trajo. El texto `result` se devuelve siempre para el fallback.

    Para clasificaciones INLINE que no necesitan herramientas, el llamante acota la llamada:
        - `max_turns`: tope de turnos de agente (p. ej. `1` fuerza una sola respuesta, sin bucle).
        - `sin_tools=True`: emite `--tools ""` (cero tools) en vez de `--add-dir`, así `claude`
          no recibe acceso al filesystem ni esquema de herramienta alguno (ahorro de contexto).
    Por defecto (sin esquema y ambos sin fijar) el comportamiento es el de siempre: `--add-dir`
    y sin tope de turnos.
    """
    if shutil.which("claude") is None:
        raise RuntimeError("El asistente (claude) no está disponible en el servidor.")
    if modelo is None:
        modelo = config.insumos_modelo()
    argv = construir_argv_claude_json(
        prompt, dir_permitido, modelo,
        max_turns=max_turns, sin_tools=sin_tools, json_schema=json_schema,
    )
    res = subprocess.run(  # noqa: S603 -- argv fijo, sin shell; prompt va como argumento
        argv,
        capture_output=True,
        text=True,
        timeout=_CLAUDE_TIMEOUT_S,
        check=False,
        env=dict(os.environ),
    )
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "claude terminó con error").strip()[:300])
    try:
        envelope = json.loads(res.stdout or "{}")
    except (json.JSONDecodeError, ValueError):
        return (res.stdout or ""), None
    if isinstance(envelope, dict):
        # Coste REAL de la llamada (tokens/coste/duración): se acumula para que el
        # registro de actividad del paso lo selle (visible en Producción).
        _acumular_metricas(_metricas_de_envelope(envelope))
        estructurado = envelope.get("structured_output")
        return (
            str(envelope.get("result") or ""),
            estructurado if isinstance(estructurado, dict) else None,
        )
    return (res.stdout or ""), None


# --------------------------------------------------------------------------- #
# Prompt                                                                        #
# --------------------------------------------------------------------------- #


# La plantilla vive en la Prompts de Texto como prompt EDITABLE (pestaña «Prompts»). La lista
# JSON a traducir se inserta en `{{ITEMS}}`. Si el store fallara, la red es la INICIAL del
# paquete (fuente única, sin texto duplicado aquí).
_PROMPT_ID = "prompt/traducir"
_MARCA_ITEMS = "{{ITEMS}}"


def _plantilla() -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > inicial del paquete)."""
    from .. import libprompts

    try:
        cuerpo = (libprompts.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar Traducir sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libprompts.cuerpo_inicial(_PROMPT_ID).strip()


def _construir_prompt(items_json: str) -> str:
    """Prompt de traducción por lotes para Haiku (plantilla editable + lista JSON)."""
    plantilla = _plantilla()
    if _MARCA_ITEMS in plantilla:
        return plantilla.replace(_MARCA_ITEMS, items_json)
    return f"{plantilla}\n\nLista de ítems:\n{items_json}"


def _payload_items(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Payload de entrada `[{id, titulo, resumen}]` recortado por ítem (truncado centralizado).

    Recorta `titulo` a `_MAX_CHARS_ITEM` y el `resumen` a lo que reste, para no superar el cap de
    contexto de entrada por ítem. PURA (no llama a claude). Compartida por el camino INLINE
    (`traducir_items`) y por el ENCOLADO (`construir_prompt_traduccion`), para que el prompt sea
    idéntico se traduzca en el acto o vía job.
    """
    payload: list[dict[str, str]] = []
    for item in items:
        item_id = str(item.get("id", ""))
        titulo, _ = json_llm.truncar_avisando(
            str(item.get("titulo", "")).strip(), _MAX_CHARS_ITEM,
            campo=f"titulo de {item_id}", log=_log,
        )
        espacio_resumen = max(0, _MAX_CHARS_ITEM - len(titulo))
        resumen, _ = json_llm.truncar_avisando(
            str(item.get("resumen", "") or "").strip(), espacio_resumen,
            campo=f"resumen de {item_id}", log=_log,
        )
        payload.append({"id": item_id, "titulo": titulo, "resumen": resumen})
    return payload


def construir_prompt_traduccion(items: list[dict[str, Any]]) -> str:
    """Prompt de traducción por lotes a partir de `items` (`[{id, titulo, resumen}]`). PURO.

    Lo usa el paso de Traducir del daemon para componer el prompt del JOB que ENCOLA por marca
    (el worker lo corre con `claude -p`); el camino inline (`traducir_items`) usa el mismo
    payload+plantilla, así el prompt es idéntico se traduzca en el acto o vía job.
    """
    return _construir_prompt(json.dumps(_payload_items(items), ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Extracción tolerante del JSON de respuesta                                   #
# --------------------------------------------------------------------------- #


# Esquema raíz para `--json-schema`: fija la clave canónica `traducciones` como array de
# objetos `{id, titulo_es, resumen_es}` (los campos que consume `traducir_items` aguas abajo).
# Con él `claude` valida la salida estructurada y la entrega en `structured_output`, lo que
# evita el parse heurístico del texto libre; el camino sin esquema sigue cayendo a
# `_extraer_traducciones`, que tolera además las claves alternativas históricas.
_ESQUEMA_TRADUCCIONES: dict[str, Any] = {
    "type": "object",
    "properties": {
        "traducciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "titulo_es": {"type": "string"},
                    "resumen_es": {"type": "string"},
                },
                "required": ["id", "titulo_es"],
            },
        }
    },
    "required": ["traducciones"],
}


def _extraer_traducciones(texto: str) -> list[dict[str, str]] | None:
    """Extrae la lista de traducciones del texto de Claude (extractor compartido)."""
    return json_llm.extraer_lista(
        texto, claves=("traducciones", "items", "translations", "resultados")
    )


def _desempaquetar(salida: SalidaEjecutor) -> tuple[str, dict[str, Any] | None]:
    """Normaliza la salida del ejecutor a `(texto, structured_output)`.

    Acepta tanto la forma histórica (`str` = solo texto) como la nueva
    (`tuple[str, dict | None]`), para no romper los ejecutores que solo devuelven texto.
    """
    if isinstance(salida, tuple):
        texto, estructurado = salida
        return str(texto or ""), (estructurado if isinstance(estructurado, dict) else None)
    return str(salida or ""), None


def _ejecutor_estructurado(prompt: str, carpeta: str) -> tuple[str, dict[str, Any] | None]:
    """Ejecutor real con `--json-schema`: devuelve `(texto, structured_output)`.

    Pasa el esquema raíz para que la salida estructurada venga validada; `claude` la entrega
    en `structured_output`. El texto `result` se devuelve siempre para el fallback.
    """
    return _ejecutar_claude_json_estructurado(
        prompt, carpeta, json_schema=_ESQUEMA_TRADUCCIONES
    )


# --------------------------------------------------------------------------- #
# API pública                                                                   #
# --------------------------------------------------------------------------- #


def traducir_items(
    items: list[dict[str, Any]],
    *,
    ejecutor: Ejecutor | None = None,
) -> list[dict[str, Any]]:
    """Traduce+tropicaliza una lista de ítems al español MX con una sola llamada a Haiku.

    Parámetros:
        items: lista de dicts con al menos `{id, titulo, resumen}` en idioma extranjero.
        ejecutor: función `(prompt, dir_permitido) -> str | (str, structured_output)`
            inyectable (para tests). None = subproceso real con `--json-schema`, que entrega
            la salida estructurada validada; si viene `(texto, structured)` se prefiere el
            array `traducciones` del structured y se cae al parse del texto si falta.

    Devuelve: `[{id, titulo_es, resumen_es, ok}]`. `ok=True` solo cuando hubo traducción
    REAL; ante cualquier fallo (subproceso, timeout, JSON inválido, ítem ausente o sin
    `titulo_es`) devuelve el original como `titulo_es`/`resumen_es` pero con `ok=False`,
    para que el llamante (el daemon) NO lo persista como traducción y reintente, sin
    envenenar el cluster con texto extranjero marcado `traducido=1`.
    """
    if not items:
        return []

    correr = ejecutor or _ejecutor_estructurado

    def _fallback() -> list[dict[str, Any]]:
        return [
            {
                "id": str(it.get("id", "")),
                "titulo_es": str(it.get("titulo", "")),
                "resumen_es": str(it.get("resumen", "") or ""),
                "ok": False,
            }
            for it in items
        ]

    try:
        prompt = construir_prompt_traduccion(items)
        with tempfile.TemporaryDirectory(prefix="keni-traduccion-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> originales
        _log.warning("traducir_items falló al llamar a claude: %s", e)
        return _fallback()

    texto, estructurado = _desempaquetar(salida)
    # Salida estructurada YA validada por `--json-schema`: prefiérela si trae el array
    # canónico `traducciones`. Si falta o no es una lista, cae al parse del texto libre.
    traducciones: list[dict[str, Any]] | None = None
    if isinstance(estructurado, dict) and isinstance(estructurado.get("traducciones"), list):
        traducciones = estructurado["traducciones"]
    if traducciones is None:
        traducciones = _extraer_traducciones(texto)
    if traducciones is None:
        _log.warning("traducir_items: no se pudo extraer JSON de la respuesta de Haiku.")
        return _fallback()

    # Normaliza la respuesta y rellena con originales los ítems que falten.
    resultado: list[dict[str, Any]] = []
    por_id: dict[str, dict[str, Any]] = {}
    for t in traducciones:
        if isinstance(t, dict) and "id" in t:
            por_id[str(t["id"])] = t

    sin_traducir: list[str] = []
    for item in items:
        item_id = str(item.get("id", ""))
        trad = por_id.get(item_id)
        titulo_es = str(trad["titulo_es"]).strip() if trad and isinstance(trad.get("titulo_es"), str) else ""
        if titulo_es:
            resultado.append({
                "id": item_id,
                "titulo_es": titulo_es,
                "resumen_es": str(trad.get("resumen_es", "") or "").strip(),
                "ok": True,
            })
        else:
            # Ítem ausente (o sin `titulo_es`) en la respuesta -> conserva el original como
            # best-effort, pero con `ok=False`: el daemon NO lo marca `traducido` y reintenta
            # en el próximo barrido (no se queda con texto extranjero pegado). NO silencioso:
            # el prompt pide TODOS los ítems y abajo queda un WARN con los faltantes.
            sin_traducir.append(item_id)
            resultado.append({
                "id": item_id,
                "titulo_es": str(item.get("titulo", "")),
                "resumen_es": str(item.get("resumen", "") or ""),
                "ok": False,
            })
    if sin_traducir:
        _log.warning(
            "traducir_items: %d de %d ítem(s) sin traducción en la respuesta "
            "(se conserva el original): %s",
            len(sin_traducir), len(items), ", ".join(sin_traducir[:10]),
        )

    return resultado


# --------------------------------------------------------------------------- #
# Post-procesado del JOB de traducción (worker)                                 #
# --------------------------------------------------------------------------- #


def construir_procesar_traducir(originales: list[dict[str, Any]]):  # noqa: ANN201 -- Procesar
    """Callback de post-procesado del JOB de traducción: parsea la salida y PERSISTE las traducciones.

    `originales` es `[{id, titulo}]` de los clusters del lote (su título EXTRANJERO original, para
    sellar `titulo_original` y mapear la respuesta por id). El worker corre `claude -p` (stream-json)
    con el prompt que armó `construir_prompt_traduccion`; aquí parseamos el texto `result` con el
    extractor tolerante (`_extraer_traducciones`) y, por cada traducción REAL (con `titulo_es`),
    marcamos el cluster `traducido=1` (lo que además limpia su `traduccion_encolada`). Un cluster
    omitido o sin `titulo_es` NO se marca: queda con su marca de encolado hasta que el limpiador de
    atascados lo re-abra y un barrido posterior lo re-encole (reintento). Devuelve `{traducidos}`.
    """
    por_id_orig = {str(o.get("id") or ""): o for o in originales if o.get("id")}

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        from .. import repos

        traducciones = _extraer_traducciones(salida) or []
        guardados = 0
        for t in traducciones:
            if not isinstance(t, dict):
                continue
            cid = str(t.get("id") or "")
            orig = por_id_orig.get(cid)
            if orig is None:
                continue
            titulo_es = str(t.get("titulo_es") or "").strip()
            if not titulo_es:
                continue
            try:
                repos.marcar_cluster_traducido(
                    cid,
                    titulo_es=titulo_es,
                    resumen_es=str(t.get("resumen_es") or ""),
                    titulo_original=str(orig.get("titulo") or ""),
                )
                guardados += 1
                # Éxito de la etapa Traducir (cluster traducido): limpia su contador de intentos
                # (vive aparte, sobrevive a la purga) para no arrastrar reintentos.
                try:
                    from ..pipeline_contenido import _intentos

                    _intentos.reset(cid, _intentos.ETAPA_TRADUCIR)
                except Exception:  # noqa: BLE001 -- el reset es best-effort; ya está traducido
                    pass
            except Exception:  # noqa: BLE001 -- persistir una traducción no aborta el resto del lote
                _log.exception("traducir: fallo al guardar la traducción del cluster %s.", cid)
        return {"traducidos": guardados, "candidatos": len(por_id_orig)}

    return procesar
