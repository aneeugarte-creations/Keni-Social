"""CI — ingesta de fuentes: SELECCIÓN pura de items + creación de temas (sin copy).

Lee los feeds RSS activos de una marca, elige items frescos (no usados, deduplicados) y crea un
`contenido` (tema) por item SIN generar copy todavía: el copy se redacta después en la fase CD,
y solo si la QA de la fuente pasa. Marca los items usados (dedup) y registra la etapa CI.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .. import config, marcas, redes, repos
from ..dominio import dedup
from ..dominio import generar as gen_dom
from ..tiempo import hoy_utc
from . import _ref
from ._comun import (
    _DIAS_DEDUP,
    _FORMATO_PIPELINE,
    ETAPA_CI,
    ORIGEN_PIPELINE,
    QA_CADUCADA,
    QA_EN_CURSO,
    QA_SALTADA,
    VERDICTO_NO_VERIFICADO,
    _log,
    registrar_etapa,
    temas_pipeline,
)

__all__ = [
    "items_ingeribles",
    "_leer_items_fuente",
    "fuentes_activas_de_marca",
    "_redes_de_fuente",
    "_copy_pendiente_de",
    "_fecha_fuente_iso",
    "_AVISO_SIN_LINEA",
    "_auto_etiquetar_linea",
    "crear_tema_de",
    "crear_tema_de_cluster",
    "clusters_para_promover",
    "categoria_efectiva",
    "cupo_produccion_restante",
    "cupos_categoria_restantes",
    "promover_clusters_marca",
    "temas_en_vuelo",
    "caducar_temas_viejos",
    "_claves_dedup_marca",
    "_url_fuente_de",
    "_nota_de_item",
    "ingerir_marca",
]

# Tope de enlaces corroborantes que se anexan a la nota de un tema promovido de un cluster.
_MAX_ENLACES_CLUSTER = 6


def items_ingeribles(
    items: list[dict[str, Any]],
    *,
    vistas: set[str],
    maximo: int,
) -> list[dict[str, Any]]:
    """Subconjunto de items de un feed que se debe ingerir (PURA, testeable).

    Reglas, en orden:
      - con `clave` no vacía (necesaria para dedup/marcado),
      - con `titulo` no vacío,
      - no ya usados (`clave` en `vistas`),
      - sin claves duplicadas dentro del propio barrido,
      - se RECORTA a `maximo` (cap de seguridad por barrido y por marca).

    Determinista: depende solo de sus argumentos (conserva el orden de entrada, que el feed
    ya trae cronológico).
    """
    elegidos: list[dict[str, Any]] = []
    vistos = set(vistas)
    for item in items:
        if len(elegidos) >= maximo:
            break
        clave = (item.get("clave") or "").strip()
        if not clave:
            continue
        if not (item.get("titulo") or "").strip():
            continue
        if clave in vistos:
            continue
        vistos.add(clave)
        elegidos.append(item)
    return elegidos


def _leer_items_fuente(fuente: dict[str, Any]) -> list[dict[str, Any]]:
    """Lee los items crudos de un feed (via `api.rss`). Best-effort: [] si falla.

    Import diferido de `api.rss` (no acoplar el daemon a la capa API en carga); reutiliza su
    `leer_items_fuente` (con el `_DESCARGADOR` mockeable de los tests).
    """
    try:
        from ..api import rss as api_rss

        return api_rss.leer_items_fuente(fuente)
    except Exception:  # noqa: BLE001 -- un feed que falla no debe abortar el barrido
        _log.warning("pipeline: no se pudo leer el feed %s", fuente.get("id", ""), exc_info=True)
        return []


def fuentes_activas_de_marca(marca: str) -> list[dict[str, Any]]:
    """Feeds RSS ACTIVOS de una marca. Best-effort: [] si la lectura falla."""
    try:
        fuentes = repos.listar_fuentes_rss()
    except Exception:  # noqa: BLE001 -- sin feeds legibles, esta marca no produce nada
        return []
    return [
        f
        for f in fuentes
        if (f.get("marca") or "") == marca and f.get("activo", True)
    ]


def _redes_de_fuente(fuente: dict[str, Any]) -> list[str]:
    """Redes objetivo de un item: las `redes_def` del feed si las tiene; si no, el defecto."""
    crudo = fuente.get("redes_def", "")
    pedidas = {r for r in (crudo if isinstance(crudo, list) else []) if redes.es_red(r)}
    if not pedidas and isinstance(crudo, str) and crudo:
        import json

        try:
            datos = json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            datos = []
        pedidas = {r for r in datos if isinstance(r, str) and redes.es_red(r)}
    if pedidas:
        return [r for r in redes.ids() if r in pedidas]
    return list(redes.redes_de_formato(_FORMATO_PIPELINE))


def _copy_pendiente_de(trabajo: dict[str, Any], nota: str, redes_ids: list[str]) -> str:
    """JSON con los parámetros que la fase CD necesitará para lanzar el copy de un tema.

    Se guarda en `contenido.copy_pendiente` al crear el tema (CI). La fase CD lo lee y lanza
    `lanzar_copy` SOLO si la QA de la fuente salió `no_verificado`, sin re-leer el feed ni
    re-resolver la og:image (ya resuelta en CI). "" si no se puede serializar (best-effort).
    """
    import json

    fuente = trabajo.get("fuente") or {}
    item = trabajo.get("item") or {}
    imagen = trabajo.get("imagen") or ""
    try:
        return json.dumps({
            "nota": nota,
            "redes_ids": list(redes_ids),
            "fuente_id": fuente.get("id") or "",
            "clave": (item.get("clave") or "").strip(),
            "imagen": imagen,
            "tipo_contenido": "fuente" if imagen else "",
        }, ensure_ascii=False)
    except (TypeError, ValueError):  # pragma: no cover -- entrada simple, no debería fallar
        return ""


def _fecha_fuente_iso(item: dict[str, Any]) -> str:
    """ISO UTC de la fecha de la FUENTE (pubDate/updated del item); "" si falta o no parsea.

    Reutiliza el parser tolerante del feed (`http_feed.fecha_a_orden`, que cubre RFC 822 e
    ISO 8601 y asume UTC para naive). Un crudo ausente/ilegible cae a la fecha mínima
    (epoch); lo tratamos como "" (la pieza no conserva fecha de fuente). Best-effort: nunca
    rompe la ingesta.
    """
    crudo = (item.get("fecha") or "").strip()
    if not crudo:
        return ""
    try:
        from datetime import UTC

        from ..dominio import http_feed

        dt = http_feed.fecha_a_orden(crudo)
        if dt.year <= 1970:  # epoch = no se pudo parsear
            return ""
        return dt.astimezone(UTC).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001 -- el dato es informativo; un fallo no debe romper la ingesta
        return ""


_AVISO_SIN_LINEA = "⚠ Sin línea: clasifícala a una línea o deséchala."


def _auto_etiquetar_linea(tema: dict[str, Any], titulo: str, resumen: str) -> None:
    """Auto-etiqueta la pieza con su LÍNEA (vertical) y ORIGEN (siempre, dentro de la etapa de copy).

    Sin línea → deja un aviso en `notas` (la pieza NO se descarta). Best-effort: un fallo no
    rompe la ingesta.
    """
    try:
        from ..dominio import clasificador_lineas

        res = clasificador_lineas.clasificar_pieza(titulo, resumen, tema.get("marca", ""))
        if res.get("vertical"):
            repos.asignar_etiqueta(tema["id"], str(res["vertical"]))
        else:
            repos.actualizar_contenido(tema["id"], {"notas": _AVISO_SIN_LINEA})
        if res.get("origen"):
            repos.asignar_etiqueta(tema["id"], str(res["origen"]))
    except Exception:  # noqa: BLE001 -- el etiquetado es best-effort; nunca rompe el barrido
        _log.warning(
            "pipeline: auto-etiquetado de línea falló (%s)", tema.get("id"), exc_info=True
        )


def crear_tema_de(
    trabajo: dict[str, Any], *, claves_vistas: set[str] | None = None
) -> dict[str, Any] | None:
    """CI — crea el `contenido` (tema) de UN trabajo de ingesta SIN generar copy, y marca el item.

    Rediseño QPC: el copy se genera DESPUÉS, en la fase CD, y SOLO si la QA de la fuente pasa.
    El tema nace con `origen=ORIGEN_PIPELINE` (para que la vista Pipelines y las fases QA/CD lo
    encuentren), la nota en `descripcion` y los parámetros de copy pendiente en `copy_pendiente`
    (JSON). Marca el item del feed como USADO (dedup) para no re-ingerirlo. None si se omite.

    `claves_vistas` (opcional): claves de dedup (`dominio.dedup.clave`) del contenido reciente de
    la marca. Si el título de este trabajo ya está ahí (misma noticia en cola o publicada hace
    poco), NO se crea el tema (se marca el item usado y se devuelve None). Tras crear, la clave
    nueva se añade al conjunto para dedup también dentro del mismo barrido. Sin él, no hay dedup.
    """
    item = trabajo["item"]
    fuente = trabajo["fuente"]
    titulo = (item.get("titulo") or "").strip()
    if not titulo:
        return None
    marca = (fuente.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return None
    clave = (item.get("clave") or "").strip()
    # Dedup de contenido: misma noticia (título normalizado) ya en la cola o publicada hace poco
    # para esta marca -> no se crea otro tema. Se marca el item usado para no re-evaluarlo.
    if claves_vistas is not None and dedup.es_duplicado(titulo, claves_vistas):
        if clave:
            try:
                repos.marcar_item(fuente["id"], clave, True)
            except Exception:  # noqa: BLE001 -- best-effort
                _log.warning("pipeline: no se pudo marcar item dup usado (%s)", clave, exc_info=True)
        _log.info("pipeline: omito duplicado «%s» (%s)", titulo[:60], marca)
        return None
    nota = _nota_de_item(item)[: gen_dom.MAX_TEXTO]
    redes_ids = _redes_de_fuente(fuente)
    try:

        tema = repos.crear_contenido(
            clase="contenido",
            titulo=titulo[:300],
            descripcion=nota[:5000],
            marca=marca,
            origen=ORIGEN_PIPELINE,
            fecha_objetivo=hoy_utc().isoformat(),
            # FOTO explícito: el pipeline no sabe si el ítem será foto o video, así que crea
            # un post de FOTO (3 redes IG/X/FB). El humano puede pasarlo a video más adelante.
            formato=_FORMATO_PIPELINE,
            copy_pendiente=_copy_pendiente_de(trabajo, nota, redes_ids),
            # Fecha de la FUENTE (pubDate del item), para mostrar en la Consola "Fuente del …"
            # junto a "Generado el …" (`creado`). "" si la fuente no traía fecha.
            fecha_fuente=_fecha_fuente_iso(item),
            # URL CANÓNICA de la nota de origen (trazabilidad + dedup por URL). El enlace ya va
            # como texto en la nota; aquí se persiste estructurado. "" si no es http(s) válido.
            url_fuente=_url_fuente_de(item),
            # NOMBRE legible del MEDIO de origen (la fuente RSS configurada): la pieza lo
            # conserva para la UI (cabecera de grupo del feed) aunque el item desaparezca.
            fuente_nombre=(fuente.get("nombre") or "").strip(),
        )
    except Exception:  # noqa: BLE001 -- sin tema, este item no produce nada (no rompe el barrido)
        _log.warning("pipeline: no se pudo crear el tema (%s)", marca, exc_info=True)
        return None
    # Auto-etiquetado de línea (vertical) y origen — gated por KENI_PIPELINE_LINEAS.
    _auto_etiquetar_linea(tema, titulo, (item.get("resumen") or "").strip())
    # Dedup intra-barrido: registra el título recién creado para que otro item con el mismo
    # título (otra fuente) en este MISMO barrido no cree un segundo tema.
    if claves_vistas is not None:
        claves_vistas.add(dedup.clave(titulo))
    # Dedup: marca el item del feed como usado tras crear el tema, para que un re-barrido
    # inmediato no lo vuelva a elegir. Best-effort.
    if clave:
        try:
            repos.marcar_item(fuente["id"], clave, True)
        except Exception:  # noqa: BLE001 -- el marcado es dedup; un fallo no debe romper el barrido
            _log.warning("pipeline: no se pudo marcar el item usado (%s)", clave, exc_info=True)
    return tema


def _nota_de_cluster(titulo: str, resumen: str, enlaces: list[str]) -> str:
    """Nota de partida del copy desde una HISTORIA: titulo + resumen + enlaces corroborantes."""
    partes = [titulo.strip(), resumen.strip()]
    nota = "\n\n".join(p for p in partes if p)
    urls = [u for u in enlaces if u][:_MAX_ENLACES_CLUSTER]
    if urls:
        nota = (nota + "\n\nFuentes:\n" + "\n".join(urls)).strip()
    return nota


def clusters_para_promover(
    marca: str, *, maximo: int, cupos_categoria: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    """Top-N historias (`estado='nuevo'`) de la marca por SCORE, con LISTÓN y DIVERSIDAD. Best-effort.

    Reusa el pool ya FUSIONADO y RANKEADO (Ola B): `listar_noticia_clusters` viene ordenado por
    score (mayor primero). Así el pipeline produce las pocas historias más relevantes por marca
    —no un tema por cada item RSS—, que es lo que frena el volumen y respeta la jerarquización.

    LISTÓN de producción automática (`noticias_liston.evaluar`): promover acaba en QA+copy
    (`claude -p`: coste real de tokens), así que antes de competir por plaza cada candidata debe
    superar el listón — verificación no dudosa, score recalculado ≥ `KENI_PROMOVER_MIN_SCORE` y
    encaje con el vocabulario de la marca ≥ `KENI_PROMOVER_MIN_MARCA` (exentas las curadas por
    el equipo y las breaking corroboradas). Las que no lo superan se quedan `nuevo` en el pool
    (visibles en el panel con su motivo; el humano puede usarlas a mano y la caducidad las
    expira sola). Se loguea cuántas quedaron bajo el listón: la criba es auditable.

    DIVERSIDAD (MMR suave): se sobremuestrea el top y `clustering.seleccionar_diversos` salta
    las historias cuyo título es casi idéntico (ratio fuzzy ≥ `KENI_PROMOVER_DIVERSIDAD_UMBRAL`,
    def 0.80) a una ya elegida en este barrido, para que un macro-tema no se coma todas las
    plazas. Suave: si faltan plazas se rellenan con las saltadas (nunca devuelve menos). Con el
    umbral a 0 se desactiva (top-N puro, comportamiento anterior).
    """
    from .. import config, noticias_liston
    from ..dominio import clustering

    umbral = config.promover_diversidad_umbral()
    # Sobremuestra acotada: suficientes candidatas para listón+diversidad sin recorrer el pool.
    # Con PLAN (cupos por categoría) la muestra crece: las categorías minoritarias del plan
    # pueden vivir lejos del top global del pool.
    limite = max(maximo * 4, maximo + 8) if cupos_categoria is None else max(maximo * 10, 80)
    try:
        clusters, _total = repos.listar_noticia_clusters(
            marca=marca, estado="nuevo", limite=limite
        )
    except Exception:  # noqa: BLE001 -- sin pool legible, esta marca no promueve nada
        _log.warning("pipeline: no se pudieron leer historias para promover (%s)", marca, exc_info=True)
        return []
    aptas: list[dict[str, Any]] = []
    bajo_liston = 0
    for c in clusters:
        try:
            supera, motivo = noticias_liston.evaluar(c)
        except Exception:  # noqa: BLE001 -- ante un fallo del listón, NO se promueve (fail-closed:
            # promover cuesta tokens; una historia retenida de más la recoge el humano o el
            # siguiente barrido, una promovida de más ya quemó el claude -p).
            _log.warning("pipeline: fallo al evaluar el listón de una historia (%s)", c.get("id"), exc_info=True)
            continue
        if supera:
            aptas.append(c)
        else:
            bajo_liston += 1
            _log.debug("pipeline: historia bajo el listón (%s): %s", c.get("id"), motivo)
    if bajo_liston:
        _log.info(
            "pipeline: %d historia(s) de %s bajo el listón de producción automática "
            "(quedan en el pool, visibles en el panel).",
            bajo_liston, marca,
        )
    if cupos_categoria is not None:
        # PLAN EDITORIAL: greedy por score con cupo por categoría — el pool viene rankeado,
        # así que cada cupo se lleva LAS MEJORES historias de su categoría. Historias de
        # categorías fuera del plan (o de cupo ya lleno) no compiten: se quedan en el pool.
        # DIVERSIDAD antes del reparto: reordena empujando los casi-duplicados al final
        # (relleno suave de `seleccionar_diversos` con maximo=len = misma lista reordenada),
        # de modo que un macro-tema no se coma su cupo con dos titulares casi iguales.
        if umbral > 0:
            aptas = clustering.seleccionar_diversos(aptas, maximo=len(aptas), umbral=umbral)
        elegidos: list[dict[str, Any]] = []
        huecos = dict(cupos_categoria)
        for c in aptas:
            if len(elegidos) >= maximo:
                break
            cat = categoria_efectiva(c)
            if huecos.get(cat, 0) <= 0:
                continue
            huecos[cat] -= 1
            elegidos.append(c)
        return elegidos
    if umbral <= 0:
        return aptas[:maximo]
    return clustering.seleccionar_diversos(aptas, maximo=maximo, umbral=umbral)


def _es_fuente_propia(fuente_id: str, cache: dict[str, bool]) -> bool:
    """True si `fuente_id` es de una fuente RSS de marca PROPIA. Memoiza por barrido (cache)."""
    fuente_id = (fuente_id or "").strip()
    if not fuente_id:
        return False
    if fuente_id not in cache:
        try:
            fuente = repos.obtener_fuente_rss(fuente_id)
        except Exception:  # noqa: BLE001 -- sin la fuente, no la tratamos como propia
            fuente = None
        cache[fuente_id] = bool(fuente and fuente.get("propia"))
    return cache[fuente_id]


def _imagen_de_cluster(items: list[dict[str, Any]]) -> str:
    """Arte del tema desde los items del cluster, PRIORIZANDO fuentes PROPIAS (derechos).

    Para un item de fuente PROPIA (`unotv.com`, `clarosports.com`…) reutilizamos su foto: la
    `imagen` del feed si la trae o, si no, RESOLVEMOS la `og:image` del artículo (la foto real
    de la nota) —igual que `ingerir_marca`—. Solo de fuentes propias bajamos a resolver la
    og:image (no tenemos derechos sobre la foto de un medio ajeno). Si ninguna propia da
    imagen, caemos a cualquier imagen ya capturada en los items (comportamiento previo). "".
    """
    cache: dict[str, bool] = {}
    # 1) Fuente PROPIA: foto del feed o, en su defecto, og:image resuelta del artículo.
    for it in items:
        if not _es_fuente_propia(it.get("fuente_id") or "", cache):
            continue
        img = (it.get("imagen") or "").strip()
        if img:
            return img
        enlace = (it.get("url") or "").strip()
        if enlace:
            try:
                resuelta = (_ref._FETCH_OG_IMAGE(enlace) or "").strip()
            except Exception:  # noqa: BLE001 -- og:image best-effort; nunca rompe el barrido
                resuelta = ""
            if resuelta:
                return resuelta
    # 2) Fallback: cualquier imagen ya presente en los items (feed media-tag), sin resolver.
    return next((it["imagen"].strip() for it in items if (it.get("imagen") or "").strip()), "")


def crear_tema_de_cluster(
    cluster: dict[str, Any], items: list[dict[str, Any]], *, claves_vistas: set[str] | None = None
) -> dict[str, Any] | None:
    """CI — promueve una HISTORIA (cluster rankeado) a tema del pipeline SIN copy. Marca el cluster usado.

    Mismo modelo que `crear_tema_de` (origen `pipeline`, nota en `descripcion`, parámetros de copy
    en `copy_pendiente` para la fase CD, QA pendiente), pero la nota viene del cluster (título +
    resumen + enlaces corroborantes de sus items) en vez de un único item RSS. La dedup contra el
    contenido reciente de la marca evita re-promover una historia que ya está en el tablero. None
    si se omite (sin marca/título válidos o duplicado), marcando el cluster usado igualmente.
    """
    marca = (cluster.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return None
    titulo = (cluster.get("titulo") or "").strip()
    if not titulo and items:
        titulo = ((items[0].get("titulo") or items[0].get("url")) or "").strip()
    if not titulo:
        return None
    cid = cluster.get("id") or ""
    # Dedup: la historia ya se trabajó hace poco para esta marca -> no se crea otro tema.
    if claves_vistas is not None and dedup.es_duplicado(titulo, claves_vistas):
        if cid:
            try:
                repos.actualizar_noticia_cluster(cid, estado="usado")
            except Exception:  # noqa: BLE001 -- best-effort
                _log.warning("pipeline: no se pudo marcar historia dup usada (%s)", cid, exc_info=True)
        _log.info("pipeline: omito historia duplicada «%s» (%s)", titulo[:60], marca)
        return None
    resumen = (cluster.get("resumen") or "").strip()
    enlaces = [it.get("url") or "" for it in items if it.get("url")]
    nota = _nota_de_cluster(titulo, resumen, enlaces)[: gen_dom.MAX_TEXTO]
    redes_ids = list(redes.redes_de_formato(_FORMATO_PIPELINE))
    imagen = _imagen_de_cluster(items)
    # Reusa el serializador de copy_pendiente con un "trabajo" sintético (sin fuente/clave RSS).
    trabajo = {"fuente": {}, "item": {"clave": ""}, "imagen": imagen}
    url_fuente = (items[0].get("url_canonica") if items else "") or ""
    try:

        tema = repos.crear_contenido(
            clase="contenido",
            titulo=titulo[:300],
            descripcion=nota[:5000],
            marca=marca,
            origen=ORIGEN_PIPELINE,
            # LÍNEA del plan con la que nació ('breaking' si lo era): queda EN la pieza
            # (estable frente al GC del pool); la leen el conteo del plan y los horarios.
            categoria=categoria_efectiva(cluster),
            fecha_objetivo=hoy_utc().isoformat(),
            formato=_FORMATO_PIPELINE,
            copy_pendiente=_copy_pendiente_de(trabajo, nota, redes_ids),
            # FECHA de la NOTA ORIGINAL: preferimos el `publicado_en` del item más reciente
            # (cuando el medio publicó la nota); si el medio no traía fecha, caemos al
            # `primer_visto` del cluster (cuando el Radar la capturó).
            fecha_fuente=((items[0].get("publicado_en") if items else "") or "")
            or (cluster.get("primer_visto") or ""),
            url_fuente=url_fuente,
            # NOMBRE del MEDIO de origen (item del cluster): se COPIA aquí porque el GC de
            # noticias puede borrar el cluster y la pieza debe conservar su procedencia.
            fuente_nombre=(((items[0].get("fuente_nombre") if items else "") or "").strip()),
        )
    except Exception:  # noqa: BLE001 -- sin tema, esta historia no produce nada (no rompe el barrido)
        _log.warning("pipeline: no se pudo crear el tema de la historia (%s)", marca, exc_info=True)
        return None
    _auto_etiquetar_linea(tema, titulo, resumen)
    if claves_vistas is not None:
        claves_vistas.add(dedup.clave(titulo))
    if cid:
        try:
            repos.actualizar_noticia_cluster(cid, estado="usado", contenido_id=tema["id"])
            repos.marcar_items_cluster_usados(cid, tema["id"])
        except Exception:  # noqa: BLE001 -- el marcado es dedup; un fallo no rompe el barrido
            _log.warning("pipeline: no se pudo marcar la historia usada (%s)", cid, exc_info=True)
    return tema


def _temas_en_vuelo_de(marca: str) -> list[dict[str, Any]]:
    """Temas del pipeline de `marca` EN VUELO (sin terminar las fases de IA). [] si falla.

    En vuelo = pendiente de QA (veredicto ''/'en_curso') O cribado-apto/saltado pero SIN copy aún.
    Compartido por el gate SERIAL (cuenta) y la CADUCIDAD (caduca los que superan el TTL): una
    sola definición de "en vuelo" para ambos.
    """
    try:
        temas = temas_pipeline(marca)
    except Exception:  # noqa: BLE001 -- sin temas legibles, no bloqueamos la promoción
        return []
    if not temas:
        return []
    try:
        # WHERE en SQL por marca (antes: tabla `contenido_plataforma` ENTERA por cada marca
        # y barrido, filtrada en Python).
        con_copy = repos.ids_contenido_con_copy(marca)
    except Exception:  # noqa: BLE001 -- sin plataformas, contamos solo los pendientes de QA
        con_copy = set()
    en_vuelo: list[dict[str, Any]] = []
    for t in temas:
        veredicto = (t.get("qa_veredicto") or "").strip()
        if veredicto in ("", QA_EN_CURSO):
            en_vuelo.append(t)  # pendiente de QA
        elif veredicto in (VERDICTO_NO_VERIFICADO, QA_SALTADA) and (t.get("id") or "") not in con_copy:
            en_vuelo.append(t)  # cribado pero pendiente de copy
    return en_vuelo


def temas_en_vuelo(marca: str) -> int:
    """Cuántos temas del pipeline de `marca` están EN VUELO (gate serial de la admisión).

    Es lo que CI mira para no promover más historias de esa marca hasta drenarlas (así cada
    item que entra se completa antes de meter nuevos). Best-effort: 0 ante cualquier fallo.
    """
    return len(_temas_en_vuelo_de(marca))


def cupo_produccion_restante(
    marca: str, *, ahora: datetime | None = None
) -> int | None:
    """Plazas de ADMISIÓN que le quedan a `marca` por su cupo diario simple; None = sin cupo.

    Solo aplica a marcas SIN plan editorial (`config.plan_dia`): un techo de temas
    auto-producidos en 24 h MÓVILES (`KENI_CUPO_DIA`, cuenta temas `origen=pipeline` por
    `creado`). Con plan, el volumen lo gobiernan los cupos POR CATEGORÍA
    (`cupos_categoria_restantes`). `None` = cupo desactivado (0): la admisión queda solo con
    el gate serial en vuelo. FAIL-CLOSED ante un contador ilegible: promover gasta tokens,
    así que sin lectura fiable se devuelve 0 (el siguiente tick reintenta).
    """
    from ..tiempo import iso_utc

    momento = ahora or datetime.now(timezone.utc)
    if momento.tzinfo is not None:
        momento = momento.astimezone(timezone.utc).replace(tzinfo=None)
    cupo_d = config.cupo_dia(marca)
    if cupo_d <= 0:
        return None
    try:
        usados = repos.contar_contenido_origen_desde(
            marca, ORIGEN_PIPELINE, iso_utc(momento - timedelta(hours=24))
        )
    except Exception:  # noqa: BLE001 -- fail-closed: sin contador fiable no se admite
        _log.warning("pipeline: no se pudo contar el cupo diario (%s)", marca, exc_info=True)
        return 0
    return max(0, cupo_d - usados)


def cupos_categoria_restantes(
    marca: str, *, ahora: datetime | None = None
) -> dict[str, int] | None:
    """Cupos del PLAN EDITORIAL DIARIO que aún quedan por llenar, por categoría; None = sin plan.

    El plan (`config.plan_dia`, p. ej. "mx:4,internacional:4,breaking:2,entretenimiento:2,
    evergreen:1") fija el objetivo del día por categoría. Se descuenta lo ya producido en
    24 h MÓVILES contando las historias PROMOVIDAS (cluster→contenido), donde una historia
    breaking consume el cupo 'breaking' sea cual sea la categoría de su feed — los slots de
    breaking son para la última hora, también la que el equipo empuja a mano desde el panel.
    Devuelve solo las categorías CON hueco (dict vacío = plan completo: hoy ya no entra más).
    FAIL-CLOSED ante un contador ilegible (dict vacío: no se admite, el tick siguiente
    reintenta)."""
    from ..tiempo import iso_utc

    plan = config.plan_dia(marca)
    if not plan:
        return None
    momento = ahora or datetime.now(timezone.utc)
    if momento.tzinfo is not None:
        momento = momento.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        resumen = repos.resumen_plan_por_categoria(
            marca, iso_utc(momento - timedelta(hours=24))
        )
    except Exception:  # noqa: BLE001 -- fail-closed (promover gasta tokens)
        _log.warning("pipeline: no se pudo contar el plan diario (%s)", marca, exc_info=True)
        return {}
    return {
        cat: hueco
        for cat, cupo in plan.items()
        if (hueco := cupo - resumen.get(cat, {}).get("generados", 0)) > 0
    }


def categoria_efectiva(cluster: dict[str, Any]) -> str:
    """Categoría con la que una historia COMPITE en el plan: 'breaking' si lo es, si no la
    de su feed (en minúsculas; '' si sus fuentes no están categorizadas). PURA."""
    if bool(int(cluster.get("breaking") or 0)):
        return "breaking"
    return str(cluster.get("categoria") or "").strip().lower()


def caducar_temas_viejos(*, ahora: datetime | None = None) -> int:
    """FRESCURA (ventana deslizante): caduca los temas EN VUELO que superaron el TTL.

    El pipeline no arrastra backlog: un tema que no completó sus fases (QA→copy) dentro de
    `KENI_PIPELINE_TEMA_TTL_HORAS` (def 24 h) se marca `qa_veredicto='caducada'` — sale del
    gate serial (libera hueco de admisión para lo fresco del ranking), la fase QA no lo criba
    y la fase CD no le genera copy. Lo de ayer no entra hoy; hoy entra lo de hoy.

    Corre al inicio de cada barrido (barato: lecturas indexadas + updates puntuales).
    Best-effort por tema; devuelve cuántos caducaron.
    """
    momento = ahora or datetime.now(timezone.utc)
    ttl = timedelta(hours=config.pipeline_tema_ttl_horas())
    caducados = 0
    for marca in marcas.ids():
        for tema in _temas_en_vuelo_de(marca):
            creado = _fecha_aware(str(tema.get("creado") or ""))
            if creado is None or momento - creado < ttl:
                continue
            tema_id = str(tema.get("id") or "")
            if not tema_id:
                continue
            nota = (
                f"⏳ Caducada ({config.pipeline_tema_ttl_horas()} h en vuelo sin completar): "
                "el pipeline prioriza lo fresco del ranking."
            )
            try:
                previas = str(tema.get("notas") or "").strip()
                repos.actualizar_contenido(
                    tema_id,
                    {
                        "qa_veredicto": QA_CADUCADA,
                        "notas": f"{previas}\n{nota}" if previas else nota,
                    },
                )
                caducados += 1
            except Exception:  # noqa: BLE001 -- un tema ilegible no debe frenar la caducidad
                _log.exception("pipeline: no se pudo caducar el tema %s", tema_id)
    if caducados:
        _log.info("pipeline: %d tema(s) caducados (TTL %d h): hueco libre para lo fresco.",
                  caducados, config.pipeline_tema_ttl_horas())
    return caducados


def _fecha_aware(crudo: str) -> datetime | None:
    """Parsea un ISO del tema a datetime CON tz (naive = UTC); None si no es parseable."""
    try:
        valor = datetime.fromisoformat(crudo)
    except (TypeError, ValueError):
        return None
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


def promover_clusters_marca(
    marca: str, *, maximo: int, cupos_categoria: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    """CI — promueve a temas las top-N historias rankeadas de una marca. Registra la etapa CI.

    Reemplaza la lectura directa de feeds RSS (que creaba un tema por item): ahora consume el pool
    ya fusionado/rankeado (Ola B). Devuelve los temas creados. Best-effort por historia.
    """
    clusters = clusters_para_promover(marca, maximo=maximo, cupos_categoria=cupos_categoria)
    claves_vistas = _claves_dedup_marca(marca)
    temas: list[dict[str, Any]] = []
    for cluster in clusters:
        try:
            items = repos.items_de_cluster(cluster.get("id") or "", limite=_MAX_ENLACES_CLUSTER)
            tema = crear_tema_de_cluster(cluster, items, claves_vistas=claves_vistas)
        except Exception:  # noqa: BLE001 -- una historia problemática no aborta el barrido
            _log.exception("pipeline: fallo al promover una historia (%s)", marca)
            continue
        if tema:
            temas.append(tema)
    registrar_etapa(
        ETAPA_CI,
        marca,
        f"Promoción de historias — {marcas.etiqueta_de(marca)}: {len(temas)} temas "
        f"de {len(clusters)} historias rankeadas",
    )
    return temas


def _claves_dedup_marca(marca: str) -> set[str]:
    """Claves de dedup (títulos normalizados) del contenido reciente de `marca` (`_DIAS_DEDUP`).

    Best-effort: si la lectura falla, devuelve un set vacío (no se deduplica, no se rompe el
    barrido). Cubre el duplicado en cola y el republicado: todo contenido de la marca creado en
    la ventana entra (esté en borrador, en revisión o ya publicado).
    """
    from datetime import timedelta

    desde = (hoy_utc() - timedelta(days=_DIAS_DEDUP)).isoformat()
    try:
        titulos = repos.titulos_recientes_marca(marca, desde)
    except Exception:  # noqa: BLE001 -- sin títulos legibles, no dedup (no rompe el barrido)
        _log.warning("pipeline: no se pudieron leer títulos para dedup (%s)", marca, exc_info=True)
        return set()
    return {k for t in titulos if (k := dedup.clave(t))}


def _url_fuente_de(item: dict[str, Any]) -> str:
    """URL CANÓNICA del enlace de origen del item, para `contenido.url_fuente` (trazabilidad/dedup).

    Solo canoniza http/https (la canonización ya descarta lo demás devolviendo ""). El enlace
    sigue viajando como texto en la nota; esto lo persiste estructurado. "" si no hay enlace
    válido. Best-effort y puro (delega en `dedup.url_canonica`).
    """
    enlace = (item.get("enlace") or "").strip()
    if not enlace.startswith(("http://", "https://")):
        return ""
    return dedup.url_canonica(enlace)


def _nota_de_item(item: dict[str, Any]) -> str:
    """Nota de partida del copy: titulo + resumen + enlace (los vacíos se omiten)."""
    partes = [
        (item.get("titulo") or "").strip(),
        (item.get("resumen") or "").strip(),
        (item.get("enlace") or "").strip(),
    ]
    return "\n\n".join(p for p in partes if p)


def ingerir_marca(marca: str, *, maximo: int) -> list[dict[str, Any]]:
    """CI — lee los feeds activos de una marca y elige items frescos. Registra la etapa CI.

    Devuelve una lista de "trabajos" `{item, fuente, propia, imagen}` listos para la fase CD.
    Para feeds de marca PROPIA resuelve la `og:image` del artículo (best-effort). Registra UNA
    entrada de actividad CI con el resumen (n temas / m fuentes / k con foto).
    """
    fuentes = fuentes_activas_de_marca(marca)
    trabajos: list[dict[str, Any]] = []
    con_foto = 0
    for fuente in fuentes:
        if len(trabajos) >= maximo:
            break
        try:
            vistas = repos.claves_vistas(fuente["id"])
        except Exception:  # noqa: BLE001 -- sin dedup legible, mejor no ingerir este feed
            continue
        crudos = _ref._leer_items_fuente(fuente)
        restante = maximo - len(trabajos)
        elegidos = items_ingeribles(crudos, vistas=vistas, maximo=restante)
        propia = bool(fuente.get("propia"))
        for item in elegidos:
            imagen = ""
            if propia:
                try:
                    imagen = _ref._FETCH_OG_IMAGE(item.get("enlace", "") or "")
                except Exception:  # noqa: BLE001 -- og:image best-effort; nunca rompe
                    imagen = ""
                if imagen:
                    con_foto += 1
            trabajos.append(
                {"item": item, "fuente": fuente, "propia": propia, "imagen": imagen}
            )
    registrar_etapa(
        ETAPA_CI,
        marca,
        f"Ingesta de fuentes — {marcas.etiqueta_de(marca)}: {len(trabajos)} temas "
        f"seleccionados de {len(fuentes)} fuentes ({con_foto} con foto)",
    )
    return trabajos
