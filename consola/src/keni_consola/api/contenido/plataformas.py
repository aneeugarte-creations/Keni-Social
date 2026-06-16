"""Handlers de las filas por plataforma de un contenido (una fila por red).

Cada contenido publicable lleva N filas `contenido_plataforma` con su propio estado y
checklist. Aquí viven el alta/edición/baja de una fila y la adaptación determinista de
una imagen por red.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...db_contenido import ConflictoVersion
from ._comun import (
    _MAX_TEXTO,
    ESTADOS_CONTENIDO_PLATAFORMA,
    _plataforma_a_dict,
    _red_nombre,
    _red_valida,
    estudio_imagen,
    eventos,
    leer_json,
    marcas,
    repos,
)


async def agregar_plataforma(request: Request) -> Response:
    """POST /api/contenido/{id}/plataformas: anade una fila por red al contenido."""
    contenido_id = request.path_params["contenido_id"]
    item = repos.obtener_contenido(contenido_id)
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    red = datos.get("red")
    if not isinstance(red, str) or not _red_valida(red):
        return JSONResponse({"error": "Red no válida."}, status_code=400)
    plat = repos.crear_contenido_plataforma(contenido_id=contenido_id, red=red)
    return JSONResponse({"plataforma": _plataforma_a_dict(plat)})


# Estado de plataforma -> evento interno que se emite al ENTRAR en ese estado.
_EVENTO_POR_ESTADO: dict[str, str] = {
    "aprobado": "pieza.aprobada",
    "publicado": "pieza.publicada",
}


async def actualizar_plataforma(request: Request) -> Response:
    """PATCH /api/contenido/{id}/plataformas/{plataforma_id}: estado/checklist/copy/...."""
    plataforma_id = request.path_params["plataforma_id"]
    if repos.obtener_contenido_plataforma(plataforma_id) is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "estado" in datos:
        if datos["estado"] not in ESTADOS_CONTENIDO_PLATAFORMA:
            return JSONResponse({"error": "Estado de plataforma inválido."}, status_code=400)
        campos["estado"] = datos["estado"]
    for flag in (
        "falta_copy",
        "falta_imagen",
        "falta_revision",
        "falta_publicar",
        "falta_video",
        "evergreen",
        "copy_in_exento",
    ):
        if flag in datos:
            campos[flag] = bool(datos[flag])
    for clave in (
        "copy",
        "imagen",
        "imagen_fuente",
        "foto",
        "video",
        "enlace",
        "fecha_programada",
        "hora_post",
        "revision",
    ):
        if clave in datos:
            v = datos.get(clave)
            campos[clave] = v.strip()[:_MAX_TEXTO] if isinstance(v, str) else ""
    # Adjuntar VIDEO limpia el checklist `falta_video` (espejo de cómo `imagen` limpia
    # `falta_imagen`): si el cliente fija un asset de video y no envía el flag explícito,
    # marcamos el paso de video como cubierto.
    if campos.get("video") and "falta_video" not in datos:
        campos["falta_video"] = False

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)

    # Estado ANTERIOR (para emitir el evento solo en la TRANSICION, no en cada PATCH).
    previa = repos.obtener_contenido_plataforma(plataforma_id)
    estado_anterior = previa.get("estado") if previa else None

    # CONCURRENCIA OPTIMISTA (ADR 0012): `version` opcional del cliente -> 409 si está obsoleta.
    version_esperada = datos.get("version")
    version_esperada = int(version_esperada) if isinstance(version_esperada, int) else None

    try:
        plat = repos.actualizar_contenido_plataforma(
            plataforma_id, campos, version_esperada=version_esperada
        )
    except ConflictoVersion:
        return JSONResponse(
            {"error": "La pieza cambió mientras la editabas; recárgala."}, status_code=409
        )
    if plat is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)

    nuevo_estado = plat.get("estado")
    tipo_evento = _EVENTO_POR_ESTADO.get(nuevo_estado or "")
    if tipo_evento is not None and nuevo_estado != estado_anterior:
        padre = repos.obtener_contenido(plat.get("contenido_id", "")) or {}
        eventos.emitir(
            tipo_evento,
            {
                "contenido_id": plat.get("contenido_id", ""),
                "plataforma_id": plataforma_id,
                "red": plat.get("red", ""),
                "red_nombre": _red_nombre(plat.get("red", "")),
                "titulo": padre.get("titulo", ""),
                "marca": padre.get("marca", ""),
                "marca_nombre": marcas.etiqueta_de(padre["marca"]) if padre.get("marca") else "",
                "estado": nuevo_estado,
            },
            contenido_id=plat.get("contenido_id", ""),
            plataforma_id=plataforma_id,
        )
    return JSONResponse({"plataforma": _plataforma_a_dict(plat)})


async def adaptar_imagen(request: Request) -> Response:
    """POST /api/contenido/{contenido_id}/adaptar-imagen {imagen}.

    Genera una imagen ADAPTADA POR RED de forma DETERMINISTA y la asigna a cada plataforma de
    la pieza: para cada red recorta la `imagen` de origen al formato de esa red (16:9, 1:1,
    9:16...) y, si la marca tiene plantilla visual, la compone tras el marco de marca. Las
    plataformas cuya composición falle se omiten (no abortan el resto).
    -> `{plataformas, adaptadas}` | 400 | 404.
    """
    contenido_id = request.path_params["contenido_id"]
    item = repos.obtener_contenido(contenido_id)
    if item is None:
        return JSONResponse({"error": "Esa pieza ya no existe."}, status_code=404)

    datos = await leer_json(request)
    imagen = datos.get("imagen")
    if not isinstance(imagen, str) or not imagen.strip():
        return JSONResponse({"error": "Falta la imagen a adaptar."}, status_code=400)
    imagen = imagen.strip()

    plataformas = repos.listar_contenido_plataforma(contenido_id)
    if not plataformas:
        return JSONResponse(
            {"error": "La pieza no tiene plataformas a las que adaptar."}, status_code=400
        )

    marca = item.get("marca") or ""
    con_plantilla = estudio_imagen.marca_tiene_plantilla(marca)

    actualizadas: list[dict] = []
    for plat in plataformas:
        formato = estudio_imagen.formato_por_red(plat.get("red", ""))
        try:
            if con_plantilla:
                res = estudio_imagen.componer(imagen, marca=marca, formato=formato)
            else:
                res = estudio_imagen.editar(imagen, "recortar", {"formato": formato})
        except estudio_imagen.EstudioError:
            continue
        plat2 = repos.actualizar_contenido_plataforma(plat["id"], {"imagen": res["id"]})
        if plat2 is not None:
            actualizadas.append(_plataforma_a_dict(plat2))

    if not actualizadas:
        return JSONResponse(
            {"error": "No se pudo adaptar la imagen a ninguna red."}, status_code=400
        )

    return JSONResponse({"plataformas": actualizadas, "adaptadas": len(actualizadas)})


async def borrar_plataforma(request: Request) -> Response:
    plataforma_id = request.path_params["plataforma_id"]
    if not repos.borrar_contenido_plataforma(plataforma_id):
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Plataforma borrada."})
