"""Dominio STREAM: parseo del stream/resultado de `claude`, metricas, presupuesto y verdicto.

Logica de negocio PURA (sin HTTP, sin subprocess, sin disco) extraida de `api/skills.py`
(hallazgo H6): aqui viven el acumulador del stream NDJSON, el parseo del JSON de
resultado, el calculo del argumento de presupuesto, la derivacion del verdicto a partir
de los simbolos ✅/⚠️/❌ y la limpieza determinista de emojis del copy. Tambien el
reparto de la salida cruda en piezas por red (via bloque ```json o, como fallback, por
encabezados de plataforma) y la derivacion del titulo.

Es la capa que consumen tanto `api.skills` (orquestacion HTTP) como `generaciones`
(trabajo en segundo plano), SIN crear el ciclo dominio↔api que antes obligaba a imports
perezosos en `generaciones.py`: este modulo no importa de `api/` ni de `generaciones`.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date


class SkillError(RuntimeError):
    """Error de ejecucion con mensaje ya en espanol, apto para mostrar al usuario."""


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


# Subconjunto de campos de `MetricasRun` que se persisten (run YAML + historial).
_CAMPOS_METRICAS_PERSISTIDOS: tuple[str, ...] = (
    "tokens_in",
    "tokens_out",
    "num_turns",
    "total_cost_usd",
    "duration_ms",
    "modelo",
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

# Env opcional: tope de presupuesto (USD) que se pasa a `claude` como `--max-budget-usd`.
_ENV_MAX_USD = "KENI_CLAUDE_MAX_USD"

# Env opcional: tope de turnos del agente que se pasa a `claude` como `--max-turns`.
_ENV_MAX_TURNS = "KENI_CLAUDE_MAX_TURNS"

# Env opcional: saltar permisos de `claude -p` (def. ON). Ver `arg_skip_permisos`.
_ENV_SKIP_PERMISOS = "KENI_CLAUDE_SKIP_PERMISSIONS"
_FALSY = frozenset({"0", "false", "no", "off", ""})

# Subtipos de error conocidos del campo `result` que conviene reportar especificamente.
_SUBTIPOS_PRESUPUESTO = frozenset({"error_max_budget", "error_budget_exceeded"})


def arg_presupuesto() -> list[str]:
    """Devuelve `['--max-budget-usd', '<n>']` si `KENI_CLAUDE_MAX_USD` es valido; si no, `[]`.

    Tolerante: un valor ausente, vacio, no numerico o <= 0 se ignora (sin tope).
    """
    crudo = (os.environ.get(_ENV_MAX_USD) or "").strip()
    if not crudo:
        return []
    try:
        valor = float(crudo)
    except ValueError:
        return []
    if valor <= 0:
        return []
    # Sin notacion cientifica ni ceros colgantes: formato estable para el argv.
    texto = f"{valor:.10f}".rstrip("0").rstrip(".")
    return ["--max-budget-usd", texto]


def arg_max_turns() -> list[str]:
    """Devuelve `['--max-turns', '<n>']` si `KENI_CLAUDE_MAX_TURNS` es valido; si no, `[]`.

    El tope de turnos limita cuantos turnos de agente puede dar `claude` antes de
    detenerse (complementa al wall-timeout, que limita por tiempo). Tolerante: un valor
    ausente, vacio, no entero o <= 0 se ignora (sin tope de turnos).
    """
    crudo = (os.environ.get(_ENV_MAX_TURNS) or "").strip()
    if not crudo:
        return []
    try:
        valor = int(crudo)
    except ValueError:
        return []
    if valor <= 0:
        return []
    return ["--max-turns", str(valor)]


def arg_skip_permisos() -> list[str]:
    """`['--dangerously-skip-permissions']` salvo `KENI_CLAUDE_SKIP_PERMISSIONS` falsy (def. ON).

    En modo `-p` (headless) NO hay forma interactiva de aprobar el "trust" de la carpeta
    ni el permiso de una herramienta. SIN esto, `claude` no carga las skills del proyecto
    (`.claude/skills`) —y la skill se ejecuta "a mano"— ni puede usar WebFetch/Bash (se
    cuelga pidiendo un permiso que nadie puede conceder). El subproceso corre ACOTADO (cwd
    de skills, tope de turnos/coste/wall-timeout y, en hosted, dentro del contenedor), por
    lo que se saltan los permisos por defecto. Desactivable con
    `KENI_CLAUDE_SKIP_PERMISSIONS=0` (p.ej. para depurar qué permiso falta)."""
    crudo = os.environ.get(_ENV_SKIP_PERMISOS, "1").strip().lower()
    return [] if crudo in _FALSY else ["--dangerously-skip-permissions"]


# --------------------------------------------------------------------------- #
# Conversion numerica tolerante + suma de tokens de `modelUsage`               #
# --------------------------------------------------------------------------- #


def _entero(valor: object) -> int | None:
    """Convierte `valor` a int si es un numero; None en cualquier otro caso."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor)
    return None


