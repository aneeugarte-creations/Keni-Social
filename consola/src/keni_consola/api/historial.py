"""API HISTORIAL de generaciones: listado, detalle y "guardar como publicación".

El historial es el registro DURADERO de las generaciones de copy/documento (lo escribe el
post-procesado vía `repos.registrar_historial_prompt`). Lo consumen TODAS las generaciones
(copy, termómetro, QA…), por eso vive en su propio módulo NEUTRO.

  - `GET  /api/prompts/historial`               -> listado (metadatos + preview).
  - `GET  /api/prompts/historial/{id}`          -> detalle (resultado completo).
  - `POST /api/prompts/historial/{id}/guardar`  -> crea publicaciones (borradores) desde la
                                                  entrada (una por pieza, o una con `red`).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import envoltura_paginacion, leer_json
from ..dominio import copy as dom_copy
from ..dominio import publicaciones as dom_publicaciones
from ..dominio import stream
from ..seguridad import autor_de_peticion

# Longitud del preview del resultado en el listado (chars).
_PREVIEW_CHARS = 140

# Paginacion del listado: el historial guarda el RESULTADO COMPLETO por entrada, asi que
# devolverlo entero crece sin tope. Acotamos por defecto y limitamos el techo por peticion.
_LIMITE_DEFECTO = 50
_LIMITE_MAX = 200


def _paginacion(request: Request) -> tuple[int, int]:
    """`(limite, desplazamiento)` del listado; `limite` por defecto 50, acotado a [1, 200]."""
    qp = request.query_params
    try:
        limite = int(qp.get("limite") or _LIMITE_DEFECTO)
    except (TypeError, ValueError):
        limite = _LIMITE_DEFECTO
    limite = max(1, min(limite, _LIMITE_MAX))
    try:
        desplazamiento = int(qp.get("desplazamiento") or 0)
    except (TypeError, ValueError):
        desplazamiento = 0
    return limite, max(0, desplazamiento)

# Mapa id->nombre de marca (catálogo único) para enriquecer el listado.
_MARCA_NOMBRE: dict[str, str] = dict(marcas.opciones())


def _preview(resultado: str) -> str:
    """Primeros ~140 chars del resultado para el listado del historial."""
    resultado = (resultado or "").strip()
    if len(resultado) <= _PREVIEW_CHARS:
        return resultado
    return resultado[:_PREVIEW_CHARS].rstrip() + "…"


def _nombre(prompt_id: str) -> str:
    """Nombre legible de la generación de origen (sin catálogo: prettify del id)."""
    return (prompt_id or "").replace("-", " ").strip().capitalize() or prompt_id


# DEPRECADO(consolidación): el listado del historial ya no lo consume ninguna página del
# front (la actividad de IA se mira en /api/pipelines y el Monitor); se elimina en fase 4.
# OJO: POST /api/prompts/historial/{id}/guardar SÍ se usa y NO está deprecado.
async def historial(request: Request) -> Response:
    """`GET /api/prompts/historial` -> listado (metadatos + preview), recientes primero.

    Paginado (`?limite=&desplazamiento=`): cada entrada lleva el resultado completo, asi que
    sin tope la respuesta crece sin limite. Por defecto se devuelven las 50 mas recientes
    (`limite` acotado a 200). Envelope RETROCOMPATIBLE: mantiene la clave `historial` y AÑADE
    `paginacion:{total, limite, desplazamiento}`.
    """
    limite, desplazamiento = _paginacion(request)
    entradas = repos.listar_historial_prompts(limite=limite, desplazamiento=desplazamiento)
    total = repos.contar_historial_prompts()
    salida = [
        {
            "id": e["id"],
            "prompt": e["prompt"],
            "prompt_nombre": _nombre(e["prompt"]),
            "marca": e["marca"],
            "marca_nombre": _MARCA_NOMBRE.get(e["marca"], e["marca"]),
            "fecha": e["fecha"],
            "titulo": e["titulo"],
            "preview": _preview(e["resultado"]),
            "piezas": e["piezas"],
            "metricas": e.get("metricas"),
            "autor_id": e.get("autor_id", "") or "",
            "autor_nombre": e.get("autor_nombre", "") or "",
        }
        for e in entradas
    ]
    return JSONResponse(
        {
            "historial": salida,
            "paginacion": envoltura_paginacion(total, limite, desplazamiento),
        }
    )


# DEPRECADO(consolidación): el detalle del historial ya no lo consume ninguna página del
# front; se elimina en fase 4 junto al listado de arriba.
async def historial_detalle(request: Request) -> Response:
    """`GET /api/prompts/historial/{id}` -> detalle con el resultado completo (404)."""
    entrada = repos.obtener_historial_prompt(request.path_params["historial_id"])
    if entrada is None:
        return JSONResponse({"error": "No se encontró ese borrador en el historial."}, status_code=404)
    return JSONResponse(
        {
            "id": entrada["id"],
            "prompt": entrada["prompt"],
            "marca": entrada["marca"],
            "fecha": entrada["fecha"],
            "titulo": entrada["titulo"],
            "resultado": entrada["resultado"],
            "piezas": entrada["piezas"],
            "metricas": entrada.get("metricas"),
            "autor_id": entrada.get("autor_id", "") or "",
            "autor_nombre": entrada.get("autor_nombre", "") or "",
        }
    )


def _redes_pedidas(datos: dict[str, object]) -> set[str] | None:
    """Conjunto de redes canónicas pedidas (`redes` plural, o el singular `red` legado).

    Acepta `redes: [...]` (selector multi-red de ResultadoDocumento) y, por compat, el
    `red` singular antiguo (lo trata como una lista de uno). Filtra a redes canónicas y
    descarta lo desconocido. Devuelve `None` si no se indicó ninguna (sin filtro).
    """
    crudas = datos.get("redes")
    if not isinstance(crudas, list):
        # Compat: el cliente viejo mandaba `red` singular.
        red = datos.get("red")
        crudas = [red] if isinstance(red, str) else []
    pedidas = {r for r in crudas if isinstance(r, str) and redes.es_red(r)}
    return pedidas or None


def _revertir(ids: list[str]) -> None:
    """Borra las publicaciones ya creadas (rollback best-effort de un guardado a medias).

    Sin transacción cross-fila en la capa de datos (cada borrador se persiste por su
    cuenta): si la creación de una pieza falla a mitad, deshacemos las anteriores para no
    dejar publicaciones rotas/huérfanas. Tolerante: un borrado que falle no relanza.
    """
    for pid in ids:
        try:
            repos.borrar_publicacion(pid)
        except Exception:  # noqa: BLE001 -- el rollback nunca debe enmascarar el error original
            continue


async def historial_guardar(request: Request) -> Response:
    """`POST /api/prompts/historial/{id}/guardar` -> crea publicaciones (borradores).

    Con piezas: UNA publicación (borrador) por pieza, acotadas a las `redes` pedidas
    (selector multi-red). Sin piezas (entradas antiguas): requiere `red`/`redes` ∈ redes
    canónicas y mete el documento entero en un borrador por red. 404 si la entrada no
    existe; 400 si no hay ninguna red válida o si las pedidas no casan ninguna pieza.

    Garantía TODO-O-NADA: si la creación de alguna pieza falla a mitad, se revierten las
    ya creadas (no quedan publicaciones rotas) y se devuelve un 500 en español.
    """
    historial_id = request.path_params["historial_id"]
    entrada = repos.obtener_historial_prompt(historial_id)
    if entrada is None:
        return JSONResponse({"error": "No se encontró ese borrador en el historial."}, status_code=404)

    datos = await leer_json(request)
    if not isinstance(datos, dict):
        datos = {}
    titulo_dado = datos.get("titulo")
    titulo_dado = titulo_dado.strip() if isinstance(titulo_dado, str) else ""
    redes_filtro = _redes_pedidas(datos)

    marca = entrada["marca"]
    verdicto = stream.derivar_verdicto(entrada["resultado"])
    titulo = titulo_dado or entrada["titulo"] or stream.derivar_titulo(entrada["resultado"])
    piezas = entrada["piezas"]
    autor = autor_de_peticion(request)

    if piezas:
        # Sin redes pedidas no creamos nada (evita inundar el tablero con todas las redes
        # de golpe): el usuario debe elegir al menos una en el selector.
        if redes_filtro is None:
            return JSONResponse(
                {"error": "Elige al menos una red para guardar el termómetro como publicación."},
                status_code=400,
            )
        # ¿Alguna pieza casa con las redes pedidas? Si no, avisamos en vez de devolver vacío.
        redes_piezas = {p.get("red") for p in piezas if isinstance(p, dict)}
        if not (redes_filtro & redes_piezas):
            return JSONResponse(
                {"error": "Ninguna de las redes elegidas tiene contenido en este termómetro."},
                status_code=400,
            )
        try:
            publicaciones = dom_copy.crear_publicaciones_desde_piezas(
                piezas, marca=marca, titulo=titulo, verdicto=verdicto, origen=historial_id,
                redes_filtro=redes_filtro, autor=autor, atomico=True,
            )
        except Exception:  # noqa: BLE001 -- creación a medias: ya revirtió; error en español
            return JSONResponse(
                {"error": "No se pudieron guardar todas las publicaciones; no se guardó ninguna."},
                status_code=500,
            )
        return JSONResponse({"publicaciones": publicaciones})

    # Entrada antigua sin piezas: requiere red(es) explícitas; el documento entero va a cada una.
    if redes_filtro is None:
        return JSONResponse(
            {"error": "Indica la red para guardar este borrador como publicación."}, status_code=400
        )
    creadas: list[dict[str, object]] = []
    try:
        for red in sorted(redes_filtro):
            pub = dom_publicaciones.crear_borrador(
                marca, red, titulo=titulo, contenido=entrada["resultado"], veredicto=verdicto,
                origen=historial_id, autor=autor,
            )
            creadas.append(pub)
    except Exception:  # noqa: BLE001 -- guardado a medias: revierte y error en español
        _revertir([str(p.get("id")) for p in creadas if p.get("id")])
        return JSONResponse(
            {"error": "No se pudieron guardar todas las publicaciones; no se guardó ninguna."},
            status_code=500,
        )
    return JSONResponse({"publicaciones": creadas})


RUTAS = [
    Route("/api/prompts/historial", historial, methods=["GET"]),
    Route("/api/prompts/historial/{historial_id}/guardar", historial_guardar, methods=["POST"]),
    Route("/api/prompts/historial/{historial_id}", historial_detalle, methods=["GET"]),
]
