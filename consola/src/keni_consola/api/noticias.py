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


# Máximo de enlaces corroborantes (fuentes) a exponer en una Historia.
_MAX_ENLACES_HISTORIA = 8


def _historia_a_dict(cluster: dict[str, Any], enlaces: list[dict[str, Any]]) -> dict[str, Any]:
    """Serializa una historia (cluster) a la forma `Historia` (snake_case) del contrato.

    `enlaces` = hasta `_MAX_ENLACES_HISTORIA` items del cluster como fuentes corroborantes
    `{titulo, url, fuente}` (deduplicados por url, preservando orden). `marca_nombre` resuelve
    el nombre humano de la marca dominante.
    """
    vistos: set[str] = set()
    enlaces_pub: list[dict[str, str]] = []
    for it in enlaces:
        url = (it.get("url") or "").strip()
        clave = url.lower() or (it.get("titulo") or "").strip().lower()
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        enlaces_pub.append(
            {
                "titulo": it.get("titulo") or "",
                "url": url,
                "fuente": it.get("fuente_nombre") or "",
            }
        )
        if len(enlaces_pub) >= _MAX_ENLACES_HISTORIA:
            break
    return {
        "id": cluster["id"],
        "titulo": cluster.get("titulo") or "",
        "resumen": cluster.get("resumen") or "",
        "marca": cluster.get("marca") or "",
        "marca_nombre": marcas.etiqueta_de(cluster["marca"]) if cluster.get("marca") else "",
        "categoria": cluster.get("categoria") or "",
        "geo": cluster.get("geo") or "",
        "n_items": int(cluster.get("n_items") or 0),
        "n_fuentes": int(cluster.get("n_fuentes") or 0),
        "idiomas": cluster.get("idiomas") or [],
        "senal": int(cluster.get("senal") or 0),
        "score": float(cluster.get("score") or 0.0),
        "breaking": int(cluster.get("breaking") or 0),
        "primer_visto": cluster.get("primer_visto") or "",
        "ultimo_visto": cluster.get("ultimo_visto") or "",
        "estado": cluster.get("estado") or "nuevo",
        "contenido_id": cluster.get("contenido_id") or "",
        "enlaces": enlaces_pub,
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


# --------------------------------------------------------------------------- #
# HISTORIAS (Ola B): newsroom story view sobre los clusters                     #
# --------------------------------------------------------------------------- #


async def listar_historias(request: Request) -> Response:
    """GET /api/noticias/historias: historias filtrables + paginadas, MÁS RELEVANTES primero.

    Query: `marca` ('' / ausente = todas), `categoria`, `desde` (ISO; `ultimo_visto >= desde`),
    `estado` (nuevo|usado|descartado), `limit`, `offset`. Orden: `score` desc. Devuelve
    `{historias, total}`. Cada historia trae sus enlaces corroborantes (hasta ~8).
    """
    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    estado = (request.query_params.get("estado") or "").strip() or None
    if estado is not None and estado not in repos.ESTADOS_NOTICIA_CLUSTER:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)

    categoria = (request.query_params.get("categoria") or "").strip() or None
    desde = (request.query_params.get("desde") or "").strip() or None

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

    clusters, total = repos.listar_noticia_clusters(
        marca=marca or None,
        categoria=categoria,
        desde=desde,
        estado=estado,
        limite=limite,
        desplazamiento=desplazamiento,
    )
    historias = [
        _historia_a_dict(c, repos.items_de_cluster(c["id"], limite=_MAX_ENLACES_HISTORIA))
        for c in clusters
    ]
    return JSONResponse({"historias": historias, "total": total})


async def detalle_historia(request: Request) -> Response:
    """GET /api/noticias/historias/{id}: la historia + TODOS sus items de archivo."""
    cluster_id = request.path_params["cluster_id"]
    cluster = repos.obtener_noticia_cluster(cluster_id)
    if cluster is None:
        return JSONResponse({"error": "Esa historia ya no existe."}, status_code=404)
    items = repos.items_de_cluster(cluster_id)
    historia = _historia_a_dict(cluster, items)
    return JSONResponse({"historia": historia, "items": [_item_a_dict(it) for it in items]})


