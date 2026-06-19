"""API del TALLER EVERGREEN / brainstorming: ideas de contenido EVERGREEN.

CONCEPTO (pedido por el cliente): la IA NO genera contenido evergreen a ciegas. En su lugar,
PROPONE una LISTA de ideas; una persona las APRUEBA o las DESCARTA; y solo para las aprobadas
se GENERA el contenido (una pieza `flujo='evergreen'` en el tablero). Es un pequeño taller de
brainstorming con un humano en el bucle.

RECURSOS:
  - `GET    /api/evergreen/ideas?marca=&estado=`     catálogo de ideas (filtros opcionales).
  - `POST   /api/evergreen/ideas`                    crea una idea MANUAL {marca, titulo, descripcion}.
  - `PATCH  /api/evergreen/ideas/{id}`               cambia estado (aprobar/descartar) y/o edita texto.
  - `DELETE /api/evergreen/ideas/{id}`               borra una idea.
  - `POST   /api/evergreen/proponer`                 {marca, contexto?} lanza la generación de IDEAS
                                                 (IA): crea las filas como `propuesta`/`ia` cuando
                                                 el job completa (en el worker).
  - `POST   /api/evergreen/ideas/{id}/generar`       SOLO si `estado='aprobada'`: crea una pieza
                                                 `flujo='evergreen'` en el tablero y lanza su copy;
                                                 guarda `publicacion_id` en la idea.

SEGURIDAD / VALIDACION:
  - Multiusuario via middleware (sesión o token), igual que el resto del tablero.
  - `marca` SIEMPRE del catálogo único (`consola.marcas`); `estado` de la allowlist
    (`estados.ESTADOS_EVERGREEN_IDEA`). Nada se confía del cliente; SQL parametrizado en `repos`/`db`.
  - La generación corre en SEGUNDO PLANO con el lanzador neutro (`claude -p` encolado); el
    frontend sondea `GET /api/generaciones/{id}`.
"""

from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, marcas, permisos, redes, repos
from .._http_json import leer_json
from ..dominio import idear as dom_idear
from ..dominio import generar as gen_dom
from ..dominio import stream
from ..estados import (
    ESTADO_EVERGREEN_APROBADA,
    ESTADO_EVERGREEN_GENERADA,
    ESTADO_EVERGREEN_PROPUESTA,
    ESTADOS_EVERGREEN_IDEA,
    FLUJO_EVERGREEN,
    ORIGENES_EVERGREEN_IDEA_MANUAL,
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


def _listar(marca: str | None, estado: str | None, preferentes: set[str] | None) -> dict:
    ideas = repos.listar_evergreen_ideas(marca=marca, estado=estado)
    # FOCO POR DEFECTO (no es restriccion): sin marca explicita, el taller se ENFOCA en las
    # marcas preferentes de la sesion. Sobreescribible con `?marca=` (cualquiera). Sin
    # preferencia (admin/token/sin marcas) ve todo. Post-filtro en memoria.
    if preferentes is not None:
        ideas = [i for i in ideas if not i.get("marca") or i.get("marca") in preferentes]
    return {
        "ideas": [_idea_a_dict(i) for i in ideas],
        "estados": list(ESTADOS_EVERGREEN_IDEA),
        "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
    }


async def listar(request: Request) -> Response:
    """GET /api/evergreen/ideas: catálogo de ideas evergreen. Filtros: `marca`, `estado`."""
    q = request.query_params
    estado = q.get("estado") or None
    if estado is not None and estado not in ESTADOS_EVERGREEN_IDEA:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)
    marca = q.get("marca") or None
    # Las preferentes solo aplican sin marca explícita; con marca, no se filtra (None).
    preferentes = None if marca else permisos.marcas_preferentes(request)
    return JSONResponse(await run_in_threadpool(_listar, marca, estado, preferentes))


