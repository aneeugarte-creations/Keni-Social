"""API Biblioteca de medios: repositorio editorial INTERNO de imágenes/clips aprobados.

Catalogo reutilizable de medios (imagenes/clips) que el equipo aprueba una vez y reusa al
armar piezas. NO publica a redes (eso es Metricool): es un activo interno, etiquetable y
buscable. El binario lo guarda/sirve `consola.media` (disco o S3, anti-traversal, nombre
generado por el servidor); aqui catalogamos ese objeto con metadatos editoriales y
etiquetas, y se sirve por la misma ruta `GET /api/media/{nombre}`.

Endpoints:
  - `GET    /api/biblioteca-media`        listado (filtros `?marca=&tipo=&solo_aprobados=1`).
  - `POST   /api/biblioteca-media`        subir UN archivo (multipart) + catalogarlo.
  - `POST   /api/biblioteca-media/catalogar` cataloga un `objeto` YA subido (JSON).
  - `PUT    /api/biblioteca-media/{id}`   edita metadatos/etiquetas/aprobacion.
  - `DELETE /api/biblioteca-media/{id}`   descataloga (y borra el binario si no quedan refs).

SEGURIDAD / VALIDACION:
  - El NOMBRE del objeto lo genera SIEMPRE `media.guardar_subida` (uuid+ext saneada).
  - `marca` (si viene) SOLO del catalogo unico; `tipo` ∈ {imagen, clip}.
  - `etiquetas` se normalizan (strings, sin vacios, deduplicadas) y se guardan como JSON.
  - SQL parametrizado; errores en espanol, sin tracebacks crudos.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import almacen_media, marcas, media, repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion

# Marcas validas: TODAS las del catalogo unico (por su id canonico).
_MARCAS_IDS = {m[0] for m in marcas.opciones()}

# Tipos de medio del catalogo interno. `imagen` cubre los formatos que sube/genera la
# consola hoy; `clip` queda declarado para video (el binario lo gestiona Metricool al
# publicar; aqui solo se referencia/cataloga la imagen de portada o el objeto subido).
_TIPOS = frozenset({"imagen", "clip"})

_MAX_ETIQUETAS = 30
_MAX_LARGO_ETIQUETA = 40


def _normalizar_etiquetas(crudo: Any) -> tuple[list[str] | None, str | None]:
    """Normaliza etiquetas a lista de strings (sin vacios, deduplicadas). `(lista, None)`/`(None, msg)`."""
    if crudo is None:
        return [], None
    if not isinstance(crudo, list):
        return None, "Las etiquetas deben ser una lista de texto."
    if len(crudo) > _MAX_ETIQUETAS:
        return None, f"Demasiadas etiquetas (máximo {_MAX_ETIQUETAS})."
    salida: list[str] = []
    for e in crudo:
        if not isinstance(e, str):
            return None, "Cada etiqueta debe ser texto."
        limpia = e.strip()
        if not limpia:
            continue
        if len(limpia) > _MAX_LARGO_ETIQUETA:
            return None, "Una etiqueta es demasiado larga."
        if limpia not in salida:
            salida.append(limpia)
    return salida, None


def _cargar_etiquetas(crudo: str) -> list[str]:
    """Deserializa el JSON de etiquetas; lista vacia si esta corrupto."""
    try:
        datos = json.loads(crudo or "[]")
    except (ValueError, TypeError):
        return []
    return [e for e in datos if isinstance(e, str)] if isinstance(datos, list) else []


def _media_a_dict(m: dict[str, Any]) -> dict[str, Any]:
    """Serializa un item de biblioteca con su URL de servido y nombres legibles."""
    return {
        "id": m["id"],
        "objeto": m["objeto"],
        "url": f"/api/media/{m['objeto']}",
        "tipo": m["tipo"],
        "titulo": m["titulo"],
        "descripcion": m["descripcion"],
        "marca": m["marca"],
        "marca_nombre": marcas.etiqueta_de(m["marca"]) if m["marca"] else "",
        "etiquetas": _cargar_etiquetas(m["etiquetas"]),
        "credito": m["credito"],
        "aprobado": bool(m["aprobado"]),
        "autor_nombre": m.get("autor_nombre", ""),
        "creado": m.get("creado", ""),
        "actualizado": m.get("actualizado", ""),
    }


def _validar_marca(marca: Any) -> tuple[str | None, str | None]:
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return None, "La marca debe ser texto."
    if marca and marca not in _MARCAS_IDS:
        return None, "Marca no permitida."
    return marca, None


def _validar_tipo(tipo: Any) -> tuple[str | None, str | None]:
    if tipo is None or tipo == "":
        return "imagen", None
    if not isinstance(tipo, str) or tipo not in _TIPOS:
        return None, "Tipo de medio no permitido (imagen o clip)."
    return tipo, None


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """Listado de la biblioteca. `?marca=&tipo=&solo_aprobados=1` filtran (AND)."""
    qp = request.query_params
    marca = qp.get("marca") or None
    tipo = qp.get("tipo") or None
    solo_aprobados = qp.get("solo_aprobados") in ("1", "true", "si")
    items = repos.listar_media_biblioteca(
        marca=marca, tipo=tipo, solo_aprobados=solo_aprobados
    )
    return JSONResponse({"medios": [_media_a_dict(m) for m in items]})


def _leer_metadatos(datos: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Valida los metadatos comunes (titulo/descripcion/marca/tipo/etiquetas/credito)."""
    marca, error = _validar_marca(datos.get("marca", ""))
    if error is not None:
        return None, error
    tipo, error = _validar_tipo(datos.get("tipo"))
    if error is not None:
        return None, error
    etiquetas, error = _normalizar_etiquetas(datos.get("etiquetas"))
    if error is not None:
        return None, error
    titulo = datos.get("titulo", "")
    descripcion = datos.get("descripcion", "")
    credito = datos.get("credito", "")
    if not all(isinstance(x, str) for x in (titulo, descripcion, credito)):
        return None, "El título, la descripción y el crédito deben ser texto."
    return (
        {
            "tipo": tipo,
            "titulo": titulo.strip(),
            "descripcion": descripcion,
            "marca": marca,
            "etiquetas": json.dumps(etiquetas, ensure_ascii=False),
            "credito": credito.strip(),
            "aprobado": bool(datos.get("aprobado", True)),
        },
        None,
    )


