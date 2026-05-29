"""FACHADA Skills: allowlists, cwd, prompts, parseo y lanzamiento (reexportados del dominio).

Tras el hallazgo H6 (3 etapas), este modulo YA NO contiene handlers HTTP: es una FACHADA
estable que reexpone, bajo `skills.<simbolo>`, lo que otros modulos de la consola consumen
sin tener que conocer en que capa del dominio vive cada pieza. Sus consumidores:

  - `api/skills_generacion_api.py`: los handlers de ejecucion/historial (3a etapa).
  - `api/rss.py`, `api/hashtags.py`, `api/termometro.py`, `api/agentes.py`: lanzan
    generaciones / parsean stream usando `skills.<simbolo>`.
  - los tests: parsean salidas y metricas via `skills.<simbolo>`.

La LOGICA DE NEGOCIO vive en `dominio/` (no aqui): parseo del stream, presupuesto,
verdicto, limpieza de emojis, reparto en piezas, prompts, cosecha de imagenes,
post-procesado, resolucion del cwd y lanzamiento del trabajo. Este modulo SOLO mantiene
las allowlists (skills∈catalogo de archivos, marcas∈catalogo unico) y el tope de texto,
mas los reexports. Modulos de `dominio/` y los CLI NO importan de aqui (hallazgo N13):
resuelven cwd / lanzamiento directamente en `dominio.skills`.

URLs y contratos HTTP: viven en `api/skills_generacion_api.py` y
`api/skills_catalogo_api.py`; no cambian.
"""

from __future__ import annotations

from collections.abc import Iterable

from .. import marcas, redes, skills_catalogo
from ..dominio import skills as dom_skills
from ..dominio import stream
from ..dominio.publicaciones import crear_borrador, publicacion_a_dict

# Parseo del stream / metricas / presupuesto / verdicto / limpieza (dominio.stream):
SkillError = stream.SkillError
MetricasRun = stream.MetricasRun
AcumuladorStream = stream.AcumuladorStream
metricas_a_dict = stream.metricas_a_dict
parsear_resultado_json = stream.parsear_resultado_json
parsear_salida = stream.parsear_salida
quitar_emojis = stream.quitar_emojis
derivar_verdicto = stream.derivar_verdicto
derivar_titulo = stream.derivar_titulo
_derivar_verdicto = stream.derivar_verdicto  # alias historico (privado) usado por callsites
_arg_presupuesto = stream.arg_presupuesto  # alias historico (privado) cubierto por tests

# Prompts / cosecha de imagenes / publicaciones / post-procesado (dominio.skills):
construir_prompt = dom_skills.construir_prompt
construir_prompt_ruta = dom_skills.construir_prompt_ruta
cosechar_imagenes = dom_skills.cosechar_imagenes
construir_procesar_copy = dom_skills.construir_procesar_copy
construir_procesar_documento = dom_skills.construir_procesar_documento
_crear_publicaciones_desde_piezas = dom_skills.crear_publicaciones_desde_piezas
_rutas_imagen_en_texto = dom_skills._rutas_imagen_en_texto  # cubierto por tests

# Resolucion del cwd de ejecucion de `claude` (dominio.skills). Se reexpone con el nombre
# privado historico que usan `api.rss`/`api.hashtags`/`termometro_cli` y los tests.
_cwd_skills = dom_skills.cwd_skills
_cwd_ejecucion_skills = dom_skills.cwd_ejecucion_skills

# Lanzamiento de un trabajo de IA en segundo plano (dominio.skills). Reexpuesto para
# `api.rss` (lanzar_generacion_copy via construir_procesar_copy), `api.termometro`
# (lanzar_generacion_skill) y la etiqueta legible de la actividad.
etiqueta_generacion = dom_skills.etiqueta_generacion
lanzar_generacion_copy = dom_skills.lanzar_generacion_copy
lanzar_generacion_skill = dom_skills.lanzar_generacion_skill

# Serializacion de una publicacion: vive en el dominio (sitio comun para publicaciones y
# skills); se reexpone con el nombre privado historico para los callsites.
_publicacion_a_dict = publicacion_a_dict

# Handoff A->C (ADR 0005 §Seams #1): crear un BORRADOR en C (`publicaciones`) por su
# funcion-contrato. Se reexpone por la fachada para que los routers de A (p.ej.
# `skills_generacion_api.historial_guardar` en su rama legada de UNA pieza) depositen el
# borrador por el contrato de C, no por `repos.crear_publicacion` directo.
crear_borrador = crear_borrador

# --------------------------------------------------------------------------- #
# Allowlists: skills curadas y marcas (NUNCA invocaciones arbitrarias)         #
# --------------------------------------------------------------------------- #


# Las SKILLS ya no son una allowlist fija en codigo: viven en ARCHIVOS y se gestionan
# via `skills_catalogo` (carpeta por skill con `SKILL.md` + `keni.yaml`). La pertenencia
# se resuelve dinamicamente (`_AllowlistSkills`) y los metadatos para la UI salen de
# `skills_catalogo.listar()` (ver `skills_generacion_api.opciones`).

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
    `skills_catalogo.existe`. Mantiene la misma sintaxis (`in`) que usan los handlers de
    ejecucion y `api.rss`.
    """

    def __contains__(self, skill_id: object) -> bool:
        return isinstance(skill_id, str) and skills_catalogo.existe(skill_id)


# Allowlist de skills: pertenencia dinamica contra el catalogo de archivos.
_SKILLS_IDS = _AllowlistSkills()


def _nombre_skill(skill_id: str) -> str:
    """Nombre humano de una skill desde el catalogo de archivos; cae al id si no existe."""
    return dom_skills.nombre_skill(skill_id)


# Tope de tamano del texto de entrada (evita prompts gigantes accidentales).
_MAX_TEXTO = 60_000


def normalizar_redes(crudas: Iterable[str] | None) -> list[str]:
    """Filtra/ordena ids de red contra las canonicas; sin entradas validas => las 5.

    Ignora ids desconocidos o repetidos. El resultado respeta SIEMPRE el orden fijo
    de `redes.REDES`, sea cual sea el orden en que llegaron. Si no llega ninguna red
    valida (lista vacia, None o solo basura), se usan las 5 redes canonicas. Resuelve
    el catalogo canonico aqui (frontera con `redes`) y delega el filtrado puro al dominio.
    """
    return stream.normalizar_redes(crudas, canonicas=redes.ids())