async def crear(request: Request) -> Response:
    """POST /api/evergreen/ideas: crea una idea MANUAL `{marca, titulo, descripcion?, origen?}` -> `{idea}`.

    Nace en estado `propuesta` (igual que una idea de la IA: hay que aprobarla antes de generar
    nada). `origen` distingue la aportación dentro del MISMO banco: `manual` (alta rápida), `idea`
    ("Idea del equipo") o `interna` ("Interno AMX"). Por defecto `manual`; `ia` no es válido aquí
    (la IA tiene su propio camino, `proponer`).
    """
    datos = await leer_json(request)
    marca, error = _validar_marca(datos.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "La idea necesita un título."}, status_code=400)
    descripcion = datos.get("descripcion")
    descripcion = descripcion.strip()[:_MAX_DESCRIPCION] if isinstance(descripcion, str) else ""
    origen = datos.get("origen") or "manual"
    if origen not in ORIGENES_EVERGREEN_IDEA_MANUAL:
        return JSONResponse({"error": "Origen de aportación no permitido."}, status_code=400)

    return JSONResponse(
        await run_in_threadpool(
            _crear,
            marca=marca,
            titulo=titulo.strip()[:_MAX_TITULO],
            descripcion=descripcion,
            origen=origen,
        )
    )


def _crear(*, marca: str, titulo: str, descripcion: str, origen: str) -> dict:
    idea = repos.crear_evergreen_idea(
        marca=marca,
        titulo=titulo,
        descripcion=descripcion,
        estado=ESTADO_EVERGREEN_PROPUESTA,
        origen=origen,
    )
    return {"idea": _idea_a_dict(idea)}


