"""Generación de copy A DEMANDA de un tema del tablero (botón «Generar» del feed Portal).

El canal Portal (con `KENI_PORTAL_COPY_AUTO` apagado, el default) crea sus temas con una pieza
MECÁNICA (foto del artículo + titular como copy-in) y CERO IA. Este endpoint es el único camino
que lanza su copy: una PERSONA pulsa «Generar» en la tarjeta y se encola la generación NORMAL
del pipeline (`pipeline_contenido.lanzar_redactar_de_tema`, los mismos parámetros que CI guardó
en `copy_pendiente`) con prioridad MANUAL. El borrador resultante RELLENA las filas preview del
tema (`dominio.piezas.crear_borrador_en` deposita en la fila vacía de cada red) y a partir de
ahí la pieza fluye como cualquier otra (hashtags encadenados, revisión, aprobación).

Sirve para CUALQUIER tema con `copy_pendiente` (no solo Portal); sin él, cae al lanzador del
news-pool (`autogen_redactar.lanzar_para_topic`), el mismo de usar-noticia/breaking.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...seguridad import autor_de_peticion
from .._guardas import redactar_apagado
from ._comun import autogen_redactar, generaciones, repos


def _generar_copy(publicacion_id: str, autor: dict | None) -> tuple[int, dict]:
    from ... import pipeline_contenido as pc

    tema = repos.obtener_publicacion(publicacion_id)
    if tema is None:
        return 404, {"error": "Ese contenido ya no existe."}
    marca = (tema.get("marca") or "").strip()
    if not marca:
        return 400, {"error": "El tema no tiene marca; no se puede generar copy."}
    # La MISMA guarda que el resto de botones manuales: con «Redactar» apagada para la marca,
    # encolar dejaría un «copy en marcha» mentiroso.
    err = redactar_apagado(marca)
    if err:
        return 409, err
    if pc._tiene_copy(publicacion_id):
        return 409, {"error": "Este tema ya tiene copy generado."}
    try:
        if (tema.get("copy_pendiente") or "").strip():
            gen = pc.lanzar_redactar_de_tema(tema, autor=autor, manual=True)
        else:
            gen = autogen_redactar.lanzar_para_topic(tema, manual=True)
    except generaciones.ColaLlenaError as e:
        return 429, {"error": f"La cola de generación está llena ({e}). Reintenta en un momento."}
    if gen is None:
        return 409, {"error": "No se pudo lanzar la generación de copy para este tema."}
    return 200, {"copy_en_proceso": True, "generacion_id": gen.get("id", "") if isinstance(gen, dict) else ""}


async def generar_copy(request: Request) -> Response:
    """POST /api/publicaciones/{id}/generar-copy: encola el copy del tema (prioridad MANUAL).

    Idempotente frente al doble clic: la clave de idempotencia de `dominio.generar.lanzar`
    devuelve el run en curso si el mismo trabajo ya está corriendo (no hay doble gasto).
    """
    publicacion_id = request.path_params["publicacion_id"]
    autor = autor_de_peticion(request)
    status, cuerpo = await run_in_threadpool(_generar_copy, publicacion_id, autor)
    return JSONResponse(cuerpo, status_code=status)
