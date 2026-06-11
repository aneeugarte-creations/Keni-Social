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

from datetime import UTC, datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import autogen_copy, config, estados, marcas, redes, repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion
from ..tiempo import hoy_utc

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
    """Serializa un item del archivo resolviendo el nombre humano de la marca y su tier."""
    from ..dominio import fuentes_pesos

    return {
        **item,
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
        # Tier legible del peso de la fuente (potente/normal/baja): para el timeline del detalle.
        "tier": fuentes_pesos.tier_de_peso(float(item.get("fuente_peso") or 1.0)),
    }


# Máximo de enlaces corroborantes (fuentes) a exponer en una Historia.
_MAX_ENLACES_HISTORIA = 8


def _fuentes_timeline(detalle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Timeline de outlets de una historia (de `fuentes_detalle` persistido) para la UI.

    Cada entrada: `{fuente, fuente_id, peso, tier, primer_visto, n_items}` en orden
    cronológico (el primero ABRIÓ la historia). Best-effort: entradas malformadas se saltan.
    """
    from ..dominio import fuentes_pesos

    salida: list[dict[str, Any]] = []
    for d in detalle:
        if not isinstance(d, dict):
            continue
        try:
            peso = float(d.get("peso") or 1.0)
        except (TypeError, ValueError):
            peso = 1.0
        salida.append(
            {
                "fuente": str(d.get("fuente") or ""),
                "fuente_id": str(d.get("fuente_id") or ""),
                "peso": peso,
                "tier": fuentes_pesos.tier_de_peso(peso),
                "primer_visto": str(d.get("primer_visto") or ""),
                "n_items": int(d.get("n_items") or 0),
            }
        )
    return salida


def _pieza_estado(estado: str, contenido_id: str, resumen: dict[str, str]) -> str:
    """Estado REAL de la historia DE CARA AL FEED, derivado de la pieza (no solo del cluster).

    El cluster `usado` significa "promovida a la máquina de contenido", NO "en el feed": la
    pieza sale REAL en el feed solo cuando existe su fila `contenido_plataforma` CON copy. Para
    que el badge no mienta, derivamos 5 estados:
      - 'en_pool'    -> aún no promovida (cluster 'nuevo'),
      - 'descartada' -> cluster 'descartado',
      - 'en_cola'    -> promovida pero SIN pieza en el feed todavía (dedup, sin redes, o copy
                        aún por encolar / etapa de copy detenida),
      - 'generando'  -> pieza creada, copy en proceso (fila sin `copy` aún),
      - 'en_feed'    -> pieza con copy: visible REAL en el feed.
    `resumen` = mapa `contenido_id -> 'lista'|'generando'` de `repos.estado_pieza_por_contenido`.
    """
    if estado == "descartado":
        return "descartada"
    if estado != "usado":
        return "en_pool"
    pieza = resumen.get(contenido_id) if contenido_id else None
    if pieza == "lista":
        return "en_feed"
    if pieza == "generando":
        return "generando"
    return "en_cola"


def _pieza_estado_de(cluster: dict[str, Any]) -> str:
    """`_pieza_estado` para UN cluster (un lookup); en listados usa la versión batch."""
    cid = cluster.get("contenido_id") or ""
    return _pieza_estado(
        cluster.get("estado") or "nuevo", cid, repos.estado_pieza_por_contenido([cid])
    )


def _evaluar_liston(
    cluster: dict[str, Any], vocab_memo: dict[str, frozenset[str]]
) -> tuple[bool, str]:
    """Listón de producción automática de UNA historia, con memo de vocabulario por marca.

    La MISMA evaluación que usa la promoción CI (`noticias_liston.evaluar`): el panel nunca
    dice una cosa y el pipeline hace otra. `vocab_memo` evita releer el cache del perfil
    editorial por cada historia del listado. Best-effort: ante un fallo se reporta NO
    promovible con motivo genérico (el panel no casca por una historia rara).
    """
    from .. import noticias_liston

    try:
        marca = str(cluster.get("marca") or "")
        if marca not in vocab_memo:
            vocab_memo[marca] = noticias_liston.palabras_relevancia(marca)
        return noticias_liston.evaluar(cluster, palabras_marca=vocab_memo[marca])
    except Exception:  # noqa: BLE001 -- la explicación es informativa; nunca rompe el listado
        return False, "no evaluable"


def _pesos_score_publicos() -> dict[str, float]:
    """Los PESOS vivos de la fórmula del ranking, para que la UI enseñe el cálculo.

    El `score_desglose` persistido trae las señales CRUDAS [0,1]; con los pesos (editables
    en caliente desde ajustes) la UI reconstruye la fórmula completa: señal × peso = aporte,
    Σ aportes = score. Sin esto el ranking sería una caja negra de cara al equipo.
    """
    p = config.score_pesos()
    return {
        "corroboracion": round(p.corroboracion, 3),
        "velocidad": round(p.velocidad, 3),
        "frescura": round(p.frescura, 3),
        "viralidad": round(p.viralidad, 3),
        "marca": round(p.marca, 3),
        "rendimiento": round(p.rendimiento, 3),
        "breaking": round(p.breaking, 3),
    }


def _historia_a_dict(
    cluster: dict[str, Any],
    enlaces: list[dict[str, Any]],
    *,
    pieza_estado: str = "en_pool",
    liston: tuple[bool, str] | None = None,
) -> dict[str, Any]:
    """Serializa una historia (cluster) a la forma `Historia` (snake_case) del contrato.

    `enlaces` = hasta `_MAX_ENLACES_HISTORIA` items del cluster como fuentes corroborantes
    `{titulo, url, fuente}` (deduplicados por url, preservando orden). `marca_nombre` resuelve
    el nombre humano de la marca dominante.

    TRADUCCIÓN (Ola D): si la historia está `traducido`, se sirve `titulo`/`resumen` YA en ES
    (`titulo_es`/`resumen_es`) y se exponen `titulo_original`/`idioma`/`traducido` para que la UI
    pueda mostrar "traducido de {idioma}". Si no, se sirven los originales. `verificacion` expone
    el veredicto de corroboración (corroborada / unica_fuente / dudosa).
    """
    from ..dominio import fuentes_pesos

    vistos: set[str] = set()
    enlaces_pub: list[dict[str, Any]] = []
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
                # Cuándo publicó este enlace y el tier de su fuente: la UI arma con esto la
                # frase de corroboración ("la abrió Reuters hace 42 min") sin pedir el detalle.
                "publicado_en": it.get("publicado_en") or it.get("capturado_en") or "",
                "tier": fuentes_pesos.tier_de_peso(float(it.get("fuente_peso") or 1.0)),
            }
        )
        if len(enlaces_pub) >= _MAX_ENLACES_HISTORIA:
            break

    traducido = bool(cluster.get("traducido"))
    titulo_original = cluster.get("titulo") or ""
    resumen_original = cluster.get("resumen") or ""
    if traducido:
        titulo = (cluster.get("titulo_es") or "").strip() or titulo_original
        resumen = (cluster.get("resumen_es") or "").strip() or resumen_original
        # `titulo_original` persistido tiene prioridad (es el de antes de traducir).
        titulo_original = cluster.get("titulo_original") or titulo_original
    else:
        titulo = titulo_original
        resumen = resumen_original

    return {
        "id": cluster["id"],
        "titulo": titulo,
        "resumen": resumen,
        "marca": cluster.get("marca") or "",
        "marca_nombre": marcas.etiqueta_de(cluster["marca"]) if cluster.get("marca") else "",
        "categoria": cluster.get("categoria") or "",
        "geo": cluster.get("geo") or "",
        "n_items": int(cluster.get("n_items") or 0),
        "n_fuentes": int(cluster.get("n_fuentes") or 0),
        "idiomas": cluster.get("idiomas") or [],
        "senal": int(cluster.get("senal") or 0),
        "score": float(cluster.get("score") or 0.0),
        # Relevancia EXPLICABLE: la razón humana del score y su desglose por señal (los
        # persiste el daemon al puntuar; ver `clustering.puntuar_detalle`).
        "score_razon": cluster.get("score_razon") or "",
        "score_desglose": cluster.get("score_desglose") or {},
        # LISTÓN de producción automática (la MISMA evaluación que la promoción CI): si esta
        # historia dispararía QA+copy solos, y el porqué (o el porqué no), legible.
        "promovible": bool(liston[0]) if liston else False,
        "promovible_motivo": (liston[1] if liston else ""),
        "breaking": int(cluster.get("breaking") or 0),
        "verificacion": cluster.get("verificacion") or "unica_fuente",
        # Etapas de INVESTIGACIÓN visibles por historia (ADR 0011): el veredicto de
        # VERIFICACIÓN (QA de la fuente, del contenido asociado; lo inyecta el llamante en
        # lote) y si la MARCA la asignó el clasificador IA.
        "qa_veredicto": cluster.get("qa_veredicto") or "",
        "marca_clasificada_por_ia": bool(cluster.get("marca_clasificada_por_ia")),
        "traducido": traducido,
        "idioma": cluster.get("idioma") or "",
        "titulo_original": titulo_original,
        "primer_visto": cluster.get("primer_visto") or "",
        "ultimo_visto": cluster.get("ultimo_visto") or "",
        "estado": cluster.get("estado") or "nuevo",
        "contenido_id": cluster.get("contenido_id") or "",
        # Estado REAL de cara al feed (derivado de la pieza, no solo del cluster). El front
        # pinta el badge con ESTE campo: nunca dice "En el feed" si la pieza no está.
        "pieza_estado": pieza_estado,
        "enlaces": enlaces_pub,
        # Los PESOS vivos de la fórmula (editables en ajustes): con las señales crudas del
        # desglose, la UI enseña el cálculo completo (señal × peso = aporte, Σ = score).
        "score_pesos": _pesos_score_publicos(),
        # TRACKING DE FUENTES (ranking ponderado): masa de corroboración (Σ peso por outlet),
        # quién ABRIÓ la historia y el timeline de outlets (orden cronológico, con peso/tier).
        "peso_fuentes": float(cluster.get("peso_fuentes") or 0.0),
        "velocidad": float(cluster.get("velocidad") or 0.0),
        "primera_fuente_nombre": cluster.get("primera_fuente_nombre") or "",
        "fuentes": _fuentes_timeline(cluster.get("fuentes_detalle") or []),
    }


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
    from ..dominio import fuentes_pesos

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


# --------------------------------------------------------------------------- #
# HISTORIAS (Ola B): newsroom story view sobre los clusters                     #
# --------------------------------------------------------------------------- #


async def listar_historias(request: Request) -> Response:
    """GET /api/noticias/historias: historias filtrables + paginadas, MÁS RELEVANTES primero.

    Query: `marca` ('' / ausente = todas), `desde` (ISO; `ultimo_visto >= desde`), `estado`
    (nuevo|usado|descartado), `limit`, `offset`. Orden: `score` desc (jerarquización por el
    algoritmo de ponderación), `ultimo_visto` desc como desempate. Ya NO se filtra por `categoria`
    (el eje es marca/línea editorial). Devuelve `{historias, total}` con enlaces corroborantes.
    """
    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    estado = (request.query_params.get("estado") or "").strip() or None
    if estado is not None and estado not in repos.ESTADOS_NOTICIA_CLUSTER:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)

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
        desde=desde,
        estado=estado,
        limite=limite,
        desplazamiento=desplazamiento,
    )
    # Estado REAL de cara al feed + veredicto QA (verificación). El QA vive en la HISTORIA
    # (`noticias_clusters.qa_veredicto`, ADR 0011 F3): la criba corre sobre el cluster ANTES de
    # admitir. Se prefiere el veredicto NATIVO del cluster y se cae al del `contenido` heredado
    # (batch, evita N+1) solo para historias admitidas ANTES de F3 (cluster sin veredicto propio).
    cids = [c.get("contenido_id") or "" for c in clusters]
    resumen_pieza = repos.estado_pieza_por_contenido(cids)
    qa_map = repos.qa_veredicto_por_contenido(cids)
    vocab_memo: dict[str, frozenset[str]] = {}  # vocabulario por marca, 1 lectura por request
    historias = [
        _historia_a_dict(
            {**c, "qa_veredicto": (c.get("qa_veredicto") or "") or qa_map.get(c.get("contenido_id") or "", "")},
            repos.items_de_cluster(c["id"], limite=_MAX_ENLACES_HISTORIA),
            pieza_estado=_pieza_estado(
                c.get("estado") or "nuevo", c.get("contenido_id") or "", resumen_pieza
            ),
            liston=_evaluar_liston(c, vocab_memo),
        )
        for c in clusters
    ]
    return JSONResponse({"historias": historias, "total": total})


# Historias por línea en la respuesta de la Mesa (top-N por sección; "Ver todas" pagina
# contra /historias con su filtro). Tope defensivo del query param.
_MESA_POR_LINEA_DEF = 5
_MESA_POR_LINEA_MAX = 20
# Muestra del pool que se reparte por línea (el pool viene rankeado por score: con cientos
# de historias vivas la muestra cubre de sobra el top de cada línea).
_MESA_MUESTRA = 300


async def mesa(request: Request) -> Response:
    """GET /api/noticias/mesa?marca=&por_linea=: el pool SEGMENTADO por las líneas del plan.

    La vista de trabajo de la Mesa de redacción: para una marca concreta devuelve sus líneas
    del plan editorial diario (cupo, generados/publicados en 24 h móviles, restante) con las
    top-N candidatas (`estado='nuevo'`) de cada una, más el bloque `fuera_de_plan` (líneas de
    feed que el plan no contempla). Una historia compite por la línea de su
    `categoria_efectiva` ('breaking' si lo es — el MISMO criterio que la admisión CI).
    Sin plan configurado: `plan=false` y todo el pool va en `fuera_de_plan` (la UI degrada a
    lista plana). Orden de líneas: breaking primero, luego el orden del plan.
    """
    from ..pipeline_contenido import _ingesta as _pc_ingesta
    from ..tiempo import inicio_dia_cdmx_iso_utc

    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    if not marca:
        return JSONResponse(
            {"error": "La mesa es por marca: elige una marca concreta."}, status_code=400
        )
    try:
        por_linea = int(request.query_params.get("por_linea") or _MESA_POR_LINEA_DEF)
    except ValueError:
        por_linea = _MESA_POR_LINEA_DEF
    por_linea = max(1, min(por_linea, _MESA_POR_LINEA_MAX))

    plan = config.plan_dia(marca)  # dict ordenado categoria -> cupo ({} sin plan)
    resumen_plan: dict[str, dict[str, int]] = {}
    if plan:
        try:
            # Por JORNADA MX (la parrilla del día): a medianoche de México vuelve a 0.
            resumen_plan = repos.resumen_plan_por_categoria(
                marca, inicio_dia_cdmx_iso_utc()
            )
        except Exception:  # noqa: BLE001 -- sin contador, la mesa muestra progreso 0 (no casca)
            resumen_plan = {}

    clusters, _total = repos.listar_noticia_clusters(
        marca=marca, estado="nuevo", limite=_MESA_MUESTRA
    )
    # Reparto por línea (el pool ya viene ordenado por score: cada lista queda rankeada).
    por_linea_pool: dict[str, list[dict[str, Any]]] = {}
    for c in clusters:
        cat = _pc_ingesta.categoria_efectiva(c)
        destino = cat if cat in plan else "__fuera__"
        por_linea_pool.setdefault(destino, []).append(c)

    cids = [c.get("contenido_id") or "" for c in clusters]
    resumen_pieza = repos.estado_pieza_por_contenido(cids)
    # Veredicto de verificación por historia: NATIVO del cluster (ADR 0011 F3), con fallback al
    # contenido heredado para historias admitidas antes de F3 (cluster sin veredicto propio).
    qa_map = repos.qa_veredicto_por_contenido(cids)
    vocab_memo: dict[str, frozenset[str]] = {}

    def _historias(lote: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            _historia_a_dict(
                {**c, "qa_veredicto": (c.get("qa_veredicto") or "") or qa_map.get(c.get("contenido_id") or "", "")},
                repos.items_de_cluster(c["id"], limite=_MAX_ENLACES_HISTORIA),
                pieza_estado=_pieza_estado(
                    c.get("estado") or "nuevo", c.get("contenido_id") or "", resumen_pieza
                ),
                liston=_evaluar_liston(c, vocab_memo),
            )
            for c in lote[:por_linea]
        ]

    # Breaking primero (si el plan lo contempla), luego el orden del plan.
    orden = (["breaking"] if "breaking" in plan else []) + [c for c in plan if c != "breaking"]
    lineas = []
    total_generados = 0
    for cat in orden:
        contadores = resumen_plan.get(cat, {})
        generados = int(contadores.get("generados", 0))
        total_generados += generados
        pool = por_linea_pool.get(cat, [])
        lineas.append(
            {
                "linea": cat,
                "cupo": int(plan[cat]),
                "generados": generados,
                "publicados": int(contadores.get("publicados", 0)),
                "restante": max(0, int(plan[cat]) - generados),
                "en_pool": len(pool),
                "historias": _historias(pool),
            }
        )
    fuera = por_linea_pool.get("__fuera__", [])
    return JSONResponse(
        {
            "marca": marca,
            "plan": bool(plan),
            "lineas": lineas,
            "fuera_de_plan": {"en_pool": len(fuera), "historias": _historias(fuera)},
            "total_objetivo": sum(int(v) for v in plan.values()),
            "total_generados": total_generados,
        }
    )


async def detalle_historia(request: Request) -> Response:
    """GET /api/noticias/historias/{id}: la historia + TODOS sus items de archivo."""
    cluster_id = request.path_params["cluster_id"]
    cluster = repos.obtener_noticia_cluster(cluster_id)
    if cluster is None:
        return JSONResponse({"error": "Esa historia ya no existe."}, status_code=404)
    items = repos.items_de_cluster(cluster_id)
    cid = cluster.get("contenido_id") or ""
    # Veredicto NATIVO del cluster (ADR 0011 F3: la QA corre sobre la historia); fallback al
    # contenido heredado para historias admitidas antes de F3 (cluster sin veredicto propio).
    qa_veredicto = (cluster.get("qa_veredicto") or "") or (
        repos.qa_veredicto_por_contenido([cid]).get(cid, "") if cid else ""
    )
    historia = _historia_a_dict(
        {**cluster, "qa_veredicto": qa_veredicto}, items, pieza_estado=_pieza_estado_de(cluster),
        liston=_evaluar_liston(cluster, {}),
    )
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

    from ..pipeline_contenido import _ingesta as _pc_ingesta

    contenido = repos.crear_contenido(
        clase="contenido",
        flujo="importante",
        # LÍNEA del plan con la que nació ('breaking' si lo era): la curación humana también
        # consume su cupo del plan y hereda los horarios de su categoría.
        categoria=_pc_ingesta.categoria_efectiva(cluster),
        titulo=titulo[:_MAX_TITULO],
        descripcion=descripcion[:_MAX_TEXTO],
        marca=marca,
        prioridad="media",
        fecha_objetivo=hoy_utc().isoformat(),
        autor=autor_de_peticion(request),
        origen=estados.ORIGEN_HISTORIA,
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
    historia = (
        _historia_a_dict(cluster, items, pieza_estado=_pieza_estado_de(cluster))
        if cluster
        else None
    )
    return JSONResponse({"historia": historia})


async def restaurar_historia(request: Request) -> Response:
    """POST /api/noticias/historias/{id}/restaurar: devuelve una DESCARTADA al pool.

    El deshacer del flujo rápido de curación (descartar es 1 clic sin confirmación porque
    existe esto). Solo restaura historias `descartado` sin contenido enlazado; una `usado`
    ya vive en el tablero (404/400 explicables). Idempotente-amistoso: restaurar una que ya
    está `nuevo` devuelve la historia tal cual.
    """
    cluster_id = request.path_params["cluster_id"]
    cluster = repos.obtener_noticia_cluster(cluster_id)
    if cluster is None:
        return JSONResponse({"error": "Esa historia ya no existe."}, status_code=404)
    estado = cluster.get("estado") or "nuevo"
    if estado == "usado" or (cluster.get("contenido_id") or ""):
        return JSONResponse(
            {"error": "Esa historia ya se usó: vive en el tablero, no en el pool."},
            status_code=400,
        )
    if estado == "descartado":
        cluster = repos.actualizar_noticia_cluster(cluster_id, estado="nuevo") or cluster
    items = repos.items_de_cluster(cluster_id, limite=_MAX_ENLACES_HISTORIA)
    historia = _historia_a_dict(
        cluster, items, pieza_estado=_pieza_estado_de(cluster),
        liston=_evaluar_liston(cluster, {}),
    )
    return JSONResponse({"historia": historia})


# Tope de ids por lote, para que un cuerpo enorme no dispare un barrido de updates sin control.
_MAX_LOTE_DESCARTE = 500


async def descartar_historias_lote(request: Request) -> Response:
    """POST /api/noticias/historias/descartar-lote: descarta VARIAS historias de una (papelera).

    Cuerpo `{ids: [cluster_id, ...]}`. Marca cada cluster existente `estado=descartado`
    (idempotente: ignora silenciosamente los ids vacíos, repetidos o que ya no existen). Es el
    motor del multi-selección estilo correo de Investigación: seleccionar (o "todos") + descartar.
    Devuelve `{descartadas: n}` (cuántas se marcaron de verdad).
    """
    datos = await leer_json(request)
    ids = datos.get("ids")
    if not isinstance(ids, list):
        return JSONResponse({"error": "Se esperaba una lista de ids."}, status_code=400)
    descartadas = 0
    for cid in dict.fromkeys(ids):  # dedup preservando orden; evita doble update del mismo id
        if not isinstance(cid, str) or not cid:
            continue
        if descartadas >= _MAX_LOTE_DESCARTE:
            break
        if repos.obtener_noticia_cluster(cid) is None:
            continue
        repos.actualizar_noticia_cluster(cid, estado="descartado")
        descartadas += 1
    return JSONResponse({"descartadas": descartadas})


async def borrar_historias_lote(request: Request) -> Response:
    """POST /api/noticias/historias/borrar-lote: BORRA HARD (irreversible) varias historias + artículos.

    Cuerpo `{ids: [cluster_id, ...]}`. A diferencia de `descartar-lote` (que solo marca el estado),
    esto ELIMINA del archivo el cluster Y sus `noticias_items` (si no, el clustering los reagrupa y
    la historia reaparece). Idempotente; tope de seguridad `_MAX_LOTE_DESCARTE`. Devuelve `{borradas:n}`.
    """
    datos = await leer_json(request)
    ids = datos.get("ids")
    if not isinstance(ids, list):
        return JSONResponse({"error": "Se esperaba una lista de ids."}, status_code=400)
    limpios = [c for c in ids if isinstance(c, str) and c][:_MAX_LOTE_DESCARTE]
    borradas = repos.borrar_clusters_con_items(limpios)
    return JSONResponse({"borradas": borradas})


async def borrar_todas_historias(request: Request) -> Response:
    """POST /api/noticias/historias/borrar-todo: VACÍA (hard, irreversible) el pool — "dejar a 0".

    Cuerpo `{marca?, estado?}`. Borra todas las historias que casan marca/estado Y sus artículos.
    Con `marca` (lo normal, la marca activa) vacía SOLO esa marca; sin `marca`, TODAS. `estado`
    (opcional) limita a un estado (respeta el filtro de la vista). Devuelve `{borradas:n}`.
    """
    datos = await leer_json(request)
    marca = (datos.get("marca") or "").strip() or None
    if marca is not None and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    estado = (datos.get("estado") or "").strip() or None
    if estado is not None and estado not in repos.ESTADOS_NOTICIA_CLUSTER:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)
    borradas = repos.vaciar_clusters(marca, estado)
    return JSONResponse({"borradas": borradas})


RUTAS = [
    Route("/api/noticias", listar, methods=["GET"]),
    Route("/api/noticias/cobertura", cobertura, methods=["GET"]),
    Route("/api/noticias/salud", salud, methods=["GET"]),
    # Rendimiento editorial por fuente (tracking de fuentes). ANTES de `/{item_id}/...` para
    # que `fuentes` nunca se interprete como un item_id.
    Route("/api/noticias/fuentes/stats", stats_fuentes_handler, methods=["GET"]),
    Route("/api/noticias/historias", listar_historias, methods=["GET"]),
    # La Mesa de redacción: pool segmentado por las líneas del plan + progreso del día.
    Route("/api/noticias/mesa", mesa, methods=["GET"]),
    # Los lotes van ANTES de `/historias/{cluster_id}` para que `descartar-lote`/`borrar-lote`/
    # `borrar-todo` no se confundan con un cluster_id (difieren en método, pero el orden lo deja
    # explícito y a prueba de futuros GET).
    Route("/api/noticias/historias/descartar-lote", descartar_historias_lote, methods=["POST"]),
    Route("/api/noticias/historias/borrar-lote", borrar_historias_lote, methods=["POST"]),
    Route("/api/noticias/historias/borrar-todo", borrar_todas_historias, methods=["POST"]),
    Route("/api/noticias/historias/{cluster_id}", detalle_historia, methods=["GET"]),
    Route("/api/noticias/historias/{cluster_id}/usar", usar_historia, methods=["POST"]),
    Route("/api/noticias/historias/{cluster_id}/descartar", descartar_historia, methods=["POST"]),
    Route("/api/noticias/historias/{cluster_id}/restaurar", restaurar_historia, methods=["POST"]),
    Route("/api/noticias/{item_id}/usar", usar, methods=["POST"]),
    Route("/api/noticias/{item_id}/descartar", descartar, methods=["POST"]),
]
