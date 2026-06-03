"""API Publicaciones: CRUD de posts a gestionar (titulo, marca, red, estado, fechas).

El SPA gestiona el ciclo de vida de cada pieza: nace como borrador (a mano o desde
una generacion por red de Skills), se edita, se aprueba, se programa y se publica.
Persistencia en SQLite (`consola.db`, via `consola.db`). Nada se publica de verdad
aqui: solo se administra el estado editorial.

SEGURIDAD / VALIDACION (no duplica logica; reusa las fuentes de verdad):
  - `marca` SOLO puede ser una marca del catalogo unico (`consola.marcas`), por
    su `id` canonico (slug-guion), el mismo `value` que usa la generacion de copy.
  - `red` SOLO puede ser una red canonica (`consola.redes`).
  - `estado` SOLO puede ser uno de `repos.ESTADOS_PUBLICACION`.
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

from .. import marcas, permisos, redes, repos
from .._http_json import envoltura_paginacion, leer_json, paginacion_query
from ..dominio.publicaciones import publicacion_a_dict
from ..seguridad import autor_de_peticion
from . import franjas as api_franjas

# Nombres legibles de los estados (para poblar selects de la UI), en orden de flujo.
# `en_revision` (cola de aprobacion de equipo, #9) se intercala tras el borrador.
_ESTADO_NOMBRE: dict[str, str] = {
    "borrador": "Borrador",
    "en_revision": "En revisión",
    "aprobado": "Aprobado",
    "programado": "Programado",
    "publicado": "Publicado",
}

# Marcas validas como destino de copy: TODAS las del catalogo unico. value
# interno = id canonico (slug-guion); etiqueta visible = nombre humano con acentos.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}


# Alias local para los handlers de este modulo. La serializacion vive en el dominio
# (`dominio.publicaciones.publicacion_a_dict`): asi `api/skills.py` la consume desde un
# sitio comun y publico, sin importar un simbolo privado de este handler (H6/N7).
_publicacion_a_dict = publicacion_a_dict


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
    if not isinstance(estado, str) or estado not in repos.ESTADOS_PUBLICACION:
        return None, "Estado no permitido."

    titulo = datos.get("titulo", "")
    contenido = datos.get("contenido", "")
    copy_in = datos.get("copy_in", "")
    veredicto = datos.get("veredicto", "")
    fecha_programada = datos.get("fecha_programada", "")
    origen = datos.get("origen", "")
    imagen = datos.get("imagen", "")
    for valor, etiqueta in (
        (titulo, "El título"),
        (contenido, "El contenido"),
        (copy_in, "El texto en imagen"),
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
            "copy_in": copy_in,
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
            "estados": [{"id": e, "nombre": _ESTADO_NOMBRE[e]} for e in repos.ESTADOS_PUBLICACION],
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
    """Listado de publicaciones con filtros `?marca=&red=&estado=&evergreen=` y paginacion.

    Envelope RETROCOMPATIBLE: mantiene la clave `publicaciones` (las paginas que solo
    desestructuran esa clave siguen funcionando) y AÑADE `paginacion:{total, limite,
    desplazamiento}`. Sin `?limite=` se devuelve el conjunto completo (igual que antes),
    con un `total` exacto. Con `?limite=&desplazamiento=` se pagina en el indice (solo
    se leen los cuerpos YAML de la pagina).
    """
    qp = request.query_params
    marca = qp.get("marca") or None
    # Alcance por marca: un editor no puede pedir el feed de una marca que no es suya.
    rechazo = permisos.rechazo_marca(request, marca)
    if rechazo is not None:
        return rechazo
    red = qp.get("red") or None
    estado = qp.get("estado") or None
    evergreen = _parsear_bool_query(qp.get("evergreen"))
    limite, desplazamiento = paginacion_query(request)
    pubs = repos.listar_publicaciones(
        marca=marca, red=red, estado=estado, evergreen=evergreen,
        limite=limite, desplazamiento=desplazamiento,
    )
    total = repos.contar_publicaciones(marca=marca, red=red, estado=estado, evergreen=evergreen)
    return JSONResponse(
        {
            "publicaciones": [_publicacion_a_dict(p) for p in pubs],
            "paginacion": envoltura_paginacion(total, limite, desplazamiento),
        }
    )


async def crear(request: Request) -> Response:
    datos = await leer_json(request)
    entrada, error = _validar_nueva(datos)
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    pub = repos.crear_publicacion(
        entrada["marca"],
        entrada["red"],
        titulo=entrada["titulo"],
        contenido=entrada["contenido"],
        copy_in=entrada["copy_in"],
        estado=entrada["estado"],
        veredicto=entrada["veredicto"],
        fecha_programada=entrada["fecha_programada"],
        origen=entrada["origen"],
        imagen=entrada["imagen"],
        autor=autor_de_peticion(request),
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
    autor = autor_de_peticion(request) or {}
    entradas: list[dict[str, Any]] = []
    for i, cruda in enumerate(crudas, start=1):
        if not isinstance(cruda, dict):
            return JSONResponse(
                {"error": f"La publicación {i} no es válida."}, status_code=400
            )
        entrada, error = _validar_nueva(cruda)
        if error is not None:
            return JSONResponse({"error": f"Publicación {i}: {error}"}, status_code=400)
        # Atribucion por usuario (#130 Fase 1): el lote lo crea el usuario de la peticion.
        entrada["autor_id"] = autor.get("id", "")
        entrada["autor_nombre"] = autor.get("usuario", "")
        entradas.append(entrada)
    pubs = repos.crear_publicaciones(entradas)
    return JSONResponse({"publicaciones": [_publicacion_a_dict(p) for p in pubs]})


async def detalle(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL: titulo/contenido/copy_in/estado/fecha_programada (404 si no existe)."""
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
    if "copy_in" in datos:
        copy_in = datos.get("copy_in")
        if not isinstance(copy_in, str):
            return JSONResponse(
                {"error": "El texto en imagen debe ser texto."}, status_code=400
            )
        campos["copy_in"] = copy_in
    if "estado" in datos:
        estado = datos.get("estado")
        if not isinstance(estado, str) or estado not in repos.ESTADOS_PUBLICACION:
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
    if "foto" in datos:
        foto = datos.get("foto")
        if not isinstance(foto, str):
            return JSONResponse({"error": "La foto debe ser texto."}, status_code=400)
        campos["foto"] = foto.strip()
    if "evergreen" in datos:
        evergreen = datos.get("evergreen")
        if not isinstance(evergreen, bool):
            return JSONResponse({"error": "El campo evergreen debe ser verdadero o falso."}, status_code=400)
        campos["evergreen"] = evergreen
    if "placa_oculta" in datos:
        placa_oculta = datos.get("placa_oculta")
        if not isinstance(placa_oculta, bool):
            return JSONResponse(
                {"error": "El campo placa_oculta debe ser verdadero o falso."}, status_code=400
            )
        campos["placa_oculta"] = placa_oculta
    if "plantilla_diseno_id" in datos:
        plantilla_diseno_id = datos.get("plantilla_diseno_id")
        if not isinstance(plantilla_diseno_id, str):
            return JSONResponse({"error": "La plantilla debe ser texto."}, status_code=400)
        campos["plantilla_diseno_id"] = plantilla_diseno_id.strip()

    if not campos:
        return JSONResponse(
            {
                "error": (
                    "No hay nada que actualizar (título, contenido, texto en imagen, "
                    "estado, fecha, imagen o evergreen)."
                )
            },
            status_code=400,
        )

    pub = repos.actualizar_publicacion(publicacion_id, campos)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(pub)})


