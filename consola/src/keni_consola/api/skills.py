"""API Skills: generacion de copy (Claude por debajo) EN SEGUNDO PLANO + historial.

El SPA elige una skill de una ALLOWLIST curada, una marca, pega una nota/transcripcion
(o sube un archivo) y pide "Generar". La consola construye el prompt y lanza un TRABAJO
de IA en background via `consola.generaciones` (stream-json, seguible token a token); el
endpoint responde de INMEDIATO con `{generacion}` (estado "ejecutando"). El frontend
sondea `GET /api/generaciones/{id}` hasta el estado terminal. Al COMPLETARSE, el callback
`construir_procesar_copy` parsea el `result`, registra el historial (con metricas) y
AUTO-GUARDA una publicacion (borrador) por pieza; eso queda en el `resultado` del
trabajo. Nada se publica: solo borradores.

SEGURIDAD (resumen):
  - Las skills viven en ARCHIVOS (`skills_catalogo`): una carpeta por skill con su
    `SKILL.md` + `keni.yaml`. La pertenencia se valida contra el catalogo; las marcas
    contra su allowlist fija (`MARCAS`).
  - El texto del usuario viaja como ARGUMENTO de subprocess (lista argv), nunca por
    shell: sin `shell=True`, sin inyeccion de shell (ver `consola.generaciones`).
  - El trabajo corre con wall-timeout; los errores (binario no encontrado, timeout,
    presupuesto) quedan como `estado="error"` con mensaje en espanol, sin tracebacks.

SUBIR ARCHIVO: el endpoint multipart `/api/skills/ejecutar-archivo` recibe el
archivo, lo guarda en un dir TEMPORAL del SO con NOMBRE SANEADO (nunca el del
cliente), aplicando un LIMITE DE TAMANO por tipo y comprobandolo MIENTRAS lee (en
trozos).
  - `clip-a-copy` (media): su ruta temporal va al PROMPT (la skill transcribe en local)
    y el temporal se borra al TERMINAR el trabajo. El resto son skills de texto: se LEE
    el texto del archivo y el temporal se borra de inmediato.

INYECCION/MOCKEO: el unico punto que toca el binario `claude` es
`generaciones.lanzar_job_claude` (inyectable). Los tests lo reemplazan por una fake
(`lanzador_generacion_completa`) que corre el `procesar` real con una salida canned,
para NUNCA llamar a `claude` real en CI.

GENERACION POR RED: ambos endpoints aceptan `redes` (ids de `consola.redes`; en
multipart como campo repetido o CSV). Si no llegan, se usan las 5. Se anade al
prompt una instruccion ADITIVA para que la skill (a) genere solo esas redes y (b)
cierre con un bloque ```json con `piezas`. `parsear_salida` localiza ese ULTIMO
bloque, lo quita del `resultado`, y devuelve `piezas:[{red,contenido,caracteres}]`
y `verdicto` ("listo"|"revisar"|"no_publicar"|"") derivado de la 1a linea ✅/⚠️/❌.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, marcas, redes, repos, skills_catalogo
from .._http_json import leer_json
from .publicaciones import _publicacion_a_dict

# --------------------------------------------------------------------------- #
# Allowlists: skills curadas y marcas (NUNCA invocaciones arbitrarias)         #
# --------------------------------------------------------------------------- #


# Las SKILLS ya no son una allowlist fija en codigo: viven en ARCHIVOS y se gestionan
# via `skills_catalogo` (carpeta por skill con `SKILL.md` + `keni.yaml`). La pertenencia
# se resuelve dinamicamente (`_AllowlistSkills`) y los metadatos para la UI salen de
# `skills_catalogo.listar()` (ver `opciones`).

# Marcas editoriales permitidas: TODAS las del catalogo unico. VALUE interno = id
# canonico (slug-guion); etiqueta visible = nombre humano con acentos.
MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())

_MARCAS_IDS = {m[0] for m in MARCAS}

# Mapa id->nombre de marca para enriquecer el historial con nombres humanos.
_MARCA_NOMBRE = dict(MARCAS)


class _AllowlistSkills:
    """Proxy `x in _SKILLS_IDS` que consulta el CATALOGO DE ARCHIVOS en cada uso.

    Antes `_SKILLS_IDS` era un set fijo de skills hardcodeadas; ahora las skills son
    editables en disco, asi que la pertenencia se resuelve dinamicamente contra
    `skills_catalogo.existe`. Mantiene la misma sintaxis (`in`) que usan `ejecutar`,
    `ejecutar_archivo` y `api.rss`.
    """

    def __contains__(self, skill_id: object) -> bool:
        return isinstance(skill_id, str) and skills_catalogo.existe(skill_id)


# Allowlist de skills: pertenencia dinamica contra el catalogo de archivos.
_SKILLS_IDS = _AllowlistSkills()


def _nombre_skill(skill_id: str) -> str:
    """Nombre humano de una skill desde el catalogo de archivos; cae al id si no existe."""
    skill = skills_catalogo.obtener(skill_id)
    return skill.nombre if skill is not None else skill_id

# Instruccion ADITIVA de estilo que se anade a TODO prompt de generacion: el copy
# no debe llevar emojis. Es defensa en profundidad; ademas `quitar_emojis` los borra
# de forma determinista por si el modelo igual mete alguno.
_INSTRUCCION_SIN_EMOJIS = "No uses emojis en el copy."

# Tope de tamano del texto de entrada (evita prompts gigantes accidentales).
_MAX_TEXTO = 60_000

# Skills que parten de un MEDIA (video/audio): su archivo subido se referencia por
# RUTA en el prompt (la skill lo transcribe en local). El resto son de texto.
_SKILLS_MEDIA = frozenset({"clip-a-copy"})

# Limites de tamano de subida (bytes).
_MAX_SUBIDA_TEXTO = 25 * 1024 * 1024  # 25 MB para notas .txt/.md
_MAX_SUBIDA_MEDIA = 500 * 1024 * 1024  # 500 MB para video/audio (clip-a-copy)
# Trozo de lectura al volcar el archivo a disco (para medir tamano sin cargarlo todo).
_TROZO_SUBIDA = 1024 * 1024  # 1 MB

# Longitud del preview del resultado en el historial (chars).
_PREVIEW_CHARS = 140


def _max_subida(skill: str) -> int:
    """Limite de tamano (bytes) de subida para una skill, con override por env.

    `KENI_SKILLS_MAX_SUBIDA_MB` (entero, en MB) lo sobreescribe; si no es valido, se ignora.
    """
    base = _MAX_SUBIDA_MEDIA if skill in _SKILLS_MEDIA else _MAX_SUBIDA_TEXTO
    env = os.environ.get("KENI_SKILLS_MAX_SUBIDA_MB")
    if env:
        try:
            mb = int(env)
        except ValueError:
            return base
        if mb > 0:
            return mb * 1024 * 1024
    return base


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
# Invocacion de Claude (headless) — punto inyectable para los tests            #
# --------------------------------------------------------------------------- #


def _cwd_skills() -> Path:
    """Directorio desde el que corremos `claude` para que las skills esten a mano.

    Preferencia: env `KENI_SKILLS_CWD` -> repo keni-social conocido -> cwd actual.
    """
    env = os.environ.get("KENI_SKILLS_CWD")
    if env:
        candidato = Path(env)
        if candidato.is_dir():
            return candidato
    repo = Path.home() / "projects" / "keni-social"
    if repo.is_dir():
        return repo
    return Path.cwd()


def _instruccion_redes(redes_ids: list[str]) -> str:
    """Instruccion ADITIVA: limita las redes y pide un bloque json con las piezas.

    No cambia el copy ni la auto-verificacion de la skill; solo (a) acota a las
    redes pedidas y (b) anade, AL FINAL, un bloque ```json con `piezas` para esas
    redes, que la consola parsea luego. `redes_ids` ya viene validado contra las
    redes canonicas (en orden fijo).
    """
    etiquetas = ", ".join(redes.nombre_por_id(r) for r in redes_ids)
    ids_json = ", ".join(f'"{r}"' for r in redes_ids)
    return (
        f"Genera el copy SOLO para estas redes: {etiquetas}. "
        "Mantén tu formato y tu auto-verificación habituales. "
        "Además, al FINAL de toda tu respuesta, añade un único bloque de código "
        'cercado ```json con esta forma exacta: {"piezas": [{"red": "<id>", '
        '"texto": "<copy de esa red>"}, ...]}, usando como <id> únicamente estos '
        f"valores: {ids_json}. Incluye una pieza por cada red pedida."
    )


def _prompt_generico(verbo: str, skill: str, marca: str, contenido: str, redes_ids: list[str] | None) -> str:
    """Construye un prompt cuando la skill NO esta en el catalogo (back-compat puro)."""
    base = f"usa {skill} con {verbo}, marca {marca}:\n\n{contenido}"
    base = f"{base}\n\n{_INSTRUCCION_SIN_EMOJIS}"
    if redes_ids:
        return f"{base}\n\n{_instruccion_redes(redes_ids)}"
    return base


def construir_prompt(skill: str, marca: str, texto: str, redes_ids: list[str] | None = None) -> str:
    """Construye el prompt de invocacion headless para una skill+marca+texto (BACK-COMPAT).

    Mapea `texto` al PRIMER campo de texto de la skill y delega en
    `skills_catalogo.render_invocacion` (la via dinamica de archivos). Si la skill no
    esta en el catalogo (caso raro / legado), cae a un prompt generico equivalente al
    de antes. Lo usa `api.rss.generar` sin cambios. El texto viaja como argumento de
    subprocess (no por shell): sin inyeccion. La instruccion ADITIVA de redes solo se
    anade si la skill `aplica_redes`.
    """
    skilldef = skills_catalogo.obtener(skill)
    if skilldef is None:
        return _prompt_generico("la siguiente nota", skill, marca, texto, redes_ids)
    campo = skilldef.primer_campo_texto()
    valores = {campo.id: texto} if campo is not None else {}
    return skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)


def construir_prompt_ruta(
    skill: str, marca: str, ruta: str, redes_ids: list[str] | None = None
) -> str:
    """Construye el prompt para una skill de MEDIA que parte de una RUTA de archivo.

    Mapea `ruta` al campo de tipo archivo de la skill (o, si no hay, al primer campo) y
    delega en `render_invocacion`. Cae a un prompt generico si la skill no esta en el
    catalogo (back-compat).
    """
    skilldef = skills_catalogo.obtener(skill)
    if skilldef is None:
        return _prompt_generico("el archivo en esta ruta", skill, marca, ruta, redes_ids)
    campo = skilldef.campo_archivo() or skilldef.primer_campo_texto()
    valores = {campo.id: ruta} if campo is not None else {}
    return skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)


