"""CI — recolección de fuentes: SELECCIÓN pura de items + creación de temas (sin copy).

Lee los feeds RSS activos de una marca, elige items frescos (no usados, deduplicados) y crea un
`contenido` (tema) por item SIN generar copy todavía: el copy se redacta después en la fase CD,
y solo si la verificación de la fuente pasa. Marca los items usados (dedup) y registra la etapa CI.
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
    ETAPA_ADMITIR,
    ORIGEN_PIPELINE,
    ORIGEN_PORTAL,
    VERIFICACION_CADUCADA,
    VERIFICACION_EN_CURSO,
    VERIFICACION_SALTADA,
    VERIFICACION_VERIFICADO,
    VERIFICADAS_OK,
    _limpiar_snippet,
    _log,
    registrar_etapa,
    temas_pipeline,
)

__all__ = [
    "_copy_pendiente_de",
    "_AVISO_SIN_LINEA",
    "_auto_etiquetar_linea",
    "crear_tema_de_cluster",
    "clusters_para_promover",
    "clusters_pendientes_verificar",
    "categoria_efectiva",
    "cupo_produccion_restante",
    "cupos_categoria_restantes",
    "promover_clusters_marca",
    "temas_en_proceso",
    "caducar_temas_viejos",
    "caducar_verificacion_clusters_en_curso",
    "_claves_dedup_marca",
    "_nota_de_cluster",
    "_fetch_cuerpo",
]

# Tope de enlaces corroborantes que se anexan a la nota de un tema promovido de un cluster.
_MAX_ENLACES_CLUSTER = 6


def _copy_pendiente_de(trabajo: dict[str, Any], nota: str, redes_ids: list[str]) -> str:
    """JSON con los parámetros que la fase CD necesitará para lanzar el copy de un tema.

    Se guarda en `contenido.copy_pendiente` al crear el tema (CI). La fase CD lo lee y lanza
    `lanzar_copy` SOLO si la verificación de la fuente salió `no_verificado`, sin re-leer el feed ni
    re-resolver la og:image (ya resuelta en CI). "" si no se puede serializar (best-effort).
    """
    import json

    fuente = trabajo.get("fuente") or {}
    item = trabajo.get("item") or {}
    imagen = trabajo.get("imagen") or ""
    # CARRUSEL EDITORIAL (historias): cuántas NOTAS agrupa la historia (`n_notas`, con 2+ la
    # fase CD ofrece a Claude el output carrusel: una placa por sub-historia) y las fotos de
    # fuente PROPIA con el título de SU nota (`fotos_notas`), para que el modelo asigne foto
    # a cada slide. Un item RSS suelto lleva n_notas=1 (sin carrusel) y su propia foto.
    fotos_notas = [
        {"titulo": str(f.get("titulo") or "")[:300], "imagen": str(f.get("imagen") or "")}
        for f in (trabajo.get("fotos_notas") or [])
        if isinstance(f, dict) and str(f.get("imagen") or "").strip()
    ]
    n_notas = int(trabajo.get("n_notas") or 0) or 1
    try:
        return json.dumps({
            "nota": nota,
            "redes_ids": list(redes_ids),
            "fuente_id": fuente.get("id") or "",
            "clave": (item.get("clave") or "").strip(),
            "imagen": imagen,
            "fotos_notas": fotos_notas,
            "n_notas": n_notas,
            "tipo_contenido": "fuente" if imagen else "",
        }, ensure_ascii=False)
    except (TypeError, ValueError):  # pragma: no cover -- entrada simple, no debería fallar
        return ""


_AVISO_SIN_LINEA = "⚠ Sin línea: clasifícala a una línea o deséchala."


def _auto_etiquetar_linea(tema: dict[str, Any], titulo: str, resumen: str) -> None:
    """Auto-etiqueta la pieza con su LÍNEA (vertical) y ORIGEN (siempre, dentro de la etapa de Redactar).

    Sin línea → deja un aviso en `notas` (la pieza NO se descarta). Best-effort: un fallo no
    rompe la ingesta.
    """
    try:
        from ..dominio import clasificador_lineas

        res = clasificador_lineas.clasificar_pieza(titulo, resumen, tema.get("marca", ""))
        if res.get("vertical"):
            repos.asignar_etiqueta(tema["id"], str(res["vertical"]))
        else:
            repos.actualizar_publicacion(tema["id"], {"notas": _AVISO_SIN_LINEA})
        if res.get("origen"):
            repos.asignar_etiqueta(tema["id"], str(res["origen"]))
    except Exception:  # noqa: BLE001 -- el etiquetado es best-effort; nunca rompe el barrido
        _log.warning(
            "pipeline: auto-etiquetado de línea falló (%s)", tema.get("id"), exc_info=True
        )


def _nota_de_cluster(
    titulo: str,
    resumen: str,
    items: list[dict[str, Any]],
    cuerpos: dict[str, str] | None = None,
) -> str:
    """Nota de partida del copy desde una HISTORIA (cluster): arma un BLOQUE por fuente.

    PURA. Arma un bloque por fuente (medio · título · URL · resumen limpio · cuerpo del artículo
    si `cuerpos` lo trae) para que `claude -p` sintetice cruzando datos. `cuerpos` mapea URL del
    item -> cuerpo del artículo (el `content:encoded` archivado del feed o, en su defecto, el
    fetch HTTP); sin él, cada bloque queda con medio+título+resumen (mejor que solo el link).
    Tope `_MAX_ENLACES_CLUSTER`.
    """
    cuerpos = cuerpos or {}
    partes = [titulo.strip(), _limpiar_snippet(resumen)]
    bloques: list[str] = []
    urls: list[str] = []
    for it in items[:_MAX_ENLACES_CLUSTER]:
        url = (it.get("url") or "").strip()
        medio = (it.get("fuente_nombre") or "").strip()
        it_titulo = (it.get("titulo") or "").strip()
        it_resumen = _limpiar_snippet(it.get("resumen") or "")
        it_cuerpo = (cuerpos.get(url) or "").strip()
        if url:
            urls.append(url)
        encabezado = " · ".join(p for p in [medio, it_titulo] if p)
        lineas = [p for p in [encabezado, url, it_resumen, it_cuerpo] if p]
        if lineas:
            bloques.append("\n".join(lineas))
    if bloques:
        partes.append(
            "Fuentes (una misma historia; sintetiza y cruza sus datos, no copies literal):\n\n"
            + "\n\n---\n\n".join(bloques)
        )
    elif urls:
        partes.append("Fuentes:\n" + "\n".join(urls))
    return "\n\n".join(p for p in partes if p).strip()


def clusters_para_promover(
    marca: str, *, maximo: int, cupos_categoria: dict[str, int] | None = None,
    verificacion_estados: tuple[str, ...] = VERIFICADAS_OK,
) -> list[dict[str, Any]]:
    """Top-N historias (`estado='nuevo'`) de la marca por SCORE, con UMBRAL y DIVERSIDAD. Best-effort.

    `verificacion_estados` (ADR 0011 F3): el filtro de verificación es OBLIGATORIO — por defecto a las VERIFICADAS
    (`VERIFICADAS_OK` = `no_verificado`/`saltada`), así la admisión SIEMPRE verificación: las `problema`
    y las aún sin verificar nunca se materializan como contenido (no existe un camino que promueva
    sin filtrar). Se puede ESTRECHAR a un subconjunto, nunca abrir a "todo": un conjunto vacío
    promueve cero (fail-closed), no todo.

    Reusa el pool ya FUSIONADO y RANKEADO (Ola B): `listar_noticia_clusters` viene ordenado por
    score (mayor primero). Así el pipeline produce las pocas historias más relevantes por marca
    —no un tema por cada item RSS—, que es lo que limita el volumen y respeta la jerarquización.

    UMBRAL de producción automática (`noticias_umbral.evaluar`): promover acaba en verificación+copy
    (`claude -p`: coste real de tokens), así que antes de competir por plaza cada candidata debe
    superar el umbral — verificación no dudosa, score recalculado ≥ `KENI_PROMOVER_MIN_SCORE` y
    encaje con el vocabulario de la marca ≥ `KENI_PROMOVER_MIN_MARCA` (exentas las curadas por
    el equipo y las breaking corroboradas). La FUENTE PROPIA se OMITE aquí: la admite el canal
    Portal aparte (directo, sin umbral ni verificación). Las que no lo superan se quedan `nuevo` en el pool
    (visibles en el panel con su motivo; el humano puede usarlas a mano y la caducidad las
    expira sola). Se loguea cuántas quedaron bajo el umbral: la verificación es auditable.

    DIVERSIDAD (MMR suave): se sobremuestrea el top y `agrupar.seleccionar_diversos` salta
    las historias cuyo título es casi idéntico (ratio fuzzy ≥ `KENI_PROMOVER_DIVERSIDAD_UMBRAL`,
    def 0.80) a una ya elegida en este barrido, para que un macro-tema no se coma todas las
    plazas. Suave: si faltan plazas se rellenan con las saltadas (nunca devuelve menos). Con el
    umbral a 0 se desactiva (top-N puro, comportamiento anterior).
    """
    from .. import config, noticias_umbral
    from ..dominio import agrupar

    umbral = config.promover_diversidad_umbral()
    # Sobremuestra acotada: suficientes candidatas para umbral+diversidad sin recorrer el pool.
    # Con PLAN (cupos por categoría) la muestra crece: las categorías minoritarias del plan
    # pueden vivir lejos del top global del pool.
    limite = max(maximo * 4, maximo + 8) if cupos_categoria is None else max(maximo * 10, 80)
    # Con el filtro de verificación las verificadas pueden vivir más abajo en el ranking (solo se verificó el
    # top del admision): sobremuestrea más para no quedarte corto al filtrar por verificacion.
    limite = max(limite, 80)
    try:
        clusters, _total = repos.listar_noticia_clusters(
            marca=marca, estado="nuevo", limite=limite
        )
    except Exception:  # noqa: BLE001 -- sin pool legible, esta marca no promueve nada
        _log.warning("pipeline: no se pudieron leer historias para promover (%s)", marca, exc_info=True)
        return []
    # Filtro de verificación OBLIGATORIO: solo cruzan las historias con un verificacion admitido.
    clusters = [c for c in clusters if (c.get("verificacion_fuente") or "").strip() in verificacion_estados]
    aptas: list[dict[str, Any]] = []
    bajo_umbral = 0
    cache_propia: dict[str, bool] = {}
    for c in clusters:
        # FUENTE PROPIA (portal del cliente): NO la maneja investigación — la admite DIRECTO el
        # daemon Portal (canal aparte, sin umbral ni verificación). Aquí se omite para no admitirla
        # dos veces.
        if _es_fuente_propia(c.get("primera_fuente") or "", cache_propia):
            continue
        try:
            supera, motivo = noticias_umbral.evaluar(c)
        except Exception:  # noqa: BLE001 -- ante un fallo del umbral, NO se promueve (fail-closed:
            # promover cuesta tokens; una historia retenida de más la recoge el humano o el
            # siguiente barrido, una promovida de más ya gastó el claude -p).
            _log.warning("pipeline: fallo al evaluar el umbral de una historia (%s)", c.get("id"), exc_info=True)
            continue
        if supera:
            aptas.append(c)
        else:
            bajo_umbral += 1
            _log.debug("pipeline: historia bajo el umbral (%s): %s", c.get("id"), motivo)
    if bajo_umbral:
        _log.info(
            "pipeline: %d historia(s) de %s bajo el umbral de producción automática "
            "(quedan en el pool, visibles en el panel).",
            bajo_umbral, marca,
        )
    if cupos_categoria is not None:
        # PLAN EDITORIAL: greedy por score con cupo por categoría — el pool viene rankeado,
        # así que cada cupo se lleva LAS MEJORES historias de su categoría. Historias de
        # categorías fuera del plan (o de cupo ya lleno) no compiten: se quedan en el pool.
        # DIVERSIDAD antes del reparto: reordena empujando los casi-duplicados al final
        # (relleno suave de `seleccionar_diversos` con maximo=len = misma lista reordenada),
        # de modo que un macro-tema no se coma su cupo con dos titulares casi iguales.
        if umbral > 0:
            aptas = agrupar.seleccionar_diversos(aptas, maximo=len(aptas), umbral=umbral)
        elegidos: list[dict[str, Any]] = []
        huecos = dict(cupos_categoria)
        # Si el plan de la marca NO declara línea 'breaking', una última hora no debe quedar
        # invisible: compite por el cupo de su categoría de FEED (documentado: el plan ideal
        # incluye breaking:n; este fallback evita el agujero si no lo hace).
        plan_con_breaking = "breaking" in config.plan_dia(marca)
        for c in aptas:
            if len(elegidos) >= maximo:
                break
            cat = categoria_efectiva(c)
            if cat == "breaking" and not plan_con_breaking:
                cat = str(c.get("categoria") or "").strip().lower()
            if huecos.get(cat, 0) <= 0:
                continue
            huecos[cat] -= 1
            elegidos.append(c)
        return elegidos
    if umbral <= 0:
        return aptas[:maximo]
    return agrupar.seleccionar_diversos(aptas, maximo=maximo, umbral=umbral)


def clusters_pendientes_verificar(marca: str, *, maximo: int) -> list[dict[str, Any]]:
    """Top-N historias (`estado='nuevo'`) de la marca SIN verificar aún (`verificacion_fuente`==''), que
    pasan el UMBRAL — las candidatas a las que lanzar la verificación de la fuente (ADR 0011 F3).

    El umbral evita gastar `claude -p` verificando historias que jamás se admitirían (score/marca
    bajo umbral). OMITE la FUENTE PROPIA (portal del cliente): no pasa por la fase Verificar —la
    admite DIRECTO el canal Portal (sin verificación). Las ya `en_curso`/`no_verificado`/`saltada`/
    `problema` quedan fuera (su verificación ya corrió o está en curso). Ordenadas por score (el
    pool ya viene rankeado); se recorta a `maximo` (el presupuesto del admision de verificación).
    Best-effort: [] ante fallo o maximo<=0.
    """
    if maximo <= 0:
        return []
    from .. import noticias_umbral

    limite = max(maximo * 4, 80)
    try:
        clusters, _total = repos.listar_noticia_clusters(
            marca=marca, estado="nuevo", limite=limite
        )
    except Exception:  # noqa: BLE001 -- sin pool legible, esta marca no verificación nada
        _log.warning("pipeline: no se pudieron leer historias para verificación (%s)", marca, exc_info=True)
        return []
    pendientes: list[dict[str, Any]] = []
    cache_propia: dict[str, bool] = {}
    for c in clusters:
        if (c.get("verificacion_fuente") or "").strip():
            continue  # ya verificada / en curso
        # FUENTE PROPIA: la maneja el canal Portal (directo, sin verificación) -> se omite aquí.
        if _es_fuente_propia(c.get("primera_fuente") or "", cache_propia):
            continue
        try:
            supera, _motivo = noticias_umbral.evaluar(c)
        except Exception:  # noqa: BLE001 -- fail-closed: ante fallo del umbral no se verificación
            continue
        if not supera:
            continue
        pendientes.append(c)
        if len(pendientes) >= maximo:
            break
    return pendientes


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


# Tope de fotos de fuente por historia: los carruseles nativos de IG/FB admiten 10 slides,
# pero más allá de unas pocas tarjetas el carrusel de noticias pierde foco editorial.
_MAX_FOTOS_CLUSTER = 9


def _fotos_notas_de_cluster(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Fotos de los items del cluster CON el título de su nota, SOLO de fuentes PROPIAS.

    `[{titulo, imagen}, …]` sin imágenes duplicadas, en el orden de los items. Es el catálogo
    que la fase CD numera en el prompt para que el modelo asigne a cada SLIDE del carrusel la
    foto de SU sub-historia. No tenemos derechos sobre la foto de un medio AJENO: esos items
    se saltan. Tope `_MAX_FOTOS_CLUSTER`.
    """
    cache: dict[str, bool] = {}
    fotos: list[dict[str, str]] = []
    vistas: set[str] = set()
    for it in items:
        if not _es_fuente_propia(it.get("fuente_id") or "", cache):
            continue
        img = (it.get("imagen") or "").strip()
        if not img or img in vistas:
            continue
        vistas.add(img)
        fotos.append({"titulo": (it.get("titulo") or "").strip()[:300], "imagen": img})
        if len(fotos) >= _MAX_FOTOS_CLUSTER:
            break
    return fotos


