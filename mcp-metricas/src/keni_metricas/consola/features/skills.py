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
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from .. import layout
from . import Feature, RecursoEstatico, features_ordenadas

_ESTATICOS = Path(__file__).parent


# --------------------------------------------------------------------------- #
# Allowlists: skills curadas y marcas (NUNCA invocaciones arbitrarias)         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _SkillInfo:
    id: str
    nombre: str
    descripcion: str  # una linea, para no tecnicos


# Lista CURADA. El `id` es el nombre de la skill tal como la invoca Claude.
SKILLS: tuple[_SkillInfo, ...] = (
    _SkillInfo("copy-desde-nota", "Copy desde nota", "Convierte una nota en copy para redes."),
    _SkillInfo("clip-a-copy", "Clip a copy", "De la transcripcion de un clip a copy listo para publicar."),
    _SkillInfo("nota-a-formato", "Nota a formato", "Adapta una nota al formato de una plataforma concreta."),
    _SkillInfo("resumen-tendencia", "Resumen de tendencia", "Resume una tendencia a partir de varias fuentes."),
    _SkillInfo("responde-comentarios", "Responde comentarios", "Propone respuestas a comentarios de la comunidad."),
    _SkillInfo("calendario-editorial", "Calendario editorial", "Arma un calendario editorial desde el material dado."),
    _SkillInfo("nota-a-hilo", "Nota a hilo", "Convierte una nota en un hilo encadenado para redes."),
)

# Marcas editoriales permitidas (coinciden con contexto-editorial/marcas del repo).
# El primer elemento es el VALUE interno (slug-guion que Skills envia a Claude); el
# segundo es la ETIQUETA visible (nombre humano legible, con acentos). El nombre
# humano debe coincidir con el que muestra Metricas, para que el equipo vea los
# mismos nombres en TODA la consola (ver `metricas.NOMBRE_MARCA`).
MARCAS: tuple[tuple[str, str], ...] = (
    ("unotv", "UnoTV"),
    ("claro-sports", "Claro Sports"),
    ("nacion-gamer", "Nación Gamer"),
    ("piso-15", "Piso 15"),
    ("fundacion", "Fundación"),
)

_SKILLS_IDS = {s.id for s in SKILLS}
_MARCAS_IDS = {m[0] for m in MARCAS}

# Tope de tamano del texto de entrada (evita prompts gigantes accidentales).
_MAX_TEXTO = 60_000
# Timeout por defecto para la invocacion de Claude (segundos).
_TIMEOUT_DEF = 180


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


