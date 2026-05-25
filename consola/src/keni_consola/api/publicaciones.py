"""API Publicaciones: CRUD de posts a gestionar (titulo, marca, red, estado, fechas).

El SPA gestiona el ciclo de vida de cada pieza: nace como borrador (a mano o desde
una generacion por red de Skills), se edita, se aprueba, se programa y se publica.
Persistencia en SQLite (`consola.db`, via `consola.db`). Nada se publica de verdad
aqui: solo se administra el estado editorial.

SEGURIDAD / VALIDACION (no duplica logica; reusa las fuentes de verdad):
  - `marca` SOLO puede ser una marca de la allowlist de Skills (`consola.marcas`,
    las que tienen slug, mismo `value` que usa la generacion de copy).
  - `red` SOLO puede ser una red canonica (`consola.redes`).
  - `estado` SOLO puede ser uno de `db.ESTADOS_PUBLICACION`.
  - SQL parametrizado en `consola.db`; los errores salen como JSON en espanol, sin
    tracebacks crudos.

`marca_nombre` y `red_nombre` se resuelven EN SERVIDOR (la UI solo muestra nombres).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import db, marcas, redes
from .._http_json import leer_json
from . import franjas as api_franjas

# Nombres legibles de los estados (para poblar selects de la UI), en orden de flujo.
_ESTADO_NOMBRE: dict[str, str] = {
    "borrador": "Borrador",
    "aprobado": "Aprobado",
    "programado": "Programado",
    "publicado": "Publicado",
}

# Marcas validas como destino de copy: las de Skills (con slug). value interno=slug.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones_por_slug())
_MARCAS_IDS = {m[0] for m in _MARCAS}


def _publicacion_a_dict(pub: dict[str, Any]) -> dict[str, Any]:
    """Serializa una publicacion resolviendo nombres legibles de marca y red.

    Anade `imagen` (nombre de archivo en el dir de media, o "") y `imagen_url`
    (`/api/media/{imagen}` o "" si no hay imagen) para que la UI la pueda mostrar.
    """
    imagen = pub.get("imagen") or ""
    return {
        "id": pub["id"],
        "titulo": pub["titulo"],
        "marca": pub["marca"],
        "marca_nombre": marcas.etiqueta_por_slug(pub["marca"]),
        "red": pub["red"],
        "red_nombre": redes.nombre_por_id(pub["red"]),
        "contenido": pub["contenido"],
        "estado": pub["estado"],
        "veredicto": pub["veredicto"],
        "fecha_creacion": pub["fecha_creacion"],
        "fecha_actualizacion": pub["fecha_actualizacion"],
        "fecha_programada": pub["fecha_programada"],
        "origen": pub["origen"],
        "imagen": imagen,
        "imagen_url": f"/api/media/{imagen}" if imagen else "",
        "evergreen": bool(pub.get("evergreen")),
    }


def _validar_nueva(datos: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Valida el cuerpo de una publicacion nueva.

    Devuelve `(entrada_normalizada, None)` si es valida, o `(None, mensaje)` con el
    error en espanol. No toca la base; solo valida tipos y allowlists.
    """
    marca = datos.get("marca")
    red = datos.get("red")
    if not isinstance(marca, str) or marca not in _MARCAS_IDS:
        return None, "Marca no permitida."
    if not isinstance(red, str) or not redes.es_red(red):
        return None, "Red no permitida."

    estado = datos.get("estado", "borrador")
    if estado is None or estado == "":
        estado = "borrador"
    if not isinstance(estado, str) or estado not in db.ESTADOS_PUBLICACION:
        return None, "Estado no permitido."

    titulo = datos.get("titulo", "")
    contenido = datos.get("contenido", "")
    veredicto = datos.get("veredicto", "")
    fecha_programada = datos.get("fecha_programada", "")
    origen = datos.get("origen", "")
    imagen = datos.get("imagen", "")
    for valor, etiqueta in (
        (titulo, "El título"),
        (contenido, "El contenido"),
        (veredicto, "El veredicto"),
        (fecha_programada, "La fecha programada"),
        (origen, "El origen"),
        (imagen, "La imagen"),
    ):
        if not isinstance(valor, str):
            return None, f"{etiqueta} debe ser texto."

    return (
        {
            "titulo": titulo.strip(),
            "marca": marca,
            "red": red,
            "contenido": contenido,
            "estado": estado,
            "veredicto": veredicto,
            "fecha_programada": fecha_programada.strip(),
            "origen": origen.strip(),
            "imagen": imagen.strip(),
        },
        None,
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def opciones(request: Request) -> Response:
    """Catalogos para los selects del SPA: redes, estados y marcas."""
    return JSONResponse(
        {
            "redes": redes.opciones(),
            "estados": [{"id": e, "nombre": _ESTADO_NOMBRE[e]} for e in db.ESTADOS_PUBLICACION],
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in _MARCAS],
        }
    )