# Extension de la ruta saneada: sin punto, [a-z0-9] hasta 8 chars.
_RE_EXT = re.compile(r"^[a-z0-9]{1,8}$")


def _extension_segura(nombre_cliente: str | None) -> str:
    """Devuelve una extension SEGURA (`.mp4`, `.txt`, ...) o "" si no es reconocible.

    NO usa el nombre del cliente como nombre de archivo; solo extrae la extension.
    """
    if not nombre_cliente:
        return ""
    sufijo = Path(nombre_cliente).suffix.lower().lstrip(".")
    return f".{sufijo}" if _RE_EXT.match(sufijo) else ""


# Env opcional: tope de presupuesto (USD) que se pasa a `claude` como `--max-budget-usd`.
_ENV_MAX_USD = "KENI_CLAUDE_MAX_USD"

# Subtipos de error conocidos del campo `result` que conviene reportar especificamente.
_SUBTIPOS_PRESUPUESTO = frozenset({"error_max_budget", "error_budget_exceeded"})


def _arg_presupuesto() -> list[str]:
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


def normalizar_redes(crudas: Iterable[str] | None) -> list[str]:
    """Filtra/ordena ids de red contra las canonicas; sin entradas validas => las 5.

    Ignora ids desconocidos o repetidos. El resultado respeta SIEMPRE el orden fijo
    de `redes.REDES`, sea cual sea el orden en que llegaron. Si no llega ninguna red
    valida (lista vacia, None o solo basura), se usan las 5 redes canonicas.
    """
    if crudas is None:
        return redes.ids()
    pedidas = {r for r in crudas if isinstance(r, str) and redes.es_red(r)}
    if not pedidas:
        return redes.ids()
    return [r for r in redes.ids() if r in pedidas]


