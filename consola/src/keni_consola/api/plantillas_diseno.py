"""API Texto de PLANTILLAS DE DISEÑO: N plantillas reutilizables por marca (editor).

Cada plantilla es un DOCUMENTO de capas completo (logo + textos + marcos + …) que el equipo
guarda para reutilizar; se etiqueta por `categoria` (post | historia | reel | infografia | …) y
por `lineas` (ids de `etiquetas` clase=vertical) para filtrar por línea editorial. A diferencia de
`plantillas_marca` (1 plantilla POR DEFECTO por marca), aquí hay muchas.

  - `GET    /api/plantillas-diseno`        lista (filtros `?marca=&categoria=&tipo=&linea=&q=`).
  - `POST   /api/plantillas-diseno`        crea una plantilla a partir de un documento (validado).
  - `GET    /api/plantillas-diseno/{id}`   una plantilla (con su documento listo para cargar).
  - `PATCH  /api/plantillas-diseno/{id}`   edita nombre/categoria/tipo/documento/lineas/miniatura/activo.
  - `DELETE /api/plantillas-diseno/{id}`   borra.

SEGURIDAD: `marca` (si llega) del catálogo único; el `documento` se valida en el dominio
(`estudio_imagen.validar_documento`) antes de persistir; errores en español, sin tracebacks.
"""

from __future__ import annotations

import hashlib
import json

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import almacen_media, marcas, repos
from .._http_json import leer_json
from ..dominio import estudio_imagen
from ..seguridad import autor_de_peticion

_MAX_NOMBRE = 120
_MAX_LINEAS = 24
_TIPOS_VALIDOS = frozenset({"foto", "miniatura"})


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _normalizar_lineas(valor: object) -> list[str]:
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for item in valor:
        if isinstance(item, str) and item.strip() and item.strip() not in vistas:
            vistas.append(item.strip())
        if len(vistas) >= _MAX_LINEAS:
            break
    return vistas


