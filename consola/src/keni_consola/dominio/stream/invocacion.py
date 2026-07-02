"""Invocacion de `claude` del dominio STREAM: argv, metricas, resultado y acumulador.

Aqui viven las piezas ligadas a EJECUTAR `claude -p` y leer su salida (sin tocar
subprocess): el dataclass de metricas reales de un run y su serializacion, la composicion
del argv (`--max-budget-usd`/`--max-turns`/`--dangerously-skip-permissions`/
`--disallowed-tools`), el parseo del JSON de resultado (`--output-format json`) y el
acumulador del stream NDJSON (`--output-format stream-json --verbose`) con sus fases de
progreso. Logica PURA: no importa de `api/` ni de `generaciones`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ... import config
from ._comun import GeneracionError, _entero, _flotante

# --------------------------------------------------------------------------- #
# Metricas de un run de IA (tokens / turnos / coste / duracion)                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MetricasRun:
    """Metricas reales capturadas de una ejecucion de `claude -p ... --output-format json`.

    - `tokens_in`/`tokens_out`: tokens de entrada/salida (preferentemente sumados de
      `modelUsage`, con fallback a `usage`). `cache_read`/`cache_creation`: tokens de
      cache (solo de `usage`, no siempre presentes por modelo).
    - `num_turns`: turnos del agente; `total_cost_usd`: coste total en USD;
      `duration_ms`: duracion de pared en milisegundos; `session_id`: id de la sesion.
    - `modelo`: el (o los) modelos usados (coma-separados si hubo varios).
    - `ttft_ms`: time-to-first-token (ms), nativo del `result` del stream-json.
    - `tokens_por_s`: tokens de salida por segundo (derivado de `tokens_out`/`duration_ms`).
    Todos los campos son opcionales (None si la salida no los trae).
    """

    tokens_in: int | None = None
    tokens_out: int | None = None
    cache_read: int | None = None
    cache_creation: int | None = None
    num_turns: int | None = None
    total_cost_usd: float | None = None
    duration_ms: int | None = None
    session_id: str | None = None
    modelo: str | None = None
    ttft_ms: int | None = None
    tokens_por_s: float | None = None


# Subconjunto de campos de `MetricasRun` que se persisten (run YAML + historial).
# `cache_read`/`cache_creation` (tokens de prompt caching) SI se persisten: sin esa señal no se
# puede medir si el caching ocurre ni el ahorro que produce. Se omiten del dict cuando son None
# (la mayoria de runs no los traen), asi no ensucian el registro de los que no cachean.
_CAMPOS_METRICAS_PERSISTIDOS: tuple[str, ...] = (
    "tokens_in",
    "tokens_out",
    "cache_read",
    "cache_creation",
    "num_turns",
    "total_cost_usd",
    "duration_ms",
    "modelo",
    "ttft_ms",
    "tokens_por_s",
)


def metricas_a_dict(metricas: MetricasRun | None) -> dict[str, object] | None:
    """Serializa las metricas persistibles a un dict simple (o None si no hay metricas).

    Solo incluye el subconjunto que guardamos (`_CAMPOS_METRICAS_PERSISTIDOS`); las
    claves con valor None se omiten para no ensuciar el YAML/JSON.
    """
    if metricas is None:
        return None
    completo = asdict(metricas)
    return {k: completo[k] for k in _CAMPOS_METRICAS_PERSISTIDOS if completo.get(k) is not None}


# --------------------------------------------------------------------------- #
# Presupuesto y maximo de turnos: argumentos de `claude` desde el entorno      #
# --------------------------------------------------------------------------- #

# Env opcionales de la generacion `claude -p`. Nombres canonicos en `config` (fuente
# unica); re-exportados aqui por compat de referencias. La EXTRACCION del valor (parseo
# tolerante) vive en `config`; aqui solo se compone el argv para `claude`.
_ENV_MAX_USD = config.ENV_CLAUDE_MAX_USD
_ENV_MAX_TURNS = config.ENV_CLAUDE_MAX_TURNS
_ENV_SKIP_PERMISOS = config.ENV_CLAUDE_SKIP_PERMISSIONS
_ENV_DISALLOWED_TOOLS = config.ENV_CLAUDE_DISALLOWED_TOOLS
_ENV_EXCLUDE_DYNAMIC_SECTIONS = config.ENV_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS
_ENV_SESSION_PERSISTENCE = config.ENV_CLAUDE_SESSION_PERSISTENCE
_ENV_FALLBACK_MODEL = config.ENV_CLAUDE_FALLBACK_MODEL

# Subtipos de error conocidos del campo `result` que conviene reportar especificamente.
_SUBTIPOS_PRESUPUESTO = frozenset({"error_max_budget", "error_budget_exceeded"})

# Mensaje del error de RECHAZO del modelo (refusal). Es un fallo TERMINAL y NO reintentable:
# reintentar un refusal no ayuda, y su texto no casa con `_SENALES_TRANSITORIAS`, asi que el
# job queda en error / revision humana en vez de publicarse como copy vacio.
MSG_REFUSAL = "El modelo rehusó generar la respuesta (refusal)."


def _es_refusal(stop_reason: object) -> bool:
    """True si `stop_reason` indica un RECHAZO del modelo (`'refusal'`).

    `stop_reason` viaja en el `message` del evento `assistant`/`message_delta` del stream-json y,
    cuando el envelope `result` lo trae, tambien ahi. No es un error HTTP: sin esta deteccion el
    run pasaria como exito con `result` vacio.
    """
    return isinstance(stop_reason, str) and stop_reason == "refusal"


def arg_presupuesto() -> list[str]:
    """Devuelve `['--max-budget-usd', '<n>']` si `KENI_CLAUDE_MAX_USD` es valido; si no, `[]`.

    Tolerante: un valor ausente, vacio, no numerico o <= 0 se ignora (sin tope). El parseo
    del valor vive en `config.claude_max_usd`; aqui solo se compone el argv.
    """
    valor = config.claude_max_usd()
    if valor is None:
        return []
    # Sin notacion cientifica ni ceros colgantes: formato estable para el argv.
    texto = f"{valor:.10f}".rstrip("0").rstrip(".")
    return ["--max-budget-usd", texto]


def arg_max_turns() -> list[str]:
    """Devuelve `['--max-turns', '<n>']` si `KENI_CLAUDE_MAX_TURNS` es valido; si no, `[]`.

    El tope de turnos limita cuantos turnos de agente puede dar `claude` antes de
    detenerse (complementa al wall-timeout, que limita por tiempo). Tolerante: un valor
    ausente, vacio, no entero o <= 0 se ignora (sin tope de turnos). El parseo vive en
    `config.claude_max_turns`.
    """
    valor = config.claude_max_turns()
    if valor is None:
        return []
    return ["--max-turns", str(valor)]


def arg_skip_permisos() -> list[str]:
    """`['--dangerously-skip-permissions']` salvo `KENI_CLAUDE_SKIP_PERMISSIONS` falsy (def. ON).

    POR QUÉ: en modo `-p` (headless) NO hay forma interactiva de aprobar el permiso de una
    herramienta. SIN esto, en cuanto un flujo necesita una tool (WebFetch para corroborar
    datos en investigación/verificación, o Read de un fichero pasado por `--add-dir`), `claude` se
    cuelga pidiendo un permiso que nadie puede conceder. NO tiene NADA que ver con "skills":
    NO usamos el motor de skills de Claude Code (`.claude/skills`) —el contexto se inyecta
    EXPLÍCITAMENTE en el prompt desde la Texto de Prompts— y el cwd de generación es
    NEUTRO (sin `.claude/skills` ni `CLAUDE.md`). El subproceso corre ACOTADO (tope de
    turnos/coste/wall-timeout y, en hosted, dentro del contenedor). Desactivable con
    `KENI_CLAUDE_SKIP_PERMISSIONS=0` (p.ej. para depurar qué permiso falta). La decision
    vive en `config.claude_skip_permisos`.

    OJO (footgun): este flag NO es "el flag de las skills"; si lo quitas, TODOS los flujos
    que usan tools (WebFetch/Read) dejan de funcionar. Para endurecer, usa `--allowedTools`
    o amplía el veto de `arg_tools_restringidas`, no quites esto a ciegas.

    DEFENSA EN PROFUNDIDAD: como corremos con skip-permissions, las herramientas que ningún
    flujo de generación necesita (`Bash`/`Write`/`Edit`) se VETAN aparte con
    `arg_tools_restringidas`, para que un prompt-injection en el contenido de usuario/RSS no
    acabe ejecutando comandos ni escribiendo ficheros."""
    return ["--dangerously-skip-permissions"] if config.claude_skip_permisos() else []


def arg_tools_restringidas() -> list[str]:
    """Devuelve `['--disallowed-tools', '<t1>', '<t2>', ...]` con las herramientas vetadas.

    DEFENSA contra prompt-injection: como corremos con `--dangerously-skip-permissions`
    (para que las tools funcionen en headless sin aprobacion interactiva), vetamos por
    defecto `Bash`/`Write`/`Edit` —los vectores de mayor impacto (ejecucion de comandos,
    escritura de ficheros)— que NINGUN flujo de generacion necesita. Web (`WebFetch`/
    `WebSearch`) y `Read` NO se vetan por defecto: los prompts de investigacion
    (`brief-tendencias`) y la verificacion/verificación usan web para corroborar
    datos, y comparten este constructor de argv. Asi, aunque el contenido de usuario/RSS
    inyectado intente abrir una shell o escribir, `claude` lo rechaza. La lista es configurable
    (`config.claude_disallowed_tools`); un operador puede endurecerla.

    El flag de Claude Code es `--disallowed-tools` (alias `--disallowedTools`); usamos la
    forma kebab-case, consistente con `--max-budget-usd`/`--max-turns`. Los nombres de
    herramienta van como argumentos separados (acepta lista separada por coma/espacio).
    Si la lista esta vacia (config explicita) NO se añade el flag. La lista vive en
    `config.claude_disallowed_tools`."""
    tools = config.claude_disallowed_tools()
    if not tools:
        return []
    return ["--disallowed-tools", *tools]


def arg_sin_tools() -> list[str]:
    """`['--tools', '']`: deshabilita TODAS las herramientas para el run.

    El CLI documenta `--tools` con valor `""` como "disable all tools": con cero tools `claude`
    NO expone NINGUN esquema de herramienta en el system prompt, lo que ahorra ~17k tokens por
    llamada. Es para etapas JSON-in/JSON-out que no usan tool alguna (clustering/fusion,
    traduccion, decisor de formato, hashtags) y que corren a RAFAGAS (la cache se enfria y, sin
    esto, re-escriben esos 17k repetidamente). Con `--tools ""` NO tiene sentido añadir
    `--disallowed-tools` (no hay tools que vetar) ni `--add-dir` (no hay filesystem que abrir).
    """
    return ["--tools", ""]


def arg_excluir_secciones_dinamicas() -> list[str]:
    """`['--exclude-dynamic-system-prompt-sections']` si esta activo (def ON); si no, `[]`.

    Las secciones dinamicas del system prompt de Claude Code (entorno/CWD/git) son ruido para
    la generacion (cwd neutro), pase o no el copy su propio `--system-prompt`. La decision vive
    en `config.claude_exclude_dynamic_sections` (`KENI_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS` falsy lo apaga).
    """
    return (
        ["--exclude-dynamic-system-prompt-sections"]
        if config.claude_exclude_dynamic_sections()
        else []
    )


def arg_system_prompt(system: str) -> list[str]:
    """`['--system-prompt', '<system>']` si `system` no esta vacio; si no, `[]`.

    Lo usa la etapa de copy para enviar el contexto editorial ESTABLE de la marca (cuerpo
    base + linea editorial + indicaciones) como system prompt en vez de incrustarlo en el
    mensaje de usuario: ese system queda byte-identico por marca/dia y el proveedor lo cachea
    de verdad. El contenido del system es CONFIABLE (interno, lo cura el equipo); la fuente NO
    confiable (nota/RSS) se queda SIEMPRE en el mensaje de usuario, dentro de su envelope
    anti-inyeccion. El valor llega via `endurecer['system_prompt']`; "" / ausente = no se
    añade la flag (un run sin system editorial se comporta como antes).
    """
    return ["--system-prompt", system] if system else []


def arg_session_persistence() -> list[str]:
    """`['--no-session-persistence']` si NO se persiste la sesion (def); si se persiste, `[]`.

    El copy es one-shot: por defecto no persistimos la sesion. El `session_id` se sigue
    emitiendo en el stream aunque no se persista. `KENI_CLAUDE_SESSION_PERSISTENCE` truthy la
    reactiva (no añade flag). La decision vive en `config.claude_session_persistence`.
    """
    return [] if config.claude_session_persistence() else ["--no-session-persistence"]


def arg_fallback_model(*, omitir: bool = False) -> list[str]:
    """`['--fallback-model', '<lista>']` si hay fallback configurado; si no, `[]`.

    El CLI acepta varios modelos en UN solo `--fallback-model <lista>` (CSV). El fallback
    GLOBAL solo aplica cuando el run usa el modelo por defecto: si el job fija su propio
    `--model` (`omitir=True`), se respeta su eleccion y NO se añade fallback. El parseo/
    normalizacion vive en `config.claude_fallback_model`.
    """
    if omitir:
        return []
    lista = config.claude_fallback_model()
    return ["--fallback-model", lista] if lista else []


# --------------------------------------------------------------------------- #
# Suma de tokens de `modelUsage` + parseo del JSON de resultado                #
# --------------------------------------------------------------------------- #


def _tokens_de_model_usage(model_usage: object) -> tuple[int | None, int | None, str | None]:
    """Suma tokens in/out de `modelUsage` (dict modelo->{inputTokens,outputTokens}).

    Devuelve `(tokens_in, tokens_out, modelos)` donde `modelos` es la lista de modelos
    usados (coma-separada) o None. Si `modelUsage` no aporta nada utilizable, devuelve
    `(None, None, None)` para que el llamante caiga al fallback de `usage`.
    """
    if not isinstance(model_usage, dict) or not model_usage:
        return None, None, None
    total_in = 0
    total_out = 0
    visto = False
    modelos: list[str] = []
    for nombre, uso in model_usage.items():
        if isinstance(nombre, str) and nombre:
            modelos.append(nombre)
        if not isinstance(uso, dict):
            continue
        ti = _entero(uso.get("inputTokens"))
        to = _entero(uso.get("outputTokens"))
        if ti is not None:
            total_in += ti
            visto = True
        if to is not None:
            total_out += to
            visto = True
    if not visto:
        return None, None, (", ".join(modelos) or None)
    return total_in, total_out, (", ".join(modelos) or None)


def parsear_resultado_json(stdout: str) -> tuple[str, MetricasRun | None]:
    """Parsea el stdout de `claude ... --output-format json` en `(texto, metricas)`.

    Funcion PURA y testeable (no toca subprocess). Contrato:
      - Si `stdout` NO es JSON valido o no es un objeto con `type == "result"`, se trata
        TODO el stdout como texto y se devuelve `(stdout.strip(), None)` (degradacion
        robusta: la generacion de copy nunca debe romperse por un formato inesperado).
      - Si el objeto marca error (`is_error` true o `subtype` distinto de "success"),
        se lanza `GeneracionError` en espanol (mensaje especifico si es tope de presupuesto).
      - En caso de exito, el texto = campo `result`; las metricas se parsean sumando
        tokens preferentemente de `modelUsage`, con fallback a `usage`.
    """
    crudo = (stdout or "").strip()
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return crudo, None
    if not isinstance(datos, dict) or datos.get("type") != "result":
        # No es el objeto de resultado esperado: trata el stdout como texto plano.
        return crudo, None

    # Rechazo del modelo (refusal): NO es un error HTTP (`is_error` puede venir false), pero el
    # run NO produjo copy válido. Se trata como fallo terminal NO reintentable. El `result` lo
    # expone via `stop_reason` o `subtype == "refusal"`.
    subtype = datos.get("subtype")
    if _es_refusal(datos.get("stop_reason")) or (isinstance(subtype, str) and subtype == "refusal"):
        raise GeneracionError(MSG_REFUSAL)

    es_error = bool(datos.get("is_error")) or (subtype not in (None, "success"))
    if es_error:
        if isinstance(subtype, str) and subtype in _SUBTIPOS_PRESUPUESTO:
            raise GeneracionError(
                "El asistente alcanzó el tope de presupuesto configurado y se detuvo. "
                "Sube el límite o prueba con una nota más corta."
            )
        detalle = datos.get("result")
        detalle = detalle.strip() if isinstance(detalle, str) and detalle.strip() else (
            subtype if isinstance(subtype, str) and subtype else "error desconocido al generar"
        )
        raise GeneracionError(f"El asistente terminó con error: {detalle}")

    texto = datos.get("result")
    texto = texto.strip() if isinstance(texto, str) else ""

    usage = datos.get("usage") if isinstance(datos.get("usage"), dict) else {}
    tokens_in, tokens_out, modelo = _tokens_de_model_usage(datos.get("modelUsage"))
    if tokens_in is None and tokens_out is None:
        # Fallback a `usage` (tokens agregados a nivel de sesion).
        tokens_in = _entero(usage.get("input_tokens"))
        tokens_out = _entero(usage.get("output_tokens"))
    if modelo is None:
        m = datos.get("model")
        modelo = m if isinstance(m, str) and m else None

    # TTFT nativo del `result` (ms): `ttft_ms`, con `ttft_stream_ms` como fallback.
    duration_ms = _entero(datos.get("duration_ms"))
    ttft_ms = _entero(datos.get("ttft_ms"))
    if ttft_ms is None:
        ttft_ms = _entero(datos.get("ttft_stream_ms"))
    # Rendimiento: tokens de salida por segundo, solo si hay ambos valores positivos.
    tokens_por_s: float | None = None
    if tokens_out and duration_ms and tokens_out > 0 and duration_ms > 0:
        tokens_por_s = round(tokens_out / (duration_ms / 1000), 1)

    metricas = MetricasRun(
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cache_read=_entero(usage.get("cache_read_input_tokens")),
        cache_creation=_entero(usage.get("cache_creation_input_tokens")),
        num_turns=_entero(datos.get("num_turns")),
        total_cost_usd=_flotante(datos.get("total_cost_usd")),
        duration_ms=duration_ms,
        session_id=(datos.get("session_id") if isinstance(datos.get("session_id"), str) else None),
        modelo=modelo,
        ttft_ms=ttft_ms,
        tokens_por_s=tokens_por_s,
    )
    return texto, metricas


# --------------------------------------------------------------------------- #
# Fases de progreso de un run (en que ETAPA va, no cuanto falta)               #
# --------------------------------------------------------------------------- #
#
# Una generacion atraviesa estas etapas, en orden y sin retroceso:
#   - "razonando":  arranco, pero aun no llega texto VISIBLE del asistente (esta
#                   pensando / usando herramientas / el thinking no cuenta como texto).
#   - "generando":  ya llego el PRIMER token de texto visible (escribiendo el copy).
#   - "guardando":  el stream cerro con exito y el POST-PROCESADO (crear borradores,
#                   catalogar media) esta corriendo. La sella el finalizador ANTES de
#                   ejecutar `procesar`: es el marcador durable que permite al re-reclamo
#                   de la cola distinguir "murio durante claude" (re-ejecutable) de
#                   "murio guardando el resultado" (NO re-ejecutable: duplicaria borradores).
#   - "completado": el run termino (llego el `result`), con o sin texto.
# El acumulador deriva las dos primeras del propio stream ("guardando" la fija el
# finalizador); se persiste en el registro y la UI la pinta ("Razonando…" →
# "Escribiendo…" → "Terminando…"). Registros viejos sin fase la tratan como "" (la UI
# cae a su comportamiento previo).
FASE_RAZONANDO = "razonando"
FASE_GENERANDO = "generando"
FASE_GUARDANDO = "guardando"
FASE_COMPLETADO = "completado"

# Tope de la cola de razonamiento (thinking) que retenemos para mostrar en vivo: el
# pensamiento entero puede ser ENORME (decenas de miles de tokens); con la cola de los
# últimos ~6 KB basta para dar feedback inmediato ("qué está pensando") sin inflar el
# registro que se persiste en cada avance.
_MAX_RAZONAMIENTO = 6000


@dataclass
class AcumuladorStream:
    """Acumula el progreso de un run `--output-format stream-json --verbose`.

    El stream emite UN objeto JSON por linea (NDJSON). Hay DOS modos segun se pase o no
    `--include-partial-messages`:

      - SIN parciales (modo agente clasico):
          `system`/`init`  -> arranque (modelo/sesion); marca `iniciado`.
          `assistant`      -> un turno; suma tokens de su `message.usage` y cuenta turno.
          `result`         -> objeto FINAL: texto en `result`, metricas finales, terminal.

      - CON parciales (`--include-partial-messages`, lo que usamos para STREAMING en vivo):
          `stream_event` con `message_start`        -> nuevo turno (cuenta turno + modelo).
          `stream_event` `content_block_delta`/`text_delta` -> texto del ASISTENTE token a
            token: se ACUMULA en `texto` para que la UI lo muestre en vivo (el `thinking`
            NO se acumula: es irrelevante para el copy).
          `stream_event` `message_delta`/`usage`    -> tokens PARCIALES del turno.
          `assistant`/`result` siguen llegando igual; en modo parcial NO recontamos turnos
            ni tokens desde `assistant` (lo hacen los `stream_event`), via `_vio_stream`.

    `procesar_linea` consume una linea cruda y actualiza el estado. Es PURO respecto a
    I/O (no toca disco ni subprocess); el hilo lector lo alimenta y, tras cada avance,
    persiste `texto` + `metricas_parciales()`. Tolerante: lineas vacias o no JSON se
    ignoran. Si llega un `result` de error, deja `error=True` y `mensaje_error` (en
    espanol) para que el llamante marque el run en error.
    """

    iniciado: bool = False
    turnos: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    modelo: str | None = None
    session_id: str | None = None
    final: MetricasRun | None = None
    texto: str = ""
    # Razonamiento (thinking) en vivo: cola ACOTADA (`_MAX_RAZONAMIENTO`) de los últimos
    # tokens de pensamiento, para dar feedback inmediato mientras el modelo "piensa" antes
    # de escribir la respuesta (si no, la UI se queda en "Razonando…" sin nada).
    razonamiento: str = ""
    terminado: bool = False
    error: bool = False
    mensaje_error: str = ""
    # `stop_reason` observado en el stream (del `message_delta`/`assistant`). `"refusal"` marca
    # un RECHAZO del modelo: el run se trata como fallo terminal NO reintentable.
    stop_reason: str | None = None
    # True en cuanto llega un `stream_event` (modo `--include-partial-messages`): a partir
    # de ahi turnos/tokens se cuentan desde los `stream_event`, no desde `assistant`.
    _vio_stream: bool = False

    def procesar_linea(self, linea: str) -> None:
        """Consume UNA linea NDJSON del stream y actualiza el estado acumulado."""
        crudo = (linea or "").strip()
        if not crudo:
            return
        try:
            evento = json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            return  # línea irrelevante en el stream: lo ignoramos (degradacion robusta)
        if not isinstance(evento, dict):
            return
        tipo = evento.get("type")
        if tipo == "system" and evento.get("subtype") == "init":
            self.iniciado = True
            m = evento.get("model")
            if isinstance(m, str) and m and self.modelo is None:
                self.modelo = m
            sid = evento.get("session_id")
            if isinstance(sid, str) and sid:
                self.session_id = sid
        elif tipo == "stream_event":
            self._procesar_stream_event(evento.get("event"))
        elif tipo == "assistant":
            self.iniciado = True
            mensaje = evento.get("message")
            # Guarda: un `assistant` sin `message` dict (o malformado) no es un turno real;
            # no lo contamos ni leemos usage de el (evita un `turnos += 1` espurio).
            if not isinstance(mensaje, dict):
                return
            modelo = mensaje.get("model")
            if isinstance(modelo, str) and modelo and self.modelo is None:
                self.modelo = modelo
            self._registrar_stop_reason(mensaje.get("stop_reason"))
            # En modo parcial los turnos/tokens los cuentan los `stream_event`; aqui solo
            # tomamos el modelo (arriba). Sin parciales, contamos turno + tokens del usage.
            if self._vio_stream:
                return
            self.turnos += 1
            uso = mensaje.get("usage")
            if isinstance(uso, dict):
                ti = _entero(uso.get("input_tokens"))
                to = _entero(uso.get("output_tokens"))
                if ti is not None:
                    self.tokens_in += ti
                if to is not None:
                    self.tokens_out += to
        elif tipo == "result":
            self.terminado = True
            try:
                texto, metricas = parsear_resultado_json(crudo)
            except GeneracionError as e:
                self.error = True
                self.mensaje_error = str(e)
                return
            self.texto = texto
            self.final = metricas

    def _procesar_stream_event(self, evt: object) -> None:
        """Procesa un `stream_event` (modo `--include-partial-messages`): texto + turnos.

        - `message_start`        -> nuevo turno (y modelo si aun no se conocia).
        - `content_block_delta`  -> si es `text_delta`, ACUMULA el texto del asistente
                                     en `texto` (streaming en vivo); ignora `thinking_delta`.
        - `message_delta`        -> suma tokens parciales (`usage.input/output_tokens`).
        """
        self.iniciado = True
        self._vio_stream = True
        if not isinstance(evt, dict):
            return
        et = evt.get("type")
        if et == "message_start":
            self.turnos += 1
            msg = evt.get("message")
            if isinstance(msg, dict):
                m = msg.get("model")
                if isinstance(m, str) and m and self.modelo is None:
                    self.modelo = m
        elif et == "content_block_delta":
            delta = evt.get("delta")
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                t = delta.get("text")
                if isinstance(t, str):
                    self.texto += t
            elif isinstance(delta, dict) and delta.get("type") == "thinking_delta":
                # Razonamiento en vivo: acumulamos el thinking en una cola ACOTADA (solo el
                # final) para feedback inmediato sin retener el pensamiento entero.
                th = delta.get("thinking")
                if isinstance(th, str) and th:
                    self.razonamiento = (self.razonamiento + th)[-_MAX_RAZONAMIENTO:]
        elif et == "message_delta":
            delta = evt.get("delta")
            if isinstance(delta, dict):
                self._registrar_stop_reason(delta.get("stop_reason"))
            uso = evt.get("usage")
            if isinstance(uso, dict):
                ti = _entero(uso.get("input_tokens"))
                to = _entero(uso.get("output_tokens"))
                if ti is not None:
                    self.tokens_in += ti
                if to is not None:
                    self.tokens_out += to

    def _registrar_stop_reason(self, valor: object) -> None:
        """Anota el `stop_reason` del stream y marca error TERMINAL si es un rechazo (refusal).

        Un `"refusal"` se trata como fallo NO reintentable: se fija `error`/`mensaje_error` para
        que el llamante marque el run en error en vez de publicar el `result` (vacío o de rechazo)
        como copy. NO sobreescribe un error ya fijado por un `result` previo.
        """
        if not isinstance(valor, str) or not valor:
            return
        self.stop_reason = valor
        if _es_refusal(valor) and not self.error:
            self.error = True
            self.mensaje_error = MSG_REFUSAL

    def metricas_parciales(self) -> MetricasRun | None:
        """Metricas PARCIALES acumuladas hasta ahora (turnos/tokens), o None si aun nada."""
        if not (self.turnos or self.tokens_in or self.tokens_out):
            return None
        return MetricasRun(
            tokens_in=self.tokens_in or None,
            tokens_out=self.tokens_out or None,
            num_turns=self.turnos or None,
            modelo=self.modelo,
            session_id=self.session_id,
        )

    def fase(self) -> str:
        """Etapa de PROGRESO del run (en que etapa va), derivada del propio stream.

        - `FASE_COMPLETADO` en cuanto llega el `result` (terminal), con o sin texto.
        - `FASE_GENERANDO` desde que llega el PRIMER token de texto VISIBLE del asistente
          (el `thinking` NO cuenta: no acumula `texto`).
        - `FASE_RAZONANDO` mientras el run arranco pero aun no escribe texto visible.
        - `""` si aun no arranco (ni la usamos para nada todavia).

        Es PURA y monotona en la practica: el stream solo avanza (arranque → texto →
        result), nunca retrocede. La transicion razonando→generando la marca el primer
        `text_delta` (que ya alimenta `self.texto`).
        """
        if self.terminado:
            return FASE_COMPLETADO
        if self.texto:
            return FASE_GENERANDO
        if self.iniciado:
            return FASE_RAZONANDO
        return ""