# --------------------------------------------------------------------------- #
# Subida de archivo: guardado seguro en temporal + lectura/limpieza            #
# --------------------------------------------------------------------------- #


def _leer_texto_archivo(ruta: Path) -> str:
    """Lee el texto de un archivo de nota/transcripcion (utf-8, respaldo latin-1)."""
    crudo = ruta.read_bytes()
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return crudo.decode("latin-1", errors="replace")


async def _guardar_subida_segura(archivo: UploadFile, *, limite: int) -> tuple[Path, Path]:
    """Vuelca un `UploadFile` a un dir temporal del SO de forma segura.

    - Crea un dir efimero con `tempfile.mkdtemp` (permisos restringidos del SO).
    - El NOMBRE en disco lo generamos (uuid + extension saneada); NUNCA el del cliente.
    - Mide el tamano MIENTRAS escribe en trozos; si supera `limite`, aborta y limpia.

    Devuelve `(ruta_archivo, dir_temporal)`. El llamante DEBE borrar el dir tras procesar.
    """
    dir_temporal = Path(tempfile.mkdtemp(prefix="keni-skills-"))
    extension = _extension_segura(archivo.filename)
    destino = dir_temporal / f"{uuid.uuid4().hex}{extension}"
    total = 0
    try:
        with destino.open("wb") as salida:
            while True:
                trozo = await archivo.read(_TROZO_SUBIDA)
                if not trozo:
                    break
                total += len(trozo)
                if total > limite:
                    raise SkillError(
                        "El archivo es demasiado grande; sube uno más pequeño e "
                        "inténtalo de nuevo."
                    )
                salida.write(trozo)
    except SkillError:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise
    except Exception as e:  # noqa: BLE001 -- cualquier fallo de E/S: limpia y reporta en espanol
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise SkillError("No se pudo guardar el archivo subido.") from e
    if total == 0:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        raise SkillError("El archivo está vacío.")
    return destino, dir_temporal


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


def _preview(resultado: str) -> str:
    """Primeros ~140 chars del resultado para el listado del historial."""
    resultado = resultado.strip()
    if len(resultado) <= _PREVIEW_CHARS:
        return resultado
    return resultado[:_PREVIEW_CHARS].rstrip() + "…"


# Bloque ```json ... ``` cercado (el ultimo de la salida es el de las piezas).
# Tolera "json"/"JSON" tras las comillas y espacios; captura el cuerpo (no greedy).
_RE_BLOQUE_JSON = re.compile(r"```[ \t]*[jJ][sS][oO][nN][ \t]*\r?\n(.*?)```", re.DOTALL)

# Mapa del simbolo de veredicto (primera linea) a su valor interno estable.
_VEREDICTO_POR_SIMBOLO = {"✅": "listo", "⚠️": "revisar", "❌": "no_publicar"}


def _derivar_verdicto(texto: str) -> str:
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
# Fallback de reparto por encabezados de plataforma (cuando NO hay JSON valido) #
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
    verdicto = _derivar_verdicto(salida)

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
# Cosecha de IMAGENES de salida (skills de imagen: estudio-imagen)             #
# --------------------------------------------------------------------------- #
#
# Las skills de imagen (estudio-imagen) producen ARCHIVOS .png con las herramientas
# deterministas (editar.py/componer.py) o el adaptador generativo (generar.py). La
# salida de Claude es texto (el documento del revisor) que MENCIONA las rutas de esos
# archivos. Para PREVISUALIZARLOS en la Consola, tras completar la generacion
# localizamos esas rutas, las importamos al almacen de media (`/api/media/...`) y las
# devolvemos como `imagenes` en el `resultado`.

# Extensiones de imagen que reconocemos en la salida (las que producen las herramientas).
_EXT_IMAGEN = ("png", "jpg", "jpeg", "webp", "gif")

# Ruta a un archivo de imagen dentro del texto: una ruta absoluta (POSIX) o relativa con
# separadores, terminada en una extension de imagen. Tolera comillas/parentesis alrededor.
_RE_RUTA_IMAGEN = re.compile(
    r"(/?(?:[^\s\"'`<>|]+/)+[^\s\"'`<>|]+\.(?:" + "|".join(_EXT_IMAGEN) + r"))",
    re.IGNORECASE,
)

# Tope defensivo de imagenes que importamos de una sola salida (evita abusos).
_MAX_IMAGENES = 12


def _rutas_imagen_en_texto(salida: str) -> list[str]:
    """Extrae rutas de archivos de imagen mencionadas en la salida (orden, sin duplicar)."""
    if not salida:
        return []
    vistas: list[str] = []
    for m in _RE_RUTA_IMAGEN.finditer(salida):
        ruta = m.group(1)
        if ruta not in vistas:
            vistas.append(ruta)
    return vistas


def cosechar_imagenes(salida: str) -> list[dict[str, str]]:
    """Importa al almacen de media las imagenes que la salida menciona por ruta.

    Localiza rutas de archivos de imagen en `salida`, importa al media (copia) las que
    existan y sean imagenes validas, y devuelve `[{nombre, url}]` para previsualizarlas.
    Tolerante: una ruta que no exista o no se pueda importar simplemente se OMITE (la
    previsualizacion es un extra, nunca debe romper la generacion). Limita a
    `_MAX_IMAGENES` para no abusar del almacen.
    """
    from .. import media

    imagenes: list[dict[str, str]] = []
    for ruta in _rutas_imagen_en_texto(salida):
        if len(imagenes) >= _MAX_IMAGENES:
            break
        try:
            nombre = media.importar_imagen(ruta)
        except media.MediaError:
            continue  # ruta inexistente / no es imagen / demasiado grande: se omite
        except Exception:  # noqa: BLE001 -- la previsualizacion nunca rompe la generacion
            continue
        imagenes.append({"nombre": nombre, "url": f"/api/media/{nombre}"})
    return imagenes


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