def _plantilla_a_dict(item: dict) -> dict:
    """Serializa una plantilla: documento/lineas como objeto/lista, url de miniatura y marca_nombre."""
    try:
        doc = json.loads(item.get("documento") or "{}")
    except (ValueError, TypeError):
        doc = {}
    try:
        lineas = json.loads(item.get("lineas") or "[]")
    except (ValueError, TypeError):
        lineas = []
    if not isinstance(lineas, list):
        lineas = []
    miniatura = item.get("miniatura") or ""
    return {
        **item,
        "documento": doc,
        "lineas": [x for x in lineas if isinstance(x, str)],
        "miniatura_url": f"/api/media/{miniatura}" if miniatura else "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _coincide(p: dict, q: str) -> bool:
    return q.lower() in (p.get("nombre") or "").lower()


async def listar(request: Request) -> Response:
    """GET /api/plantillas-diseno: plantillas (mas recientes primero) con filtros opcionales."""
    q = request.query_params
    tipo_q = (q.get("tipo") or "").strip() or None
    if tipo_q and tipo_q not in _TIPOS_VALIDOS:
        return JSONResponse({"error": "tipo debe ser 'foto' o 'miniatura'."}, status_code=400)
    plantillas = [
        _plantilla_a_dict(item)
        for item in repos.listar_plantillas_diseno(
            marca=q.get("marca") or None,
            categoria=q.get("categoria") or None,
            tipo=tipo_q,
        )
    ]
    linea = (q.get("linea") or "").strip()
    if linea:
        plantillas = [p for p in plantillas if linea in p.get("lineas", [])]
    busqueda = (q.get("q") or "").strip()
    if busqueda:
        plantillas = [p for p in plantillas if _coincide(p, busqueda)]
    return JSONResponse({"plantillas": plantillas})


async def crear(request: Request) -> Response:
    """POST /api/plantillas-diseno: crea una plantilla desde un documento (validado). -> `{plantilla}` | 400."""
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    doc = datos.get("documento")
    if not isinstance(doc, dict):
        return JSONResponse({"error": "Falta el documento de la plantilla."}, status_code=400)
    try:
        doc_ok = estudio_imagen.validar_documento(doc)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not estudio_imagen.documento_tiene_hueco(doc_ok):
        return JSONResponse(
            {"error": "La plantilla necesita un hueco de foto: marca una imagen como «hueco de foto»."},
            status_code=400,
        )

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    nombre = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    categoria = (datos.get("categoria") or "post").strip()[:40] or "post"
    tipo_raw = (datos.get("tipo") or "").strip()
    tipo = tipo_raw if tipo_raw in _TIPOS_VALIDOS else "foto"
    miniatura = (datos.get("miniatura") or "").strip() if isinstance(datos.get("miniatura"), str) else ""
    if miniatura:
        # La miniatura es un asset REUSABLE de la plantilla: a la carpeta `plantillas/`.
        miniatura = almacen_media.promover_objeto(miniatura, "plantillas")
    lineas = _normalizar_lineas(datos.get("lineas"))

    plantilla = repos.crear_plantilla_diseno(
        marca=marca or "",
        nombre=nombre,
        categoria=categoria,
        tipo=tipo,
        documento=json.dumps(doc_ok, ensure_ascii=False),
        miniatura=miniatura,
        lineas=json.dumps(lineas, ensure_ascii=False),
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def obtener(request: Request) -> Response:
    """GET /api/plantillas-diseno/{id}: una plantilla con su documento listo para cargar. -> 404 si no existe."""
    item = repos.obtener_plantilla_diseno(request.path_params["plantilla_id"])
    if item is None:
        return JSONResponse({"error": "Esa plantilla no existe."}, status_code=404)
    return JSONResponse({"plantilla": _plantilla_a_dict(item)})


async def actualizar(request: Request) -> Response:
    """PATCH /api/plantillas-diseno/{id}: edita campos. Si llega `documento`, se valida. -> `{plantilla}` | 400/404."""
    plantilla_id = request.path_params["plantilla_id"]
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    campos: dict[str, object] = {}
    if "nombre" in datos:
        campos["nombre"] = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    if "categoria" in datos:
        campos["categoria"] = (datos.get("categoria") or "post").strip()[:40] or "post"
    if "tipo" in datos:
        tipo_raw = (datos.get("tipo") or "").strip()
        if tipo_raw and tipo_raw not in _TIPOS_VALIDOS:
            return JSONResponse({"error": "tipo debe ser 'foto' o 'miniatura'."}, status_code=400)
        campos["tipo"] = tipo_raw if tipo_raw in _TIPOS_VALIDOS else "foto"
    if "miniatura" in datos:
        campos["miniatura"] = (datos.get("miniatura") or "").strip()
    if "lineas" in datos:
        campos["lineas"] = json.dumps(_normalizar_lineas(datos.get("lineas")), ensure_ascii=False)
    if "activo" in datos:
        campos["activo"] = bool(datos["activo"])
    if "documento" in datos:
        if not isinstance(datos["documento"], dict):
            return JSONResponse({"error": "El documento debe ser un objeto."}, status_code=400)
        try:
            doc_ok = estudio_imagen.validar_documento(datos["documento"])
        except estudio_imagen.EstudioError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if not estudio_imagen.documento_tiene_hueco(doc_ok):
            return JSONResponse(
                {"error": "La plantilla necesita un hueco de foto: marca una imagen como «hueco de foto»."},
                status_code=400,
            )
        campos["documento"] = json.dumps(doc_ok, ensure_ascii=False)

    plantilla = repos.actualizar_plantilla_diseno(plantilla_id, campos)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla no existe."}, status_code=404)
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def borrar(request: Request) -> Response:
    """DELETE /api/plantillas-diseno/{id}: borra la plantilla. -> `{mensaje}` | 404."""
    item = repos.borrar_plantilla_diseno(request.path_params["plantilla_id"])
    if item is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Plantilla borrada."})


async def preview(request: Request) -> Response:
    """GET /api/plantillas-diseno/{id}/preview: MINIATURA on-demand del diseño (sin persistir).

    Renderiza el DOCUMENTO de la plantilla (sus huecos vacíos + un titular de ejemplo) a PNG. Es el
    RESPALDO de la galería cuando la plantilla no tiene `miniatura` guardada —p. ej. las creadas por
    API/agente, que no pasan por el guardado del estudio (es ahí donde se genera la miniatura)—. Así
    se ven todas sin tener que abrir+editar cada una. ETag por hash del documento; cacheable (304 sin
    recomponer si no cambió). 404 si no existe; 422 si el render falla.
    """
    item = repos.obtener_plantilla_diseno(request.path_params["plantilla_id"])
    if item is None:
        return JSONResponse({"error": "Esa plantilla no existe."}, status_code=404)
    documento = item.get("documento") or "{}"
    etag = '"' + hashlib.sha256(str(documento).encode("utf-8")).hexdigest()[:32] + '"'
    cache = "private, max-age=300"
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache})
    try:
        doc = json.loads(documento) if isinstance(documento, str) else documento
        datos = estudio_imagen.renderizar_documento_bytes(
            doc, bindings={"copy_in": "TITULAR", "etiqueta_default": ""}
        )
    except (ValueError, TypeError) as e:
        return JSONResponse({"error": f"Documento inválido: {e}"}, status_code=422)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    return Response(
        content=datos,
        media_type="image/png",
        headers={"ETag": etag, "Cache-Control": cache},
    )


RUTAS = [
    Route("/api/plantillas-diseno", listar, methods=["GET"]),
    Route("/api/plantillas-diseno", crear, methods=["POST"]),
    Route("/api/plantillas-diseno/{plantilla_id}", obtener, methods=["GET"]),
    Route("/api/plantillas-diseno/{plantilla_id}/preview", preview, methods=["GET"]),
    Route("/api/plantillas-diseno/{plantilla_id}", actualizar, methods=["PATCH"]),
    Route("/api/plantillas-diseno/{plantilla_id}", borrar, methods=["DELETE"]),
]
