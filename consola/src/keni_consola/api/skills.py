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

import os
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterable
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, marcas, redes, repos, skills_catalogo
from .._http_json import leer_json
from ..dominio import skills as dom_skills
from ..dominio import stream
from ..dominio.publicaciones import publicacion_a_dict

# La LOGICA DE NEGOCIO (parseo del stream, presupuesto, verdicto, limpieza de emojis,
# reparto en piezas, prompts, cosecha de imagenes, post-procesado) vive en `dominio/`
# (hallazgo H6): este handler solo orquesta HTTP. Se reexporta lo que los tests y otros
# modulos (`api.rss`) consumen como `skills.<symbolo>` para no romper su API publica al
# moverla de sitio.
#
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
_derivar_verdicto = stream.derivar_verdicto  # alias historico (privado) usado en este modulo
_arg_presupuesto = stream.arg_presupuesto  # alias historico (privado) cubierto por tests

# Prompts / cosecha de imagenes / publicaciones / post-procesado (dominio.skills):
construir_prompt = dom_skills.construir_prompt
construir_prompt_ruta = dom_skills.construir_prompt_ruta
cosechar_imagenes = dom_skills.cosechar_imagenes
construir_procesar_copy = dom_skills.construir_procesar_copy
construir_procesar_documento = dom_skills.construir_procesar_documento
_crear_publicaciones_desde_piezas = dom_skills.crear_publicaciones_desde_piezas
_rutas_imagen_en_texto = dom_skills._rutas_imagen_en_texto  # cubierto por tests

# Serializacion de una publicacion: vive en el dominio (sitio comun para publicaciones y
# skills); se reexpone con el nombre privado historico para los callsites de este modulo.
_publicacion_a_dict = publicacion_a_dict

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


def _cwd_ejecucion_skills() -> Path:
    """Directorio desde el que EJECUTAMOS `claude` para correr una skill.

    Debe ser el dir que CONTIENE `.claude/skills`, no la raiz del repo: solo asi `claude`
    descubre las skills como TOOLS del proyecto y resuelven sus rutas relativas
    (`contexto-editorial/...`, `.claude/skills/.../componer.py`). En keni-social las skills
    viven en `skills-copy/.claude/skills`, por eso el cwd correcto es `skills-copy/` (no la
    raiz, que es lo que devuelve `_cwd_skills()`; ese se reserva para el catalogo, que le
    anade `skills-copy/.claude/skills`). Se distingue de `_cwd_skills()` a proposito.
    """
    base = _cwd_skills()
    if (base / "skills-copy" / ".claude" / "skills").is_dir():
        return base / "skills-copy"
    if (base / ".claude" / "skills").is_dir():
        return base
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


def normalizar_redes(crudas: Iterable[str] | None) -> list[str]:
    """Filtra/ordena ids de red contra las canonicas; sin entradas validas => las 5.

    Ignora ids desconocidos o repetidos. El resultado respeta SIEMPRE el orden fijo
    de `redes.REDES`, sea cual sea el orden en que llegaron. Si no llega ninguna red
    valida (lista vacia, None o solo basura), se usan las 5 redes canonicas. Resuelve
    el catalogo canonico aqui (frontera con `redes`) y delega el filtrado puro al dominio.
    """
    return stream.normalizar_redes(crudas, canonicas=redes.ids())


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
            gen["id"], prompt=prompt, cwd=_cwd_ejecucion_skills(), procesar=procesar,
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


# El CRUD del CATALOGO de skills (pagina de gestion) + el visor de prompt viven en su
# propio modulo de API: `api/skills_catalogo_api.py` (hallazgo H6, 2a etapa). Este modulo
# orquesta SOLO la ejecucion de skills y el historial. Las URLs son identicas.


# Rutas: las que tienen segmento ESTATICO (`ejecutar`, `ejecutar-archivo`, `historial`)
# van ANTES que las de parametro (`/historial/{id}`) para que Starlette las case primero y
# no las trague la ruta parametrica. Las rutas de `/api/skills/catalogo*` viven en
# `api/skills_catalogo_api.py` (no colisionan con estas: distinto segmento).
RUTAS = [
    Route("/api/skills", opciones, methods=["GET"]),
    Route("/api/skills/ejecutar", ejecutar, methods=["POST"]),
    Route("/api/skills/ejecutar-archivo", ejecutar_archivo, methods=["POST"]),
    Route("/api/skills/historial", historial, methods=["GET"]),
    Route("/api/skills/historial/{historial_id}/guardar", historial_guardar, methods=["POST"]),
    Route("/api/skills/historial/{historial_id}", historial_detalle, methods=["GET"]),
]