def _crear_publicaciones_desde_piezas(
    piezas: list[dict[str, object]],
    *,
    marca: str,
    titulo: str,
    verdicto: str,
    origen: str,
    redes_filtro: set[str] | None = None,
) -> list[dict[str, object]]:
    """Crea UNA publicacion (borrador) por pieza y devuelve sus dicts serializados.

    Cada pieza aporta `red` y `contenido`. Si `redes_filtro` no es None, solo se
    crean las piezas cuya red este en el filtro. `marca`/`titulo`/`verdicto`/`origen`
    son comunes a todas. El estado siempre nace como `borrador`.
    """
    creadas: list[dict[str, object]] = []
    for pieza in piezas:
        red = pieza.get("red")
        contenido = pieza.get("contenido")
        if not isinstance(red, str) or not redes.es_red(red):
            continue
        if redes_filtro is not None and red not in redes_filtro:
            continue
        if not isinstance(contenido, str):
            contenido = ""
        pub = repos.crear_publicacion(
            marca,
            red,
            titulo=titulo,
            contenido=contenido,
            estado="borrador",
            veredicto=verdicto,
            origen=origen,
        )
        creadas.append(_publicacion_a_dict(pub))
    return creadas


# Orden de presentacion de los grupos en `opciones` (validadas primero).
_ORDEN_GRUPOS: tuple[str, ...] = ("validadas", "experimentales")


def _skill_para_opciones(skill: skills_catalogo.SkillDef) -> dict[str, object]:
    """Forma reducida de una skill para el formulario de generacion del SPA.

    Incluye lo que el frontend necesita para pintar el formulario dinamico (campos,
    si aplica a redes, tipo de salida, si es media). NO incluye la plantilla de
    invocacion (eso es de la pagina de gestion / `vista-prompt`).
    """
    return {
        "id": skill.id,
        "nombre": skill.nombre,
        "explicacion": skill.explicacion,
        "aplica_redes": skill.aplica_redes,
        "salida": skill.salida,
        "media": skill.media,
        "campos": [c.a_dict() for c in skill.campos],
    }


async def opciones(request: Request) -> Response:
    """Catalogo de skills (agrupado) + marcas + redes + ids de skills de media (para el SPA).

    Las skills salen del CATALOGO DE ARCHIVOS (`skills_catalogo.listar()`), agrupadas por
    `grupo` con su etiqueta humana y la bandera `experimental`. Cada skill trae lo necesario
    para el formulario dinamico (`campos`, `aplica_redes`, `salida`, `media`). `marcas` y
    `redes` (id+nombre) permiten poblar los selectores. `skills_media` se deriva del catalogo.
    """
    todas = skills_catalogo.listar()
    por_grupo: dict[str, list[skills_catalogo.SkillDef]] = {}
    for skill in todas:
        por_grupo.setdefault(skill.grupo, []).append(skill)

    # Grupos en orden fijo (validadas, experimentales) y, al final, cualquier grupo extra.
    nombres_grupo = list(_ORDEN_GRUPOS) + [g for g in por_grupo if g not in _ORDEN_GRUPOS]
    grupos = []
    for grupo in nombres_grupo:
        if grupo not in por_grupo:
            continue
        etiqueta, experimental = skills_catalogo.ETIQUETA_GRUPO.get(grupo, (grupo, False))
        grupos.append({
            "grupo": grupo,
            "etiqueta": etiqueta,
            "experimental": experimental,
            "skills": [_skill_para_opciones(s) for s in por_grupo[grupo]],
        })

    marcas_lista = [{"id": mid, "nombre": nombre} for mid, nombre in MARCAS]
    redes_lista = [{"id": r["id"], "nombre": r["nombre"]} for r in redes.opciones()]
    skills_media = sorted(s.id for s in todas if s.media)
    return JSONResponse(
        {
            "grupos": grupos,
            "marcas": marcas_lista,
            "redes": redes_lista,
            "skills_media": skills_media,
        }
    )


# Errores de subida que son de VALIDACION de entrada (=> 400).
_ERRORES_VALIDACION_ARCHIVO = frozenset({
    "El archivo es demasiado grande; sube uno más pequeño e inténtalo de nuevo.",
    "El archivo está vacío.",
    "Falta el archivo para generar el borrador.",
    "No se pudo guardar el archivo subido.",
    "Tipo de contenido no permitido.",
    "Marca no permitida.",
})


def _redes_desde_form(form) -> list[str]:  # noqa: ANN001 -- starlette FormData
    """Lee `redes` de un multipart: campo REPETIDO o un unico valor CSV.

    Acepta varias entradas `redes=x` (campo repetido) y/o un valor con comas
    (`redes=x,instagram`). Devuelve los ids crudos (sin validar); `normalizar_redes`
    se encarga de filtrar contra las canonicas.
    """
    crudas: list[str] = []
    for valor in form.getlist("redes"):
        if isinstance(valor, str):
            crudas.extend(parte.strip() for parte in valor.split(",") if parte.strip())
    return crudas


