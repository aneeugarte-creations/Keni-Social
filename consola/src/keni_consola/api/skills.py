"""API Skills: lanzador de skills headless (Claude por debajo) + historial.

El SPA elige una skill de una ALLOWLIST curada, una marca, pega una nota/transcripcion
(o sube un archivo) y pide "Generar". La consola construye el prompt de invocacion
y corre `claude -p "<prompt>"` POR DEBAJO, captura su salida, la persiste en
`skill_historial` (SQLite) y la devuelve. Nada se publica: solo borradores.

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
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import db, marcas
from .._http_json import leer_json

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

# Marcas editoriales permitidas: las que tienen `slug` (curadas como destino de
# copy). VALUE interno = slug-guion; etiqueta visible = nombre humano con acentos.
MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones_por_slug())

_SKILLS_IDS = {s.id for s in SKILLS}
_MARCAS_IDS = {m[0] for m in MARCAS}

# Mapas id->nombre para enriquecer el historial con nombres humanos.
_SKILL_NOMBRE = {s.id: s.nombre for s in SKILLS}
_MARCA_NOMBRE = dict(MARCAS)

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


def construir_prompt(skill: str, marca: str, texto: str) -> str:
    """Construye el prompt de invocacion headless para una skill+marca+texto.

    El texto viaja como argumento de subprocess (no por shell), asi que no hay
    inyeccion. Marca y skill ya estan validadas contra sus allowlists.
    """
    return f"usa {skill} con la siguiente nota, marca {marca}:\n\n{texto}"


def construir_prompt_ruta(skill: str, marca: str, ruta: str) -> str:
    """Construye el prompt para una skill de MEDIA que parte de una RUTA de archivo."""
    return f"usa {skill} con el archivo en esta ruta, marca {marca}:\n\n{ruta}"


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


def _runner(prompt: str, *, cwd: Path, timeout: int) -> str:
    """Llama a `claude -p "<prompt>"` por subprocess y devuelve su stdout.

    Esta es LA funcion que toca el binario real; los tests la parchean. Sin shell.
    """
    if shutil.which("claude") is None:
        raise SkillError(
            "No se encontró el asistente en este equipo. Instala Claude Code para "
            "poder generar borradores desde la consola."
        )
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt],
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
        detalle = (proc.stderr or "").strip() or "error desconocido al generar el borrador"
        raise SkillError(f"El asistente terminó con error: {detalle}")
    return proc.stdout.strip()


def ejecutar_skill(
    skill: str,
    marca: str,
    texto: str,
    *,
    timeout: int = _TIMEOUT_DEF,
    runner: Callable[..., str] | None = None,
) -> str:
    """Valida entradas, construye el prompt y corre Claude por debajo (headless)."""
    if skill not in _SKILLS_IDS:
        raise SkillError("Tipo de contenido no permitido.")
    if marca not in _MARCAS_IDS:
        raise SkillError("Marca no permitida.")
    texto = (texto or "").strip()
    if not texto:
        raise SkillError("Falta la nota o transcripción para generar el borrador.")
    if len(texto) > _MAX_TEXTO:
        raise SkillError("El texto es demasiado largo; acórtalo e inténtalo de nuevo.")

    prompt = construir_prompt(skill, marca, texto)
    ejecutor = runner if runner is not None else _runner
    salida = ejecutor(prompt, cwd=_cwd_skills(), timeout=timeout)
    if not salida:
        raise SkillError("El asistente no devolvió ningún contenido.")
    return salida


def ejecutar_skill_ruta(
    skill: str,
    marca: str,
    ruta: str,
    *,
    timeout: int = _TIMEOUT_DEF,
    runner: Callable[..., str] | None = None,
) -> str:
    """Como `ejecutar_skill` pero para skills de MEDIA: pasa la RUTA al prompt."""
    if skill not in _SKILLS_IDS:
        raise SkillError("Tipo de contenido no permitido.")
    if marca not in _MARCAS_IDS:
        raise SkillError("Marca no permitida.")
    if not ruta:
        raise SkillError("Falta el archivo para generar el borrador.")

    prompt = construir_prompt_ruta(skill, marca, ruta)
    ejecutor = runner if runner is not None else _runner
    salida = ejecutor(prompt, cwd=_cwd_skills(), timeout=timeout)
    if not salida:
        raise SkillError("El asistente no devolvió ningún contenido.")
    return salida


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
    try:
        resultado = ejecutar_skill(skill, marca, texto)
    except SkillError as e:
        mensaje = str(e)
        codigo = 400 if mensaje in _ERRORES_VALIDACION else 500
        return JSONResponse({"error": mensaje}, status_code=codigo)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar el borrador."}, status_code=500)
    historial_id = db.registrar_historial_skill(skill, marca, resultado)
    return JSONResponse({"resultado": resultado, "historial_id": historial_id})


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

    dir_temporal: Path | None = None
    try:
        ruta, dir_temporal = await _guardar_subida_segura(archivo, limite=_max_subida(skill))
        if skill in _SKILLS_MEDIA:
            resultado = ejecutar_skill_ruta(skill, marca, str(ruta))
        else:
            resultado = ejecutar_skill(skill, marca, _leer_texto_archivo(ruta))
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
    historial_id = db.registrar_historial_skill(skill, marca, resultado)
    return JSONResponse({"resultado": resultado, "historial_id": historial_id})


async def historial(request: Request) -> Response:
    """Listado del historial (metadatos + preview), recientes primero."""
    entradas = db.listar_historial_skills()
    salida = [
        {
            "id": e["id"],
            "skill": e["skill"],
            "skill_nombre": _SKILL_NOMBRE.get(e["skill"], e["skill"]),
            "marca": e["marca"],
            "marca_nombre": _MARCA_NOMBRE.get(e["marca"], e["marca"]),
            "fecha": e["fecha"],
            "preview": _preview(e["resultado"]),
        }
        for e in entradas
    ]
    return JSONResponse({"historial": salida})


async def historial_detalle(request: Request) -> Response:
    """Una entrada del historial con el resultado completo (404 si no existe)."""
    historial_id = request.path_params["historial_id"]
    entrada = db.obtener_historial_skill(historial_id)
    if entrada is None:
        return JSONResponse({"error": "No se encontró ese borrador en el historial."}, status_code=404)
    return JSONResponse(
        {
            "id": entrada["id"],
            "skill": entrada["skill"],
            "marca": entrada["marca"],
            "fecha": entrada["fecha"],
            "resultado": entrada["resultado"],
        }
    )


RUTAS = [
    Route("/api/skills", opciones, methods=["GET"]),
    Route("/api/skills/ejecutar", ejecutar, methods=["POST"]),
    Route("/api/skills/ejecutar-archivo", ejecutar_archivo, methods=["POST"]),
    Route("/api/skills/historial", historial, methods=["GET"]),
    Route("/api/skills/historial/{historial_id}", historial_detalle, methods=["GET"]),
]
