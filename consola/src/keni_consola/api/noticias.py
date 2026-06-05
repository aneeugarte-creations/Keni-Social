"""API del MOTOR DE INGESTA PERSISTENTE (Ola A): archivo de artículos + cobertura.

Superficie de LECTURA del archivo (`noticias_items`) + curación ligera. El motor ingiere en
background (`ingesta_daemon`); aquí el equipo VE el flujo continuo, filtra, y decide qué USA
(lleva al tablero) o DESCARTA. Nada se publica desde aquí.

  - GET  /api/noticias            -> {items:[...], total} filtrable + paginado, recientes 1º.
  - POST /api/noticias/{id}/usar  -> lleva el item al tablero (borrador) + estado=usado.
  - POST /api/noticias/{id}/descartar -> estado=descartado.
  - GET  /api/noticias/cobertura  -> resumen de salud del motor (feeds, items 24h, frescura).

MARCA-AWARE: `marca` filtra el archivo; '' o ausente = todas (vista admin). El alta del
borrador (`usar`) reusa el MISMO camino que la aportación manual (`crear_contenido` +
`autogen_copy.lanzar_para_topic`, `origen='noticia'`). Validación: `marca`/`estado` de
allowlist; SQL parametrizado en `db`. Errores en español, sin tracebacks.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import autogen_copy, marcas, redes, repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion

# Paginación: defecto holgado (el archivo es un flujo continuo) y tope duro defensivo.
_LIMITE_DEFECTO = 50
_LIMITE_MAX = 200
_MAX_TITULO = 300
_MAX_TEXTO = 8000

_MARCAS_IDS = {m[0] for m in marcas.opciones()}


def _validar_marca(valor: Any) -> tuple[str | None, str | None]:
    """`(marca, None)` o `(None, error)`. '' / None = todas (no filtra)."""
    if valor is None:
        return "", None
    if not isinstance(valor, str):
        return None, "La marca debe ser texto."
    valor = valor.strip()
    if valor and valor not in _MARCAS_IDS:
        return None, "Marca no permitida."
    return valor, None


def _redes_iniciales(crudo: Any) -> list[str]:
    """Filtra una lista de ids de red contra las canónicas (sin duplicar, en orden)."""
    if not isinstance(crudo, list):
        return []
    vistas: list[str] = []
    for r in crudo:
        if isinstance(r, str) and redes.es_red(r) and r not in vistas:
            vistas.append(r)
    return vistas


def _item_a_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Serializa un item del archivo resolviendo el nombre humano de la marca."""
    return {
        **item,
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


async def listar(request: Request) -> Response:
    """GET /api/noticias: archivo filtrable + paginado, MÁS NUEVOS primero.

    Query: `marca` ('' / ausente = todas), `categoria`, `desde` (ISO; capturado_en >= desde),
    `q` (búsqueda en titulo+resumen), `estado` (nuevo|usado|descartado), `limit`, `offset`.
    Devuelve `{items, total}` (total = nº que pasa los filtros, para la paginación).
    """
    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    estado = (request.query_params.get("estado") or "").strip() or None
    if estado is not None and estado not in repos.ESTADOS_NOTICIA_ITEM:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)

    categoria = (request.query_params.get("categoria") or "").strip() or None
    desde = (request.query_params.get("desde") or "").strip() or None
    q = (request.query_params.get("q") or "").strip() or None

    try:
        limite = int(request.query_params.get("limit") or _LIMITE_DEFECTO)
    except ValueError:
        limite = _LIMITE_DEFECTO
    limite = max(1, min(limite, _LIMITE_MAX))
    try:
        desplazamiento = int(request.query_params.get("offset") or 0)
    except ValueError:
        desplazamiento = 0
    desplazamiento = max(0, desplazamiento)

    items, total = repos.listar_noticias_items(
        marca=marca or None,
        categoria=categoria,
        desde=desde,
        q=q,
        estado=estado,
        limite=limite,
        desplazamiento=desplazamiento,
    )
    return JSONResponse({"items": [_item_a_dict(it) for it in items], "total": total})