def _runner(prompt: str, *, cwd: Path, timeout: int) -> str:
    """Llama a `claude -p "<prompt>"` por subprocess y devuelve su stdout.

    Esta es LA funcion que toca el binario real; los tests la parchean para no
    llamar a Claude en CI. No usa shell: el prompt es un argv item, no shell.
    """
    if shutil.which("claude") is None:
        raise SkillError(
            "No se encontro el comando 'claude' en el PATH. Instala Claude Code para "
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
        raise SkillError("No se encontro el comando 'claude' en el PATH.") from e
    except subprocess.TimeoutExpired as e:
        raise SkillError(
            f"Claude tardo demasiado (mas de {timeout} s) y se cancelo. "
            "Prueba con una nota mas corta."
        ) from e
    if proc.returncode != 0:
        detalle = (proc.stderr or "").strip() or "error desconocido al ejecutar Claude"
        raise SkillError(f"Claude termino con error: {detalle}")
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
        raise SkillError("Skill no permitida.")
    if marca not in _MARCAS_IDS:
        raise SkillError("Marca no permitida.")
    texto = (texto or "").strip()
    if not texto:
        raise SkillError("Falta la nota o transcripcion para generar el borrador.")
    if len(texto) > _MAX_TEXTO:
        raise SkillError("El texto es demasiado largo; acortalo e intenta de nuevo.")

    prompt = construir_prompt(skill, marca, texto)
    ejecutor = runner if runner is not None else _runner
    salida = ejecutor(prompt, cwd=_cwd_skills(), timeout=timeout)
    if not salida:
        raise SkillError("Claude no devolvio ningun contenido.")
    return salida


# --------------------------------------------------------------------------- #
# Render                                                                       #
# --------------------------------------------------------------------------- #


def _pagina_skills() -> str:
    opciones_skill = ['<option value="">Elige una skill...</option>']
    for s in SKILLS:
        opciones_skill.append(
            f'<option value="{escape(s.id)}" data-desc="{escape(s.descripcion)}">{escape(s.nombre)}</option>'
        )

    opciones_marca = ['<option value="">Elige una marca...</option>']
    for mid, mnombre in MARCAS:
        opciones_marca.append(f'<option value="{escape(mid)}">{escape(mnombre)}</option>')

    contenido = f"""
<h1>Generar copy</h1>
<p class="intro">Elige una skill y una marca, pega tu nota o transcripcion y pulsa Generar.
La consola corre Claude por debajo y te muestra el borrador aqui.</p>
<p class="aviso-global" role="note">Nada se publica; revisa antes de usar.</p>

<form id="form-skills" class="skills-form">
  <div class="skills-campos">
    <label for="skills-skill">Skill
      <select id="skills-skill" name="skill" required>{"".join(opciones_skill)}</select>
    </label>
    <label for="skills-marca">Marca
      <select id="skills-marca" name="marca" required>{"".join(opciones_marca)}</select>
    </label>
  </div>
  <p id="skills-desc" class="skills-desc" aria-live="polite"></p>

  <label for="skills-texto">Nota o transcripcion (o pega una ruta de archivo)</label>
  <textarea id="skills-texto" name="texto" class="skills-texto" spellcheck="false"
    placeholder="Pega aqui la nota, la transcripcion del clip, o la ruta de un archivo..."></textarea>

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


async def _leer_json(request: Request) -> dict:
    try:
        datos = await request.json()
    except Exception:  # noqa: BLE001 -- body invalido => dict vacio (se valida abajo)
        return {}
    return datos if isinstance(datos, dict) else {}


async def api_ejecutar(request: Request) -> Response:
    datos = await _leer_json(request)
    skill = datos.get("skill")
    marca = datos.get("marca")
    texto = datos.get("texto")
    if not isinstance(skill, str) or not isinstance(marca, str) or not isinstance(texto, str):
        return JSONResponse({"error": "Faltan skill, marca o texto."}, status_code=400)
    # Rechazo de allowlist explicito antes de ejecutar nada.
    if skill not in _SKILLS_IDS:
        return JSONResponse({"error": "Skill no permitida."}, status_code=400)
    if marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    try:
        # Inyectable: en tests se parchea `skills.ejecutar_skill` o `skills._runner`.
        resultado = ejecutar_skill(skill, marca, texto)
    except SkillError as e:
        # Entradas invalidas (texto vacio/largo) => 400; el resto (fallo de Claude)
        # tambien sale como mensaje claro, sin traceback. Usamos 400 para validacion
        # y 500 para fallo del motor.
        mensaje = str(e)
        codigo = 400 if mensaje in (
            "Falta la nota o transcripcion para generar el borrador.",
            "El texto es demasiado largo; acortalo e intenta de nuevo.",
            "Skill no permitida.",
            "Marca no permitida.",
        ) else 500
        return JSONResponse({"error": mensaje}, status_code=codigo)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al navegador
        return JSONResponse({"error": "No se pudo generar el borrador."}, status_code=500)
    return JSONResponse({"resultado": resultado})


FEATURE = Feature(
    id="skills",
    etiqueta="Generar copy",
    orden=30,
    descripcion="Elige una skill, una marca y tu nota; la consola corre Claude por debajo.",
    rutas=[
        Route("/skills", pagina_skills),
        Route("/api/skills/ejecutar", api_ejecutar, methods=["POST"]),
    ],
    estaticos=[
        RecursoEstatico("skills.css", _ESTATICOS / "skills.css", "text/css; charset=utf-8"),
        RecursoEstatico("skills.js", _ESTATICOS / "skills.js", "application/javascript; charset=utf-8"),
    ],
    css=["skills.css"],
    js=["skills.js"],
)
