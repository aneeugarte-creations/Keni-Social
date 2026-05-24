"""Feature Skills: lanzador de skills headless (Claude por debajo, sin tocar la CLI).

Objetivo "el equipo no toca Claude Code": el usuario elige una skill de una lista
CURADA, una marca, pega una nota/transcripcion (o una ruta de archivo) y pulsa
"Generar". La consola construye el prompt de invocacion y corre Claude en modo
headless (`claude -p "<prompt>"`) POR DEBAJO, captura su salida y la muestra en la
misma pagina. Nada se publica: es solo generacion de borradores para revisar.

SEGURIDAD (resumen):
  - La lista de skills es una ALLOWLIST fija (`SKILLS`); nunca se ejecuta una
    invocacion arbitraria. Las marcas tambien son una allowlist (`MARCAS`).
  - El texto del usuario viaja como ARGUMENTO de subprocess (lista argv), nunca
    por shell: sin `shell=True`, sin inyeccion de shell.
  - La consola sigue atada a 127.0.0.1 (ver `__main__.py`).
  - `claude` corre con `timeout=` del propio subprocess; los errores (binario no
    encontrado, timeout, rc!=0) salen como mensajes en espanol, sin tracebacks.

SUPUESTO DE CWD (documentado): para que las skills curadas esten disponibles,
`claude` se ejecuta desde un directorio donde el plugin/repo keni-social este a
mano. Por defecto usamos el repo keni-social si existe en una ruta conocida; si no,
caemos al cwd del proceso (util cuando el plugin keni-social esta instalado a nivel
de usuario y las skills se resuelven globalmente). El cwd usado es informativo y se
puede sobreescribir con la env var `KENI_SKILLS_CWD`.

INYECCION/MOCKEO: `ejecutar_skill` delega en `_runner` (modulo-nivel) que es la
funcion que de verdad llama a `claude`. Los tests parchean `skills._runner` (o
`skills.ejecutar_skill`) para NUNCA llamar a `claude` real en CI.

SUBIR ARCHIVO (en vez de pegar texto/ruta): el formulario tambien acepta un
`<input type="file">`. El endpoint multipart `/api/skills/ejecutar-archivo` recibe
el archivo (Starlette `request.form()`, requiere `python-multipart` — llega via la
pila `mcp`/`starlette`), lo guarda en un dir TEMPORAL del SO con NOMBRE SANEADO
(nunca el nombre crudo del cliente), aplicando un LIMITE DE TAMANO por tipo de
contenido y comprobandolo MIENTRAS lee (en trozos, sin cargar 500 MB en memoria de
golpe). Tras procesar, BORRA el temporal (siempre, incluso ante error).

Que se hace con el archivo segun el tipo de contenido:
  - `clip-a-copy` es la unica skill que parte de un MEDIA (video/audio): su ruta
    temporal va al PROMPT (la skill transcribe en local). Reusa el mismo runner.
  - El resto son skills de texto (nota/transcripcion): se LEE el texto del archivo
    (decodificado utf-8, con respaldo latin-1) y se usa como `texto`, igual que si
    se hubiera pegado.
El archivo NUNCA se ejecuta; la ruta/los contenidos viajan como argv (sin shell).
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
from html import escape
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from .. import layout, marcas
from .._http_json import leer_json
from . import Feature, RecursoEstatico, features_ordenadas

_ESTATICOS = Path(__file__).parent.parent / "estaticos"


# --------------------------------------------------------------------------- #
# Allowlists: skills curadas y marcas (NUNCA invocaciones arbitrarias)         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _SkillInfo:
    id: str
    nombre: str
    descripcion: str  # una linea, para no tecnicos


# Lista CURADA de TIPOS DE CONTENIDO, organizada en DOS GRUPOS para el render del
# `<select>` (un `<optgroup>` por grupo) y para que el equipo distinga de un vistazo
# lo VALIDADO de lo EXPERIMENTAL. El `id` es el nombre de la skill tal como la invoca
# Claude por debajo y DEBE existir como carpeta en `skills-copy/.claude/skills/` (un
# test de la consola verifica que no haya drift entre estas listas y el disco).
#
# - "Validadas con el equipo": tipos que el piloto pidió y usa de verdad.
# - "Experimentales (no validadas con el piloto)": construidas adelantadas a la
#   demanda; el piloto no las pidió. Se ofrecen aparte y etiquetadas como tales.
#
# La LÓGICA de ejecución (allowlist, prompt, runner) NO distingue grupos: ambos son
# skills curadas igual de válidas; el grupo es solo una señal de UI/curaduría.


@dataclass(frozen=True)
class _GrupoSkills:
    etiqueta: str  # título visible del grupo (label del <optgroup>)
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
# Es la fuente para la allowlist y el test anti-drift: ambos grupos son skills
# válidas, solo cambia dónde se muestran en la UI.
SKILLS: tuple[_SkillInfo, ...] = tuple(s for g in GRUPOS_SKILLS for s in g.skills)

# Marcas editoriales permitidas. Se leen de la fuente UNICA de marcas de la consola
# (`marcas`), tomando solo las que tienen `slug` (las curadas como destino de copy
# en Skills). El VALUE interno es el slug-guion que Skills envia a Claude; la
# ETIQUETA visible es el nombre humano con acentos, identico al que muestra
# Metricas, para que el equipo vea los mismos nombres en TODA la consola.
MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones_por_slug())

_SKILLS_IDS = {s.id for s in SKILLS}
_MARCAS_IDS = {m[0] for m in MARCAS}

# Tope de tamano del texto de entrada (evita prompts gigantes accidentales).
_MAX_TEXTO = 60_000
# Timeout por defecto para la invocacion de Claude (segundos).
_TIMEOUT_DEF = 180

# Skills que parten de un MEDIA (video/audio): su archivo subido se referencia por
# RUTA en el prompt (la skill lo transcribe en local). El resto son skills de texto
# (nota/transcripcion): se LEE el contenido del archivo y se usa como `texto`.
_SKILLS_MEDIA = frozenset({"clip-a-copy"})

# Limites de tamano de subida (bytes). Para notas/texto basta poco; para media
# (clip-a-copy) permitimos un video razonable. Configurable por env para casos
# especiales (p.ej. un podcast largo) sin tocar codigo.
_MAX_SUBIDA_TEXTO = 25 * 1024 * 1024  # 25 MB para notas .txt/.md
_MAX_SUBIDA_MEDIA = 500 * 1024 * 1024  # 500 MB para video/audio (clip-a-copy)
# Trozo de lectura al volcar el archivo a disco (para medir tamano sin cargarlo todo).
_TROZO_SUBIDA = 1024 * 1024  # 1 MB


def _max_subida(skill: str) -> int:
    """Limite de tamano (bytes) de subida para una skill, con override por env.

    `KENI_SKILLS_MAX_SUBIDA_MB` (entero, en MB) sobreescribe el limite para casos
    especiales (p.ej. un podcast largo). Si no es valido, se ignora.
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
    Es un supuesto informativo; si el plugin keni-social esta instalado a nivel de
    usuario, las skills se resuelven igual desde cualquier cwd.
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

    El texto del usuario se incrusta tal cual; viaja como argumento de subprocess,
    no por shell, asi que no hay inyeccion. Marca y skill ya estan validadas contra
    sus allowlists antes de llegar aqui.
    """
    return f"usa {skill} con la siguiente nota, marca {marca}:\n\n{texto}"


def construir_prompt_ruta(skill: str, marca: str, ruta: str) -> str:
    """Construye el prompt para una skill de MEDIA que parte de una RUTA de archivo.

    Lo usa `clip-a-copy`: la skill transcribe el video/audio en local. La ruta es la
    de un temporal del SO (saneada por nosotros), no la del cliente, y viaja como
    argumento de subprocess (no por shell), asi que no hay inyeccion.
    """
    return f"usa {skill} con el archivo en esta ruta, marca {marca}:\n\n{ruta}"


# Extension de la ruta saneada -> sin punto, [a-z0-9] hasta 8 chars (evita nombres raros).
_RE_EXT = re.compile(r"^[a-z0-9]{1,8}$")


def _extension_segura(nombre_cliente: str | None) -> str:
    """Devuelve una extension SEGURA (`.mp4`, `.txt`, ...) o "" si no es reconocible.

    NO usa el nombre del cliente como nombre de archivo; solo extrae la extension
    para que la skill de media sepa el formato. Cualquier cosa rara -> sin extension.
    """
    if not nombre_cliente:
        return ""
    sufijo = Path(nombre_cliente).suffix.lower().lstrip(".")
    return f".{sufijo}" if _RE_EXT.match(sufijo) else ""


def _runner(prompt: str, *, cwd: Path, timeout: int) -> str:
    """Llama a `claude -p "<prompt>"` por subprocess y devuelve su stdout.

    Esta es LA funcion que toca el binario real; los tests la parchean para no
    llamar a Claude en CI. No usa shell: el prompt es un argv item, no shell.
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
    """Valida entradas, construye el prompt y corre Claude por debajo (headless).

    Devuelve el texto generado. Lanza `SkillError` (mensaje en espanol) ante
    entradas invalidas o fallos de ejecucion. `runner` permite inyectar la funcion
    que llama a `claude` (por defecto `_runner`); los tests lo usan / parchean.
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
    """Como `ejecutar_skill` pero para skills de MEDIA: pasa la RUTA al prompt.

    La usa `clip-a-copy`: el video/audio subido (ya guardado en un temporal seguro)
    se referencia por ruta para que la skill lo transcribe en local. Reusa el mismo
    `runner` mockeable; en tests se inyecta/parchea para no llamar a `claude`.
    """
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
    """Lee el texto de un archivo de nota/transcripcion (utf-8, respaldo latin-1).

    El tamano ya se acota al guardarlo (limite de texto), asi que aqui podemos leer
    todo. Decodifica utf-8 y, si falla, cae a latin-1 (nunca lanza por encoding).
    """
    crudo = ruta.read_bytes()
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return crudo.decode("latin-1", errors="replace")


async def _guardar_subida_segura(archivo: UploadFile, *, limite: int) -> tuple[Path, Path]:
    """Vuelca un `UploadFile` a un dir temporal del SO de forma segura.

    - Crea un dir efimero con `tempfile.mkdtemp` (permisos restringidos del SO).
    - El NOMBRE en disco lo generamos nosotros (uuid + extension saneada); NUNCA se
      usa el nombre crudo del cliente (evita path traversal / nombres raros).
    - Mide el tamano MIENTRAS escribe en trozos; si supera `limite`, aborta, limpia
      y lanza `SkillError` (sin cargar el archivo entero en memoria).

    Devuelve `(ruta_archivo, dir_temporal)`. El llamante DEBE borrar el dir temporal
    (`shutil.rmtree`) tras procesar, pase lo que pase.
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
# Render                                                                       #
# --------------------------------------------------------------------------- #