async def subir(request: Request) -> Response:
    """Sube UN archivo (multipart `archivo`) y lo cataloga en la biblioteca de una vez.

    Los metadatos viajan como campos del mismo form (`titulo`, `marca`, `tipo`,
    `etiquetas` como JSON o coma-separadas, `credito`, `descripcion`).
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro
        return JSONResponse({"error": "No se pudo leer el archivo subido."}, status_code=400)
    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "No se recibió ningún archivo."}, status_code=400)
    try:
        objeto = await media.guardar_subida(archivo)
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo
        return JSONResponse({"error": "No se pudo guardar el archivo."}, status_code=500)

    # `etiquetas` en multipart puede venir como JSON o como lista coma-separada.
    crudo_etiquetas: Any = form.get("etiquetas")
    if isinstance(crudo_etiquetas, str) and crudo_etiquetas.strip():
        try:
            crudo_etiquetas = json.loads(crudo_etiquetas)
        except (ValueError, TypeError):
            crudo_etiquetas = [t.strip() for t in crudo_etiquetas.split(",")]
    datos = {
        "titulo": form.get("titulo", ""),
        "descripcion": form.get("descripcion", ""),
        "marca": form.get("marca", ""),
        "tipo": form.get("tipo", "imagen"),
        "etiquetas": crudo_etiquetas,
        "credito": form.get("credito", ""),
        "aprobado": (form.get("aprobado", "1") not in ("0", "false", "no")),
    }
    meta, error = _leer_metadatos(datos)
    if error is not None:
        almacen_media.borrar_objeto(objeto)  # no dejar binario huerfano si los metadatos fallan
        return JSONResponse({"error": error}, status_code=400)

    autor = autor_de_peticion(request) or {}
    item = repos.crear_media_biblioteca(objeto=objeto, autor=autor, **meta)
    return JSONResponse({"medio": _media_a_dict(item)})


async def catalogar(request: Request) -> Response:
    """Cataloga un `objeto` de media YA subido (JSON `{objeto, titulo?, marca?, ...}`).

    Util para catalogar una imagen GENERADA por IA (que ya vive en el almacen tras
    `POST /api/media/generar`) sin volver a subirla.
    """
    datos = await leer_json(request)
    objeto = datos.get("objeto")
    if not isinstance(objeto, str) or not objeto.strip():
        return JSONResponse({"error": "Falta el objeto de media a catalogar."}, status_code=400)
    objeto = objeto.strip()
    if media.leer_media(objeto) is None:
        return JSONResponse({"error": "Ese medio no existe en el almacén."}, status_code=404)
    if repos.existe_media_objeto(objeto):
        return JSONResponse({"error": "Ese medio ya está en la biblioteca."}, status_code=409)
    meta, error = _leer_metadatos(datos)
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    autor = autor_de_peticion(request) or {}
    item = repos.crear_media_biblioteca(objeto=objeto, autor=autor, **meta)
    return JSONResponse({"medio": _media_a_dict(item)})


async def actualizar(request: Request) -> Response:
    """Edicion PARCIAL de metadatos `{titulo?, descripcion?, marca?, tipo?, etiquetas?, credito?, aprobado?}`."""
    media_id = request.path_params["media_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "titulo" in datos:
        titulo = datos.get("titulo")
        if not isinstance(titulo, str):
            return JSONResponse({"error": "El título debe ser texto."}, status_code=400)
        campos["titulo"] = titulo.strip()
    if "descripcion" in datos:
        descripcion = datos.get("descripcion")
        if not isinstance(descripcion, str):
            return JSONResponse({"error": "La descripción debe ser texto."}, status_code=400)
        campos["descripcion"] = descripcion
    if "credito" in datos:
        credito = datos.get("credito")
        if not isinstance(credito, str):
            return JSONResponse({"error": "El crédito debe ser texto."}, status_code=400)
        campos["credito"] = credito.strip()
    if "marca" in datos:
        marca, error = _validar_marca(datos.get("marca"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["marca"] = marca
    if "tipo" in datos:
        tipo, error = _validar_tipo(datos.get("tipo"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["tipo"] = tipo
    if "etiquetas" in datos:
        etiquetas, error = _normalizar_etiquetas(datos.get("etiquetas"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["etiquetas"] = json.dumps(etiquetas, ensure_ascii=False)
    if "aprobado" in datos:
        campos["aprobado"] = bool(datos.get("aprobado"))
    if not campos:
        return JSONResponse({"error": "No hay nada que actualizar."}, status_code=400)

    item = repos.actualizar_media_biblioteca(media_id, campos)
    if item is None:
        return JSONResponse({"error": "Ese medio ya no existe en la biblioteca."}, status_code=404)
    return JSONResponse({"medio": _media_a_dict(item)})


async def borrar(request: Request) -> Response:
    """Descataloga un medio y borra su binario del almacen (best-effort)."""
    media_id = request.path_params["media_id"]
    item = repos.borrar_media_biblioteca(media_id)
    if item is None:
        return JSONResponse({"error": "Ese medio ya no existe en la biblioteca."}, status_code=404)
    # El binario se borra al descatalogar: la biblioteca es el catalogo de verdad. Si una
    # pieza ya lo copio/uso, conserva su propia referencia; el borrado aqui es del activo
    # reutilizable. Best-effort (idempotente): un fallo de almacen no rompe la respuesta.
    almacen_media.borrar_objeto(item["objeto"])
    return JSONResponse({"mensaje": "Medio eliminado de la biblioteca."})


RUTAS = [
    Route("/api/biblioteca-media", listar, methods=["GET"]),
    Route("/api/biblioteca-media", subir, methods=["POST"]),
    Route("/api/biblioteca-media/catalogar", catalogar, methods=["POST"]),
    Route("/api/biblioteca-media/{media_id}", actualizar, methods=["PUT"]),
    Route("/api/biblioteca-media/{media_id}", borrar, methods=["DELETE"]),
]