def _parsear_bool_query(valor: str | None) -> bool | None:
    """Interpreta un parametro de query como bool: '1'/'true' -> True, '0'/'false' -> False.

    Devuelve None si el parametro no viene (sin filtrar). Cualquier otro valor se trata
    como no presente para no filtrar de forma sorpresiva.
    """
    if valor is None:
        return None
    bajo = valor.strip().lower()
    if bajo in ("1", "true", "si", "sí"):
        return True
    if bajo in ("0", "false", "no"):
        return False
    return None


async def listar(request: Request) -> Response:
    """Listado de publicaciones con filtros opcionales `?marca=&red=&estado=&evergreen=`."""
    qp = request.query_params
    marca = qp.get("marca") or None
    red = qp.get("red") or None
    estado = qp.get("estado") or None
    evergreen = _parsear_bool_query(qp.get("evergreen"))
    pubs = db.listar_publicaciones(marca=marca, red=red, estado=estado, evergreen=evergreen)
    return JSONResponse({"publicaciones": [_publicacion_a_dict(p) for p in pubs]})


async def crear(request: Request) -> Response:
    datos = await leer_json(request)
    entrada, error = _validar_nueva(datos)
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    pub = db.crear_publicacion(
        entrada["marca"],
        entrada["red"],
        titulo=entrada["titulo"],
        contenido=entrada["contenido"],
        estado=entrada["estado"],
        veredicto=entrada["veredicto"],
        fecha_programada=entrada["fecha_programada"],
        origen=entrada["origen"],
        imagen=entrada["imagen"],
    )
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


async def crear_lote(request: Request) -> Response:
    """Crea varias publicaciones de una vez. Todo o nada: si una falla, 400 y no inserta."""
    datos = await leer_json(request)
    crudas = datos.get("publicaciones")
    if not isinstance(crudas, list) or not crudas:
        return JSONResponse(
            {"error": "Envía una lista de publicaciones a crear."}, status_code=400
        )
    entradas: list[dict[str, Any]] = []
    for i, cruda in enumerate(crudas, start=1):
        if not isinstance(cruda, dict):
            return JSONResponse(
                {"error": f"La publicación {i} no es válida."}, status_code=400
            )
        entrada, error = _validar_nueva(cruda)
        if error is not None:
            return JSONResponse({"error": f"Publicación {i}: {error}"}, status_code=400)
        entradas.append(entrada)
    pubs = db.crear_publicaciones(entradas)
    return JSONResponse({"publicaciones": [_publicacion_a_dict(p) for p in pubs]})


