"""Handlers de copy asistido por IA del tablero.

  - `previsualizar`: expande las variables `{...}` (placeholders) de un texto.
  - `asistente_ia`: lanza el asistente IA (generar/variantes/resumir) sobre un contenido.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import (
    _MAX_TEXTO,
    asistente,
    autor_de_peticion,
    leer_json,
    marcas,
    placeholders,
    redes,
    repos,
)


async def previsualizar(request: Request) -> Response:
    """POST /api/publicaciones/{id}/preview: expande las variables `{...}` de un texto.

    Cuerpo JSON `{texto}`: devuelve `{preview}` con `{marca}`/`{fecha}`/`{hashtags}`/...
    ya sustituidas usando el contexto del contenido (marca, titulo, programa). Es la
    previsualizacion por plataforma del copy (no persiste nada). `{...}` desconocidas se
    dejan literales. 404 si el contenido no existe.
    """
    publicacion_id = request.path_params["publicacion_id"]
    item = repos.obtener_publicacion(publicacion_id)
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    texto = datos.get("texto")
    if not isinstance(texto, str):
        texto = ""
    preview = placeholders.expandir_para_contenido(texto[:_MAX_TEXTO], item)
    return JSONResponse({"preview": preview})


async def asistente_ia(request: Request) -> Response:
    """POST /api/publicaciones/{id}/asistente: lanza el asistente IA sobre un contenido.

    Cuerpo JSON `{modo, redes?}` (`modo` ∈ generar|variantes|resumir). Reutiliza el prompt
    de copy y la pipeline de generacion: arma el brief del contenido (titulo+descripcion+
    notas), lanza un trabajo en segundo plano y responde `{generacion}` (estado
    "ejecutando"). El frontend sondea `GET /api/generaciones/{id}` y, al completarse, lee
    `resultado.piezas` para rellenar el `copy` de cada fila `pieza`.

    Requiere que el contenido tenga MARCA (la voz de marca es el insumo del prompt) y al
    menos una red CANONICA en sus plataformas (el canal "web" no entra en los prompts de
    copy). Si faltan, responde 400 con un mensaje en espanol.
    """
    publicacion_id = request.path_params["publicacion_id"]
    item = repos.obtener_publicacion(publicacion_id)
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)

    marca = item.get("marca", "") or ""
    if not marca or not marcas.es_marca(marca):
        return JSONResponse(
            {"error": "Asigna una marca al contenido para usar el asistente."},
            status_code=400,
        )
    datos = await leer_json(request)
    modo = datos.get("modo", "generar")
    if modo not in asistente.MODOS:
        return JSONResponse({"error": "Modo de asistente no válido."}, status_code=400)

    # Redes del cuerpo (si llegan) o, por defecto, las redes CANONICAS del contenido. El
    # canal "web" se descarta (las skills de copy trabajan sobre redes sociales).
    crudas = datos.get("redes")
    if isinstance(crudas, list):
        pedidas = [r for r in crudas if isinstance(r, str) and redes.es_red(r)]
    else:
        pedidas = [p["red"] for p in repos.listar_piezas_fila(publicacion_id) if redes.es_red(p["red"])]
    redes_ids = [r for r in redes.ids() if r in set(pedidas)]
    if not redes_ids:
        return JSONResponse(
            {"error": "Añade al menos una red social al contenido para generar copy."},
            status_code=400,
        )

    # Defensa en profundidad contra token-flooding del prompt: aunque estos campos se
    # guardan ya recortados a `_MAX_TEXTO` al escribir el contenido, se vuelve a truncar
    # aqui (mismo limite) antes de armar el brief del asistente, por si el almacen trajera
    # un valor mas largo.
    gen = asistente.lanzar(
        modo=modo,
        marca=marca,
        titulo=(item.get("titulo", "") or "")[:_MAX_TEXTO],
        descripcion=(item.get("descripcion", "") or "")[:_MAX_TEXTO],
        notas=(item.get("notas", "") or "")[:_MAX_TEXTO],
        redes_ids=redes_ids,
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"generacion": gen})