def _pagina_skills() -> str:
    # El <select> agrupa los tipos de contenido en un <optgroup> por grupo: los
    # validados con el equipo y, aparte, los experimentales (etiquetados como
    # tales en el propio label del grupo). Los `value` (slugs) no cambian, así que
    # la lógica de ejecución es idéntica; solo cambia la presentación.
    opciones_skill = ['<option value="">Elige un tipo de contenido...</option>']
    for grupo in GRUPOS_SKILLS:
        opciones_skill.append(f'<optgroup label="{escape(grupo.etiqueta)}">')
        for s in grupo.skills:
            opciones_skill.append(
                f'<option value="{escape(s.id)}" data-desc="{escape(s.descripcion)}">{escape(s.nombre)}</option>'
            )
        opciones_skill.append("</optgroup>")

    opciones_marca = ['<option value="">Elige una marca...</option>']
    for mid, mnombre in MARCAS:
        opciones_marca.append(f'<option value="{escape(mid)}">{escape(mnombre)}</option>')

    contenido = f"""
<h1>Generar copy</h1>
<p class="intro">Elige un tipo de contenido y una marca, pega tu nota o transcripción
<strong>o sube un archivo</strong>, y pulsa Generar. Te devolvemos un borrador listo para revisar.</p>
<p class="aviso-global" role="note">Nada se publica; revisa el borrador antes de usarlo.</p>

<form id="form-skills" class="skills-form">
  <div class="skills-campos">
    <label for="skills-skill">Tipo de contenido
      <select id="skills-skill" name="skill" required>{"".join(opciones_skill)}</select>
    </label>
    <label for="skills-marca">Marca
      <select id="skills-marca" name="marca" required>{"".join(opciones_marca)}</select>
    </label>
  </div>
  <p id="skills-desc" class="skills-desc" aria-live="polite"></p>

  <p class="skills-modo-ayuda">Pega texto <strong>o</strong> sube un archivo (lo que te resulte más cómodo).</p>

  <label for="skills-texto">Nota o transcripción</label>
  <textarea id="skills-texto" name="texto" class="skills-texto" spellcheck="false"
    placeholder="Pega aquí la nota o la transcripción del clip..."></textarea>

  <label for="skills-archivo" class="skills-archivo-label">O sube un archivo
    <span class="skills-archivo-pista">(nota .txt/.md; o video/audio si es «Clip a copy»)</span>
  </label>
  <input type="file" id="skills-archivo" name="archivo" class="skills-archivo">
  <p id="skills-archivo-nombre" class="skills-archivo-nombre" aria-live="polite"></p>

  <div class="skills-acciones">
    <button type="submit" class="primario" id="skills-generar">Generar</button>
    <span class="estado" id="skills-estado" role="status" aria-live="polite"></span>
  </div>
</form>

<section id="skills-resultado-wrap" class="skills-resultado-wrap" hidden>
  <h2>Borrador generado</h2>
  <div class="skills-resultado-acciones">
    <button type="button" class="boton" id="skills-copiar">Copiar</button>
    <button type="button" class="boton" id="skills-descargar">Descargar</button>
    <span class="estado" id="skills-copia-estado" role="status" aria-live="polite"></span>
  </div>
  <pre id="skills-resultado" class="skills-resultado" tabindex="0"></pre>
</section>
"""
    return layout.render_pagina(
        features=features_ordenadas(),
        activa=FEATURE.id,
        titulo=FEATURE.etiqueta,
        contenido=contenido,
        css=FEATURE.css,
        js=FEATURE.js,
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def pagina_skills(request: Request) -> Response:
    return HTMLResponse(_pagina_skills())


# Mensajes de SkillError que son fallos de VALIDACION de entrada (=> 400), no
# fallos del motor (=> 500). Deben coincidir exactamente con los que lanza
# `ejecutar_skill`; se centralizan aqui para mantenerlos en sincronia.
_ERRORES_VALIDACION = frozenset({
    "Falta la nota o transcripción para generar el borrador.",
    "El texto es demasiado largo; acórtalo e inténtalo de nuevo.",
    "Tipo de contenido no permitido.",
    "Marca no permitida.",
})


async def api_ejecutar(request: Request) -> Response:
    datos = await leer_json(request)
    skill = datos.get("skill")
    marca = datos.get("marca")
    texto = datos.get("texto")
    if not isinstance(skill, str) or not isinstance(marca, str) or not isinstance(texto, str):
        return JSONResponse(
            {"error": "Faltan el tipo de contenido, la marca o el texto."}, status_code=400
        )
    # Rechazo de allowlist explicito antes de ejecutar nada.
    if skill not in _SKILLS_IDS:
        return JSONResponse({"error": "Tipo de contenido no permitido."}, status_code=400)
    if marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    try:
        # Inyectable: en tests se parchea `skills.ejecutar_skill` o `skills._runner`.
        resultado = ejecutar_skill(skill, marca, texto)
    except SkillError as e:
        # Entradas invalidas (texto vacio/largo) => 400; el resto (fallo del motor)
        # tambien sale como mensaje claro, sin traceback. 400 para validacion,
        # 500 para fallo del motor.
        mensaje = str(e)
        codigo = 400 if mensaje in _ERRORES_VALIDACION else 500
        return JSONResponse({"error": mensaje}, status_code=codigo)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al navegador
        return JSONResponse({"error": "No se pudo generar el borrador."}, status_code=500)
    return JSONResponse({"resultado": resultado})


# Errores de subida que son de VALIDACION de entrada (=> 400), no fallo del motor.
_ERRORES_VALIDACION_ARCHIVO = frozenset({
    "El archivo es demasiado grande; sube uno más pequeño e inténtalo de nuevo.",
    "El archivo está vacío.",
    "Falta el archivo para generar el borrador.",
    "No se pudo guardar el archivo subido.",
    "Tipo de contenido no permitido.",
    "Marca no permitida.",
})


async def api_ejecutar_archivo(request: Request) -> Response:
    """Genera un borrador a partir de un archivo SUBIDO (multipart), sin pegar rutas.

    El usuario sube un archivo en vez de pegar texto. Lo guardamos en un temporal
    seguro (nombre saneado, limite de tamano por tipo, limpieza garantizada) y:
      - clip-a-copy (media): pasamos la RUTA temporal al prompt.
      - resto (texto): LEEMOS el texto del archivo y lo usamos como nota.
    El runner sigue siendo mockeable; en tests jamas se llama a `claude` real.
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse(
            {"error": "No se pudo leer el archivo subido."}, status_code=400
        )
    skill = form.get("skill")
    marca = form.get("marca")
    archivo = form.get("archivo")

    if not isinstance(skill, str) or not isinstance(marca, str):
        return JSONResponse(
            {"error": "Faltan el tipo de contenido o la marca."}, status_code=400
        )
    if skill not in _SKILLS_IDS:
        return JSONResponse({"error": "Tipo de contenido no permitido."}, status_code=400)
    if marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    if not isinstance(archivo, UploadFile):
        return JSONResponse(
            {"error": "No se recibió ningún archivo. Súbelo o pega el texto."},
            status_code=400,
        )

    dir_temporal: Path | None = None
    try:
        ruta, dir_temporal = await _guardar_subida_segura(
            archivo, limite=_max_subida(skill)
        )
        if skill in _SKILLS_MEDIA:
            # Media (clip-a-copy): la skill transcribe en local; pasamos la RUTA.
            resultado = ejecutar_skill_ruta(skill, marca, str(ruta))
        else:
            # Texto: leemos el contenido del archivo y lo tratamos como nota pegada.
            resultado = ejecutar_skill(skill, marca, _leer_texto_archivo(ruta))
    except SkillError as e:
        mensaje = str(e)
        es_validacion = mensaje in _ERRORES_VALIDACION_ARCHIVO or mensaje in _ERRORES_VALIDACION
        codigo = 400 if es_validacion else 500
        return JSONResponse({"error": mensaje}, status_code=codigo)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al navegador
        return JSONResponse({"error": "No se pudo generar el borrador."}, status_code=500)
    finally:
        # Limpieza garantizada del temporal, pase lo que pase.
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
    return JSONResponse({"resultado": resultado})


FEATURE = Feature(
    id="skills",
    etiqueta="Generar copy",
    orden=30,
    descripcion="Elige un tipo de contenido, una marca y tu nota; te devolvemos un borrador para revisar.",
    rutas=[
        Route("/skills", pagina_skills),
        Route("/api/skills/ejecutar", api_ejecutar, methods=["POST"]),
        Route("/api/skills/ejecutar-archivo", api_ejecutar_archivo, methods=["POST"]),
    ],
    estaticos=[
        RecursoEstatico("skills.css", _ESTATICOS / "skills.css", "text/css; charset=utf-8"),
        RecursoEstatico("skills.js", _ESTATICOS / "skills.js", "application/javascript; charset=utf-8"),
    ],
    css=["skills.css"],
    js=["skills.js"],
)