async def usar(request: Request) -> Response:
    """POST /api/noticias/{id}/usar: lleva el item al tablero (borrador) + estado=usado.

    Cuerpo `{redes?: [ids], generar?: bool}`. Reusa el camino de la aportación manual: crea un
    `contenido` (`flujo='importante'`, `origen='noticia'`, `tipo_contenido='fuente'`) con el
    título/resumen/url del item y, si hay marca y `generar` (def True), encola copy en segundo
    plano. Marca el item `estado=usado` + `contenido_id`. Idempotente-amistoso: si ya estaba
    usado, devuelve el contenido enlazado sin duplicar.
    """
    item_id = request.path_params["item_id"]
    item = repos.obtener_noticia_item(item_id)
    if item is None:
        return JSONResponse({"error": "Esa noticia ya no existe."}, status_code=404)
    if item.get("estado") == "usado" and item.get("contenido_id"):
        return JSONResponse(
            {"contenido": {"id": item["contenido_id"]}, "copy_en_proceso": False, "ya_usada": True}
        )

    datos = await leer_json(request)
    redes_iniciales = _redes_iniciales(datos.get("redes"))
    marca = item.get("marca") or ""

    titulo = (item.get("titulo") or "").strip() or (item.get("url") or "")
    if not titulo:
        return JSONResponse({"error": "La noticia no tiene título ni enlace."}, status_code=400)
    descripcion = (item.get("resumen") or "").strip()
    if item.get("url"):
        # Deja el enlace de origen en la nota para trazar la fuente.
        descripcion = (descripcion + f"\n\nFuente: {item['url']}").strip()

    contenido = repos.crear_contenido(
        clase="contenido",
        flujo="importante",
        titulo=titulo[:_MAX_TITULO],
        descripcion=descripcion[:_MAX_TEXTO],
        marca=marca,
        prioridad="media",
        fecha_objetivo=date.today().isoformat(),
        autor=autor_de_peticion(request),
        origen="noticia",
        tipo_contenido="fuente",
        fecha_fuente=item.get("publicado_en") or "",
        url_fuente=item.get("url_canonica") or "",
    )
    for red in redes_iniciales:
        repos.crear_contenido_plataforma(
            contenido_id=contenido["id"], red=red, falta_copy=True, falta_imagen=True
        )

    # Copy en segundo plano (best-effort), gateado por marca + flag `generar` (def True).
    generar = datos.get("generar", True)
    genero = False
    if marca and generar:
        try:
            genero = autogen_copy.lanzar_para_topic(contenido) is not None
        except Exception:  # noqa: BLE001 -- la generación es opcional; nunca tumba el uso
            genero = False

    repos.actualizar_noticia_item(item_id, estado="usado", contenido_id=contenido["id"])
    plataformas = repos.listar_contenido_plataforma(contenido["id"])
    return JSONResponse(
        {
            "contenido": {**contenido, "plataformas": plataformas},
            "copy_en_proceso": genero,
        }
    )


async def descartar(request: Request) -> Response:
    """POST /api/noticias/{id}/descartar: marca el item `estado=descartado`."""
    item_id = request.path_params["item_id"]
    if repos.obtener_noticia_item(item_id) is None:
        return JSONResponse({"error": "Esa noticia ya no existe."}, status_code=404)
    item = repos.actualizar_noticia_item(item_id, estado="descartado")
    return JSONResponse({"item": _item_a_dict(item) if item else None})


async def cobertura(request: Request) -> Response:
    """GET /api/noticias/cobertura: resumen de salud del motor de ingesta."""
    return JSONResponse(repos.resumen_cobertura())


RUTAS = [
    Route("/api/noticias", listar, methods=["GET"]),
    Route("/api/noticias/cobertura", cobertura, methods=["GET"]),
    Route("/api/noticias/{item_id}/usar", usar, methods=["POST"]),
    Route("/api/noticias/{item_id}/descartar", descartar, methods=["POST"]),
]
