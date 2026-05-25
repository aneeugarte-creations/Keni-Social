"""API Skills: lanzador de skills headless (Claude por debajo) + historial.

El SPA elige una skill de una ALLOWLIST curada, una marca, pega una nota/transcripcion
(o sube un archivo) y pide "Generar". La consola construye el prompt de invocacion
y corre `claude -p "<prompt>" --output-format json` POR DEBAJO, captura el texto del
campo `result` Y las METRICAS del run (tokens/turnos/coste/duracion via
`parsear_resultado_json`), lo persiste en `skill_historial` y lo devuelve. Nada se
publica: solo borradores. `_runner` devuelve `(texto, MetricasRun | None)`.

SEGURIDAD (resumen):
  - La lista de skills es una ALLOWLIST fija (`SKILLS`); las marcas tambien (`MARCAS`).
  - El texto del usuario viaja como ARGUMENTO de subprocess (lista argv), nunca por
    shell: sin `shell=True`, sin inyeccion de shell.
  - `claude` corre con `timeout=`; los errores (binario no encontrado, timeout,
    rc!=0) salen como mensajes en espanol, sin tracebacks.

SUBIR ARCHIVO: el endpoint multipart `/api/skills/ejecutar-archivo` recibe el
archivo, lo guarda en un dir TEMPORAL del SO con NOMBRE SANEADO (nunca el del
cliente), aplicando un LIMITE DE TAMANO por tipo y comprobandolo MIENTRAS lee (en
trozos). Tras procesar, BORRA el temporal (siempre, incluso ante error).
  - `clip-a-copy` (media): su ruta temporal va al PROMPT (la skill transcribe en
    local). El resto son skills de texto: se LEE el texto del archivo como `texto`.

INYECCION/MOCKEO: `ejecutar_skill`/`ejecutar_skill_ruta` delegan en `_runner`
(modulo-nivel), que es lo unico que toca el binario `claude`. Los tests parchean
`_runner`/`ejecutar_skill` para NUNCA llamar a `claude` real en CI.

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
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json
from .publicaciones import _publicacion_a_dict

# --------------------------------------------------------------------------- #
# Allowlists: skills curadas y marcas (NUNCA invocaciones arbitrarias)         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _SkillInfo:
    id: str
    nombre: str
    descripcion: str  # una linea, para no tecnicos


@dataclass(frozen=True)
class _GrupoSkills:
    etiqueta: str  # titulo visible del grupo
    experimental: bool  # True => se etiqueta como experimental en la UI
    skills: tuple[_SkillInfo, ...]


GRUPOS_SKILLS: tuple[_GrupoSkills, ...] = (
    _GrupoSkills(
        etiqueta="Validadas con el equipo",
        experimental=False,
        skills=(
            _SkillInfo("copy-desde-nota", "Copy desde nota", "Convierte una nota en copy para redes."),
            _SkillInfo("clip-a-copy", "Clip a copy", "De la transcripción de un clip a copy listo para publicar."),
            _SkillInfo("nota-a-formato", "Nota a formato", "Adapta una nota al formato de una plataforma concreta."),
            _SkillInfo("resumen-tendencia", "Resumen de tendencia", "Resume una tendencia a partir de varias fuentes."),
            _SkillInfo(
                "youtube-metadata",
                "Metadatos de YouTube",
                "Arma título, descripción, etiquetas y capítulos para un video de YouTube.",
            ),
        ),
    ),
    _GrupoSkills(
        etiqueta="Experimentales (no validadas con el piloto)",
        experimental=True,
        skills=(
            _SkillInfo("nota-a-hilo", "Nota a hilo", "Convierte una nota en un hilo encadenado para redes."),
            _SkillInfo(
                "calendario-editorial",
                "Calendario editorial",
                "Arma un calendario editorial desde el material dado.",
            ),
            _SkillInfo(
                "responde-comentarios",
                "Responde comentarios",
                "Propone respuestas a comentarios de la comunidad.",
            ),
        ),
    ),
)

# Vista PLANA de todas las skills curadas (de todos los grupos), en orden de grupo.
SKILLS: tuple[_SkillInfo, ...] = tuple(s for g in GRUPOS_SKILLS for s in g.skills)

# Marcas editoriales permitidas: TODAS las del catalogo unico. VALUE interno = id
# canonico (slug-guion); etiqueta visible = nombre humano con acentos.
MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())

_SKILLS_IDS = {s.id for s in SKILLS}
_MARCAS_IDS = {m[0] for m in MARCAS}

# Mapas id->nombre para enriquecer el historial con nombres humanos.
_SKILL_NOMBRE = {s.id: s.nombre for s in SKILLS}
_MARCA_NOMBRE = dict(MARCAS)

# Instruccion ADITIVA de estilo que se anade a TODO prompt de generacion: el copy
# no debe llevar emojis. Es defensa en profundidad; ademas `quitar_emojis` los borra
# de forma determinista por si el modelo igual mete alguno.
_INSTRUCCION_SIN_EMOJIS = "No uses emojis en el copy."

# Tope de tamano del texto de entrada (evita prompts gigantes accidentales).
_MAX_TEXTO = 60_000
# Timeout por defecto para la invocacion de Claude (segundos).
_TIMEOUT_DEF = 180

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


def construir_prompt(skill: str, marca: str, texto: str, redes_ids: list[str] | None = None) -> str:
    """Construye el prompt de invocacion headless para una skill+marca+texto.

    El texto viaja como argumento de subprocess (no por shell), asi que no hay
    inyeccion. Marca y skill ya estan validadas contra sus allowlists. Si se pasan
    `redes_ids`, se anade una instruccion ADITIVA (redes + bloque json de piezas).
    """
    base = f"usa {skill} con la siguiente nota, marca {marca}:\n\n{texto}"
    base = f"{base}\n\n{_INSTRUCCION_SIN_EMOJIS}"
    if redes_ids:
        return f"{base}\n\n{_instruccion_redes(redes_ids)}"
    return base


def construir_prompt_ruta(
    skill: str, marca: str, ruta: str, redes_ids: list[str] | None = None
) -> str:
    """Construye el prompt para una skill de MEDIA que parte de una RUTA de archivo."""
    base = f"usa {skill} con el archivo en esta ruta, marca {marca}:\n\n{ruta}"
    base = f"{base}\n\n{_INSTRUCCION_SIN_EMOJIS}"
    if redes_ids:
        return f"{base}\n\n{_instruccion_redes(redes_ids)}"
    return base


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


def _runner(prompt: str, *, cwd: Path, timeout: int) -> tuple[str, MetricasRun | None]:
    """Llama a `claude -p "<prompt>" --output-format json` por subprocess.

    Devuelve `(texto, metricas)` (texto = campo `result`; metricas parseadas, o None si
    la salida no es el JSON de resultado esperado). Esta es LA funcion que toca el
    binario real; los tests la parchean. Sin shell. Aplica `--max-budget-usd` desde
    `KENI_CLAUDE_MAX_USD` si esta configurado.
    """
    if shutil.which("claude") is None:
        raise SkillError(
            "No se encontró el asistente en este equipo. Instala Claude Code para "
            "poder generar borradores desde la consola."
        )
    argv = ["claude", "-p", prompt, "--output-format", "json", *_arg_presupuesto()]
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:  # carrera: el binario desaparecio entre which y run
        raise SkillError("No se encontró el asistente en este equipo.") from e
    except subprocess.TimeoutExpired as e:
        raise SkillError(
            f"El asistente tardó demasiado (más de {timeout} s) y se canceló. "
            "Prueba con una nota más corta."
        ) from e
    if proc.returncode != 0:
        # Aun con rc!=0, el stdout puede traer el JSON de resultado con el error
        # (p.ej. tope de presupuesto): si es asi, `parsear_resultado_json` lo
        # convierte en un SkillError especifico. Si no, usamos stderr.
        salida = (proc.stdout or "").strip()
        if salida:
            return parsear_resultado_json(salida)
        detalle = (proc.stderr or "").strip() or "error desconocido al generar el borrador"
        raise SkillError(f"El asistente terminó con error: {detalle}")
    return parsear_resultado_json(proc.stdout)


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


def ejecutar_skill(
    skill: str,
    marca: str,
    texto: str,
    *,
    redes_ids: list[str] | None = None,
    timeout: int = _TIMEOUT_DEF,
    runner: Callable[..., tuple[str, MetricasRun | None]] | None = None,
) -> tuple[str, MetricasRun | None]:
    """Valida entradas, construye el prompt y corre Claude por debajo (headless).

    Devuelve `(texto, metricas)`: el copy generado y las metricas del run (None si la
    salida no trajo el JSON de resultado esperado).
    """
    if skill not in _SKILLS_IDS:
        raise SkillError("Tipo de contenido no permitido.")
    if marca not in _MARCAS_IDS:
        raise SkillError("Marca no permitida.")
    texto = (texto or "").strip()
    if not texto:
        raise SkillError("Falta la nota o transcripción para generar el borrador.")
    if len(texto) > _MAX_TEXTO:
        raise SkillError("El texto es demasiado largo; acórtalo e inténtalo de nuevo.")

    prompt = construir_prompt(skill, marca, texto, redes_ids)
    ejecutor = runner if runner is not None else _runner
    salida, metricas = ejecutor(prompt, cwd=_cwd_skills(), timeout=timeout)
    if not salida:
        raise SkillError("El asistente no devolvió ningún contenido.")
    return salida, metricas


def ejecutar_skill_ruta(
    skill: str,
    marca: str,
    ruta: str,
    *,
    redes_ids: list[str] | None = None,
    timeout: int = _TIMEOUT_DEF,
    runner: Callable[..., tuple[str, MetricasRun | None]] | None = None,
) -> tuple[str, MetricasRun | None]:
    """Como `ejecutar_skill` pero para skills de MEDIA: pasa la RUTA al prompt.

    Devuelve `(texto, metricas)` igual que `ejecutar_skill`.
    """
    if skill not in _SKILLS_IDS:
        raise SkillError("Tipo de contenido no permitido.")
    if marca not in _MARCAS_IDS:
        raise SkillError("Marca no permitida.")
    if not ruta:
        raise SkillError("Falta el archivo para generar el borrador.")

    prompt = construir_prompt_ruta(skill, marca, ruta, redes_ids)
    ejecutor = runner if runner is not None else _runner
    salida, metricas = ejecutor(prompt, cwd=_cwd_skills(), timeout=timeout)
    if not salida:
        raise SkillError("El asistente no devolvió ningún contenido.")
    return salida, metricas


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


async def opciones(request: Request) -> Response:
    """Grupos de skills + marcas + ids de skills de media (para el SPA)."""
    grupos = [
        {
            "etiqueta": g.etiqueta,
            "experimental": g.experimental,
            "skills": [
                {"id": s.id, "nombre": s.nombre, "descripcion": s.descripcion} for s in g.skills
            ],
        }
        for g in GRUPOS_SKILLS
    ]
    marcas_lista = [{"id": mid, "nombre": nombre} for mid, nombre in MARCAS]
    return JSONResponse(
        {"grupos": grupos, "marcas": marcas_lista, "skills_media": sorted(_SKILLS_MEDIA)}
    )


# Mensajes de SkillError que son fallos de VALIDACION de entrada (=> 400).
_ERRORES_VALIDACION = frozenset({
    "Falta la nota o transcripción para generar el borrador.",
    "El texto es demasiado largo; acórtalo e inténtalo de nuevo.",
    "Tipo de contenido no permitido.",
    "Marca no permitida.",
})

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


def _responder_generacion(
    skill: str,
    marca: str,
    texto_nota: str,
    parsed: dict[str, object],
    titulo_dado: str,
    metricas: MetricasRun | None = None,
) -> Response:
    """Registra el historial (con piezas+titulo+metricas), AUTO-GUARDA publicaciones y responde.

    - Deriva el `titulo` (del dado o de la nota) y lo registra junto a las piezas.
    - Guarda las `metricas` del run (tokens/turnos/coste/duracion) en el historial.
    - Crea UNA publicacion (borrador) por pieza con `origen = historial_id`. Si no hay
      piezas (no se pudo partir por red), no crea ninguna y devuelve `publicaciones: []`.
    """
    resultado = parsed["resultado"]
    piezas = parsed["piezas"]
    verdicto = parsed["verdicto"]
    titulo = titulo_dado or derivar_titulo(texto_nota)
    historial_id = repos.registrar_historial_skill(
        skill, marca, resultado, piezas=piezas, titulo=titulo, metricas=metricas_a_dict(metricas)
    )
    publicaciones = _crear_publicaciones_desde_piezas(
        piezas, marca=marca, titulo=titulo, verdicto=verdicto, origen=historial_id
    )
    return JSONResponse(
        {
            "resultado": resultado,
            "historial_id": historial_id,
            "verdicto": verdicto,
            "piezas": piezas,
            "publicaciones": publicaciones,
        }
    )


async def ejecutar(request: Request) -> Response:
    datos = await leer_json(request)
    skill = datos.get("skill")
    marca = datos.get("marca")
    texto = datos.get("texto")
    if not isinstance(skill, str) or not isinstance(marca, str) or not isinstance(texto, str):
        return JSONResponse(
            {"error": "Faltan el tipo de contenido, la marca o el texto."}, status_code=400
        )
    if skill not in _SKILLS_IDS:
        return JSONResponse({"error": "Tipo de contenido no permitido."}, status_code=400)
    if marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    crudas = datos.get("redes")
    redes_ids = normalizar_redes(crudas if isinstance(crudas, list) else None)
    titulo_dado = datos.get("titulo")
    titulo_dado = titulo_dado.strip() if isinstance(titulo_dado, str) else ""
    try:
        salida, metricas = ejecutar_skill(skill, marca, texto, redes_ids=redes_ids)
    except SkillError as e:
        mensaje = str(e)
        codigo = 400 if mensaje in _ERRORES_VALIDACION else 500
        return JSONResponse({"error": mensaje}, status_code=codigo)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar el borrador."}, status_code=500)
    return _responder_generacion(
        skill, marca, texto, parsear_salida(salida, redes_ids), titulo_dado, metricas
    )


async def ejecutar_archivo(request: Request) -> Response:
    """Genera un borrador a partir de un archivo SUBIDO (multipart)."""
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "No se pudo leer el archivo subido."}, status_code=400)
    skill = form.get("skill")
    marca = form.get("marca")
    archivo = form.get("archivo")

    if not isinstance(skill, str) or not isinstance(marca, str):
        return JSONResponse({"error": "Faltan el tipo de contenido o la marca."}, status_code=400)
    if skill not in _SKILLS_IDS:
        return JSONResponse({"error": "Tipo de contenido no permitido."}, status_code=400)
    if marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    if not isinstance(archivo, UploadFile):
        return JSONResponse(
            {"error": "No se recibió ningún archivo. Súbelo o pega el texto."}, status_code=400
        )

    redes_crudas = _redes_desde_form(form)
    redes_ids = normalizar_redes(redes_crudas or None)
    titulo_form = form.get("titulo")
    titulo_dado = titulo_form.strip() if isinstance(titulo_form, str) else ""

    texto_nota = ""
    dir_temporal: Path | None = None
    metricas: MetricasRun | None = None
    try:
        ruta, dir_temporal = await _guardar_subida_segura(archivo, limite=_max_subida(skill))
        if skill in _SKILLS_MEDIA:
            salida, metricas = ejecutar_skill_ruta(skill, marca, str(ruta), redes_ids=redes_ids)
        else:
            texto_nota = _leer_texto_archivo(ruta)
            salida, metricas = ejecutar_skill(skill, marca, texto_nota, redes_ids=redes_ids)
    except SkillError as e:
        mensaje = str(e)
        es_validacion = mensaje in _ERRORES_VALIDACION_ARCHIVO or mensaje in _ERRORES_VALIDACION
        codigo = 400 if es_validacion else 500
        return JSONResponse({"error": mensaje}, status_code=codigo)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar el borrador."}, status_code=500)
    finally:
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
    parsed = parsear_salida(salida, redes_ids)
    # Para skills de media no hay nota de texto; el titulo se deriva del resultado.
    base_titulo = texto_nota or parsed["resultado"]
    return _responder_generacion(skill, marca, base_titulo, parsed, titulo_dado, metricas)


async def historial(request: Request) -> Response:
    """Listado del historial (metadatos + preview), recientes primero."""
    entradas = repos.listar_historial_skills()
    salida = [
        {
            "id": e["id"],
            "skill": e["skill"],
            "skill_nombre": _SKILL_NOMBRE.get(e["skill"], e["skill"]),
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


RUTAS = [
    Route("/api/skills", opciones, methods=["GET"]),
    Route("/api/skills/ejecutar", ejecutar, methods=["POST"]),
    Route("/api/skills/ejecutar-archivo", ejecutar_archivo, methods=["POST"]),
    Route("/api/skills/historial", historial, methods=["GET"]),
    Route("/api/skills/historial/{historial_id}/guardar", historial_guardar, methods=["POST"]),
    Route("/api/skills/historial/{historial_id}", historial_detalle, methods=["GET"]),
]
