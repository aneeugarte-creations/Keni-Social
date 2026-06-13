"""Pool de ÍTEMS del archivo (Ola A) + monitor de COBERTURA / SALUD de fuentes (Ola D).

Superficie de LECTURA del archivo (`noticias_items`) + curación ligera por item: el equipo
VE el flujo continuo, filtra, y decide qué USA (lleva al tablero) o DESCARTA. Aquí viven los
handlers a nivel de ITEM (`listar`/`usar`/`descartar`) y el monitor de salud de fuentes
(`cobertura`/`salud`/`stats_fuentes_handler`) con sus helpers puros (`_frescura_min`,
`construir_salud`). Las HISTORIAS (clusters) viven en `historias.py`. Nada se publica desde aquí.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import autogen_copy, config, marcas, repos
from ..._http_json import leer_json
from ...seguridad import autor_de_peticion
from ...tiempo import hoy_utc
from ._comun import (
    _LIMITE_DEFECTO,
    _LIMITE_MAX,
    _MAX_TEXTO,
    _MAX_TITULO,
    _item_a_dict,
    _redes_iniciales,
    _validar_marca,
)


async def listar(request: Request) -> Response:
    """GET /api/noticias: archivo filtrable + paginado, MÁS NUEVOS primero.

    Query: `marca` ('' / ausente = todas), `desde` (ISO; capturado_en >= desde), `q` (búsqueda en
    titulo+resumen), `estado` (nuevo|usado|descartado), `limit`, `offset`. Ya NO se filtra por
    `categoria` (el eje es marca/línea editorial). Devuelve `{items, total}`.
    """
    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    estado = (request.query_params.get("estado") or "").strip() or None
    if estado is not None and estado not in repos.ESTADOS_NOTICIA_ITEM:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)

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
        # LÍNEA del plan: la categoría del ITEM (un item suelto no tiene señal de breaking).
        categoria=str(item.get("categoria") or "").strip().lower(),
        titulo=titulo[:_MAX_TITULO],
        descripcion=descripcion[:_MAX_TEXTO],
        marca=marca,
        prioridad="media",
        fecha_objetivo=hoy_utc().isoformat(),
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
# Monitor de COBERTURA / SALUD de fuentes a escala (Ola D)                      #
# --------------------------------------------------------------------------- #


def _frescura_min(ultimo_item: str, *, ahora: datetime) -> int | None:
    """Minutos transcurridos desde el último item de un feed (None si nunca capturó nada).

    Best-effort: un timestamp no parseable cuenta como "sin frescura conocida" (None). Acota a
    >= 0 (un reloj adelantado no produce frescuras negativas).
    """
    if not ultimo_item:
        return None
    try:
        dt = datetime.fromisoformat(ultimo_item)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return max(0, int((ahora - dt).total_seconds() // 60))


def construir_salud(
    feeds: list[dict[str, Any]],
    distribuciones: dict[str, dict[str, int]],
    *,
    sla_min: int,
    ahora: datetime,
) -> dict[str, Any]:
    """Arma el payload de `/api/noticias/salud` (PURA: sin BD ni reloj propio). Ver contrato.

    `feeds` = filas de `repos.salud_feeds` (cada una con `items_24h` + `ultimo_item`).
    `distribuciones` = `repos.conteos_items_recientes` (`por_categoria` / `por_idioma`).
    Deriva por feed `frescura_min` (minutos desde el último item) y, en el resumen, el nº de
    feeds `stale` (activos sin items nuevos en > `sla_min`), `huecos` (categorías presentes en
    feeds activos pero SIN items frescos en 24h) y `frescura_global_min` (el feed activo más
    fresco). Determinista para los mismos datos.
    """
    por_categoria = distribuciones.get("por_categoria") or {}
    por_idioma = distribuciones.get("por_idioma") or {}

    feeds_pub: list[dict[str, Any]] = []
    activos = 0
    auto_desactivados = 0
    fallando = 0
    stale = 0
    items_24h_total = 0
    frescuras_activas: list[int] = []
    # Categorías esperadas = las que cubren feeds ACTIVOS; un hueco es una esperada sin items 24h.
    categorias_esperadas: set[str] = set()

    for f in feeds:
        es_activo = bool(f.get("activo"))
        es_auto = bool(f.get("desactivado_auto"))
        ultimo_item = str(f.get("ultimo_item") or "")
        fmin = _frescura_min(ultimo_item, ahora=ahora)
        items_24h = int(f.get("items_24h") or 0)
        items_24h_total += items_24h
        if es_activo:
            activos += 1
            categoria = str(f.get("categoria") or "")
            categorias_esperadas.add(categoria)
            if fmin is not None:
                frescuras_activas.append(fmin)
            if fmin is None or fmin > sla_min:
                stale += 1
        if es_auto:
            auto_desactivados += 1
        if (f.get("ultimo_error") or "").strip():
            fallando += 1

        feeds_pub.append(
            {
                "id": f.get("id") or "",
                "nombre": f.get("nombre") or "",
                "categoria": f.get("categoria") or "",
                "marca": f.get("marca") or "",
                "marca_nombre": marcas.etiqueta_de(f["marca"]) if f.get("marca") else "",
                "activo": es_activo,
                "desactivado_auto": es_auto,
                "ultima_actualizacion": f.get("ultima_actualizacion") or "",
                "ultimo_error": f.get("ultimo_error") or "",
                "errores_seguidos": int(f.get("errores_seguidos") or 0),
                "items_24h": items_24h,
                "frescura_min": fmin,
                # Filtro de ENTRADA por agenda de marca: descartados en el último sondeo.
                "ultimo_filtrados": int(f.get("ultimo_filtrados") or 0),
            }
        )

    # Huecos: categoría esperada (de un feed activo) sin items frescos en 24h. Normaliza el ''
    # de un feed sin categoría a la misma etiqueta que usan las distribuciones.
    cats_con_items = {c for c, n in por_categoria.items() if n > 0}
    huecos: list[str] = []
    for cat in sorted(categorias_esperadas):
        etiqueta = cat or "(sin categoría)"
        if etiqueta not in cats_con_items:
            huecos.append(etiqueta)

    return {
        "resumen": {
            "feeds_total": len(feeds),
            "activos": activos,
            "auto_desactivados": auto_desactivados,
            "fallando": fallando,
            "stale": stale,
            "items_24h": items_24h_total,
            "por_categoria": por_categoria,
            "por_idioma": por_idioma,
            "huecos": huecos,
            "frescura_global_min": min(frescuras_activas) if frescuras_activas else None,
        },
        "feeds": feeds_pub,
    }


async def stats_fuentes_handler(request: Request) -> Response:
    """GET /api/noticias/fuentes/stats?marca=&dias=: RENDIMIENTO editorial por fuente.

    Para evaluar fuentes: cuántas historias aporta cada una, cuántas ABRIÓ (publicó primero),
    cuántas acabaron usadas (promovidas al tablero) y su tasa de uso. `dias` acota la ventana
    (def 7, máx 90). Marca-aware (items de la marca + compartidos). Orden: más historias 1º.
    """
    from ...dominio import fuentes_pesos

    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    try:
        dias = int(request.query_params.get("dias") or 7)
    except ValueError:
        dias = 7
    dias = max(1, min(dias, 90))
    fuentes = []
    for f in repos.stats_fuentes(marca or None, dias=dias):
        historias = int(f.get("historias") or 0)
        usadas = int(f.get("usadas") or 0)
        fuentes.append(
            {
                **f,
                "tier": fuentes_pesos.tier_de_peso(float(f.get("peso") or 1.0)),
                "tasa_uso": round(usadas / historias, 3) if historias else 0.0,
            }
        )
    return JSONResponse({"fuentes": fuentes, "dias": dias})


async def salud(request: Request) -> Response:
    """GET /api/noticias/salud?marca=: monitor de cobertura a escala (Ola D).

    Resumen + salud por feed: items 24h, frescura (min desde el último item), stale (SLA),
    huecos de cobertura, distribuciones por categoría/idioma. Marca-aware (`?marca=`).
    """
    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    feeds = repos.salud_feeds(marca or None)
    distribuciones = repos.conteos_items_recientes(marca or None, horas=24)
    payload = construir_salud(
        feeds,
        distribuciones,
        sla_min=config.feed_sla_min(),
        ahora=datetime.now(UTC),
    )
    return JSONResponse(payload)
