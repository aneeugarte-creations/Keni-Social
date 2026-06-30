"""Dominio STREAM: parseo del stream/resultado de `claude`, metricas, presupuesto y verdicto.

Logica de negocio PURA (sin HTTP, sin subprocess, sin disco): aqui viven el acumulador del
stream NDJSON, el parseo del JSON de resultado, el calculo del argumento de presupuesto,
la derivacion del verdicto a partir de los simbolos ✅/⚠️/❌ y la limpieza determinista
de emojis del copy. Tambien el reparto de la salida cruda en piezas por red (via bloque
```json o, como fallback, por encabezados de plataforma) y la derivacion del titulo.

Es la capa que consumen tanto `api.skills` (orquestacion HTTP) como `generaciones`
(trabajo en segundo plano). Este modulo no importa de `api/` ni de `generaciones`.

FACADE: este paquete trocea `stream.py` en areas por responsabilidad —`_comun` (excepcion +
conversiones), `invocacion` (argv/metricas/resultado/acumulador), `parser` (reparto en piezas
por red) y `texto` (verdicto/emojis/titulo/redes)— y re-exporta aqui EXACTAMENTE la misma
superficie publica (mas los pocos nombres privados que terceros referencian, p. ej.
`_RE_BLOQUE_JSON`), de modo que `from ..dominio import stream` y `stream.<nombre>` siguen
funcionando sin cambios.
"""

from __future__ import annotations

from ._comun import GeneracionError, _entero, _flotante
from .invocacion import (
    _CAMPOS_METRICAS_PERSISTIDOS,
    _ENV_DISALLOWED_TOOLS,
    _ENV_EXCLUDE_DYNAMIC_SECTIONS,
    _ENV_FALLBACK_MODEL,
    _ENV_MAX_TURNS,
    _ENV_MAX_USD,
    _ENV_SESSION_PERSISTENCE,
    _ENV_SKIP_PERMISOS,
    _MAX_RAZONAMIENTO,
    _SUBTIPOS_PRESUPUESTO,
    FASE_COMPLETADO,
    FASE_GENERANDO,
    FASE_RAZONANDO,
    MSG_REFUSAL,
    AcumuladorStream,
    MetricasRun,
    _tokens_de_model_usage,
    arg_excluir_secciones_dinamicas,
    arg_fallback_model,
    arg_max_turns,
    arg_presupuesto,
    arg_session_persistence,
    arg_sin_tools,
    arg_skip_permisos,
    arg_system_prompt,
    arg_tools_restringidas,
    metricas_a_dict,
    parsear_resultado_json,
)
from .parser import (
    _ALIAS_RED,
    _CLAVES_COPY,
    _FRONTERA_VALOR,
    _MAX_SLIDES,
    _RE_BLOQUE_JSON,
    _RE_ENCABEZADO_RED,
    _desescapar_json_str,
    _id_red_de_encabezado,
    _objeto_copy_tolerante,
    _piezas_desde_por_red,
    _repartir_por_encabezados,
    _slides_de,
    parsear_salida,
    parsear_salida_unificada,
)
from .texto import (
    _MAX_TITULO,
    _RE_COLA_LINEA,
    _RE_EMOJI,
    _RE_ESPACIOS,
    _VEREDICTO_POR_SIMBOLO,
    derivar_titulo,
    derivar_verdicto,
    normalizar_redes,
    quitar_emojis,
)

__all__ = [
    # _comun
    "GeneracionError",
    "_entero",
    "_flotante",
    # invocacion
    "MetricasRun",
    "metricas_a_dict",
    "_CAMPOS_METRICAS_PERSISTIDOS",
    "arg_presupuesto",
    "arg_max_turns",
    "arg_skip_permisos",
    "arg_tools_restringidas",
    "arg_sin_tools",
    "arg_excluir_secciones_dinamicas",
    "arg_system_prompt",
    "arg_session_persistence",
    "arg_fallback_model",
    "parsear_resultado_json",
    "MSG_REFUSAL",
    "_tokens_de_model_usage",
    "AcumuladorStream",
    "FASE_RAZONANDO",
    "FASE_GENERANDO",
    "FASE_COMPLETADO",
    "_MAX_RAZONAMIENTO",
    "_SUBTIPOS_PRESUPUESTO",
    "_ENV_MAX_USD",
    "_ENV_MAX_TURNS",
    "_ENV_SKIP_PERMISOS",
    "_ENV_DISALLOWED_TOOLS",
    "_ENV_EXCLUDE_DYNAMIC_SECTIONS",
    "_ENV_SESSION_PERSISTENCE",
    "_ENV_FALLBACK_MODEL",
    # parser
    "parsear_salida",
    "parsear_salida_unificada",
    "_RE_BLOQUE_JSON",
    "_ALIAS_RED",
    "_RE_ENCABEZADO_RED",
    "_id_red_de_encabezado",
    "_repartir_por_encabezados",
    "_piezas_desde_por_red",
    "_CLAVES_COPY",
    "_FRONTERA_VALOR",
    "_desescapar_json_str",
    "_objeto_copy_tolerante",
    "_MAX_SLIDES",
    "_slides_de",
    # texto
    "derivar_verdicto",
    "quitar_emojis",
    "derivar_titulo",
    "normalizar_redes",
    "_VEREDICTO_POR_SIMBOLO",
    "_RE_EMOJI",
    "_RE_ESPACIOS",
    "_RE_COLA_LINEA",
    "_MAX_TITULO",
]
