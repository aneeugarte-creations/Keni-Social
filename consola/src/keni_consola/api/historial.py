"""API HISTORIAL de generaciones: "guardar como publicación".

El historial es el registro DURADERO de las generaciones de copy/documento (lo escribe el
post-procesado vía `repos.registrar_historial_prompt`). Lo consumen TODAS las generaciones
(copy, termómetro, verificación…), por eso vive en su propio módulo NEUTRO.

  - `POST /api/prompts/historial/{id}/guardar`  -> crea publicaciones (borradores) desde la
                                                  entrada (una por pieza, o una con `red`).

(El listado y el detalle del historial por HTTP se retiraron en la consolidación: la
actividad de IA se mira en `/api/pipelines` y el Monitor; el registro se sigue leyendo
desde el dominio vía `repos`.)
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import redes, repos
from .._http_json import leer_json
from ..dominio import copy as dom_copy
from ..dominio import publicaciones as dom_publicaciones
from ..dominio import stream
from ..seguridad import autor_de_peticion


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
    dejar publicaciones rotas/sueltas. Tolerante: un borrado que falle no relanza.
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
                marca, red, titulo=titulo, contenido=entrada["resultado"], revision=verdicto,
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
    Route("/api/prompts/historial/{historial_id}/guardar", historial_guardar, methods=["POST"]),
]
