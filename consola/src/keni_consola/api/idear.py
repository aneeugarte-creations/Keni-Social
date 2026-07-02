"""API del TALLER EVERGREEN / brainstorming: ideas de contenido EVERGREEN.

CONCEPTO (pedido por el cliente): la IA NO genera contenido evergreen a ciegas. En su lugar,
PROPONE una LISTA de ideas; una persona las APRUEBA o las DESCARTA. Al APROBAR una idea se lanza
una INVESTIGACIÓN con `claude -p` (web) que produce MATERIAL VERIFICADO; al completar nace un TEMA
del pipeline (`origen='pipeline'`, `flujo='evergreen'`, verificación `verificado`) que PRODUCCIÓN
recoge igual que una historia de noticias. Espejo del motor de noticias, con un humano en el bucle.

RECURSOS:
  - `GET    /api/evergreen/ideas?marca=&estado=`     catálogo de ideas (filtros opcionales).
  - `POST   /api/evergreen/ideas`                    crea una idea MANUAL {marca, titulo, descripcion}.
  - `PATCH  /api/evergreen/ideas/{id}`               cambia estado (aprobar/descartar) y/o edita texto.
                                                 Aprobar LANZA la investigación de la idea.
  - `DELETE /api/evergreen/ideas/{id}`               borra una idea.
  - `POST   /api/evergreen/proponer`                 {marca, contexto?} lanza la generación de IDEAS
                                                 (IA): crea las filas como `propuesta`/`ia` cuando
                                                 el job completa (en el worker).

SEGURIDAD / VALIDACION:
  - Multiusuario via middleware (sesión o token), igual que el resto del tablero.
  - `marca` SIEMPRE del catálogo único (`consola.marcas`); `estado` de la allowlist
    (`estados.ESTADOS_EVERGREEN_IDEA`). Nada se confía del cliente; SQL parametrizado en `repos`/`db`.
  - La generación corre en SEGUNDO PLANO con el lanzador neutro (`claude -p` encolado); el
    frontend sondea `GET /api/generaciones/{id}`.
"""

from __future__ import annotations

import logging
from typing import Any

from keni_shared import marcas
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, permisos, repos
from .._http_json import leer_json
from ..dominio import idear as dom_idear
from ..estados import (
    ESTADO_EVERGREEN_APROBADA,
    ESTADO_EVERGREEN_PROPUESTA,
    ESTADOS_EVERGREEN_IDEA,
    ORIGENES_EVERGREEN_IDEA_MANUAL,
)
from ..seguridad import autor_de_peticion

_log = logging.getLogger("keni_consola.idear")

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

    `estado` debe ser de la allowlist. `titulo`/`descripcion` son opcionales (edición). APROBAR
    una idea (transición a `aprobada`) LANZA su investigación con `claude -p`. 404 si la idea ya
    no existe.
    """
    idea_id = request.path_params["idea_id"]
    datos = await leer_json(request)
    autor = autor_de_peticion(request)
    status, cuerpo = await run_in_threadpool(_actualizar, idea_id, datos, autor)
    return JSONResponse(cuerpo, status_code=status)


def _actualizar(idea_id: str, datos: dict, autor: dict[str, str] | None) -> tuple[int, dict]:
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

    # APROBAR = lanzar la investigación. Se lanza cuando el PATCH pone `aprobada` y la idea aún no
    # tiene tema (primera aprobación o REINTENTO tras un fallo). Editar texto sin `estado` no relanza;
    # una idea ya `generada` (con `publicacion_id`) tampoco. Un re-lanzamiento con una investigación
    # en vuelo devuelve ese mismo run (idempotencia por `idea_id`), no arranca otro.
    aprueba_ahora = (
        campos.get("estado") == ESTADO_EVERGREEN_APROBADA
        and not (idea.get("publicacion_id") or "")
    )
    if not aprueba_ahora:
        return 200, {"idea": _idea_a_dict(idea)}

    from ..pipeline_contenido import _investigar_evergreen as inv

    try:
        gen = inv.lanzar_investigar_idea(idea, autor=autor)
    except generaciones.ColaLlenaError:
        return 429, {
            "error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos."
        }
    except Exception:  # noqa: BLE001 -- un fallo al lanzar deja la idea aprobada (reintentable)
        _log.exception("evergreen: no se pudo lanzar la investigación de la idea %s", idea_id)
        return 200, {"idea": _idea_a_dict(idea)}

    if gen is None:
        return 200, {"idea": _idea_a_dict(idea)}
    return 200, {"idea": _idea_a_dict(idea), "generacion": gen}


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
    gen = dom_idear.lanzar_propuesta(marca=marca, contexto=contexto, autor=autor)
    return {"generacion": gen}


RUTAS = [
    Route("/api/evergreen/ideas", listar, methods=["GET"]),
    Route("/api/evergreen/ideas", crear, methods=["POST"]),
    Route("/api/evergreen/ideas/{idea_id}", actualizar, methods=["PATCH"]),
    Route("/api/evergreen/ideas/{idea_id}", borrar, methods=["DELETE"]),
    Route("/api/evergreen/proponer", proponer, methods=["POST"]),
]