async def actualizar(request: Request) -> Response:
    """PATCH /api/evergreen/ideas/{id}: cambia `estado` (aprobar/descartar) y/o edita texto.

    `estado` debe ser de la allowlist. `titulo`/`descripcion` son opcionales (edición). 404 si
    la idea ya no existe.
    """
    idea_id = request.path_params["idea_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_actualizar, idea_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _actualizar(idea_id: str, datos: dict) -> tuple[int, dict]:
    idea_actual = repos.obtener_evergreen_idea(idea_id)
    if idea_actual is None:
        return 404, {"error": "Esa idea ya no existe."}
    campos: dict[str, Any] = {}

    if "estado" in datos:
        estado = datos.get("estado")
        if estado not in ESTADOS_EVERGREEN_IDEA:
            return 400, {"error": "Estado no permitido."}
        campos["estado"] = estado
    if "titulo" in datos:
        titulo = datos.get("titulo")
        if not isinstance(titulo, str) or not titulo.strip():
            return 400, {"error": "El título no puede quedar vacío."}
        campos["titulo"] = titulo.strip()[:_MAX_TITULO]
    if "descripcion" in datos:
        descripcion = datos.get("descripcion")
        campos["descripcion"] = (
            descripcion.strip()[:_MAX_DESCRIPCION] if isinstance(descripcion, str) else ""
        )

    if not campos:
        return 400, {"error": "Indica algún campo a actualizar."}

    idea = repos.actualizar_evergreen_idea(idea_id, campos)
    if idea is None:
        return 404, {"error": "Esa idea ya no existe."}
    return 200, {"idea": _idea_a_dict(idea)}


def _borrar(idea_id: str) -> tuple[int, dict]:
    idea = repos.obtener_evergreen_idea(idea_id)
    if idea is None:
        return 404, {"error": "Esa idea ya no existe."}
    if not repos.borrar_evergreen_idea(idea_id):
        return 404, {"error": "Esa idea ya no existe."}
    return 200, {"mensaje": "Idea borrada."}


async def borrar(request: Request) -> Response:
    """DELETE /api/evergreen/ideas/{id}: borra la idea (no toca la pieza generada, si la hubiera)."""
    idea_id = request.path_params["idea_id"]
    status, cuerpo = await run_in_threadpool(_borrar, idea_id)
    return JSONResponse(cuerpo, status_code=status)


async def proponer(request: Request) -> Response:
    """POST /api/evergreen/proponer `{marca, contexto?}` -> `{generacion}` (tipo "evergreen-ideas").

    Lanza una generación de IDEAS evergreen EN SEGUNDO PLANO. El frontend sondea
    `GET /api/generaciones/{id}`; al completarse, el worker habrá creado las filas `evergreen_ideas`
    en estado `propuesta`, origen `ia`. NO genera contenido (eso es `generar`, al aprobar).
    """
    datos = await leer_json(request)
    marca, error = _validar_marca(datos.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    contexto = datos.get("contexto")
    contexto = contexto.strip()[:_MAX_CONTEXTO] if isinstance(contexto, str) else ""

    autor = autor_de_peticion(request)
    return JSONResponse(await run_in_threadpool(_proponer, marca, contexto, autor))


def _proponer(marca: str, contexto: str, autor: dict[str, str] | None) -> dict:
    # `proponer` no crea NADA antes de encolar (solo valida): deja propagar `ColaLlenaError`
    # al manejador CENTRAL (`_manejar_cola_llena`), que responde 429 + `Retry-After` consistente.
    # No la atrapamos aquí (no hay efecto que limpiar, a diferencia de `generar_pieza`).
    gen = dom_idear.lanzar_propuesta(marca=marca, contexto=contexto, autor=autor)
    return {"generacion": gen}


async def generar_pieza(request: Request) -> Response:
    """POST /api/evergreen/ideas/{id}/generar -> `{idea, generacion}`.

    SOLO si la idea está `aprobada`: crea una pieza `flujo='evergreen'` en el tablero
    (`repos.crear_publicacion`), lanza su copy con el lanzador existente (`generar.lanzar_copy`,
    EN SEGUNDO PLANO) anidado bajo esa pieza, y guarda el `publicacion_id` en la idea. Opcional:
    `{redes:[..]}` para acotar las redes del copy (por defecto, todas las canónicas).
    """
    idea_id = request.path_params["idea_id"]
    datos = await leer_json(request)
    crudas = datos.get("redes")
    redes_ids = stream.normalizar_redes(
        crudas if isinstance(crudas, list) else None, canonicas=redes.ids()
    )
    autor = autor_de_peticion(request)
    status, cuerpo = await run_in_threadpool(_generar_pieza, idea_id, redes_ids, autor)
    return JSONResponse(cuerpo, status_code=status)


def _generar_pieza(
    idea_id: str, redes_ids: list[str], autor: dict[str, str] | None
) -> tuple[int, dict]:
    idea = repos.obtener_evergreen_idea(idea_id)
    if idea is None:
        return 404, {"error": "Esa idea ya no existe."}
    if idea["estado"] != ESTADO_EVERGREEN_APROBADA:
        return 400, {"error": "Solo se puede generar contenido de una idea aprobada."}
    if not gen_dom.marca_valida(idea["marca"]):
        return 400, {"error": "Marca no permitida."}

    titulo = idea["titulo"]
    descripcion = idea.get("descripcion", "")
    # La nota de la pieza es la idea aprobada (título + descripción): es el material a redactar.
    nota = "\n\n".join(p for p in (titulo, descripcion) if p)[: gen_dom.MAX_TEXTO]

    # Pieza padre del tablero: evergreen, origen "evergreen" (taller de brainstorming).
    contenido = repos.crear_publicacion(
        clase="contenido",
        flujo=FLUJO_EVERGREEN,
        titulo=titulo,
        descripcion=descripcion,
        marca=idea["marca"],
        origen="evergreen",
        autor=autor,
    )

    try:
        gen = gen_dom.lanzar_copy(
            tipo="evergreen",
            origen_historial="brainstorming-evergreen",
            marca=idea["marca"],
            contexto=nota,
            redes_ids=redes_ids,
            titulo=titulo,
            titulo_dado=titulo,
            texto_base=nota,
            autor=autor,
            publicacion_id=contenido["id"],
        )
    except generaciones.ColaLlenaError:
        return 429, {
            "error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos."
        }

    # TERMINAL feliz: la idea pasa a `generada` (cajón histórico del taller, sin más
    # acciones) y queda enlazada a su pieza. Volver a generarla = duplicar contenido.
    actualizada = repos.actualizar_evergreen_idea(
        idea_id, {"publicacion_id": contenido["id"], "estado": ESTADO_EVERGREEN_GENERADA}
    )
    return 200, {"idea": _idea_a_dict(actualizada or idea), "generacion": gen}


RUTAS = [
    Route("/api/evergreen/ideas", listar, methods=["GET"]),
    Route("/api/evergreen/ideas", crear, methods=["POST"]),
    Route("/api/evergreen/ideas/{idea_id}", actualizar, methods=["PATCH"]),
    Route("/api/evergreen/ideas/{idea_id}", borrar, methods=["DELETE"]),
    Route("/api/evergreen/proponer", proponer, methods=["POST"]),
    Route("/api/evergreen/ideas/{idea_id}/generar", generar_pieza, methods=["POST"]),
]
