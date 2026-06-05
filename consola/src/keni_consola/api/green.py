"""API del TALLER GREEN / brainstorming: ideas de contenido EVERGREEN.

CONCEPTO (pedido por el cliente): la IA NO genera contenido evergreen a ciegas. En su lugar,
PROPONE una LISTA de ideas; una persona las APRUEBA o las DESCARTA; y solo para las aprobadas
se GENERA el contenido (una pieza `flujo='evergreen'` en el tablero). Es un pequeño taller de
brainstorming con un humano en el bucle.

RECURSOS:
  - `GET    /api/green/ideas?marca=&estado=`     catálogo de ideas (filtros opcionales).
  - `POST   /api/green/ideas`                    crea una idea MANUAL {marca, titulo, descripcion}.
  - `PATCH  /api/green/ideas/{id}`               cambia estado (aprobar/descartar) y/o edita texto.
  - `DELETE /api/green/ideas/{id}`               borra una idea.
  - `POST   /api/green/proponer`                 {marca, contexto?} lanza la generación de IDEAS
                                                 (IA): crea las filas como `propuesta`/`ia` cuando
                                                 el job completa (en el worker).
  - `POST   /api/green/ideas/{id}/generar`       SOLO si `estado='aprobada'`: crea una pieza
                                                 `flujo='evergreen'` en el tablero y lanza su copy;
                                                 guarda `contenido_id` en la idea.

SEGURIDAD / VALIDACION:
  - Multiusuario via middleware (sesión o token), igual que el resto del tablero.
  - `marca` SIEMPRE del catálogo único (`consola.marcas`); `estado` de la allowlist
    (`estados.ESTADOS_GREEN_IDEA`). Nada se confía del cliente; SQL parametrizado en `repos`/`db`.
  - La generación corre en SEGUNDO PLANO con el lanzador neutro (`claude -p` encolado); el
    frontend sondea `GET /api/generaciones/{id}`.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, marcas, permisos, redes, repos
from .._http_json import leer_json
from ..dominio import generar as gen_dom
from ..dominio import green as dom_green
from ..dominio import stream
from ..estados import (
    ESTADO_GREEN_APROBADA,
    ESTADO_GREEN_PROPUESTA,
    ESTADOS_GREEN_IDEA,
    FLUJO_EVERGREEN,
)
from ..seguridad import autor_de_peticion

_MAX_TITULO = 200
_MAX_DESCRIPCION = 2000
# Contexto opcional del taller (tono/temas a evitar) que se adjunta al prompt de propuesta.
_MAX_CONTEXTO = 4000


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """La marca es OBLIGATORIA y debe ser del catálogo. `(marca, None)` o `(None, mensaje)`."""
    if not isinstance(marca, str) or not marca.strip():
        return None, "La marca es obligatoria."
    marca = marca.strip()
    if not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _idea_a_dict(idea: dict[str, Any]) -> dict[str, Any]:
    """Serializa una idea añadiendo el nombre legible de su marca."""
    return {
        **idea,
        "marca_nombre": marcas.etiqueta_de(idea["marca"]) if idea.get("marca") else "",
    }


async def listar(request: Request) -> Response:
    """GET /api/green/ideas: catálogo de ideas evergreen. Filtros: `marca`, `estado`."""
    q = request.query_params
    estado = q.get("estado") or None
    if estado is not None and estado not in ESTADOS_GREEN_IDEA:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)
    # Alcance por marca: una sesion acotada no puede pedir ideas de una marca ajena.
    rechazo = permisos.rechazo_marca(request, q.get("marca") or None)
    if rechazo is not None:
        return rechazo
    ideas = repos.listar_green_ideas(marca=q.get("marca") or None, estado=estado)
    # SCOPING POR DEFECTO: sin marca explicita, una sesion acotada solo ve SUS marcas
    # (post-filtro en memoria; admin/sin restriccion ve todo).
    if not (q.get("marca") or None):
        visibles = permisos.marcas_scope(request)
        if visibles is not None:
            ideas = [i for i in ideas if not i.get("marca") or i.get("marca") in visibles]
    return JSONResponse(
        {
            "ideas": [_idea_a_dict(i) for i in ideas],
            "estados": list(ESTADOS_GREEN_IDEA),
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
        }
    )


async def crear(request: Request) -> Response:
    """POST /api/green/ideas: crea una idea MANUAL `{marca, titulo, descripcion?}` -> `{idea}`.

    Nace en estado `propuesta`, origen `manual` (igual que una idea de la IA: hay que aprobarla
    antes de generar nada).
    """
    datos = await leer_json(request)
    marca, error = _validar_marca(datos.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    # Alcance por marca: no crees ideas para una marca fuera de tu alcance.
    rechazo = permisos.rechazo_marca(request, marca)
    if rechazo is not None:
        return rechazo
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "La idea necesita un título."}, status_code=400)
    descripcion = datos.get("descripcion")
    descripcion = descripcion.strip()[:_MAX_DESCRIPCION] if isinstance(descripcion, str) else ""

    idea = repos.crear_green_idea(
        marca=marca,
        titulo=titulo.strip()[:_MAX_TITULO],
        descripcion=descripcion,
        estado=ESTADO_GREEN_PROPUESTA,
        origen="manual",
    )
    return JSONResponse({"idea": _idea_a_dict(idea)})


async def actualizar(request: Request) -> Response:
    """PATCH /api/green/ideas/{id}: cambia `estado` (aprobar/descartar) y/o edita texto.

    `estado` debe ser de la allowlist. `titulo`/`descripcion` son opcionales (edición). 404 si
    la idea ya no existe.
    """
    idea_id = request.path_params["idea_id"]
    idea_actual = repos.obtener_green_idea(idea_id)
    if idea_actual is None:
        return JSONResponse({"error": "Esa idea ya no existe."}, status_code=404)
    rechazo = permisos.rechazo_pieza(request, idea_actual.get("marca") or "")
    if rechazo is not None:
        return rechazo
    datos = await leer_json(request)
    campos: dict[str, Any] = {}

    if "estado" in datos:
        estado = datos.get("estado")
        if estado not in ESTADOS_GREEN_IDEA:
            return JSONResponse({"error": "Estado no permitido."}, status_code=400)
        campos["estado"] = estado
    if "titulo" in datos:
        titulo = datos.get("titulo")
        if not isinstance(titulo, str) or not titulo.strip():
            return JSONResponse({"error": "El título no puede quedar vacío."}, status_code=400)
        campos["titulo"] = titulo.strip()[:_MAX_TITULO]
    if "descripcion" in datos:
        descripcion = datos.get("descripcion")
        campos["descripcion"] = (
            descripcion.strip()[:_MAX_DESCRIPCION] if isinstance(descripcion, str) else ""
        )

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)

    idea = repos.actualizar_green_idea(idea_id, campos)
    if idea is None:
        return JSONResponse({"error": "Esa idea ya no existe."}, status_code=404)
    return JSONResponse({"idea": _idea_a_dict(idea)})


async def borrar(request: Request) -> Response:
    """DELETE /api/green/ideas/{id}: borra la idea (no toca la pieza generada, si la hubiera)."""
    idea_id = request.path_params["idea_id"]
    # Alcance por marca: no borres una idea de otra marca (404 generico desde fuera del tenant).
    idea = repos.obtener_green_idea(idea_id)
    if idea is None:
        return JSONResponse({"error": "Esa idea ya no existe."}, status_code=404)
    rechazo = permisos.rechazo_pieza(request, idea.get("marca") or "")
    if rechazo is not None:
        return rechazo
    if not repos.borrar_green_idea(idea_id):
        return JSONResponse({"error": "Esa idea ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Idea borrada."})


async def proponer(request: Request) -> Response:
    """POST /api/green/proponer `{marca, contexto?}` -> `{generacion}` (tipo "green-ideas").

    Lanza una generación de IDEAS evergreen EN SEGUNDO PLANO. El frontend sondea
    `GET /api/generaciones/{id}`; al completarse, el worker habrá creado las filas `green_ideas`
    en estado `propuesta`, origen `ia`. NO genera contenido (eso es `generar`, al aprobar).
    """
    datos = await leer_json(request)
    marca, error = _validar_marca(datos.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    # Alcance por marca: no lances propuestas de IA para una marca fuera de tu alcance.
    rechazo = permisos.rechazo_marca(request, marca)
    if rechazo is not None:
        return rechazo
    contexto = datos.get("contexto")
    contexto = contexto.strip()[:_MAX_CONTEXTO] if isinstance(contexto, str) else ""

    autor = autor_de_peticion(request)
    try:
        gen = dom_green.lanzar_propuesta(marca=marca, contexto=contexto, autor=autor)
    except generaciones.ColaLlenaError:
        return JSONResponse(
            {"error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
            status_code=429,
        )
    return JSONResponse({"generacion": gen})


async def generar_pieza(request: Request) -> Response:
    """POST /api/green/ideas/{id}/generar -> `{idea, generacion}`.

    SOLO si la idea está `aprobada`: crea una pieza `flujo='evergreen'` en el tablero
    (`repos.crear_contenido`), lanza su copy con el lanzador existente (`generar.lanzar_copy`,
    EN SEGUNDO PLANO) anidado bajo esa pieza, y guarda el `contenido_id` en la idea. Opcional:
    `{redes:[..]}` para acotar las redes del copy (por defecto, todas las canónicas).
    """
    idea_id = request.path_params["idea_id"]
    idea = repos.obtener_green_idea(idea_id)
    if idea is None:
        return JSONResponse({"error": "Esa idea ya no existe."}, status_code=404)
    rechazo = permisos.rechazo_pieza(request, idea.get("marca") or "")
    if rechazo is not None:
        return rechazo
    if idea["estado"] != ESTADO_GREEN_APROBADA:
        return JSONResponse(
            {"error": "Solo se puede generar contenido de una idea aprobada."}, status_code=400
        )
    if not gen_dom.marca_valida(idea["marca"]):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    datos = await leer_json(request)
    crudas = datos.get("redes")
    redes_ids = stream.normalizar_redes(
        crudas if isinstance(crudas, list) else None, canonicas=redes.ids()
    )

    autor = autor_de_peticion(request)
    titulo = idea["titulo"]
    descripcion = idea.get("descripcion", "")
    # La nota de la pieza es la idea aprobada (título + descripción): es el material a redactar.
    nota = "\n\n".join(p for p in (titulo, descripcion) if p)[: gen_dom.MAX_TEXTO]

    # Pieza padre del tablero: evergreen, origen "green" (taller de brainstorming).
    contenido = repos.crear_contenido(
        clase="contenido",
        flujo=FLUJO_EVERGREEN,
        titulo=titulo,
        descripcion=descripcion,
        marca=idea["marca"],
        origen="green",
        autor=autor,
    )

    try:
        gen = gen_dom.lanzar_copy(
            tipo="green",
            origen_historial="brainstorming-green",
            marca=idea["marca"],
            contexto=nota,
            redes_ids=redes_ids,
            titulo=titulo,
            titulo_dado=titulo,
            texto_base=nota,
            autor=autor,
            contenido_id=contenido["id"],
        )
    except generaciones.ColaLlenaError:
        return JSONResponse(
            {"error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
            status_code=429,
        )

    actualizada = repos.actualizar_green_idea(idea_id, {"contenido_id": contenido["id"]})
    return JSONResponse(
        {"idea": _idea_a_dict(actualizada or idea), "generacion": gen}
    )


RUTAS = [
    Route("/api/green/ideas", listar, methods=["GET"]),
    Route("/api/green/ideas", crear, methods=["POST"]),
    Route("/api/green/ideas/{idea_id}", actualizar, methods=["PATCH"]),
    Route("/api/green/ideas/{idea_id}", borrar, methods=["DELETE"]),
    Route("/api/green/proponer", proponer, methods=["POST"]),
    Route("/api/green/ideas/{idea_id}/generar", generar_pieza, methods=["POST"]),
]