async def detalle(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    pub = db.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL: titulo/contenido/estado/fecha_programada (404 si no existe)."""
    publicacion_id = request.path_params["publicacion_id"]
    datos = await leer_json(request)

    campos: dict[str, Any] = {}
    if "titulo" in datos:
        titulo = datos.get("titulo")
        if not isinstance(titulo, str):
            return JSONResponse({"error": "El título debe ser texto."}, status_code=400)
        campos["titulo"] = titulo.strip()
    if "contenido" in datos:
        contenido = datos.get("contenido")
        if not isinstance(contenido, str):
            return JSONResponse({"error": "El contenido debe ser texto."}, status_code=400)
        campos["contenido"] = contenido
    if "estado" in datos:
        estado = datos.get("estado")
        if not isinstance(estado, str) or estado not in db.ESTADOS_PUBLICACION:
            return JSONResponse({"error": "Estado no permitido."}, status_code=400)
        campos["estado"] = estado
    if "fecha_programada" in datos:
        fecha = datos.get("fecha_programada")
        if not isinstance(fecha, str):
            return JSONResponse(
                {"error": "La fecha programada debe ser texto."}, status_code=400
            )
        campos["fecha_programada"] = fecha.strip()
    if "imagen" in datos:
        imagen = datos.get("imagen")
        if not isinstance(imagen, str):
            return JSONResponse({"error": "La imagen debe ser texto."}, status_code=400)
        campos["imagen"] = imagen.strip()
    if "evergreen" in datos:
        evergreen = datos.get("evergreen")
        if not isinstance(evergreen, bool):
            return JSONResponse({"error": "El campo evergreen debe ser verdadero o falso."}, status_code=400)
        campos["evergreen"] = evergreen

    if not campos:
        return JSONResponse(
            {
                "error": (
                    "No hay nada que actualizar (título, contenido, estado, fecha, "
                    "imagen o evergreen)."
                )
            },
            status_code=400,
        )

    pub = db.actualizar_publicacion(publicacion_id, campos)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


async def borrar(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    if not db.borrar_publicacion(publicacion_id):
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Publicación borrada."})


def calcular_hueco_para(
    pub: dict[str, Any], ahora: datetime | None = None
) -> str | None:
    """Calcula el proximo hueco futuro para `pub` segun las franjas configuradas.

    Devuelve el datetime ISO ('YYYY-MM-DDTHH:MM') del hueco, o None si no hay NINGUNA
    franja aplicable a la (marca, red) de la publicacion. `ahora` se puede inyectar
    para tests; por defecto es `datetime.now()`. Los huecos ya ocupados por OTRAS
    publicaciones en estado `programado` (su `fecha_programada`) se evitan.
    """
    if ahora is None:
        ahora = datetime.now()
    franjas = db.listar_franjas()
    aplican = api_franjas.franjas_aplicables(franjas, pub["marca"], pub["red"])
    if not aplican:
        return None
    ocupados = {
        otra["fecha_programada"]
        for otra in db.listar_publicaciones(estado="programado")
        if otra["id"] != pub["id"] and otra["fecha_programada"]
    }
    return api_franjas.proximo_hueco(aplican, ahora, ocupados)


async def encolar(request: Request) -> Response:
    """Programa la publicacion en el proximo hueco futuro de sus franjas.

    `POST /api/publicaciones/{id}/encolar` -> `{publicacion}` (estado=programado y
    fecha_programada puesta al hueco). 404 si no existe; 400 si no hay franjas
    aplicables a su (marca, red).
    """
    publicacion_id = request.path_params["publicacion_id"]
    pub = db.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    hueco = calcular_hueco_para(pub)
    if hueco is None:
        return JSONResponse(
            {"error": "No hay franjas configuradas para esta marca/red."}, status_code=400
        )
    actualizada = db.actualizar_publicacion(
        publicacion_id, {"estado": "programado", "fecha_programada": hueco}
    )
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(actualizada)})


async def duplicar(request: Request) -> Response:
    """Duplica una publicacion como borrador, con overrides opcionales.

    `POST /api/publicaciones/{id}/duplicar` con JSON opcional `{red?, marca?, titulo?}`.
    Copia contenido/imagen/veredicto/hashtags; estado=borrador, fecha_programada=''.
    -> `{publicacion}` | 404.
    """
    publicacion_id = request.path_params["publicacion_id"]
    original = db.obtener_publicacion(publicacion_id)
    if original is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    marca = original["marca"]
    red = original["red"]
    titulo = original["titulo"]
    if "marca" in datos:
        nueva_marca = datos.get("marca")
        if not isinstance(nueva_marca, str) or nueva_marca not in _MARCAS_IDS:
            return JSONResponse({"error": "Marca no permitida."}, status_code=400)
        marca = nueva_marca
    if "red" in datos:
        nueva_red = datos.get("red")
        if not isinstance(nueva_red, str) or not redes.es_red(nueva_red):
            return JSONResponse({"error": "Red no permitida."}, status_code=400)
        red = nueva_red
    if "titulo" in datos:
        nuevo_titulo = datos.get("titulo")
        if not isinstance(nuevo_titulo, str):
            return JSONResponse({"error": "El título debe ser texto."}, status_code=400)
        titulo = nuevo_titulo.strip()

    copia = db.crear_publicacion(
        marca,
        red,
        titulo=titulo,
        contenido=original["contenido"],
        estado="borrador",
        veredicto=original["veredicto"],
        fecha_programada="",
        origen=original["origen"],
        imagen=original["imagen"],
    )
    return JSONResponse({"publicacion": _publicacion_a_dict(copia)})


async def reciclar(request: Request) -> Response:
    """Recicla (evergreen) una publicacion: la DUPLICA y la encola si hay franjas.

    `POST /api/publicaciones/{id}/reciclar` -> `{publicacion, encolado}` | 404.
    La copia nace como `borrador` con `evergreen=1`, copiando contenido/imagen/
    veredicto/red/marca de la original. Si hay franjas aplicables a su (marca, red),
    se ENCOLA al proximo hueco (reusa `calcular_hueco_para`): pasa a `programado` con
    `fecha_programada` puesta y `encolado=true`. Si no hay franjas, se queda en
    `borrador` con `encolado=false`.
    """
    publicacion_id = request.path_params["publicacion_id"]
    original = db.obtener_publicacion(publicacion_id)
    if original is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    copia = db.crear_publicacion(
        original["marca"],
        original["red"],
        titulo=original["titulo"],
        contenido=original["contenido"],
        estado="borrador",
        veredicto=original["veredicto"],
        fecha_programada="",
        origen=original["origen"],
        imagen=original["imagen"],
        evergreen=True,
    )

    hueco = calcular_hueco_para(copia)
    if hueco is not None:
        actualizada = db.actualizar_publicacion(
            copia["id"], {"estado": "programado", "fecha_programada": hueco}
        )
        if actualizada is not None:
            return JSONResponse(
                {"publicacion": _publicacion_a_dict(actualizada), "encolado": True}
            )
    return JSONResponse({"publicacion": _publicacion_a_dict(copia), "encolado": False})


RUTAS = [
    Route("/api/publicaciones/opciones", opciones, methods=["GET"]),
    Route("/api/publicaciones", listar, methods=["GET"]),
    Route("/api/publicaciones", crear, methods=["POST"]),
    Route("/api/publicaciones/lote", crear_lote, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/encolar", encolar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/duplicar", duplicar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/reciclar", reciclar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}", detalle, methods=["GET"]),
    Route("/api/publicaciones/{publicacion_id}", actualizar, methods=["PUT"]),
    Route("/api/publicaciones/{publicacion_id}", borrar, methods=["DELETE"]),
]