def _flotante(valor: object) -> float | None:
    """Convierte `valor` a float si es un numero; None en cualquier otro caso."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    return None


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
        se lanza `SkillError` en espanol (mensaje especifico si es tope de presupuesto).
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

    subtype = datos.get("subtype")
    es_error = bool(datos.get("is_error")) or (subtype not in (None, "success"))
    if es_error:
        if isinstance(subtype, str) and subtype in _SUBTIPOS_PRESUPUESTO:
            raise SkillError(
                "El asistente alcanzó el tope de presupuesto configurado y se detuvo. "
                "Sube el límite o prueba con una nota más corta."
            )
        detalle = datos.get("result")
        detalle = detalle.strip() if isinstance(detalle, str) and detalle.strip() else (
            subtype if isinstance(subtype, str) and subtype else "error desconocido al generar"
        )
        raise SkillError(f"El asistente terminó con error: {detalle}")

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

    metricas = MetricasRun(
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cache_read=_entero(usage.get("cache_read_input_tokens")),
        cache_creation=_entero(usage.get("cache_creation_input_tokens")),
        num_turns=_entero(datos.get("num_turns")),
        total_cost_usd=_flotante(datos.get("total_cost_usd")),
        duration_ms=_entero(datos.get("duration_ms")),
        session_id=(datos.get("session_id") if isinstance(datos.get("session_id"), str) else None),
        modelo=modelo,
    )
    return texto, metricas


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
            NO se acumula: es ruido para el copy).
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
    terminado: bool = False
    error: bool = False
    mensaje_error: str = ""
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
            return  # ruido en el stream: lo ignoramos (degradacion robusta)
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
            modelo = mensaje.get("model") if isinstance(mensaje, dict) else None
            if isinstance(modelo, str) and modelo and self.modelo is None:
                self.modelo = modelo
            # En modo parcial los turnos/tokens los cuentan los `stream_event`; aqui solo
            # tomamos el modelo (arriba). Sin parciales, contamos turno + tokens del usage.
            if self._vio_stream:
                return
            self.turnos += 1
            if isinstance(mensaje, dict):
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
            except SkillError as e:
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
        elif et == "message_delta":
            uso = evt.get("usage")
            if isinstance(uso, dict):
                ti = _entero(uso.get("input_tokens"))
                to = _entero(uso.get("output_tokens"))
                if ti is not None:
                    self.tokens_in += ti
                if to is not None:
                    self.tokens_out += to

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


# --------------------------------------------------------------------------- #
# Verdicto del copy (primera linea ✅/⚠️/❌)                                    #
# --------------------------------------------------------------------------- #

# Bloque ```json ... ``` cercado (el ultimo de la salida es el de las piezas).
# Tolera "json"/"JSON" tras las comillas y espacios; captura el cuerpo (no greedy).
_RE_BLOQUE_JSON = re.compile(r"```[ \t]*[jJ][sS][oO][nN][ \t]*\r?\n(.*?)```", re.DOTALL)

# Mapa del simbolo de veredicto (primera linea) a su valor interno estable.
_VEREDICTO_POR_SIMBOLO = {"✅": "listo", "⚠️": "revisar", "❌": "no_publicar"}


def derivar_verdicto(texto: str) -> str:
    """Deriva el veredicto desde la PRIMERA linea con contenido (✅/⚠️/❌).

    Devuelve "listo"|"revisar"|"no_publicar" segun el simbolo que aparezca en esa
    linea, o "" si no hay ninguno. Mira solo la primera linea no vacia.
    """
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        for simbolo, valor in _VEREDICTO_POR_SIMBOLO.items():
            if simbolo in linea:
                return valor
        return ""
    return ""


# --------------------------------------------------------------------------- #
# Limpieza de emojis del copy generado por IA (determinista)                   #
# --------------------------------------------------------------------------- #

# Rangos unicode de emojis/simbolos pictograficos que quitamos del copy. Cubre:
#   - Emoticonos (U+1F600-U+1F64F)
#   - Misc Symbols and Pictographs (U+1F300-U+1F5FF)
#   - Transporte y mapas (U+1F680-U+1F6FF)
#   - Symbols and Pictographs Extended-A (U+1FA70-U+1FAFF)
#   - Supplemental Symbols and Pictographs (U+1F900-U+1F9FF)
#   - Banderas / Regional Indicators (U+1F1E6-U+1F1FF)
#   - Misc Symbols (U+2600-U+26FF) y Dingbats (U+2700-U+27BF) -> incluye ✅⚠❌
#   - Variation Selector U+FE0F y ZWJ U+200D (unen secuencias tipo familia/banderas)
# NOTA: NO toca acentos (latin) ni los caracteres de las URLs (ASCII), porque esos
# puntos de codigo caen fuera de estos rangos. El veredicto se deriva ANTES de
# aplicar esto (ver `parsear_salida`), asi que su simbolo no se pierde.
_RE_EMOJI = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticonos
    "\U0001f300-\U0001f5ff"  # misc symbols and pictographs
    "\U0001f680-\U0001f6ff"  # transporte y mapas
    "\U0001fa70-\U0001faff"  # symbols and pictographs extended-a
    "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
    "\U0001f1e6-\U0001f1ff"  # regional indicators (banderas)
    "\U00002600-\U000026ff"  # misc symbols (incluye ⚠)
    "\U00002700-\U000027bf"  # dingbats (incluye ✅❌)
    "\U0000fe0f"  # variation selector-16
    "\U0000200d"  # zero width joiner (ZWJ)
    "]+",
    flags=re.UNICODE,
)

# Colapsa dobles espacios (no saltos de linea) que deja el borrado de emojis.
_RE_ESPACIOS = re.compile(r"[ \t]{2,}")
# Espacios/tabs colgando al FINAL de una linea (antes de un salto o del fin).
_RE_COLA_LINEA = re.compile(r"[ \t]+(?=\n|$)")


def quitar_emojis(texto: str) -> str:
    """Quita emojis/simbolos pictograficos del texto de forma determinista.

    Borra los puntos de codigo en `_RE_EMOJI` (emojis, dingbats, banderas,
    variation selectors y ZWJ), colapsa los dobles espacios que pueda dejar el
    borrado y recorta los extremos. NO toca acentos ni URLs (caen fuera de los
    rangos). Sobre un texto sin emojis es practicamente la identidad (salvo el
    recorte de extremos y el colapso de espacios dobles).
    """
    if not texto:
        return texto
    limpio = _RE_EMOJI.sub("", texto)
    # Colapsa los dobles espacios/tabs horizontales (no los saltos de linea) que
    # deja el borrado de un emoji rodeado de espacios.
    limpio = _RE_ESPACIOS.sub(" ", limpio)
    # Quita el espacio que pueda quedar colgando al final de cada linea (p.ej. un
    # emoji al final de la linea); conserva los saltos y la sangria a la izquierda.
    limpio = _RE_COLA_LINEA.sub("", limpio)
    return limpio.strip()


# --------------------------------------------------------------------------- #
# Reparto de la salida en piezas por red (JSON cercado o, fallback, encabezados) #
# --------------------------------------------------------------------------- #

# Variantes tolerantes de etiqueta -> id canonico de `redes`. En minusculas y sin
# `#`/`*`/`:` (esos se quitan al normalizar el encabezado). El orden no importa: el
# reparto final se emite en el orden fijo de las redes pedidas.
_ALIAS_RED: dict[str, str] = {
    "x": "x",
    "x/twitter": "x",
    "twitter": "x",
    "instagram": "instagram",
    "ig": "instagram",
    "facebook": "facebook",
    "fb": "facebook",
    "tiktok": "tiktok",
    "youtube": "youtube",
}

# Encabezado de plataforma: linea cuyo unico contenido (ignorando `#`/`##`, `**`,
# `:` y espacios) es una de las etiquetas conocidas. Captura la etiqueta cruda.
# El sufijo tolera `:` y `*` en cualquier orden ("Instagram:", "**Twitter**",
# "**Instagram:**").
_RE_ENCABEZADO_RED = re.compile(
    r"^[ \t]*#{0,6}[ \t]*\*{0,2}[ \t]*"
    r"([A-Za-z][A-Za-z/]*)"
    r"[ \t]*[:*]*[ \t]*$"
)


def _id_red_de_encabezado(linea: str) -> str | None:
    """Si `linea` es un encabezado de plataforma reconocible, devuelve su id canonico.

    Tolera `#`/`##`/.../`**`/`:` alrededor de la etiqueta ("## X", "**Twitter:**",
    "Instagram:", "IG"). Devuelve None si la linea no es uno de esos encabezados.
    """
    m = _RE_ENCABEZADO_RED.match(linea)
    if m is None:
        return None
    return _ALIAS_RED.get(m.group(1).strip().lower())


def _repartir_por_encabezados(texto: str, redes_ids: list[str]) -> dict[str, str]:
    """Parte `texto` por encabezados de plataforma y asigna el cuerpo a cada red.

    Recorre las lineas: cada encabezado reconocible abre una seccion; el texto hasta
    el siguiente encabezado (o el fin) es el copy de esa red. Acota a `redes_ids`
    (ignora redes fuera de las pedidas) y deja la primera ocurrencia ante duplicados.
    Devuelve `{red_id: copy}` (vacio si no hay encabezados reconocibles).
    """
    permitidas = set(redes_ids)
    por_red: dict[str, list[str]] = {}
    actual: str | None = None
    for linea in texto.splitlines():
        red = _id_red_de_encabezado(linea)
        if red is not None:
            # Solo abrimos seccion para redes pedidas y no vistas antes.
            actual = red if (red in permitidas and red not in por_red) else None
            if actual is not None:
                por_red[actual] = []
            continue
        if actual is not None:
            por_red[actual].append(linea)
    return {red: "\n".join(cuerpo).strip() for red, cuerpo in por_red.items()}


def _piezas_desde_por_red(por_red: dict[str, str], redes_ids: list[str]) -> list[dict[str, object]]:
    """Construye las piezas en el ORDEN FIJO de las redes pedidas, sin emojis.

    Cada `contenido` se limpia con `quitar_emojis` y `caracteres = len(contenido)`
    YA limpio. Solo incluye redes presentes en `por_red`.
    """
    piezas: list[dict[str, object]] = []
    for r in redes_ids:
        if r not in por_red:
            continue
        contenido = quitar_emojis(por_red[r])
        piezas.append({"red": r, "contenido": contenido, "caracteres": len(contenido)})
    return piezas


def parsear_salida(salida: str, redes_ids: list[str]) -> dict[str, object]:
    """Parte la salida cruda en `resultado` limpio + `piezas` + `verdicto`.

    - Localiza el ULTIMO bloque ```json cercado y lo `json.loads`; mapea su clave
      `piezas` a `[{red, contenido, caracteres}]` (solo redes en `redes_ids`, en
      orden fijo; `caracteres` = len(contenido)).
    - QUITA ese bloque json del texto para que `resultado` quede limpio.
    - Deriva `verdicto` de la primera linea con ✅/⚠️/❌ ANTES de tocar nada (asi el
      simbolo se conserva aunque luego se borren los emojis del copy).
    - FALLBACK: si no hay bloque JSON valido (o no trae `piezas` utilizables), intenta
      repartir el texto por ENCABEZADOS de plataforma. Si tampoco hay encabezados
      reconocibles, `piezas=[]` (comportamiento previo).
    - `resultado` y el `contenido` de cada pieza salen SIN emojis (`quitar_emojis`);
      el JSON sigue siendo la via preferente, el fallback solo actua si aquel falla.

    Devuelve `{"resultado": str, "piezas": [...], "verdicto": str}`.
    """
    salida = salida or ""
    # El veredicto se deriva PRIMERO, sobre el texto crudo, para no perder su simbolo.
    verdicto = derivar_verdicto(salida)

    coincidencias = list(_RE_BLOQUE_JSON.finditer(salida))
    datos = None
    limpio = salida.strip()
    if coincidencias:
        ultima = coincidencias[-1]
        try:
            datos = json.loads(ultima.group(1))
        except (json.JSONDecodeError, ValueError):
            # JSON malformado: dejamos el texto tal cual (incluido el bloque), sin piezas via JSON.
            datos = None
        else:
            # Texto LIMPIO: quitamos solo el ultimo bloque json (el de las piezas).
            limpio = (salida[: ultima.start()] + salida[ultima.end():]).strip()

    por_red: dict[str, str] = {}
    permitidas = set(redes_ids)
    crudas = datos.get("piezas") if isinstance(datos, dict) else None
    if isinstance(crudas, list):
        for cruda in crudas:
            if not isinstance(cruda, dict):
                continue
            red = cruda.get("red")
            texto = cruda.get("texto")
            if not isinstance(red, str) or red not in permitidas:
                continue  # ignora redes desconocidas o fuera de las pedidas
            if not isinstance(texto, str):
                continue
            por_red.setdefault(red, texto)  # primera gana ante duplicados

    # FALLBACK: sin piezas via JSON, intenta repartir por encabezados de plataforma.
    if not por_red:
        por_red = _repartir_por_encabezados(limpio, redes_ids)

    piezas = _piezas_desde_por_red(por_red, redes_ids)
    return {"resultado": quitar_emojis(limpio), "piezas": piezas, "verdicto": verdicto}


# --------------------------------------------------------------------------- #
# Titulo derivado de la nota                                                   #
# --------------------------------------------------------------------------- #

# Largo maximo del titulo derivado de la nota (chars).
_MAX_TITULO = 80


def derivar_titulo(texto: str) -> str:
    """Deriva un titulo legible desde el texto: 1a linea no vacia recortada a ~80 chars.

    Si no hay ninguna linea con contenido, cae a `"Borrador {YYYY-MM-DD}"`.
    """
    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        if limpia:
            if len(limpia) > _MAX_TITULO:
                return limpia[:_MAX_TITULO].rstrip() + "…"
            return limpia
    return f"Borrador {date.today().isoformat()}"


# --------------------------------------------------------------------------- #
# Normalizacion de redes pedidas                                              #
# --------------------------------------------------------------------------- #


def normalizar_redes(crudas: Iterable[str] | None, *, canonicas: list[str]) -> list[str]:
    """Filtra/ordena ids de red contra las `canonicas`; sin entradas validas => todas.

    Ignora ids desconocidos o repetidos. El resultado respeta SIEMPRE el orden de
    `canonicas`, sea cual sea el orden en que llegaron. Si no llega ninguna red valida
    (lista vacia, None o solo basura), se devuelven todas las `canonicas`.
    """
    if crudas is None:
        return list(canonicas)
    validas = set(canonicas)
    pedidas = {r for r in crudas if isinstance(r, str) and r in validas}
    if not pedidas:
        return list(canonicas)
    return [r for r in canonicas if r in pedidas]