def _imagen_de_cluster(items: list[dict[str, Any]]) -> str:
    """Arte (PORTADA) del tema desde los items del cluster, SOLO de fuentes PROPIAS (derechos).

    La `imagen` del feed del primer item propia que la traiga (`_fotos_notas_de_cluster`) o,
    si ninguno la traía, la `og:image` resuelta del primer artículo propia (un solo fetch por
    historia). "" si nada: el arte lo pone la etapa de Ilustrar
    (o el equipo). Nunca la foto de un medio ajeno.
    """
    fotos = _fotos_notas_de_cluster(items)
    if fotos:
        return fotos[0]["imagen"]
    cache: dict[str, bool] = {}
    for it in items:
        if not _es_fuente_propia(it.get("fuente_id") or "", cache):
            continue
        enlace = (it.get("url") or "").strip()
        if not enlace:
            continue
        try:
            resuelta = (_ref._FETCH_OG_IMAGE(enlace) or "").strip()
        except Exception:  # noqa: BLE001 -- og:image best-effort; nunca rompe el barrido
            resuelta = ""
        # Un solo intento por historia (el primer artículo propia con URL).
        return resuelta
    return ""


def _fotos_notas_de_familia(
    familia_con_items: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> list[dict[str, str]]:
    """Catálogo de fotos del carrusel de un MACRO-EVENTO: UNA entrada por SUB-HISTORIA.

    Misma forma que `_fotos_notas_de_cluster` (`{titulo, imagen}`), pero el catálogo lo numeran
    las sub-historias, no las fuentes: cada slide es un ÁNGULO del gran evento. `titulo` es el
    representativo de la sub-historia (su cluster, o el primer item) e `imagen` su foto PROPIA
    representativa (la primera de `_fotos_notas_de_cluster`) o "" si la sub-historia no tiene
    fuente propia (slide de solo texto: no usamos foto de un medio ajeno).
    """
    fotos: list[dict[str, str]] = []
    for cluster, items in familia_con_items:
        titulo = (cluster.get("titulo") or "").strip()
        if not titulo and items:
            titulo = (items[0].get("titulo") or "").strip()
        propias = _fotos_notas_de_cluster(items)
        fotos.append({
            "titulo": titulo[:300],
            "imagen": propias[0]["imagen"] if propias else "",
        })
    return fotos


def _nota_de_familia(
    tema_macro: str,
    familia_con_items: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    cuerpos_por_cluster: dict[str, dict[str, str]],
) -> str:
    """Nota de partida del copy de un MACRO-EVENTO: un encabezado de cobertura + un bloque por sub-historia.

    PURA. El encabezado declara que es la COBERTURA del gran evento «{tema_macro}» y que cada
    SUB-HISTORIA es un ÁNGULO/slide distinto del mismo evento (que el modelo no las mezcle); luego
    anexa, por sub-historia, el bloque de `_nota_de_cluster` (medio·título·url·resumen·cuerpo de
    sus fuentes). `cuerpos_por_cluster` mapea `cluster_id -> {url: cuerpo}`.
    """
    encabezado = (
        f"COBERTURA del macro-evento «{tema_macro}». Cada SUB-HISTORIA a continuación es un "
        "ÁNGULO distinto (un slide del carrusel) del MISMO gran evento: sintetiza cada una en su "
        "propia placa, sin mezclarlas ni repetir datos entre slides."
    )
    bloques = [encabezado]
    for cluster, items in familia_con_items:
        titulo = (cluster.get("titulo") or "").strip()
        resumen = (cluster.get("resumen") or "").strip()
        cuerpos = cuerpos_por_cluster.get(cluster.get("id") or "", {})
        bloque = _nota_de_cluster(titulo, resumen, items, cuerpos)
        if bloque:
            bloques.append(bloque)
    return "\n\n===\n\n".join(bloques).strip()


def crear_tema_de_cluster(
    cluster: dict[str, Any], items: list[dict[str, Any]], *, claves_vistas: set[str] | None = None,
    portal: bool = False,
) -> dict[str, Any] | None:
    """CI — promueve una HISTORIA (cluster rankeado) a tema del pipeline SIN copy. Marca el cluster usado.

    Modelo: origen `pipeline`, nota en `descripcion`, parámetros de copy
    en `copy_pendiente` para la fase CD, verificación pendiente), pero la nota viene del cluster (título +
    resumen + enlaces corroborantes de sus items) en vez de un único item RSS. La dedup contra el
    contenido reciente de la marca evita re-promover una historia que ya está en el tablero. None
    si se omite (sin marca/título válidos o duplicado), marcando el cluster usado igualmente.

    `portal`: canal PORTAL (marca propia). El tema nace con `origen='portal'` y verificación
    `saltada` (va DIRECTO a producción, sin pasar por la fase Verificar) y aparece en la pestaña
    Portal del feed. El resto (nota, imagen de la fuente, copy_pendiente, dedup) es idéntico.
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
    # MACRO-EVENTO (Fase B): si la historia pertenece a un gran evento, toda la FAMILIA se promueve
    # como UN solo carrusel (un slide por sub-historia), no una pieza por sub-historia.
    tema_macro = (cluster.get("tema_macro") or "").strip()
    if tema_macro:
        try:
            familia = repos.clusters_por_tema_macro(tema_macro, marca, solo_nuevos=True)
        except Exception:  # noqa: BLE001 -- sin familia legible, cae a la ruta por-cluster normal
            _log.warning(
                "pipeline: no se pudo leer la familia del macro-evento «%s» (%s)",
                tema_macro[:60], marca, exc_info=True,
            )
            familia = None
        if familia is not None:
            ids_familia = {(c.get("id") or "") for c in familia}
            if cid and cid not in ids_familia:
                # Otra promoción de la familia ya absorbió esta sub-historia: no dupliques pieza.
                _log.info(
                    "pipeline: historia ya absorbida por su macro-evento «%s» (%s)",
                    tema_macro[:60], marca,
                )
                return None
            if len(familia) >= 2:
                return _crear_carrusel_de_familia(
                    tema_macro, marca, familia, claves_vistas=claves_vistas
                )
            # len(familia) < 2: solo queda esta sub-historia viva -> ruta por-cluster normal.
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
    # Cuerpo de CADA fuente del cluster: PRIMERO el `content:encoded` archivado del feed (gratis,
    # ya en BD); solo para las fuentes que no lo traían se intenta el fetch HTTP (gateado). Así la
    # nota lleva el texto real de todas las fuentes, no solo sus URLs.
    cuerpos = dict(repos.cuerpos_de_cluster(cid))
    for it in items[:_MAX_ENLACES_CLUSTER]:
        url = (it.get("url") or "").strip()
        if url and not cuerpos.get(url):
            if cuerpo := _fetch_cuerpo(url):
                cuerpos[url] = cuerpo
    nota = _nota_de_cluster(titulo, resumen, items, cuerpos)[: gen_dom.MAX_TEXTO]
    redes_ids = list(redes.redes_de_formato(_FORMATO_PIPELINE))
    imagen = _imagen_de_cluster(items)
    # Reusa el serializador de copy_pendiente con un "trabajo" sintético (sin fuente/clave RSS).
    # `n_notas` (cuántas SUB-HISTORIAS agrupa) + `fotos_notas` (foto propia por nota) habilitan
    # el output CARRUSEL en la fase CD (una placa por sub-historia; Claude decide).
    trabajo = {
        "fuente": {}, "item": {"clave": ""}, "imagen": imagen,
        "fotos_notas": _fotos_notas_de_cluster(items),
        "n_notas": min(len(items), _MAX_ENLACES_CLUSTER),
    }
    url_fuente = (items[0].get("url_canonica") if items else "") or ""
    try:

        tema = repos.crear_publicacion(
            clase="contenido",
            titulo=titulo[:300],
            descripcion=nota[:5000],
            marca=marca,
            origen=ORIGEN_PORTAL if portal else ORIGEN_PIPELINE,
            # LÍNEA del plan con la que nació ('breaking' si lo era): queda EN la pieza
            # (estable frente al GC del pool); la leen el conteo del plan y los horarios.
            categoria=categoria_efectiva(cluster),
            fecha_objetivo=hoy_utc().isoformat(),
            formato=_FORMATO_PIPELINE,
            copy_pendiente=_copy_pendiente_de(trabajo, nota, redes_ids),
            # VERIFICACIÓN HEREDADA (ADR 0011 F3): la verificación corrió sobre la HISTORIA antes de admitir;
            # el tema NACE con el verificacion de su cluster (`no_verificado`/`saltada`), así la fase
            # de copy lo recoge de inmediato y la frontera "verificación = investigación" queda en los datos.
            verificacion_fuente=(VERIFICACION_SALTADA if portal else (cluster.get("verificacion_fuente") or "").strip()),
            verificar_hallazgos=(cluster.get("verificar_hallazgos") or ""),
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
            repos.actualizar_noticia_cluster(cid, estado="usado", publicacion_id=tema["id"])
            repos.marcar_items_cluster_usados(cid, tema["id"])
        except Exception:  # noqa: BLE001 -- el marcado es dedup; un fallo no rompe el barrido
            _log.warning("pipeline: no se pudo marcar la historia usada (%s)", cid, exc_info=True)
    return tema


def _crear_carrusel_de_familia(
    tema_macro: str, marca: str, familia: list[dict[str, Any]], *,
    claves_vistas: set[str] | None = None,
) -> dict[str, Any] | None:
    """CI — promueve TODA la familia de un MACRO-EVENTO como UN solo tema CARRUSEL (Fase B).

    Un slide por SUB-HISTORIA (cluster de la familia), ABSORBIENDO a los hermanos: el evento es el
    título, la nota cruza los ángulos y `n_notas` (= nº de sub-historias, ≥2) habilita el carrusel en
    la fase CD. Marca toda la familia `usado` enlazada a la pieza para que ningún hermano se promueva
    por separado (sin carruseles duplicados; la familia consume UN cupo). None si no se pudo crear.
    """
    familia = familia[:_MAX_FOTOS_CLUSTER]
    familia_con_items: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    cuerpos_por_cluster: dict[str, dict[str, str]] = {}
    for c in familia:
        cid_f = c.get("id") or ""
        items_f = repos.items_de_cluster(cid_f, limite=_MAX_ENLACES_CLUSTER)
        familia_con_items.append((c, items_f))
        cuerpos = dict(repos.cuerpos_de_cluster(cid_f))
        for it in items_f[:_MAX_ENLACES_CLUSTER]:
            url = (it.get("url") or "").strip()
            if url and not cuerpos.get(url):
                if cuerpo := _fetch_cuerpo(url):
                    cuerpos[url] = cuerpo
        cuerpos_por_cluster[cid_f] = cuerpos
    cluster_lead, items_lead = familia_con_items[0]
    resumen_lead = (cluster_lead.get("resumen") or "").strip()
    fotos_notas_familia = _fotos_notas_de_familia(familia_con_items)
    nota = _nota_de_familia(tema_macro, familia_con_items, cuerpos_por_cluster)[: gen_dom.MAX_TEXTO]
    redes_ids = list(redes.redes_de_formato(_FORMATO_PIPELINE))
    imagen = _imagen_de_cluster(items_lead)
    # `n_notas` = nº de SUB-HISTORIAS (≥2): habilita el output CARRUSEL (una placa por ángulo)
    # en la fase CD; `fotos_notas` numera la foto propia de cada sub-historia para asignarla a su slide.
    trabajo = {
        "fuente": {}, "item": {"clave": ""}, "imagen": imagen,
        "fotos_notas": fotos_notas_familia,
        "n_notas": len(fotos_notas_familia) or len(familia),
    }
    url_fuente = (items_lead[0].get("url_canonica") if items_lead else "") or ""
    try:
        tema = repos.crear_publicacion(
            clase="contenido",
            # El EVENTO es el título de la pieza (cada sub-historia es un slide, no un tema).
            titulo=tema_macro[:300],
            descripcion=nota[:5000],
            marca=marca,
            origen=ORIGEN_PIPELINE,
            categoria=categoria_efectiva(cluster_lead),
            fecha_objetivo=hoy_utc().isoformat(),
            formato=_FORMATO_PIPELINE,
            copy_pendiente=_copy_pendiente_de(trabajo, nota, redes_ids),
            verificacion_fuente=(cluster_lead.get("verificacion_fuente") or "").strip(),
            verificar_hallazgos=(cluster_lead.get("verificar_hallazgos") or ""),
            fecha_fuente=((items_lead[0].get("publicado_en") if items_lead else "") or "")
            or (cluster_lead.get("primer_visto") or ""),
            url_fuente=url_fuente,
            fuente_nombre=(((items_lead[0].get("fuente_nombre") if items_lead else "") or "").strip()),
        )
    except Exception:  # noqa: BLE001 -- sin tema, el macro-evento no produce nada (no rompe el barrido)
        _log.warning(
            "pipeline: no se pudo crear el carrusel del macro-evento «%s» (%s)",
            tema_macro[:60], marca, exc_info=True,
        )
        return None
    _auto_etiquetar_linea(tema, tema_macro, resumen_lead)
    if claves_vistas is not None and (clave := dedup.clave(tema_macro)):
        claves_vistas.add(clave)
    # ABSORBE TODA la familia: cada hermano queda `usado` enlazado a esta pieza (best-effort por
    # cluster; un fallo no aborta el barrido).
    for c in familia:
        cid_f = c.get("id") or ""
        if not cid_f:
            continue
        try:
            repos.actualizar_noticia_cluster(cid_f, estado="usado", publicacion_id=tema["id"])
            repos.marcar_items_cluster_usados(cid_f, tema["id"])
        except Exception:  # noqa: BLE001 -- el marcado es dedup; un fallo no rompe el barrido
            _log.warning(
                "pipeline: no se pudo absorber la sub-historia %s al macro-evento (%s)",
                cid_f, marca, exc_info=True,
            )
    _log.info(
        "pipeline: macro-evento «%s» -> carrusel de %d sub-historias (%s)",
        tema_macro[:60], len(familia), marca,
    )
    return tema


def _temas_en_proceso_de(marca: str) -> list[dict[str, Any]]:
    """Temas del pipeline de `marca` EN PROCESO (sin terminar las fases de IA). [] si falla.

    En proceso = pendiente de verificación (verificacion ''/'en_curso') O verificado-apto/saltado pero SIN copy aún.
    Compartido por el gate SERIAL (cuenta) y la CADUCIDAD (caduca los que superan el TTL): una
    sola definición de "en proceso" para ambos.
    """
    try:
        temas = temas_pipeline(marca)
    except Exception:  # noqa: BLE001 -- sin temas legibles, no bloqueamos la promoción
        return []
    if not temas:
        return []
    try:
        # WHERE en SQL por marca (antes: tabla `pieza` ENTERA por cada marca
        # y barrido, filtrada en Python).
        con_copy = repos.ids_publicacion_con_copy(marca)
    except Exception:  # noqa: BLE001 -- sin plataformas, contamos solo los pendientes de verificación
        con_copy = set()
    en_proceso: list[dict[str, Any]] = []
    for t in temas:
        verificacion = (t.get("verificacion_fuente") or "").strip()
        if verificacion in ("", VERIFICACION_EN_CURSO):
            en_proceso.append(t)  # pendiente de verificación
        elif verificacion in (VERIFICACION_VERIFICADO, VERIFICACION_SALTADA) and (t.get("id") or "") not in con_copy:
            en_proceso.append(t)  # verificado pero pendiente de copy
    return en_proceso


def temas_en_proceso(marca: str) -> int:
    """Cuántos temas del pipeline de `marca` están EN PROCESO (gate serial de la admisión).

    Es lo que CI mira para no promover más historias de esa marca hasta vaciarlas (así cada
    item que entra se completa antes de meter nuevos). Best-effort: 0 ante cualquier fallo.
    """
    return len(_temas_en_proceso_de(marca))


def cupo_produccion_restante(
    marca: str, *, ahora: datetime | None = None
) -> int | None:
    """Plazas de ADMISIÓN que le quedan a `marca` por su cupo diario simple; None = sin cupo.

    Solo aplica a marcas SIN plan editorial (`config.plan_dia`): un techo de temas
    auto-producidos en la JORNADA MX (parrilla del día, desde la medianoche de México, NO
    una ventana móvil de 24 h) — `KENI_CUPO_DIA`, cuenta temas `origen=pipeline` por
    `creado`. Con plan, el volumen lo gobiernan los cupos POR CATEGORÍA
    (`cupos_categoria_restantes`). `None` = cupo desactivado (0): la admisión queda solo con
    el gate serial en curso. FAIL-CLOSED ante un contador ilegible: promover gasta tokens,
    así que sin lectura fiable se devuelve 0 (el siguiente tick reintenta).
    """
    from ..tiempo import inicio_dia_cdmx_iso_utc

    momento = ahora or datetime.now(timezone.utc)
    if momento.tzinfo is not None:
        momento = momento.astimezone(timezone.utc).replace(tzinfo=None)
    cupo_d = config.cupo_dia(marca)
    if cupo_d <= 0:
        return None
    try:
        usados = repos.contar_publicacion_origen_desde(
            marca, ORIGEN_PIPELINE, inicio_dia_cdmx_iso_utc(momento)
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
    evergreen:1") fija el objetivo del día por categoría. Se descuenta lo ya producido en la
    JORNADA MX (parrilla del día, desde la medianoche de México — NO una ventana móvil de 24 h:
    a medianoche local los cupos reabren) contando las historias PROMOVIDAS (cluster→contenido),
    donde una historia breaking consume el cupo 'breaking' sea cual sea la categoría de su feed —
    los slots de breaking son para la última hora, también la que el equipo empuja a mano.
    Devuelve solo las categorías CON hueco (dict vacío = plan completo: hoy ya no entra más).
    FAIL-CLOSED ante un contador ilegible (dict vacío: no se admite, el tick siguiente
    reintenta)."""
    from ..tiempo import inicio_dia_cdmx_iso_utc

    plan = config.plan_dia(marca)
    if not plan:
        return None
    momento = ahora or datetime.now(timezone.utc)
    if momento.tzinfo is not None:
        momento = momento.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        resumen = repos.resumen_plan_por_categoria(
            marca, inicio_dia_cdmx_iso_utc(momento)
        )
    except Exception:  # noqa: BLE001 -- fail-closed (promover gasta tokens)
        _log.warning("pipeline: no se pudo contar el plan diario (%s)", marca, exc_info=True)
        return {}
    huecos: dict[str, int] = {}
    for cat, cupo in plan.items():
        if cat == "breaking":
            # La ÚLTIMA HORA excede el plan: el cupo es techo para lo normal, no para una
            # breaking corroborada. Techo efectivo = cupo + KENI_BREAKING_EXTRA_DIA (def 4),
            # para que un día muy movido tampoco se desboque. Con extra 0, techo duro.
            cupo += config.breaking_extra_dia()
        hueco = cupo - resumen.get(cat, {}).get("generados", 0)
        if hueco > 0:
            huecos[cat] = hueco
    return huecos


def categoria_efectiva(cluster: dict[str, Any]) -> str:
    """Categoría con la que una historia COMPITE en el plan: 'breaking' si lo es, si no la
    de su feed (en minúsculas; '' si sus fuentes no están categorizadas). PURA."""
    if bool(int(cluster.get("breaking") or 0)):
        return "breaking"
    return str(cluster.get("categoria") or "").strip().lower()


def caducar_temas_viejos(*, ahora: datetime | None = None) -> int:
    """FRESCURA (ventana deslizante): caduca los temas en curso que superaron el TTL.

    El pipeline no arrastra backlog: un tema que no completó sus fases (verificación→copy) dentro de
    `KENI_PIPELINE_TEMA_TTL_HORAS` (def 24 h) se marca `verificacion_fuente='caducada'` — sale del
    gate serial (libera hueco de admisión para lo fresco del ranking), la fase verificación no lo verificación
    y la fase CD no le genera copy. Lo de ayer no entra hoy; hoy entra lo de hoy.

    Corre al inicio de cada barrido (barato: lecturas indexadas + updates puntuales).
    Best-effort por tema; devuelve cuántos caducaron.
    """
    momento = ahora or datetime.now(timezone.utc)
    ttl = timedelta(hours=config.pipeline_tema_ttl_horas())
    caducados = 0
    for marca in marcas.ids():
        for tema in _temas_en_proceso_de(marca):
            creado = _fecha_aware(str(tema.get("creado") or ""))
            if creado is None or momento - creado < ttl:
                continue
            tema_id = str(tema.get("id") or "")
            if not tema_id:
                continue
            nota = (
                f"⏳ Caducada ({config.pipeline_tema_ttl_horas()} h en curso sin completar): "
                "el pipeline prioriza lo fresco del ranking."
            )
            try:
                previas = str(tema.get("notas") or "").strip()
                repos.actualizar_publicacion(
                    tema_id,
                    {
                        "verificacion_fuente": VERIFICACION_CADUCADA,
                        "notas": f"{previas}\n{nota}" if previas else nota,
                    },
                )
                caducados += 1
            except Exception:  # noqa: BLE001 -- un tema ilegible no debe detener la caducidad
                _log.exception("pipeline: no se pudo caducar el tema %s", tema_id)
    if caducados:
        _log.info("pipeline: %d tema(s) caducados (TTL %d h): hueco libre para lo fresco.",
                  caducados, config.pipeline_tema_ttl_horas())
    return caducados


def caducar_verificacion_clusters_en_curso(*, ahora: datetime | None = None) -> int:
    """Limpiador de la verificación: resetea los clusters `verificacion_fuente='en_curso'` atascados (ADR 0011 F3).

    Si una verificación de la fuente sobre un cluster muere (deploy/OOM/cuelgue), el cluster quedaría
    `en_curso` para siempre: ni se re-verificación ni se admite. Pasado el TTL de `en_curso` (el mismo
    que el limpiador de `contenido`, `config.verificacion_en_curso_ttl_seg`), vuelve a "" para re-verificar.
    Corre al inicio del barrido de investigación. Best-effort; devuelve cuántos reparó.
    """
    momento = ahora or datetime.now(timezone.utc)
    umbral = momento - timedelta(seconds=config.verificacion_en_curso_ttl_seg())
    try:
        n = repos.reparar_verificacion_clusters_en_curso(umbral.astimezone(timezone.utc).isoformat())
    except Exception:  # noqa: BLE001 -- la reparación es best-effort; nunca rompe el barrido
        _log.exception("pipeline: fallo el limpiador de verificación de clusters en curso.")
        return 0
    if n:
        _log.info("pipeline: %d cluster(s) con verificación en_curso atascada reseteados a re-verificación.", n)
    return n


def _fecha_aware(crudo: str) -> datetime | None:
    """Parsea un ISO del tema a datetime CON tz (naive = UTC); None si no es parseable."""
    try:
        valor = datetime.fromisoformat(crudo)
    except (TypeError, ValueError):
        return None
    return valor.replace(tzinfo=timezone.utc) if valor.tzinfo is None else valor


def promover_clusters_marca(
    marca: str, *, maximo: int, cupos_categoria: dict[str, int] | None = None,
    verificacion_estados: tuple[str, ...] = VERIFICADAS_OK,
) -> list[dict[str, Any]]:
    """CI — promueve a temas las top-N historias rankeadas de una marca. Registra la etapa CI.

    Consume el pool ya fusionado/rankeado (Ola B). El filtro `verificacion_estados` (ADR 0011 F3) es
    OBLIGATORIO — por defecto las VERIFICADAS (`VERIFICADAS_OK`): la admisión SIEMPRE verificación, no
    hay camino que promueva sin filtrar por verificacion. Devuelve los temas creados. Best-effort por
    historia.
    """
    clusters = clusters_para_promover(
        marca, maximo=maximo, cupos_categoria=cupos_categoria, verificacion_estados=verificacion_estados
    )
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
        ETAPA_ADMITIR,
        marca,
        f"Promoción de historias — {marcas.etiqueta_de(marca)}: {len(temas)} temas "
        f"de {len(clusters)} historias rankeadas",
    )
    return temas