def construir_procesar_copy(
    skill: str,
    marca: str,
    *,
    redes_ids: list[str],
    titulo_dado: str,
    texto_base: str,
    con_imagenes: bool = False,
) -> generaciones.Procesar:
    """Devuelve el callback de post-procesado de una generacion de copy/RSS.

    El callback `procesar(salida, metricas) -> dict` corre al COMPLETARSE el trabajo:
    parsea la salida cruda en piezas/verdicto, registra el historial (con sus metricas),
    AUTO-GUARDA una publicacion (borrador) por pieza y devuelve la MISMA forma que antes
    entregaba la generacion sincrona: `{resultado, historial_id, verdicto, piezas,
    publicaciones}`. Es lo que se guarda como `resultado` del registro de generacion.
    Si `con_imagenes` (skill de imagen), ademas importa las imagenes producidas al media
    y las anade como `imagenes` para previsualizarlas.
    """

    def procesar(salida: str, metricas: MetricasRun | None) -> dict[str, object]:
        parsed = parsear_salida(salida, redes_ids)
        titulo = titulo_dado or derivar_titulo(texto_base or str(parsed["resultado"]))
        historial_id = repos.registrar_historial_skill(
            skill, marca, parsed["resultado"], piezas=parsed["piezas"], titulo=titulo,
            metricas=metricas_a_dict(metricas),
        )
        publicaciones = _crear_publicaciones_desde_piezas(
            parsed["piezas"], marca=marca, titulo=titulo,
            verdicto=parsed["verdicto"], origen=historial_id,
        )
        resultado: dict[str, object] = {
            "resultado": parsed["resultado"],
            "historial_id": historial_id,
            "verdicto": parsed["verdicto"],
            "piezas": parsed["piezas"],
            "publicaciones": publicaciones,
        }
        if con_imagenes:
            resultado["imagenes"] = cosechar_imagenes(salida)
        return resultado

    return procesar


def construir_procesar_documento(
    skill: str,
    marca: str,
    *,
    titulo_base: str,
    titulo_dado: str = "",
    con_imagenes: bool = False,
) -> generaciones.Procesar:
    """Callback de post-procesado de una skill de salida `documento` (sin piezas).

    El callback `procesar(salida, metricas) -> dict` corre al COMPLETARSE el trabajo:
    limpia emojis del documento, deriva el verdicto de la primera linea ✅/⚠️/❌, deriva
    un titulo (del primer campo de texto o del documento), registra el historial SIN
    piezas y NO auto-crea publicaciones. Devuelve
    `{documento, verdicto, historial_id, piezas: [], publicaciones: []}`. Si
    `con_imagenes` (skill de imagen, p.ej. estudio-imagen), ademas importa las imagenes
    producidas al media y las anade como `imagenes` para previsualizarlas.
    """

    def procesar(salida: str, metricas: MetricasRun | None) -> dict[str, object]:
        doc = quitar_emojis(salida)
        verdicto = _derivar_verdicto(salida)
        titulo = titulo_dado or derivar_titulo(titulo_base or doc)
        historial_id = repos.registrar_historial_skill(
            skill, marca, doc, piezas=[], titulo=titulo, metricas=metricas_a_dict(metricas),
        )
        resultado: dict[str, object] = {
            "documento": doc,
            "verdicto": verdicto,
            "historial_id": historial_id,
            "piezas": [],
            "publicaciones": [],
        }
        if con_imagenes:
            # La cosecha lee las RUTAS de la salida CRUDA (no del documento sin emojis).
            resultado["imagenes"] = cosechar_imagenes(salida)
        return resultado

    return procesar


def etiqueta_generacion(skill: str, marca: str) -> str:
    """Etiqueta legible de una generacion (para el progreso y la lista de actividad)."""
    return f"{_nombre_skill(skill)} · {_MARCA_NOMBRE.get(marca, marca)}"


def _lanzar_con_procesar(
    *,
    tipo: str,
    skill: str,
    marca: str,
    prompt: str,
    procesar: generaciones.Procesar,
    dir_temporal: Path | None = None,
) -> dict[str, object]:
    """Crea el registro de generacion, lanza el trabajo de claude EN BACKGROUND y
    devuelve el registro ACTUAL (puede haber avanzado ya si el lanzador es una fake)."""
    gen = generaciones.crear(
        {"tipo": tipo, "marca": marca, "etiqueta": etiqueta_generacion(skill, marca)}
    )
    try:
        generaciones.lanzar_job_claude(
            gen["id"], prompt=prompt, cwd=_cwd_skills(), procesar=procesar,
            dir_temporal=dir_temporal,
        )
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; reflejamos error en el registro
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        generaciones.actualizar(
            gen["id"],
            {"estado": generaciones.ESTADO_ERROR, "error": "No se pudo iniciar la generación.",
             "fecha_fin": generaciones.ahora_iso()},
        )
    return generaciones.obtener(gen["id"]) or gen


def lanzar_generacion_copy(
    *,
    tipo: str,
    skill: str,
    marca: str,
    prompt: str,
    redes_ids: list[str],
    titulo_dado: str,
    texto_base: str,
    dir_temporal: Path | None = None,
) -> dict[str, object]:
    """Lanza una generacion de PIEZAS (copy por red) en background. Usada por copy/RSS."""
    procesar = construir_procesar_copy(
        skill, marca, redes_ids=redes_ids, titulo_dado=titulo_dado, texto_base=texto_base
    )
    return _lanzar_con_procesar(
        tipo=tipo, skill=skill, marca=marca, prompt=prompt, procesar=procesar,
        dir_temporal=dir_temporal,
    )


def lanzar_generacion_skill(
    *,
    skilldef: skills_catalogo.SkillDef,
    marca: str,
    prompt: str,
    redes_ids: list[str],
    titulo_base: str,
    dir_temporal: Path | None = None,
) -> dict[str, object]:
    """Lanza una generacion en background eligiendo el post-procesado segun `salida`.

    - `salida == "piezas"`: parsea piezas por red + auto-crea publicaciones (comportamiento
      de copy). El titulo SIEMPRE se deriva (nunca lo da el cliente).
    - `salida == "documento"`: limpia el documento, deriva verdicto/titulo, registra el
      historial SIN piezas y NO crea publicaciones.
    """
    if skilldef.salida == "piezas":
        procesar = construir_procesar_copy(
            skilldef.id, marca, redes_ids=redes_ids, titulo_dado="", texto_base=titulo_base,
            con_imagenes=skilldef.media,
        )
    else:
        procesar = construir_procesar_documento(
            skilldef.id, marca, titulo_base=titulo_base, con_imagenes=skilldef.media,
        )
    return _lanzar_con_procesar(
        tipo="copy", skill=skilldef.id, marca=marca, prompt=prompt, procesar=procesar,
        dir_temporal=dir_temporal,
    )


class _ValidacionCampos(SkillError):
    """Un campo requerido falta o un valor es invalido (=> 400 con mensaje en espanol)."""