async def usar_historia(request: Request) -> Response:
    """POST /api/noticias/historias/{id}/usar: lleva la historia al tablero (borrador).

    Cuerpo `{redes?: [ids], generar?: bool}`. Reusa el camino de la aportación manual: crea un
    `contenido` (`flujo='importante'`, `origen='historia'`, `tipo_contenido='fuente'`) con el
    título/resumen representativos de la historia y sus enlaces corroborantes en la nota; si
    hay marca y `generar` (def True), encola copy. Marca el cluster `usado` + `contenido_id` y
    todos sus items `usado`. Idempotente-amistoso: si ya estaba usado, devuelve lo enlazado.
    """
    cluster_id = request.path_params["cluster_id"]
    cluster = repos.obtener_noticia_cluster(cluster_id)
    if cluster is None:
        return JSONResponse({"error": "Esa historia ya no existe."}, status_code=404)
    if cluster.get("estado") == "usado" and cluster.get("contenido_id"):
        return JSONResponse(
            {
                "contenido": {"id": cluster["contenido_id"]},
                "copy_en_proceso": False,
                "ya_usada": True,
            }
        )

    datos = await leer_json(request)
    redes_iniciales = _redes_iniciales(datos.get("redes"))
    marca = cluster.get("marca") or ""

    items = repos.items_de_cluster(cluster_id, limite=_MAX_ENLACES_HISTORIA)
    titulo = (cluster.get("titulo") or "").strip() or (items[0]["url"] if items else "")
    if not titulo:
        return JSONResponse({"error": "La historia no tiene título ni enlace."}, status_code=400)
    descripcion = (cluster.get("resumen") or "").strip()
    # Enlaces corroborantes en la nota, para trazar las fuentes de la historia.
    fuentes = [it.get("url") for it in items if it.get("url")][:_MAX_ENLACES_HISTORIA]
    if fuentes:
        descripcion = (descripcion + "\n\nFuentes:\n" + "\n".join(fuentes)).strip()

    url_fuente = items[0].get("url_canonica") if items else ""
    fecha_fuente = cluster.get("primer_visto") or ""

    contenido = repos.crear_contenido(
        clase="contenido",
        flujo="importante",
        titulo=titulo[:_MAX_TITULO],
        descripcion=descripcion[:_MAX_TEXTO],
        marca=marca,
        prioridad="media",
        fecha_objetivo=date.today().isoformat(),
        autor=autor_de_peticion(request),
        origen="historia",
        tipo_contenido="fuente",
        fecha_fuente=fecha_fuente,
        url_fuente=url_fuente or "",
    )
    for red in redes_iniciales:
        repos.crear_contenido_plataforma(
            contenido_id=contenido["id"], red=red, falta_copy=True, falta_imagen=True
        )

    generar = datos.get("generar", True)
    genero = False
    if marca and generar:
        try:
            genero = autogen_copy.lanzar_para_topic(contenido) is not None
        except Exception:  # noqa: BLE001 -- la generación es opcional; nunca tumba el uso
            genero = False

    repos.actualizar_noticia_cluster(cluster_id, estado="usado", contenido_id=contenido["id"])
    repos.marcar_items_cluster_usados(cluster_id, contenido["id"])
    plataformas = repos.listar_contenido_plataforma(contenido["id"])
    return JSONResponse(
        {
            "contenido": {**contenido, "plataformas": plataformas},
            "copy_en_proceso": genero,
        }
    )


async def descartar_historia(request: Request) -> Response:
    """POST /api/noticias/historias/{id}/descartar: marca la historia `estado=descartado`."""
    cluster_id = request.path_params["cluster_id"]
    if repos.obtener_noticia_cluster(cluster_id) is None:
        return JSONResponse({"error": "Esa historia ya no existe."}, status_code=404)
    cluster = repos.actualizar_noticia_cluster(cluster_id, estado="descartado")
    items = repos.items_de_cluster(cluster_id, limite=_MAX_ENLACES_HISTORIA) if cluster else []
    return JSONResponse({"historia": _historia_a_dict(cluster, items) if cluster else None})


RUTAS = [
    Route("/api/noticias", listar, methods=["GET"]),
    Route("/api/noticias/cobertura", cobertura, methods=["GET"]),
    Route("/api/noticias/historias", listar_historias, methods=["GET"]),
    Route("/api/noticias/historias/{cluster_id}", detalle_historia, methods=["GET"]),
    Route("/api/noticias/historias/{cluster_id}/usar", usar_historia, methods=["POST"]),
    Route("/api/noticias/historias/{cluster_id}/descartar", descartar_historia, methods=["POST"]),
    Route("/api/noticias/{item_id}/usar", usar, methods=["POST"]),
    Route("/api/noticias/{item_id}/descartar", descartar, methods=["POST"]),
]
