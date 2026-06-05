"""API de Insumos del día (cajones) — cuatro bandejas de material diario.

Los cuatro cajones reciben el material que el equipo de redes de AMX recibe cada día:
  - portal        : lista numerada Portal/SMS
  - corresponsales: el "así vamos" por estado
  - reporteros    : PDF de agenda de coberturas
  - eventos_claro : Excel/CSV de programación TV Claro Sports

Contrato completo: docs/maquina-contenido/01-insumos-del-dia.md

Endpoints:
  GET  /api/insumos                  -> {fecha, cajones:[{cajon,lotes,items},...]}
  GET  /api/insumos/dias             -> {dias:[{fecha,total,por_cajon},...]}}
  POST /api/insumos/aportar          -> {lote, items}  (multipart/form-data o JSON)
  GET  /api/insumos/lote/{id}        -> {lote, items}
  PATCH /api/insumos/item/{id}       -> {item}
  POST /api/insumos/item/{id}/usar   -> {item, contenido_id}
  DELETE /api/insumos/lote/{id}      -> {ok: true}
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import autogen_copy, marcas, redes, repos
from .._http_json import leer_json
from ..dominio import insumos_parse
from ..seguridad import autor_de_peticion

_log = logging.getLogger("keni_consola.api.insumos")

# Cajones en el orden del contrato (siempre los 4, incluso vacíos).
_CAJONES: tuple[str, ...] = ("portal", "corresponsales", "reporteros", "eventos_claro")
_MARCAS_IDS = {m[0] for m in marcas.opciones()}

# Límites de texto de entrada.
_MAX_TEXTO = 256_000  # ~256 KB para texto pegado
_MAX_ARCHIVO = 10 * 1024 * 1024  # 10 MB para archivos

# Campos editables de un ítem (PATCH).
_CAMPOS_PATCH_ITEM = frozenset(
    {"titulo", "resumen", "marca", "linea", "hora", "lugar", "estado_material", "tipo"}
)


# --------------------------------------------------------------------------- #
# Helpers de serialización                                                     #
# --------------------------------------------------------------------------- #


def _lote_a_dict(lote: dict[str, Any]) -> dict[str, Any]:
    """Serializa un lote añadiendo marca_nombre."""
    return {
        **lote,
        "marca_nombre": marcas.etiqueta_de(lote["marca"]) if lote.get("marca") else "",
    }


def _item_a_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Serializa un ítem añadiendo marca_nombre (usado ya viene como bool de db)."""
    return {
        **item,
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _redes_iniciales(crudo: Any) -> list[str]:
    """Filtra una lista de ids de red contra las canónicas."""
    if not isinstance(crudo, list):
        return []
    vistas: list[str] = []
    for r in crudo:
        if isinstance(r, str) and redes.es_red(r) and r not in vistas:
            vistas.append(r)
    return vistas


# --------------------------------------------------------------------------- #
# GET /api/insumos                                                             #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """`GET /api/insumos?fecha=YYYY-MM-DD&cajon=&marca=`

    Devuelve los 4 cajones para la fecha pedida (def hoy), cada uno con sus lotes e ítems.
    """
    fecha = (request.query_params.get("fecha") or "").strip()
    if not fecha:
        fecha = date.today().isoformat()
    cajon_filtro = (request.query_params.get("cajon") or "").strip() or None
    marca_filtro = (request.query_params.get("marca") or "").strip() or None

    if cajon_filtro and cajon_filtro not in _CAJONES:
        return JSONResponse({"error": "Cajón no válido."}, status_code=400)
    if marca_filtro and marca_filtro not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no válida."}, status_code=400)

    cajones_resultado: list[dict[str, Any]] = []
    for cajon in _CAJONES:
        if cajon_filtro and cajon != cajon_filtro:
            cajones_resultado.append({"cajon": cajon, "lotes": [], "items": []})
            continue
        lotes = repos.listar_lotes(fecha=fecha, cajon=cajon)
        items = repos.listar_insumo_items(fecha=fecha, cajon=cajon, marca=marca_filtro)
        cajones_resultado.append({
            "cajon": cajon,
            "lotes": [_lote_a_dict(lt) for lt in lotes],
            "items": [_item_a_dict(i) for i in items],
        })

    return JSONResponse({"fecha": fecha, "cajones": cajones_resultado})


# --------------------------------------------------------------------------- #
# GET /api/insumos/dias                                                        #
# --------------------------------------------------------------------------- #


async def dias(request: Request) -> Response:
    """`GET /api/insumos/dias` -> historial de días con insumos."""
    resultado = repos.dias_con_insumos()
    return JSONResponse({"dias": resultado})


# --------------------------------------------------------------------------- #
# POST /api/insumos/aportar                                                    #
# --------------------------------------------------------------------------- #


async def aportar(request: Request) -> Response:
    """`POST /api/insumos/aportar` (multipart/form-data O JSON body).

    Campos obligatorios: `cajon`.
    Opcionales: `fecha` (def hoy), `marca`, `texto` O `archivo`.
    Parsea con Haiku de forma SÍNCRONA, inserta lote + ítems y los devuelve.
    Si el parse falla, devuelve lote con estado "error" (HTTP 200, no 500).
    """
    content_type = request.headers.get("content-type", "")
    archivo_bytes: bytes = b""
    archivo_nombre: str = ""
    texto: str = ""
    cajon: str = ""
    fecha: str = ""
    marca: str = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        cajon = str(form.get("cajon") or "").strip()
        fecha = str(form.get("fecha") or "").strip()
        marca = str(form.get("marca") or "").strip()
        texto = str(form.get("texto") or "").strip()
        archivo_field = form.get("archivo")
        if isinstance(archivo_field, UploadFile):
            archivo_nombre = archivo_field.filename or "insumo.bin"
            archivo_bytes = await archivo_field.read(_MAX_ARCHIVO + 1)
            if len(archivo_bytes) > _MAX_ARCHIVO:
                return JSONResponse(
                    {"error": "El archivo supera el límite de 10 MB."}, status_code=400
                )
    else:
        datos = await leer_json(request)
        cajon = str(datos.get("cajon") or "").strip()
        fecha = str(datos.get("fecha") or "").strip()
        marca = str(datos.get("marca") or "").strip()
        texto = str(datos.get("texto") or "").strip()

    # Validaciones básicas.
    if cajon not in _CAJONES:
        return JSONResponse(
            {"error": f"El cajón es obligatorio y debe ser uno de: {', '.join(_CAJONES)}."},
            status_code=400,
        )
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no válida."}, status_code=400)
    if not fecha:
        fecha = date.today().isoformat()
    if not texto and not archivo_bytes:
        return JSONResponse(
            {"error": "Debes aportar texto o un archivo."}, status_code=400
        )

    # Resuelve el material: archivo tiene prioridad sobre texto.
    if archivo_bytes:
        data = archivo_bytes
        nombre = archivo_nombre
    else:
        data = texto[:_MAX_TEXTO].encode("utf-8", errors="replace")
        nombre = f"texto_{cajon}.txt"

    # Autor de la petición.
    autor = autor_de_peticion(request)
    creado_por = (autor or {}).get("usuario") or (autor or {}).get("id") or ""

    # Crea el lote primero (con estado "listo" provisional).
    lote = repos.crear_insumo_lote(
        fecha=fecha,
        cajon=cajon,
        marca=marca,
        origen_texto=texto[:10000] if not archivo_bytes else "",
        origen_archivo=nombre if archivo_bytes else "",
        estado="listo",
        creado_por=creado_por,
    )
    lote_id = lote["id"]

    # Parsea con Haiku (síncrono).
    items_parseados, errores = insumos_parse.extraer_insumos(
        data,
        nombre=nombre,
        cajon=cajon,
        fecha=fecha,
        lote_id=lote_id,
    )

    if errores and not items_parseados:
        # Fallo total: actualiza el lote como error.
        mensaje_error = "; ".join(e.get("motivo", "error") for e in errores[:3])
        lote = repos.actualizar_insumo_lote(lote_id, {"estado": "error", "error": mensaje_error}) or lote
        return JSONResponse({"lote": _lote_a_dict(lote), "items": []})

    # Inserta los ítems y actualiza el lote.
    items_insertados = repos.crear_insumo_items(items_parseados)
    lote = repos.actualizar_insumo_lote(
        lote_id,
        {"total_items": len(items_insertados), "estado": "listo"},
    ) or lote

    return JSONResponse({
        "lote": _lote_a_dict(lote),
        "items": [_item_a_dict(i) for i in items_insertados],
    })


# --------------------------------------------------------------------------- #
# GET /api/insumos/lote/{id}                                                   #
# --------------------------------------------------------------------------- #


async def detalle_lote(request: Request) -> Response:
    """`GET /api/insumos/lote/{lote_id}` -> {lote, items}."""
    lote_id = request.path_params["lote_id"]
    lote = repos.obtener_insumo_lote(lote_id)
    if lote is None:
        return JSONResponse({"error": "Ese lote no existe."}, status_code=404)
    items = repos.listar_insumo_items(lote_id=lote_id)
    return JSONResponse({
        "lote": _lote_a_dict(lote),
        "items": [_item_a_dict(i) for i in items],
    })


# --------------------------------------------------------------------------- #
# PATCH /api/insumos/item/{id}                                                 #
# --------------------------------------------------------------------------- #


async def editar_item(request: Request) -> Response:
    """`PATCH /api/insumos/item/{item_id}` -> {item}.

    Campos editables: titulo, resumen, marca, linea, hora, lugar, estado_material, tipo.
    """
    item_id = request.path_params["item_id"]
    if repos.obtener_insumo_item(item_id) is None:
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    for campo in _CAMPOS_PATCH_ITEM:
        if campo in datos:
            campos[campo] = datos[campo]
    if "marca" in campos:
        m = campos["marca"]
        if m and m not in _MARCAS_IDS:
            return JSONResponse({"error": "Marca no válida."}, status_code=400)
    if "tipo" in campos and campos["tipo"] not in {"nota", "cobertura", "evento"}:
        return JSONResponse({"error": "Tipo no válido."}, status_code=400)
    if "estado_material" in campos and campos["estado_material"] not in {"tengo", "espero", ""}:
        return JSONResponse({"error": "estado_material no válido."}, status_code=400)
    item = repos.actualizar_insumo_item(item_id, campos)
    if item is None:
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    return JSONResponse({"item": _item_a_dict(item)})


# --------------------------------------------------------------------------- #
# POST /api/insumos/item/{id}/usar                                             #
# --------------------------------------------------------------------------- #


async def usar_item(request: Request) -> Response:
    """`POST /api/insumos/item/{item_id}/usar` -> {item, contenido_id}.

    Lleva el ítem al tablero (`repos.crear_contenido`, origen="insumo",
    flujo="importante"), opcionalmente lanza copy en segundo plano y marca el ítem
    como usado con el `contenido_id` resultante.

    Cuerpo JSON (todo opcional):
      {redes: ["x", ...], generar: bool}
    """
    item_id = request.path_params["item_id"]
    item = repos.obtener_insumo_item(item_id)
    if item is None:
        return JSONResponse({"error": "Ese ítem no existe."}, status_code=404)
    if item.get("usado"):
        # Ya fue llevado al tablero; devuelve el estado actual.
        return JSONResponse({"item": _item_a_dict(item), "contenido_id": item.get("contenido_id", "")})

    datos = await leer_json(request)
    redes_iniciales = _redes_iniciales(datos.get("redes"))
    generar = datos.get("generar", True)
    autor = autor_de_peticion(request)

    # Crea el item del tablero.
    contenido = repos.crear_contenido(
        clase="contenido",
        flujo="importante",
        titulo=item["titulo"],
        descripcion=item.get("resumen", ""),
        marca=item.get("marca", ""),
        prioridad="media",
        fecha_objetivo=item.get("fecha", date.today().isoformat()),
        autor=autor,
        origen="insumo",
        tipo_contenido="fuente",
        notas=f"Cajón: {item.get('cajon', '')} | Línea: {item.get('linea', '')}",
    )
    for red in redes_iniciales:
        repos.crear_contenido_plataforma(
            contenido_id=contenido["id"], red=red, falta_copy=True, falta_imagen=True
        )

    # Copy en segundo plano (best-effort), gateado por marca y por generar.
    genero = False
    if item.get("marca") and generar:
        try:
            genero = autogen_copy.lanzar_para_topic(contenido) is not None
        except Exception:  # noqa: BLE001 -- la generación es opcional
            genero = False

    # Marca el ítem como usado.
    item_actualizado = repos.marcar_insumo_item_usado(item_id, contenido_id=contenido["id"])
    if item_actualizado is None:
        item_actualizado = item

    return JSONResponse({
        "item": _item_a_dict(item_actualizado),
        "contenido_id": contenido["id"],
        "copy_en_proceso": genero,
    })


# --------------------------------------------------------------------------- #
# DELETE /api/insumos/lote/{id}                                                #
# --------------------------------------------------------------------------- #


async def borrar_lote(request: Request) -> Response:
    """`DELETE /api/insumos/lote/{lote_id}` -> {ok: true}. Borra lote + sus ítems."""
    lote_id = request.path_params["lote_id"]
    if not repos.borrar_insumo_lote(lote_id):
        return JSONResponse({"error": "Ese lote no existe."}, status_code=404)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# Rutas                                                                        #
# --------------------------------------------------------------------------- #

RUTAS = [
    Route("/api/insumos", listar, methods=["GET"]),
    Route("/api/insumos/dias", dias, methods=["GET"]),
    Route("/api/insumos/aportar", aportar, methods=["POST"]),
    Route("/api/insumos/lote/{lote_id}", detalle_lote, methods=["GET"]),
    Route("/api/insumos/lote/{lote_id}", borrar_lote, methods=["DELETE"]),
    Route("/api/insumos/item/{item_id}", editar_item, methods=["PATCH"]),
    Route("/api/insumos/item/{item_id}/usar", usar_item, methods=["POST"]),
]