def _valores_validados(
    skilldef: skills_catalogo.SkillDef,
    crudos: dict[str, object],
    *,
    saltar_campos: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Extrae y valida los valores de los campos de TEXTO de la skill.

    `crudos` mapea `campo_id -> valor`. Para cada campo (salvo los de `saltar_campos`,
    p.ej. el `archivo` que ya se guardo aparte): exige los requeridos, recorta el texto,
    y acota el tamano total. Los campos `archivo` se ignoran aqui (su valor es una ruta
    que pone el endpoint). Lanza `_ValidacionCampos` (=> 400) si falta un requerido o el
    texto es demasiado largo.
    """
    valores: dict[str, str] = {}
    total = 0
    for campo in skilldef.campos:
        if campo.id in saltar_campos or campo.tipo == "archivo":
            continue
        crudo = crudos.get(campo.id)
        valor = crudo.strip() if isinstance(crudo, str) else ""
        if campo.requerido and not valor:
            raise _ValidacionCampos(f"Falta el campo obligatorio: {campo.etiqueta}.")
        total += len(valor)
        valores[campo.id] = valor
    if total > _MAX_TEXTO:
        raise _ValidacionCampos("El texto es demasiado largo; acórtalo e inténtalo de nuevo.")
    return valores


def _titulo_base_de_valores(skilldef: skills_catalogo.SkillDef, valores: dict[str, str]) -> str:
    """Texto del primer campo de texto (para derivar un titulo legible)."""
    campo = skilldef.primer_campo_texto()
    if campo is None:
        return ""
    return valores.get(campo.id, "")


async def ejecutar(request: Request) -> Response:
    """Lanza la generacion de una skill EN SEGUNDO PLANO -> `{generacion}` (estado ejecutando).

    Cuerpo JSON: `{skill, marca, valores: {campo_id: valor}, redes?}` (sin `titulo`: el
    titulo se deriva siempre). Valida skill∈catalogo, marca∈catalogo y los campos
    requeridos. Renderiza la invocacion via `skills_catalogo.render_invocacion` y lanza el
    trabajo, eligiendo el post-procesado segun `salida` (piezas | documento). No bloquea:
    el frontend sondea `GET /api/generaciones/{id}` y recoge `resultado` al completarse.
    """
    datos = await leer_json(request)
    skill = datos.get("skill")
    marca = datos.get("marca")
    if not isinstance(skill, str) or not isinstance(marca, str):
        return JSONResponse(
            {"error": "Faltan el tipo de contenido o la marca."}, status_code=400
        )
    skilldef = skills_catalogo.obtener(skill)
    if skilldef is None:
        return JSONResponse({"error": "Tipo de contenido no permitido."}, status_code=400)
    if marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    crudos = datos.get("valores")
    if not isinstance(crudos, dict):
        crudos = {}
    try:
        valores = _valores_validados(skilldef, crudos)
    except _ValidacionCampos as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    crudas = datos.get("redes")
    redes_ids = normalizar_redes(crudas if isinstance(crudas, list) else None)

    prompt = skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)
    gen = lanzar_generacion_skill(
        skilldef=skilldef, marca=marca, prompt=prompt, redes_ids=redes_ids,
        titulo_base=_titulo_base_de_valores(skilldef, valores),
    )
    return JSONResponse({"generacion": gen})


async def ejecutar_archivo(request: Request) -> Response:
    """Genera un borrador a partir de un archivo SUBIDO (multipart), EN SEGUNDO PLANO.

    Form: `skill`, `marca`, `archivo` (el binario), los demas valores de campos de TEXTO
    como campos del form (`<campo_id>=<valor>`) y `redes` (repetido o CSV). El archivo se
    guarda en un temporal saneado y se sustituye su valor en el campo de la skill:
      - Si la skill tiene un campo `archivo` (skill de media: clip-a-copy / revisa-imagen),
        se sustituye su RUTA temporal y el temporal vive hasta que termina el trabajo (la
        skill lo lee/transcribe en local); el lanzador lo borra al finalizar.
      - Si la skill NO tiene campo `archivo` (skill de texto usada con subida), se LEE el
        texto del archivo, se asigna al primer campo de texto y el temporal se borra ya.
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "No se pudo leer el archivo subido."}, status_code=400)
    skill = form.get("skill")
    marca = form.get("marca")
    archivo = form.get("archivo")

    if not isinstance(skill, str) or not isinstance(marca, str):
        return JSONResponse({"error": "Faltan el tipo de contenido o la marca."}, status_code=400)
    skilldef = skills_catalogo.obtener(skill)
    if skilldef is None:
        return JSONResponse({"error": "Tipo de contenido no permitido."}, status_code=400)
    if marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    if not isinstance(archivo, UploadFile):
        return JSONResponse(
            {"error": "No se recibió ningún archivo. Súbelo o pega el texto."}, status_code=400
        )

    redes_crudas = _redes_desde_form(form)
    redes_ids = normalizar_redes(redes_crudas or None)

    # Valores de los campos de TEXTO desde el form (cada campo.id). El campo que recibe el
    # archivo subido se SALTA en la validacion (lo rellena el endpoint):
    #   - skill con campo `archivo`: ese campo (su valor sera la RUTA temporal).
    #   - skill de texto: el primer campo de texto (su valor sera el TEXTO leido del archivo).
    campo_archivo = skilldef.campo_archivo()
    campo_destino = campo_archivo or skilldef.primer_campo_texto()
    saltar = frozenset({campo_destino.id}) if campo_destino is not None else frozenset()
    crudos = {campo.id: form.get(campo.id) for campo in skilldef.campos}
    try:
        valores = _valores_validados(skilldef, crudos, saltar_campos=saltar)
    except _ValidacionCampos as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    # Guardado seguro del archivo a un temporal (puede fallar por tamano/E-S => 400/500).
    try:
        ruta, dir_temporal = await _guardar_subida_segura(archivo, limite=_max_subida(skill))
    except SkillError as e:
        mensaje = str(e)
        codigo = 400 if mensaje in _ERRORES_VALIDACION_ARCHIVO else 500
        return JSONResponse({"error": mensaje}, status_code=codigo)

    if campo_archivo is not None:
        # MEDIA / RUTA: el campo de archivo recibe la RUTA temporal; el temporal vive hasta
        # que termine el trabajo (la skill lo lee/transcribe en local). El lanzador lo borra.
        valores[campo_archivo.id] = str(ruta)
        prompt = skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)
        gen = lanzar_generacion_skill(
            skilldef=skilldef, marca=marca, prompt=prompt, redes_ids=redes_ids,
            titulo_base=_titulo_base_de_valores(skilldef, valores), dir_temporal=dir_temporal,
        )
        return JSONResponse({"generacion": gen})

    # TEXTO: leemos el contenido ya (rapido), lo ponemos en el primer campo de texto y
    # borramos el temporal de inmediato.
    try:
        texto_nota = _leer_texto_archivo(ruta)
    except OSError:
        shutil.rmtree(dir_temporal, ignore_errors=True)
        return JSONResponse({"error": "No se pudo leer el archivo subido."}, status_code=400)
    finally:
        shutil.rmtree(dir_temporal, ignore_errors=True)
    if not texto_nota.strip():
        return JSONResponse({"error": "El archivo está vacío."}, status_code=400)
    if len(texto_nota) > _MAX_TEXTO:
        return JSONResponse(
            {"error": "El texto es demasiado largo; acórtalo e inténtalo de nuevo."},
            status_code=400,
        )
    campo_texto = skilldef.primer_campo_texto()
    if campo_texto is not None:
        valores[campo_texto.id] = texto_nota
    prompt = skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)
    gen = lanzar_generacion_skill(
        skilldef=skilldef, marca=marca, prompt=prompt, redes_ids=redes_ids,
        titulo_base=_titulo_base_de_valores(skilldef, valores),
    )
    return JSONResponse({"generacion": gen})


