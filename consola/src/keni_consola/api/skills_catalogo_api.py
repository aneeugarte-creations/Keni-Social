"""API del CATALOGO de skills (pagina de gestion) + visor de prompt.

CRUD puro del catalogo de skills respaldado por ARCHIVOS (`skills_catalogo`): una
carpeta por skill con su `SKILL.md` + `keni.yaml`. Aqui viven SOLO los handlers de
gestion del catalogo (listar/crear/obtener/actualizar/SKILL.md/borrar) y el visor de
prompt (`vista-prompt`), que rinde la invocacion EXACTA que recibiria Claude sin
llamarlo. La generacion de copy y el historial viven en `api/skills.py`.

Este modulo se separo de `api/skills.py` (hallazgo H6, 2a etapa): son responsabilidades
independientes de la logica de generacion. Las URLs y los contratos HTTP son IDENTICOS a
los de antes; solo cambia el fichero. La app los descubre por su variable `RUTAS` (ver
`api/__init__.py`), asi que no hace falta tocar `app.py`.

SEGURIDAD: la pertenencia de una skill se valida contra el catalogo de archivos
(`skills_catalogo.existe`); el id se sanea contra path-traversal en `skills_catalogo`
(ids con separadores no resuelven). Los errores salen como JSON en espanol, sin
tracebacks crudos.

ORDEN DE RUTAS: las que tienen segmento ESTATICO (`/catalogo`, `/catalogo/{id}/skill-md`,
`/catalogo/{id}/vista-prompt`) van ANTES que las puramente parametricas
(`/catalogo/{id}`) para que Starlette las case primero y no las trague la ruta
parametrica.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import redes, skills_catalogo
from .._http_json import leer_json
from ..dominio import stream

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
    # Mismo filtrado que `api.skills.normalizar_redes`: resuelve el catalogo canonico aqui
    # (frontera con `redes`) y delega el filtrado puro al dominio. Sin entradas validas => las 5.
    redes_ids = stream.normalizar_redes(
        crudas if isinstance(crudas, list) else None, canonicas=redes.ids()
    )
    prompt = skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)
    return JSONResponse({"prompt": prompt})


# Rutas: las que tienen segmento ESTATICO van ANTES que las de parametro
# (`/catalogo/{skill_id}`) para que Starlette las case primero y no las trague la ruta
# parametrica.
RUTAS = [
    Route("/api/skills/catalogo", catalogo_listar, methods=["GET"]),
    Route("/api/skills/catalogo", catalogo_crear, methods=["POST"]),
    Route("/api/skills/catalogo/{skill_id}/skill-md", catalogo_skill_md, methods=["PUT"]),
    Route("/api/skills/catalogo/{skill_id}/vista-prompt", catalogo_vista_prompt, methods=["POST"]),
    Route("/api/skills/catalogo/{skill_id}", catalogo_obtener, methods=["GET"]),
    Route("/api/skills/catalogo/{skill_id}", catalogo_actualizar, methods=["PUT"]),
    Route("/api/skills/catalogo/{skill_id}", catalogo_borrar, methods=["DELETE"]),
]
