"""Handlers de las filas por plataforma de un contenido (una fila por red).

Cada contenido publicable lleva N filas `pieza` con su propio estado y
checklist. Aquí viven el alta/edición/baja de una fila y la adaptación determinista de
una imagen por red.

CONCURRENCIA: los handlers son `async` pero el acceso a Postgres (`repos`) es síncrono;
el trabajo de BD de cada petición va en `run_in_threadpool` (un helper síncrono por
petición) para no bloquear el event loop.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...db_publicacion import ConflictoVersion
from ._comun import (
    _MAX_TEXTO,
    ESTADOS_PIEZA,
    _plataforma_a_dict,
    _red_nombre,
    _red_valida,
    estudio_imagen,
    eventos,
    leer_json,
    marcas,
    repos,
)


def _agregar_plataforma(publicacion_id: str, datos: dict) -> tuple[int, dict]:
    if repos.obtener_publicacion(publicacion_id) is None:
        return 404, {"error": "Ese contenido ya no existe."}
    red = datos.get("red")
    if not isinstance(red, str) or not _red_valida(red):
        return 400, {"error": "Red no válida."}
    plat = repos.crear_pieza_fila(publicacion_id=publicacion_id, red=red)
    return 200, {"plataforma": _plataforma_a_dict(plat)}


async def agregar_plataforma(request: Request) -> Response:
    """POST /api/publicaciones/{id}/plataformas: anade una fila por red al contenido."""
    publicacion_id = request.path_params["publicacion_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_agregar_plataforma, publicacion_id, datos)
    return JSONResponse(cuerpo, status_code=status)


# Estado de plataforma -> evento interno que se emite al ENTRAR en ese estado.
# `pieza.aprobada` NO está aquí: ya no hay estado de reposo `aprobado`; ese evento lo emite el
# flujo de aprobación (`api.aprobacion`) cuando la cadena junta sus 2 OK.
_EVENTO_POR_ESTADO: dict[str, str] = {
    "publicado": "pieza.publicada",
}


def _actualizar_plataforma(pieza_id: str, datos: dict) -> tuple[int, dict]:
    previa = repos.obtener_pieza_fila(pieza_id)
    if previa is None:
        return 404, {"error": "Esa plataforma ya no existe."}
    # Estado ANTERIOR (para emitir el evento solo en la TRANSICION, no en cada PATCH).
    estado_anterior = previa.get("estado")
    campos: dict[str, object] = {}

    if "estado" in datos:
        if datos["estado"] not in ESTADOS_PIEZA:
            return 400, {"error": "Estado de plataforma inválido."}
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
        return 400, {"error": "Indica algún campo a actualizar."}

    # CONCURRENCIA OPTIMISTA (ADR 0012): `version` opcional del cliente -> 409 si está obsoleta.
    version_esperada = datos.get("version")
    version_esperada = int(version_esperada) if isinstance(version_esperada, int) else None

    try:
        plat = repos.actualizar_pieza_fila(
            pieza_id, campos, version_esperada=version_esperada
        )
    except ConflictoVersion:
        return 409, {"error": "La pieza cambió mientras la editabas; recárgala."}
    if plat is None:
        return 404, {"error": "Esa plataforma ya no existe."}

    nuevo_estado = plat.get("estado")
    tipo_evento = _EVENTO_POR_ESTADO.get(nuevo_estado or "")
    if tipo_evento is not None and nuevo_estado != estado_anterior:
        padre = repos.obtener_publicacion(plat.get("publicacion_id", "")) or {}
        eventos.emitir(
            tipo_evento,
            {
                "publicacion_id": plat.get("publicacion_id", ""),
                "pieza_id": pieza_id,
                "red": plat.get("red", ""),
                "red_nombre": _red_nombre(plat.get("red", "")),
                "titulo": padre.get("titulo", ""),
                "marca": padre.get("marca", ""),
                "marca_nombre": marcas.etiqueta_de(padre["marca"]) if padre.get("marca") else "",
                "estado": nuevo_estado,
            },
            publicacion_id=plat.get("publicacion_id", ""),
            pieza_id=pieza_id,
        )
    return 200, {"plataforma": _plataforma_a_dict(plat)}


async def actualizar_plataforma(request: Request) -> Response:
    """PATCH /api/publicaciones/{id}/plataformas/{pieza_id}: estado/checklist/copy/...."""
    pieza_id = request.path_params["pieza_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_actualizar_plataforma, pieza_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _adaptar_imagen(publicacion_id: str, datos: dict) -> tuple[int, dict]:
    item = repos.obtener_publicacion(publicacion_id)
    if item is None:
        return 404, {"error": "Esa pieza ya no existe."}

    imagen = datos.get("imagen")
    if not isinstance(imagen, str) or not imagen.strip():
        return 400, {"error": "Falta la imagen a adaptar."}
    imagen = imagen.strip()

    plataformas = repos.listar_piezas_fila(publicacion_id)
    if not plataformas:
        return 400, {"error": "La pieza no tiene plataformas a las que adaptar."}

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
        plat2 = repos.actualizar_pieza_fila(plat["id"], {"imagen": res["id"]})
        if plat2 is not None:
            actualizadas.append(_plataforma_a_dict(plat2))

    if not actualizadas:
        return 400, {"error": "No se pudo adaptar la imagen a ninguna red."}

    return 200, {"plataformas": actualizadas, "adaptadas": len(actualizadas)}


async def adaptar_imagen(request: Request) -> Response:
    """POST /api/publicaciones/{publicacion_id}/adaptar-imagen {imagen}.

    Genera una imagen ADAPTADA POR RED de forma DETERMINISTA y la asigna a cada plataforma de
    la pieza: para cada red recorta la `imagen` de origen al formato de esa red (16:9, 1:1,
    9:16...) y, si la marca tiene plantilla visual, la compone tras el marco de marca. Las
    plataformas cuya composición falle se omiten (no abortan el resto).
    -> `{plataformas, adaptadas}` | 400 | 404.
    """
    publicacion_id = request.path_params["publicacion_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_adaptar_imagen, publicacion_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _borrar_plataforma(pieza_id: str) -> tuple[int, dict]:
    if not repos.borrar_pieza_fila(pieza_id):
        return 404, {"error": "Esa plataforma ya no existe."}
    return 200, {"mensaje": "Plataforma borrada."}


async def borrar_plataforma(request: Request) -> Response:
    pieza_id = request.path_params["pieza_id"]
    status, cuerpo = await run_in_threadpool(_borrar_plataforma, pieza_id)
    return JSONResponse(cuerpo, status_code=status)