async def historial(request: Request) -> Response:
    """Listado del historial (metadatos + preview), recientes primero."""
    entradas = repos.listar_historial_skills()
    salida = [
        {
            "id": e["id"],
            "skill": e["skill"],
            "skill_nombre": _nombre_skill(e["skill"]),
            "marca": e["marca"],
            "marca_nombre": _MARCA_NOMBRE.get(e["marca"], e["marca"]),
            "fecha": e["fecha"],
            "titulo": e["titulo"],
            "preview": _preview(e["resultado"]),
            "piezas": e["piezas"],
            "metricas": e.get("metricas"),
        }
        for e in entradas
    ]
    return JSONResponse({"historial": salida})


async def historial_detalle(request: Request) -> Response:
    """Una entrada del historial con el resultado completo (404 si no existe)."""
    historial_id = request.path_params["historial_id"]
    entrada = repos.obtener_historial_skill(historial_id)
    if entrada is None:
        return JSONResponse({"error": "No se encontró ese borrador en el historial."}, status_code=404)
    return JSONResponse(
        {
            "id": entrada["id"],
            "skill": entrada["skill"],
            "marca": entrada["marca"],
            "fecha": entrada["fecha"],
            "titulo": entrada["titulo"],
            "resultado": entrada["resultado"],
            "piezas": entrada["piezas"],
            "metricas": entrada.get("metricas"),
        }
    )


async def historial_guardar(request: Request) -> Response:
    """Recupera una entrada del historial como publicaciones (borradores).

    `POST /api/skills/historial/{id}/guardar` con JSON opcional `{titulo?, redes?, red?}`:
      - Si la entrada tiene `piezas`: crea UNA publicacion por pieza (filtradas a `redes`
        si se pasa). Usa `titulo` (param) o el de la entrada o el derivado del resultado.
      - Si NO tiene piezas (entradas antiguas): requiere `red` (∈ redes canonicas) y crea
        UNA publicacion con `contenido = resultado` y esa red. Sin `red` => 400.
    -> `{publicaciones:[Publicacion]}` | 404 si la entrada no existe.
    """
    historial_id = request.path_params["historial_id"]
    entrada = repos.obtener_historial_skill(historial_id)
    if entrada is None:
        return JSONResponse(
            {"error": "No se encontró ese borrador en el historial."}, status_code=404
        )

    datos = await leer_json(request)
    titulo_dado = datos.get("titulo")
    titulo_dado = titulo_dado.strip() if isinstance(titulo_dado, str) else ""
    crudas = datos.get("redes")
    redes_filtro: set[str] | None = None
    if isinstance(crudas, list):
        redes_filtro = {r for r in crudas if isinstance(r, str) and redes.es_red(r)}

    marca = entrada["marca"]
    verdicto = _derivar_verdicto(entrada["resultado"])
    titulo = titulo_dado or entrada["titulo"] or derivar_titulo(entrada["resultado"])
    piezas = entrada["piezas"]

    if piezas:
        publicaciones = _crear_publicaciones_desde_piezas(
            piezas,
            marca=marca,
            titulo=titulo,
            verdicto=verdicto,
            origen=historial_id,
            redes_filtro=redes_filtro,
        )
        return JSONResponse({"publicaciones": publicaciones})

    # Entrada antigua sin piezas: requiere una red explicita.
    red = datos.get("red")
    if not isinstance(red, str) or not redes.es_red(red):
        return JSONResponse(
            {"error": "Indica la red para guardar este borrador como publicación."},
            status_code=400,
        )
    if redes_filtro is not None and red not in redes_filtro:
        return JSONResponse(
            {"error": "La red indicada no está entre las redes pedidas."}, status_code=400
        )
    pub = repos.crear_publicacion(
        marca,
        red,
        titulo=titulo,
        contenido=entrada["resultado"],
        estado="borrador",
        veredicto=verdicto,
        origen=historial_id,
    )
    return JSONResponse({"publicaciones": [_publicacion_a_dict(pub)]})


# --------------------------------------------------------------------------- #
# CRUD del CATALOGO de skills (pagina de gestion) + visor de prompt            #
# --------------------------------------------------------------------------- #


async def catalogo_listar(request: Request) -> Response:
    """`GET /api/skills/catalogo` -> `{skills: [definicion completa]}` (orden, id)."""
    return JSONResponse({"skills": [s.a_dict() for s in skills_catalogo.listar()]})