def clusters_portal(marca: str, *, maximo: int) -> list[dict[str, Any]]:
    """Historias (`estado='nuevo'`) de la marca de FUENTE PROPIA, para el canal PORTAL.

    SIN umbral ni verificación: el portal del cliente es first-party y se auto-produce TODO. Lee el
    pool rankeado y se queda con las cuyo origen primario es una fuente `propia=1`. Ordenadas por
    score (el pool ya viene rankeado); recortadas a `maximo`. Best-effort: [] ante fallo o maximo<=0.
    """
    if maximo <= 0:
        return []
    limite = max(maximo * 4, 80)
    try:
        clusters, _total = repos.listar_noticia_clusters(marca=marca, estado="nuevo", limite=limite)
    except Exception:  # noqa: BLE001 -- sin pool legible, esta marca no aporta al Portal este tick
        _log.warning("portal: no se pudieron leer historias propias (%s)", marca, exc_info=True)
        return []
    cache_propia: dict[str, bool] = {}
    propias: list[dict[str, Any]] = []
    for c in clusters:
        if _es_fuente_propia(c.get("primera_fuente") or "", cache_propia):
            propias.append(c)
            if len(propias) >= maximo:
                break
    return propias


def promover_portal(marca: str, *, maximo: int) -> list[dict[str, Any]]:
    """Canal PORTAL — admite DIRECTO las historias de fuente propia de `marca` como temas
    `origen='portal'` (sin umbral ni verificación, ver `crear_tema_de_cluster(portal=True)`).

    Reusa la misma creación de tema que el pipeline (nota del cluster, imagen de la fuente,
    `copy_pendiente`, dedup), solo que el tema nace `origen='portal'`/`saltada` y va DIRECTO a
    producción. Registra la etapa. Devuelve los temas creados. Best-effort por historia.
    """
    clusters = clusters_portal(marca, maximo=maximo)
    if not clusters:
        return []
    claves_vistas = _claves_dedup_marca(marca)
    temas: list[dict[str, Any]] = []
    for cluster in clusters:
        try:
            items = repos.items_de_cluster(cluster.get("id") or "", limite=_MAX_ENLACES_CLUSTER)
            tema = crear_tema_de_cluster(cluster, items, claves_vistas=claves_vistas, portal=True)
        except Exception:  # noqa: BLE001 -- una historia problemática no aborta el barrido del Portal
            _log.exception("portal: fallo al admitir una historia propia (%s)", marca)
            continue
        if tema:
            temas.append(tema)
    if temas:
        registrar_etapa(
            ETAPA_ADMITIR, marca,
            f"Portal — {marcas.etiqueta_de(marca)}: {len(temas)} temas de fuente propia",
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


def _fetch_cuerpo(enlace: str) -> str:
    """Cuerpo del artículo de `enlace` SI el flag `pipeline_fetch_fuente` está ON; "" si no.

    Concentra el gate + el seam: las builders de nota quedan PURAS (sin red) y la decisión de
    pegar a la red vive aquí. Best-effort: gateada off o ante cualquier fallo, devuelve "" y la
    nota cae a título+resumen como hasta ahora.
    """
    if not enlace or not config.pipeline_fetch_fuente():
        return ""
    try:
        return (_ref._FETCH_ARTICULO(enlace) or "").strip()
    except Exception:  # noqa: BLE001 -- el cuerpo es un extra; nunca rompe el barrido
        return ""