async def borrar(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    if not repos.borrar_publicacion(publicacion_id):
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
    franjas = repos.listar_franjas()
    aplican = api_franjas.franjas_aplicables(franjas, pub["marca"], pub["red"])
    if not aplican:
        return None
    ocupados = {
        otra["fecha_programada"]
        for otra in repos.listar_publicaciones(estado="programado")
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
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    hueco = calcular_hueco_para(pub)
    if hueco is None:
        return JSONResponse(
            {"error": "No hay franjas configuradas para esta marca/red."}, status_code=400
        )
    actualizada = repos.actualizar_publicacion(
        publicacion_id, {"estado": "programado", "fecha_programada": hueco}
    )
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(actualizada)})


async def duplicar(request: Request) -> Response:
    """Duplica una publicacion como borrador, con overrides opcionales.

    `POST /api/publicaciones/{id}/duplicar` con JSON opcional `{red?, marca?, titulo?}`.
    Copia contenido/copy_in/imagen/veredicto/hashtags; estado=borrador, fecha_programada=''.
    -> `{publicacion}` | 404.
    """
    publicacion_id = request.path_params["publicacion_id"]
    original = repos.obtener_publicacion(publicacion_id)
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

    copia = repos.crear_publicacion(
        marca,
        red,
        titulo=titulo,
        contenido=original["contenido"],
        copy_in=original.get("copy_in", ""),
        estado="borrador",
        veredicto=original["veredicto"],
        fecha_programada="",
        origen=original["origen"],
        imagen=original["imagen"],
        autor=autor_de_peticion(request),
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
    original = repos.obtener_publicacion(publicacion_id)
    if original is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    copia = repos.crear_publicacion(
        original["marca"],
        original["red"],
        titulo=original["titulo"],
        contenido=original["contenido"],
        copy_in=original.get("copy_in", ""),
        estado="borrador",
        veredicto=original["veredicto"],
        fecha_programada="",
        origen=original["origen"],
        imagen=original["imagen"],
        evergreen=True,
        autor=autor_de_peticion(request),
    )

    hueco = calcular_hueco_para(copia)
    if hueco is not None:
        actualizada = repos.actualizar_publicacion(
            copia["id"], {"estado": "programado", "fecha_programada": hueco}
        )
        if actualizada is not None:
            return JSONResponse(
                {"publicacion": _publicacion_a_dict(actualizada), "encolado": True}
            )
    return JSONResponse({"publicacion": _publicacion_a_dict(copia), "encolado": False})


async def programar_metricool(request: Request) -> Response:
    """Programa/previsualiza la pieza en Metricool a demanda (botón de la UI).

    `POST /api/publicaciones/{id}/metricool`. Respeta el gate `KENI_PUBLICAR_REAL`:
    con el flag OFF (default) es DRY-RUN (previsualiza el cuerpo que se enviaría,
    NO publica ni persiste); con ON publica de verdad, persiste `id_post_metricool`
    y pasa la pieza a `publicado`. -> `{resultado, publicacion}` | 400 | 404.
    """
    # Import local: `programador` es infra (no es router de ninguna app); el camino
    # real solo se activa con el gate. Mantiene el módulo de API sin acoplarse a él.
    from .. import programador

    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    resultado = programador.programar_pieza_metricool(pub)
    if not resultado.get("ok"):
        return JSONResponse(
            {"error": resultado.get("motivo") or "No se pudo programar en Metricool."},
            status_code=400,
        )
    actualizada = repos.obtener_publicacion(publicacion_id)
    return JSONResponse(
        {
            "resultado": resultado,
            "publicacion": _publicacion_a_dict(actualizada) if actualizada else None,
        }
    )


async def integrar_foto(request: Request) -> Response:
    """Integra una FOTO subida dentro de la plantilla de marca de la publicación.

    `POST /api/publicaciones/{id}/integrar-foto {imagen}` (imagen = id de media de la foto).
    Si la pieza tiene marca (cualquiera del catálogo) RECOMPONE de forma determinista
    (síncrona, ~<1s) la foto detrás de la plantilla por SPEC usando el `copy_in` de la pieza
    como titular; sin marca devuelve la foto tal cual. NO persiste: devuelve la imagen
    resultante para que el SPA la fije y la guarde con el resto de la edición.
    -> `{imagen, imagen_url}` | 400 | 404.
    """
    from ..dominio import estudio_imagen

    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    imagen = datos.get("imagen")
    if not isinstance(imagen, str) or not imagen.strip():
        return JSONResponse({"error": "Falta la foto a integrar."}, status_code=400)
    imagen = imagen.strip()
    # `copy_in` opcional: el SPA puede mandar el texto-en-imagen VIGENTE (aún sin guardar) para
    # que la placa use ese titular; si no viene, se usa el `copy_in` persistido de la pieza.
    copy_in = datos.get("copy_in")
    titular = copy_in if isinstance(copy_in, str) else (pub.get("copy_in") or "")

    marca = pub.get("marca") or ""
    final = imagen
    if estudio_imagen.marca_tiene_plantilla(marca):
        try:
            resultado = estudio_imagen.componer(
                imagen,
                marca=marca,
                formato=estudio_imagen.formato_por_red(pub.get("red") or ""),
                titular=titular,
                etiqueta=None,
                autor=autor_de_peticion(request),
            )
            final = resultado.get("id") or imagen
        except estudio_imagen.EstudioError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    return JSONResponse({"imagen": final, "imagen_url": f"/api/media/{final}"})


async def aplicar_plantilla(request: Request) -> Response:
    """Aplica una PLANTILLA del estudio a la publicación y RECOMPONE su imagen.

    `POST /api/publicaciones/{id}/aplicar-plantilla {plantilla_id}`: renderiza el documento de la
    plantilla (PlantillaDiseno) con la FOTO y el COPY-IN actuales de la pieza, fija la imagen
    resultante y recuerda la plantilla elegida (`plantilla_diseno_id`). Persiste. Así el equipo
    prueba distintas plantillas y compara el resultado real. -> `{publicacion}` | 400 | 404.
    """
    from ..dominio import estudio_imagen

    publicacion_id = request.path_params["publicacion_id"]
    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None:
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)

    datos = await leer_json(request)
    plantilla_id = datos.get("plantilla_id")
    if not isinstance(plantilla_id, str) or not plantilla_id.strip():
        return JSONResponse({"error": "Falta la plantilla a aplicar."}, status_code=400)
    plantilla_id = plantilla_id.strip()
    plantilla = repos.obtener_plantilla_diseno(plantilla_id)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)

    # `foto`/`copy_in` opcionales: el SPA manda los valores VIGENTES del editor (aún sin guardar)
    # para componer con ellos; si no vienen, se usan los persistidos de la pieza.
    foto_req = datos.get("foto")
    foto = foto_req if isinstance(foto_req, str) else (pub.get("foto") or "")
    copy_in_req = datos.get("copy_in")
    copy_in = copy_in_req if isinstance(copy_in_req, str) else (pub.get("copy_in") or "")

    try:
        resultado = estudio_imagen.componer_desde_plantilla(
            plantilla.get("documento") or "{}", copy_in=copy_in, foto=foto,
        )
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    actualizada = repos.actualizar_publicacion(
        publicacion_id,
        {"imagen": resultado["id"], "plantilla_diseno_id": plantilla_id, "foto": foto},
    )
    if actualizada is None:  # carrera: borrada entre el obtener y el actualizar
        return JSONResponse({"error": "Esa publicación ya no existe."}, status_code=404)
    return JSONResponse({"publicacion": _publicacion_a_dict(actualizada)})


RUTAS = [
    Route("/api/publicaciones/opciones", opciones, methods=["GET"]),
    Route("/api/publicaciones", listar, methods=["GET"]),
    Route("/api/publicaciones", crear, methods=["POST"]),
    Route("/api/publicaciones/lote", crear_lote, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/encolar", encolar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/duplicar", duplicar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/reciclar", reciclar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/metricool", programar_metricool, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/integrar-foto", integrar_foto, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/aplicar-plantilla", aplicar_plantilla, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}", detalle, methods=["GET"]),
    Route("/api/publicaciones/{publicacion_id}", actualizar, methods=["PUT"]),
    Route("/api/publicaciones/{publicacion_id}", borrar, methods=["DELETE"]),
]