async def catalogo_crear(request: Request) -> Response:
    """`POST /api/skills/catalogo` -> crea una skill `{nombre, ...}` -> `{skill}` (400 dup/invalida)."""
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "El nombre de la skill es obligatorio."}, status_code=400)
    kwargs: dict[str, object] = {}
    for clave in ("explicacion", "grupo", "salida"):
        valor = datos.get(clave)
        if isinstance(valor, str) and valor:
            kwargs[clave] = valor
    if isinstance(datos.get("aplica_redes"), bool):
        kwargs["aplica_redes"] = datos["aplica_redes"]
    try:
        skill = skills_catalogo.crear(nombre, **kwargs)
    except skills_catalogo.SkillCatalogoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"skill": skill.a_dict()})


async def catalogo_obtener(request: Request) -> Response:
    """`GET /api/skills/catalogo/{id}` -> `{skill: {...metadata...}, skill_md: "<SKILL.md>"}` (404)."""
    skill_id = request.path_params["skill_id"]
    skill = skills_catalogo.obtener(skill_id)
    if skill is None:
        return JSONResponse({"error": "Esa skill no existe."}, status_code=404)
    try:
        skill_md = skills_catalogo.leer_skill_md(skill_id)
    except skills_catalogo.SkillCatalogoError:
        skill_md = ""
    return JSONResponse({"skill": skill.a_dict(), "skill_md": skill_md})


async def catalogo_actualizar(request: Request) -> Response:
    """`PUT /api/skills/catalogo/{id}` -> reescribe metadatos -> `{skill}` (404/400)."""
    skill_id = request.path_params["skill_id"]
    if not skills_catalogo.existe(skill_id):
        return JSONResponse({"error": "Esa skill no existe."}, status_code=404)
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Los metadatos de la skill no son válidos."}, status_code=400)
    try:
        skill = skills_catalogo.actualizar(skill_id, datos)
    except skills_catalogo.SkillCatalogoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"skill": skill.a_dict()})


async def catalogo_skill_md(request: Request) -> Response:
    """`PUT /api/skills/catalogo/{id}/skill-md` -> `{contenido}` -> `{mensaje}` (404/400)."""
    skill_id = request.path_params["skill_id"]
    if not skills_catalogo.existe(skill_id):
        return JSONResponse({"error": "Esa skill no existe."}, status_code=404)
    datos = await leer_json(request)
    contenido = datos.get("contenido")
    try:
        skills_catalogo.guardar_skill_md(skill_id, contenido)
    except skills_catalogo.SkillCatalogoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"mensaje": "SKILL.md guardado."})


async def catalogo_borrar(request: Request) -> Response:
    """`DELETE /api/skills/catalogo/{id}` -> `{mensaje}` (404; defensivo dentro de la raiz)."""
    skill_id = request.path_params["skill_id"]
    if not skills_catalogo.existe(skill_id):
        return JSONResponse({"error": "Esa skill no existe."}, status_code=404)
    try:
        skills_catalogo.borrar(skill_id)
    except skills_catalogo.SkillCatalogoError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"mensaje": "Skill eliminada."})


async def catalogo_vista_prompt(request: Request) -> Response:
    """`POST /api/skills/catalogo/{id}/vista-prompt` -> `{marca, valores, redes}` -> `{prompt}`.

    Renderiza la invocacion EXACTA que recibiria Claude (sin llamarlo): util para el
    visor de prompt del frontend. Aplica la misma logica que `ejecutar`: sustituye los
    valores en la plantilla, anade la instruccion de "sin emojis" y, si la skill
    `aplica_redes`, la instruccion de redes. No valida campos requeridos (es solo vista
    previa). 404 si la skill no existe.
    """
    skill_id = request.path_params["skill_id"]
    skilldef = skills_catalogo.obtener(skill_id)
    if skilldef is None:
        return JSONResponse({"error": "Esa skill no existe."}, status_code=404)
    datos = await leer_json(request)
    marca = datos.get("marca")
    marca = marca if isinstance(marca, str) else ""
    crudos = datos.get("valores")
    valores: dict[str, str] = {}
    if isinstance(crudos, dict):
        for campo in skilldef.campos:
            v = crudos.get(campo.id)
            valores[campo.id] = v if isinstance(v, str) else ""
    crudas = datos.get("redes")
    redes_ids = normalizar_redes(crudas if isinstance(crudas, list) else None)
    prompt = skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)
    return JSONResponse({"prompt": prompt})


# Rutas: las que tienen segmento ESTATICO (`ejecutar`, `ejecutar-archivo`, `historial`,
# `catalogo`) van ANTES que las de parametro (`/catalogo/{id}`, `/historial/{id}`) para
# que Starlette las case primero y no las trague la ruta parametrica.
RUTAS = [
    Route("/api/skills", opciones, methods=["GET"]),
    Route("/api/skills/ejecutar", ejecutar, methods=["POST"]),
    Route("/api/skills/ejecutar-archivo", ejecutar_archivo, methods=["POST"]),
    Route("/api/skills/catalogo", catalogo_listar, methods=["GET"]),
    Route("/api/skills/catalogo", catalogo_crear, methods=["POST"]),
    Route("/api/skills/catalogo/{skill_id}/skill-md", catalogo_skill_md, methods=["PUT"]),
    Route("/api/skills/catalogo/{skill_id}/vista-prompt", catalogo_vista_prompt, methods=["POST"]),
    Route("/api/skills/catalogo/{skill_id}", catalogo_obtener, methods=["GET"]),
    Route("/api/skills/catalogo/{skill_id}", catalogo_actualizar, methods=["PUT"]),
    Route("/api/skills/catalogo/{skill_id}", catalogo_borrar, methods=["DELETE"]),
    Route("/api/skills/historial", historial, methods=["GET"]),
    Route("/api/skills/historial/{historial_id}/guardar", historial_guardar, methods=["POST"]),
    Route("/api/skills/historial/{historial_id}", historial_detalle, methods=["GET"]),
]
