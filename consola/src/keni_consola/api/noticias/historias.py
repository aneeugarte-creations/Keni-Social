"""HISTORIAS: newsroom story view sobre los clusters + la Mesa de redacción.

Vista por HISTORIA (cluster) del archivo: listar/detalle, la Mesa segmentada por las líneas
del plan, la promoción al tablero (`usar`), y la curación a escala (descartar + lotes de
descarte/borrado/vaciado). Aquí viven sus handlers y los helpers de serialización de
una historia (`_historia_a_dict` y satélites: estado de pieza, umbral de producción, pesos del
score, timeline de fuentes). El pool a nivel de ITEM vive en `items.py`.
"""

from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import autogen_redactar, bootstrap_lineas, config, estados, marcas, repos
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

# Máximo de enlaces corroborantes (fuentes) a exponer en una Historia.
_MAX_ENLACES_HISTORIA = 8


def _fuentes_timeline(detalle: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Timeline de outlets de una historia (de `fuentes_detalle` persistido) para la UI.

    Cada entrada: `{fuente, fuente_id, peso, tier, primer_visto, n_items}` en orden
    cronológico (el primero ABRIÓ la historia). Best-effort: entradas malformadas se saltan.
    """
    from ...dominio import fuentes_pesos

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


def _pieza_estado(estado: str, publicacion_id: str, resumen: dict[str, str]) -> str:
    """Estado REAL de la historia DE CARA AL FEED, derivado de la pieza (no solo del cluster).

    El cluster `usado` significa "promovida a la máquina de contenido", NO "en el feed": la
    pieza sale REAL en el feed solo cuando existe su fila `pieza` CON copy. Para
    que el badge no mienta, derivamos 5 estados:
      - 'en_pool'    -> aún no promovida (cluster 'nuevo'),
      - 'descartada' -> cluster 'descartado',
      - 'en_cola'    -> promovida pero SIN pieza en el feed todavía (dedup, sin redes, o copy
                        aún por encolar / etapa Redactar detenida),
      - 'generando'  -> pieza creada, copy en proceso (fila sin `copy` aún),
      - 'en_feed'    -> pieza con copy: visible REAL en el feed.
    `resumen` = mapa `publicacion_id -> 'lista'|'generando'` de `repos.estado_pieza_por_publicacion`.
    """
    if estado == "descartado":
        return "descartada"
    if estado != "usado":
        return "en_pool"
    pieza = resumen.get(publicacion_id) if publicacion_id else None
    if pieza == "lista":
        return "en_feed"
    if pieza == "generando":
        return "generando"
    return "en_cola"


def _pieza_estado_de(cluster: dict[str, Any]) -> str:
    """`_pieza_estado` para UN cluster (un lookup); en listados usa la versión batch."""
    cid = cluster.get("publicacion_id") or ""
    return _pieza_estado(
        cluster.get("estado") or "nuevo", cid, repos.estado_pieza_por_publicacion([cid])
    )


def _evaluar_umbral(
    cluster: dict[str, Any], vocab_memo: dict[str, frozenset[str]]
) -> tuple[bool, str]:
    """Umbral de producción automática de UNA historia, con memo de vocabulario por marca.

    La MISMA evaluación que usa la promoción CI (`noticias_umbral.evaluar`): el panel nunca
    dice una cosa y el pipeline hace otra. `vocab_memo` evita releer el cache del perfil
    editorial por cada historia del listado. Best-effort: ante un fallo se reporta NO
    promovible con motivo genérico (el panel no falla por una historia rara).
    """
    from ... import noticias_umbral

    try:
        marca = str(cluster.get("marca") or "")
        if marca not in vocab_memo:
            vocab_memo[marca] = noticias_umbral.palabras_relevancia(marca)
        return noticias_umbral.evaluar(cluster, palabras_marca=vocab_memo[marca])
    except Exception:  # noqa: BLE001 -- la explicación es informativa; nunca rompe el listado
        return False, "no evaluable"


def _auto_promocion_activa(marca: str, gate_memo: dict[str, bool]) -> bool:
    """¿La auto-promoción (admisión CI «Crear noticias») está encendida para `marca`? Memoizado.

    Es el MISMO gate que abre/cierra la admisión real del barrido de investigación
    (`config.etapa_activa(ENV_PIPELINE_RECOLECTAR, marca)`: maestro global ON y marca no excluida).
    Se lee UNA vez por marca y por request (vía `gate_memo`), no por historia. Best-effort: ante un
    fallo de config se reporta apagada (el badge no promete de más).
    """
    if marca not in gate_memo:
        try:
            gate_memo[marca] = config.etapa_activa(config.ENV_PIPELINE_RECOLECTAR, marca)
        except Exception:  # noqa: BLE001 -- sin gate legible, no prometemos "sale sola"
            gate_memo[marca] = False
    return gate_memo[marca]


def _evaluar_promovible(
    cluster: dict[str, Any],
    vocab_memo: dict[str, frozenset[str]],
    gate_memo: dict[str, bool],
) -> tuple[bool, str]:
    """¿Esta historia se auto-promovería AHORA DE VERDAD? `(promovible, motivo)`.

    Paridad HONESTA con la auto-promoción real (no solo el umbral de score/marca). Una historia
    «sale sola al feed» solo si las TRES condiciones se cumplen:
      1. la máquina de admisión está ENCENDIDA para su marca (`_auto_promocion_activa`); si no, el
         umbral da igual: nada se admite. Es la causa habitual de un badge que mentía (la máquina
         suele estar apagada por defecto).
      2. su `verificacion_fuente` está en `VERIFICADAS_OK` (la admisión filtra por verificación: una
         historia que ahí se descartaría NO es realmente promovible).
      3. supera el umbral de score/marca/maduración/no-dudosa (`_evaluar_umbral`).
    El gate y la verificación se comprueban ANTES del umbral para dar el motivo más útil.
    """
    from ...pipeline_contenido._comun import VERIFICADAS_OK

    marca = str(cluster.get("marca") or "")
    if not _auto_promocion_activa(marca, gate_memo):
        return False, "auto-promoción apagada"
    verificacion = (cluster.get("verificacion_fuente") or "").strip()
    if verificacion not in VERIFICADAS_OK:
        return False, "pendiente de verificación de la fuente"
    return _evaluar_umbral(cluster, vocab_memo)


def _pesos_score_publicos(marca: str = "") -> dict[str, float]:
    """Los PESOS de MÉRITO vivos del ranking (perfil de la marca), para que la UI enseñe el cálculo.

    Modelo v2: el score es `mérito × confianza`. El `score_desglose` persistido trae las señales
    CRUDAS [0,1]; con estos pesos de mérito (perfil POR MARCA) la UI reconstruye la fórmula:
    Σ (señal × peso) = mérito, y `mérito × confianza` (la confianza sale de la corroboración,
    `piso_confianza` es su suelo) = score. Sin esto el ranking sería una caja negra para el equipo.
    """
    p = config.score_pesos(marca)
    return {
        "frescura": round(p.frescura, 3),
        "marca": round(p.marca, 3),
        "evento": round(p.evento, 3),
        "viralidad": round(p.viralidad, 3),
        "velocidad": round(p.velocidad, 3),
        "rendimiento": round(p.rendimiento, 3),
        "breaking": round(p.breaking, 3),
        "piso_confianza": round(p.piso_confianza, 3),
    }


def _historia_a_dict(
    cluster: dict[str, Any],
    enlaces: list[dict[str, Any]],
    *,
    pieza_estado: str = "en_pool",
    umbral: tuple[bool, str] | None = None,
) -> dict[str, Any]:
    """Serializa una historia (cluster) a la forma `Historia` (snake_case) del contrato.

    `enlaces` = hasta `_MAX_ENLACES_HISTORIA` items del cluster como fuentes corroborantes
    `{titulo, url, fuente}` (deduplicados por url, preservando orden). `marca_nombre` resuelve
    el nombre humano de la marca dominante.

    TRADUCCIÓN: si la historia está `traducido`, se sirve `titulo`/`resumen` YA en ES
    (`titulo_es`/`resumen_es`) y se exponen `titulo_original`/`idioma`/`traducido` para que la UI
    pueda mostrar "traducido de {idioma}". Si no, se sirven los originales. `verificacion` expone
    la corroboración (corroborada / unica_fuente / dudosa).
    """
    from ...dominio import fuentes_pesos

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
                # `fuente_id` para que la UI marque el origen (p. ej. "(Google Trends)") sin
                # depender del nombre del medio, que en Trends es el outlet suelto.
                "fuente_id": it.get("fuente_id") or "",
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

    # La mesa se ve SIEMPRE en español: una historia EXTRANJERA aún sin traducir NUNCA muestra su
    # titular en idioma original. Se marca `traduciendo` y se sirve un placeholder hasta que la
    # fase Traducir (cada barrido, ~30 s, por prioridad de score) la pase a ES. Mismo criterio
    # que Admitir (`_falta_traduccion`). El original sigue disponible en `titulo_original`.
    idioma_l = (cluster.get("idioma") or "").strip().lower()
    traduciendo = bool(idioma_l) and not idioma_l.startswith("es") and not traducido
    if traduciendo:
        titulo = "Traduciendo…"
        resumen = ""

    return {
        "id": cluster["id"],
        "titulo": titulo,
        "resumen": resumen,
        "marca": cluster.get("marca") or "",
        "marca_nombre": marcas.etiqueta_de(cluster["marca"]) if cluster.get("marca") else "",
        # MACRO-EVENTO (Fase A): etiqueta de la familia de clusters de un mismo gran evento
        # (la pone Fusionar sin fundirlos); el panel agrupa por aquí. Vacío = sin macro-evento.
        "tema_macro": cluster.get("tema_macro") or "",
        "categoria": cluster.get("categoria") or "",
        "geo": cluster.get("geo") or "",
        "n_items": int(cluster.get("n_items") or 0),
        "n_fuentes": int(cluster.get("n_fuentes") or 0),
        "idiomas": cluster.get("idiomas") or [],
        "senal": int(cluster.get("senal") or 0),
        "score": float(cluster.get("score") or 0.0),
        # Relevancia EXPLICABLE: la razón humana del score y su desglose por señal (los
        # persiste el daemon al puntuar; ver `agrupar.puntuar_detalle`).
        "score_razon": cluster.get("score_razon") or "",
        "score_desglose": cluster.get("score_desglose") or {},
        # "Sale sola al feed" HONESTO: True solo si esta historia se auto-promovería AHORA de
        # verdad — máquina de admisión ENCENDIDA para la marca + `verificacion_fuente` OK + umbral
        # de score/marca (lo calcula `_evaluar_promovible`). `promovible_motivo` lo explica
        # (p. ej. "auto-promoción apagada" si la máquina está OFF).
        "promovible": bool(umbral[0]) if umbral else False,
        "promovible_motivo": (umbral[1] if umbral else ""),
        "breaking": int(cluster.get("breaking") or 0),
        "verificacion": cluster.get("verificacion") or "unica_fuente",
        # Etapas de INVESTIGACIÓN visibles por historia (ADR 0011): el verificacion de
        # VERIFICACIÓN (verificación de la fuente, del contenido asociado; lo inyecta el llamante en
        # lote) y si la MARCA la asignó el clasificador IA.
        "verificacion_fuente": cluster.get("verificacion_fuente") or "",
        "marca_clasificada_por_ia": bool(cluster.get("marca_clasificada_por_ia")),
        "traducido": traducido,
        # Extranjera aún sin traducir: la UI muestra la fila con un indicador "Traduciendo…" en
        # vez del titular en idioma original (que va en `titulo_original`).
        "traduciendo": traduciendo,
        "idioma": cluster.get("idioma") or "",
        "titulo_original": titulo_original,
        "primer_visto": cluster.get("primer_visto") or "",
        "ultimo_visto": cluster.get("ultimo_visto") or "",
        "estado": cluster.get("estado") or "nuevo",
        "publicacion_id": cluster.get("publicacion_id") or "",
        # Estado REAL de cara al feed (derivado de la pieza, no solo del cluster). El front
        # pinta el badge con ESTE campo: nunca dice "En el feed" si la pieza no está.
        "pieza_estado": pieza_estado,
        "enlaces": enlaces_pub,
        # Los PESOS vivos de la fórmula (editables en ajustes): con las señales crudas del
        # desglose, la UI enseña el cálculo completo (señal × peso = aporte, Σ = score).
        "score_pesos": _pesos_score_publicos(cluster.get("marca") or ""),
        # TRACKING DE FUENTES (ranking ponderado): masa de corroboración (Σ peso por outlet),
        # quién ABRIÓ la historia y el timeline de outlets (orden cronológico, con peso/tier).
        "peso_fuentes": float(cluster.get("peso_fuentes") or 0.0),
        "velocidad": float(cluster.get("velocidad") or 0.0),
        "primera_fuente_nombre": cluster.get("primera_fuente_nombre") or "",
        # `fuente_id` del outlet que ABRIÓ: la UI marca el origen (p. ej. "(Google Trends)")
        # sin fiarse del nombre, que en Trends es el medio suelto que cubrió el tema.
        "primera_fuente_id": cluster.get("primera_fuente") or "",
        "fuentes": _fuentes_timeline(cluster.get("fuentes_detalle") or []),
    }


def _listar_historias(
    marca: str | None,
    desde: str | None,
    estado: str | None,
    limite: int,
    desplazamiento: int,
) -> dict[str, Any]:
    clusters, total = repos.listar_noticia_clusters(
        marca=marca or None,
        desde=desde,
        estado=estado,
        limite=limite,
        desplazamiento=desplazamiento,
    )
    # Estado REAL de cara al feed + verificacion verificación (verificación). El verificación vive en la HISTORIA
    # (`noticias_clusters.verificacion_fuente`, ADR 0011): la verificación corre sobre el cluster ANTES de
    # admitir. Se prefiere el verificacion NATIVO del cluster y se cae al del `contenido` heredado
    # (batch, evita N+1) solo para historias admitidas ANTES de F3 (cluster sin verificacion propio).
    cids = [c.get("publicacion_id") or "" for c in clusters]
    resumen_pieza = repos.estado_pieza_por_publicacion(cids)
    verificacion_map = repos.verificacion_fuente_por_publicacion(cids)
    vocab_memo: dict[str, frozenset[str]] = {}  # vocabulario por marca, 1 lectura por request
    gate_memo: dict[str, bool] = {}  # gate de auto-promoción por marca, 1 lectura por request
    historias = []
    for c in clusters:
        enriquecido = {
            **c,
            "verificacion_fuente": (c.get("verificacion_fuente") or "")
            or verificacion_map.get(c.get("publicacion_id") or "", ""),
        }
        historias.append(
            _historia_a_dict(
                enriquecido,
                repos.items_de_cluster(c["id"], limite=_MAX_ENLACES_HISTORIA),
                pieza_estado=_pieza_estado(
                    c.get("estado") or "nuevo", c.get("publicacion_id") or "", resumen_pieza
                ),
                umbral=_evaluar_promovible(enriquecido, vocab_memo, gate_memo),
            )
        )
    return {"historias": historias, "total": total}


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

    cuerpo = await run_in_threadpool(
        _listar_historias, marca, desde, estado, limite, desplazamiento
    )
    return JSONResponse(cuerpo)


# Historias por línea en la respuesta de la Mesa (top-N por sección; "Ver todas" pagina
# contra /historias con su filtro). Tope defensivo del query param.
_MESA_POR_LINEA_DEF = 5
_MESA_POR_LINEA_MAX = 20
# Muestra del pool que se reparte por línea (el pool viene rankeado por score: con cientos
# de historias vivas la muestra cubre de sobra el top de cada línea). Los conteos `en_pool` se
# escalan al COUNT(*) real del pool, así no mienten cuando el pool supera la muestra.
_MESA_MUESTRA = 300
# Tope de candidatas (rankeadas por score) que viajan en la lista de navegación por GRUPO.
# El conteo por grupo (`en_pool`) se escala al pool real; esta lista es solo el browse visible.
_MESA_GRUPO_TOPE = 60

# Orden de los GRUPOS en la barra de navegación de la Mesa (mayor prioridad primero), según el
# peso editorial real de Claro Sports. Un grupo fuera de esta lista va después, alfabético.
_ORDEN_GRUPOS: tuple[str, ...] = (
    "Fútbol", "Motor", "Olímpicos", "NFL", "Boxeo", "NBA", "Béisbol",
    "Otros deportes", "Actualidad",
)


def _grupos_ordenados(etiquetas: list[dict[str, Any]]) -> list[str]:
    """Grupos distintos (no vacíos) de las líneas de una marca, en el orden de la barra.

    Vacío si la marca no usa grupos (p. ej. UnoTV): la Mesa conserva su layout por plan.
    """
    presentes = {(e.get("grupo") or "") for e in etiquetas if (e.get("grupo") or "")}
    en_orden = [g for g in _ORDEN_GRUPOS if g in presentes]
    return en_orden + sorted(g for g in presentes if g not in _ORDEN_GRUPOS)


# Clave de la línea «fuera del plan» en el reparto por línea de la Mesa (marcas sin grupos).
_LINEA_FUERA = "__fuera__"


def _linea_de_cluster_plan(
    marca: str, cluster: dict[str, Any], plan: dict[str, int], vert_etiquetas: list[dict[str, Any]]
) -> str:
    """Clave de LÍNEA del plan con la que una candidata compite (marcas SIN grupos).

    La MISMA clasificación de la Mesa por plan: una historia compite por la línea de su feed
    (id); si el slug del feed no cae en una línea del plan, se clasifica por CONTENIDO (keywords).
    Devuelve la línea del plan o `_LINEA_FUERA` si no cae en ninguna. PURA (recibe plan/líneas).
    """
    from ...pipeline_contenido import _admitir as _pc_ingesta

    cat = _pc_ingesta.linea_de_cluster(marca, cluster, vert_etiquetas)
    return cat if cat in plan else _LINEA_FUERA


def _linea_de_cluster_grupo(
    cluster: dict[str, Any], vert_etiquetas: list[dict[str, Any]]
) -> str:
    """Id de LÍNEA vertical de una candidata por LÉXICO (marcas CON grupos, p. ej. Claro Sports).

    La MISMA clasificación de la barra de grupos: clasifica el texto contra las líneas de la
    marca. '' si nada casa. PURA (recibe las líneas ya leídas).
    """
    from ...dominio import clasificador_lineas

    texto = f"{cluster.get('titulo', '')} {cluster.get('resumen', '')}"
    return clasificador_lineas.clasificar(texto, vert_etiquetas) or ""


def _serializar_historias(
    lote: list[dict[str, Any]],
    *,
    resumen_pieza: dict[str, str],
    verificacion_map: dict[str, str],
    vocab_memo: dict[str, frozenset[str]],
    gate_memo: dict[str, bool],
) -> list[dict[str, Any]]:
    """Serializa un lote de clusters al contrato `Historia` (estado de pieza + verificación + umbral).

    El MISMO enriquecimiento batch que usa la Mesa: verificación NATIVA del cluster con fallback al
    contenido heredado, estado REAL de pieza y promovible honesto. Los memos (vocabulario/gate por
    marca) se comparten entre llamadas para no releer por historia.
    """
    salida: list[dict[str, Any]] = []
    for c in lote:
        enriquecido = {
            **c,
            "verificacion_fuente": (c.get("verificacion_fuente") or "")
            or verificacion_map.get(c.get("publicacion_id") or "", ""),
        }
        salida.append(
            _historia_a_dict(
                enriquecido,
                repos.items_de_cluster(c["id"], limite=_MAX_ENLACES_HISTORIA),
                pieza_estado=_pieza_estado(
                    c.get("estado") or "nuevo", c.get("publicacion_id") or "", resumen_pieza
                ),
                umbral=_evaluar_promovible(enriquecido, vocab_memo, gate_memo),
            )
        )
    return salida


def _mesa(marca: str, por_linea: int) -> dict[str, Any]:
    from ...tiempo import inicio_dia_cdmx_iso_utc

    plan = config.plan_dia(marca)  # dict ordenado categoria -> cupo ({} sin plan)
    resumen_plan: dict[str, dict[str, int]] = {}
    if plan:
        try:
            # Por JORNADA MX (la parrilla del día): a medianoche de México vuelve a 0.
            resumen_plan = repos.resumen_plan_por_categoria(
                marca, inicio_dia_cdmx_iso_utc()
            )
        except Exception:  # noqa: BLE001 -- sin contador, la mesa muestra progreso 0 (no falla)
            resumen_plan = {}

    clusters, total_pool = repos.listar_noticia_clusters(
        marca=marca, estado="nuevo", limite=_MESA_MUESTRA
    )
    # CONTEO HONESTO: `total_pool` es el COUNT(*) REAL del pool de la marca. La clasificación por
    # línea/grupo solo puede correr sobre la MUESTRA topada (`_MESA_MUESTRA`), que es lo que se
    # renderiza como top-N. Si el pool real supera la muestra, los conteos de la muestra
    # subestiman: se ESCALAN al total real (factor = total_pool / muestra) para que cada `en_pool`
    # sea representativo del pool entero y no del recorte (el "300 vs 13"). Sin tope (muestra ⊇
    # pool) el factor es 1.0 y los conteos son exactos. `historias[]` sigue siendo top-N por línea.
    _factor = (total_pool / len(clusters)) if clusters else 1.0

    def _en_pool(n_muestra: int) -> int:
        """Escala un conteo de la MUESTRA al pool REAL (exacto si la muestra no se topó)."""
        return n_muestra if _factor == 1.0 else round(n_muestra * _factor)

    # Líneas (vertical) de la marca: el reparto al plan y la barra de grupos las reusan.
    vert_etiquetas = repos.listar_etiquetas(marca=marca, clase="vertical", solo_activas=True)
    grupos_orden = _grupos_ordenados(vert_etiquetas)
    # Reparto por LÍNEA (el pool ya viene ordenado por score: cada lista queda rankeada). Una
    # historia compite por la línea de su feed (id); si el slug del feed no cae en una línea del
    # plan, se clasifica por CONTENIDO (keywords) — así un feed mixto (divulgación) reparte cada
    # nota a su línea. Las marcas con grupos clasifican aparte (abajo) y aquí no reclasifican.
    etiquetas_fallback = [] if grupos_orden else vert_etiquetas
    por_linea_pool: dict[str, list[dict[str, Any]]] = {}
    for c in clusters:
        destino = _linea_de_cluster_plan(marca, c, plan, etiquetas_fallback)
        por_linea_pool.setdefault(destino, []).append(c)

    # Barra de GRUPOS (navegación temática): solo marcas con grupos definidos (p. ej. Claro
    # Sports). Clasifica cada candidata en su LÍNEA por léxico (keywords) y la cuelga de su GRUPO.
    # El resto de marcas (sin grupos, p. ej. UnoTV) conserva el layout por plan y se salta el coste.
    grupo_por_cluster: dict[str, str] = {}
    linea_por_cluster: dict[str, str] = {}
    conteo_grupo: dict[str, int] = dict.fromkeys(grupos_orden, 0)
    conteo_linea: dict[str, int] = {}
    if grupos_orden:
        grupo_de_linea = {e["id"]: (e.get("grupo") or "") for e in vert_etiquetas}
        for c in clusters:
            lid = _linea_de_cluster_grupo(c, vert_etiquetas)
            grupo = grupo_de_linea.get(lid, "")
            grupo_por_cluster[c["id"]] = grupo
            linea_por_cluster[c["id"]] = lid
            if grupo in conteo_grupo:
                conteo_grupo[grupo] += 1
            if lid:
                conteo_linea[lid] = conteo_linea.get(lid, 0) + 1

    def _etiqueta_linea(clave: str) -> str:
        rotulo = bootstrap_lineas.ETIQUETAS_CLAVE_NO_LINEA.get(clave)
        if rotulo is not None:
            return rotulo
        et = repos.obtener_etiqueta(clave)
        return (et or {}).get("nombre") or clave

    cids = [c.get("publicacion_id") or "" for c in clusters]
    resumen_pieza = repos.estado_pieza_por_publicacion(cids)
    # Verificacion de verificación por historia: NATIVO del cluster (ADR 0011), con fallback al
    # contenido heredado para historias admitidas antes de F3 (cluster sin verificacion propio).
    verificacion_map = repos.verificacion_fuente_por_publicacion(cids)
    vocab_memo: dict[str, frozenset[str]] = {}
    gate_memo: dict[str, bool] = {}  # gate de auto-promoción por marca, 1 lectura por request

    def _historias(lote: list[dict[str, Any]], limite: int | None = None) -> list[dict[str, Any]]:
        tope = por_linea if limite is None else limite
        return _serializar_historias(
            lote[:tope],
            resumen_pieza=resumen_pieza,
            verificacion_map=verificacion_map,
            vocab_memo=vocab_memo,
            gate_memo=gate_memo,
        )

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
                "etiqueta": _etiqueta_linea(cat),
                "cupo": int(plan[cat]),
                "generados": generados,
                "publicados": int(contadores.get("publicados", 0)),
                "restante": max(0, int(plan[cat]) - generados),
                "en_pool": _en_pool(len(pool)),
                "historias": _historias(pool),
            }
        )
    fuera = por_linea_pool.get("__fuera__", [])
    # Navegación por GRUPO (si la marca usa grupos): la lista visible (top por score, tag de grupo)
    # y el resumen ordenado de chips con su conteo. En este modo el front ignora `fuera_de_plan`
    # (los grupos cubren todo el pool), así que no se construye su lista.
    historias_grupo: list[dict[str, Any]] = []
    grupos: list[dict[str, Any]] = []
    if grupos_orden:
        historias_grupo = _historias(clusters, limite=_MESA_GRUPO_TOPE)
        for h in historias_grupo:
            h["grupo"] = grupo_por_cluster.get(h["id"], "")
            h["linea"] = linea_por_cluster.get(h["id"], "")
        # Líneas de cada grupo (2º nivel de navegación): id, nombre y candidatas en pool. Orden:
        # las que tienen candidatas primero (mayor conteo arriba), las vacías al final. `vert_etiquetas`
        # ya viene alfabético por nombre, así que el orden estable rompe empates alfabéticamente.
        lineas_por_grupo: dict[str, list[dict[str, Any]]] = {}
        for e in vert_etiquetas:
            g = e.get("grupo") or ""
            if not g:
                continue
            lineas_por_grupo.setdefault(g, []).append(
                {
                    "linea": e["id"],
                    "nombre": e.get("nombre") or e["id"],
                    "en_pool": _en_pool(conteo_linea.get(e["id"], 0)),
                }
            )
        grupos = [
            {
                "grupo": g,
                "en_pool": _en_pool(conteo_grupo.get(g, 0)),
                "lineas": sorted(lineas_por_grupo.get(g, []), key=lambda li: -li["en_pool"]),
            }
            for g in grupos_orden
        ]
    return {
        "marca": marca,
        "plan": bool(plan),
        "lineas": lineas,
        "fuera_de_plan": {
            "en_pool": _en_pool(len(fuera)),
            "historias": [] if grupos_orden else _historias(fuera),
        },
        # Tamaño REAL del pool (COUNT(*), no la muestra topada): el número honesto de candidatas
        # vivas de la marca. Los `en_pool` por línea/grupo se escalan a este total.
        "en_pool_total": total_pool,
        "total_objetivo": sum(int(v) for v in plan.values()),
        "total_generados": total_generados,
        "grupos": grupos,
        "historias_grupo": historias_grupo,
    }


async def mesa(request: Request) -> Response:
    """GET /api/noticias/mesa?marca=&por_linea=: el pool SEGMENTADO por las líneas del plan.

    La vista de trabajo de la Mesa de redacción: para una marca concreta devuelve sus líneas
    del plan editorial diario (cupo, generados/publicados en 24 h móviles, restante) con las
    top-N candidatas (`estado='nuevo'`) de cada una, más el bloque `fuera_de_plan` (líneas de
    feed que el plan no contempla). Una historia compite por la línea de su
    `categoria_efectiva` ('breaking' si lo es — el MISMO criterio que Admitir (CI)).
    Sin plan configurado: `plan=false` y todo el pool va en `fuera_de_plan` (la UI degrada a
    lista plana). Orden de líneas: breaking primero, luego el orden del plan.

    CONTEO HONESTO: `en_pool_total` es el COUNT(*) REAL del pool; los `en_pool` por línea/grupo se
    escalan a ese total (la clasificación corre sobre una muestra topada). `historias[]` son SIEMPRE
    el top-N por línea, no el pool entero (para el resto, "Ver todas" pagina contra /historias).
    """
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

    cuerpo = await run_in_threadpool(_mesa, marca, por_linea)
    return JSONResponse(cuerpo)


# Pool entero de la marca que la paginación por línea clasifica (el pool está acotado por el TTL,
# ≈300-400 candidatas, nunca miles: clasificar el pool completo en cada request es barato).
_MESA_LINEA_POOL_MAX = 2000
# Página de la lista paginada por línea (mismo tamaño que la lista plana de la vista admin).
_MESA_LINEA_LIMIT_DEF = 30
_MESA_LINEA_LIMIT_MAX = 60


def _clusters_de_linea(
    marca: str, linea: str, clusters: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Filtra el pool a la LÍNEA pedida, REUSANDO la clasificación de la Mesa.

    Si la marca usa grupos (Claro Sports) clasifica por LÉXICO (`_linea_de_cluster_grupo`); si no,
    por el reparto del plan (`_linea_de_cluster_plan`, que incluye `breaking` y `_LINEA_FUERA`). La
    `linea` pedida casa la clave de ese reparto: un id de etiqueta vertical, `breaking`/`evergreen`,
    o `__fuera__` (alias `fuera`). El pool ya viene rankeado por score, así que la salida también.
    """
    vert_etiquetas = repos.listar_etiquetas(marca=marca, clase="vertical", solo_activas=True)
    grupos_orden = _grupos_ordenados(vert_etiquetas)
    objetivo = _LINEA_FUERA if linea in (_LINEA_FUERA, "fuera") else linea
    if grupos_orden:
        return [c for c in clusters if _linea_de_cluster_grupo(c, vert_etiquetas) == objetivo]
    plan = config.plan_dia(marca)
    return [
        c for c in clusters if _linea_de_cluster_plan(marca, c, plan, vert_etiquetas) == objetivo
    ]


def _mesa_linea(marca: str, linea: str, desplazamiento: int, limite: int) -> dict[str, Any]:
    """Candidatas de UNA línea, PAGINADAS: la página (offset/limit) + el TOTAL real de la línea.

    Trae el pool entero de la marca (`estado='nuevo'`, acotado por el TTL), lo clasifica con la
    MISMA lógica de la Mesa y filtra a `linea`. Devuelve `{historias, total}` con cada historia en
    el contrato `Historia` (mismo `_historia_a_dict`: promovible honesto, score, fuentes…).
    """
    clusters, _ = repos.listar_noticia_clusters(
        marca=marca, estado="nuevo", limite=_MESA_LINEA_POOL_MAX
    )
    de_linea = _clusters_de_linea(marca, linea, clusters)
    total = len(de_linea)
    pagina = de_linea[desplazamiento : desplazamiento + limite]

    cids = [c.get("publicacion_id") or "" for c in pagina]
    resumen_pieza = repos.estado_pieza_por_publicacion(cids)
    verificacion_map = repos.verificacion_fuente_por_publicacion(cids)
    historias = _serializar_historias(
        pagina,
        resumen_pieza=resumen_pieza,
        verificacion_map=verificacion_map,
        vocab_memo={},
        gate_memo={},
    )
    return {"historias": historias, "total": total}


async def mesa_linea(request: Request) -> Response:
    """GET /api/noticias/mesa/linea?marca=&linea=&offset=&limit=: candidatas de UNA línea, PAGINADAS.

    El complemento navegable de la Mesa: mientras `mesa` resume el top-N por línea, esto recorre
    TODAS las candidatas (`estado='nuevo'`) de una marca+línea, rankeadas por score, en páginas
    (offset/limit, def 30). `linea` es la clave del reparto de la Mesa: un id de etiqueta vertical,
    `breaking`/`evergreen`, o `__fuera__` (alias `fuera`) para lo que el plan no contempla. Devuelve
    `{historias, total}` (el total es el de la línea entera, no el de la página) con el contrato
    `Historia` completo. Marca obligatoria; sin `linea` es 400.
    """
    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    if not marca:
        return JSONResponse(
            {"error": "La mesa es por marca: elige una marca concreta."}, status_code=400
        )
    linea = (request.query_params.get("linea") or "").strip()
    if not linea:
        return JSONResponse({"error": "Falta la línea a paginar."}, status_code=400)

    try:
        limite = int(request.query_params.get("limit") or _MESA_LINEA_LIMIT_DEF)
    except ValueError:
        limite = _MESA_LINEA_LIMIT_DEF
    limite = max(1, min(limite, _MESA_LINEA_LIMIT_MAX))
    try:
        desplazamiento = int(request.query_params.get("offset") or 0)
    except ValueError:
        desplazamiento = 0
    desplazamiento = max(0, desplazamiento)

    cuerpo = await run_in_threadpool(_mesa_linea, marca, linea, desplazamiento, limite)
    return JSONResponse(cuerpo)


def _detalle_historia(cluster_id: str) -> tuple[int, dict[str, Any]]:
    cluster = repos.obtener_noticia_cluster(cluster_id)
    if cluster is None:
        return 404, {"error": "Esa historia ya no existe."}
    items = repos.items_de_cluster(cluster_id)
    cid = cluster.get("publicacion_id") or ""
    # Verificacion NATIVO del cluster (ADR 0011: la verificación corre sobre la historia); fallback al
    # contenido heredado para historias admitidas antes de F3 (cluster sin verificacion propio).
    verificacion_fuente = (cluster.get("verificacion_fuente") or "") or (
        repos.verificacion_fuente_por_publicacion([cid]).get(cid, "") if cid else ""
    )
    enriquecido = {**cluster, "verificacion_fuente": verificacion_fuente}
    historia = _historia_a_dict(
        enriquecido, items, pieza_estado=_pieza_estado_de(cluster),
        umbral=_evaluar_promovible(enriquecido, {}, {}),
    )
    return 200, {"historia": historia, "items": [_item_a_dict(it) for it in items]}


async def detalle_historia(request: Request) -> Response:
    """GET /api/noticias/historias/{id}: la historia + TODOS sus items de archivo."""
    cluster_id = request.path_params["cluster_id"]
    status, cuerpo = await run_in_threadpool(_detalle_historia, cluster_id)
    return JSONResponse(cuerpo, status_code=status)


def _cargar_usar(
    cluster_id: str,
) -> tuple[int | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Lee el cluster y resuelve los cortes tempranos (no existe / ya usada) antes de traducir.

    Devuelve `(status, cuerpo, cluster)`: si `status` no es None el handler responde ya; si es
    None, `cluster` es la historia cargada lista para traducir y materializar.
    """
    cluster = repos.obtener_noticia_cluster(cluster_id)
    if cluster is None:
        return 404, {"error": "Esa historia ya no existe."}, None
    if cluster.get("estado") == "usado" and cluster.get("publicacion_id"):
        return (
            200,
            {
                "contenido": {"id": cluster["publicacion_id"]},
                "copy_en_proceso": False,
                "ya_usada": True,
            },
            None,
        )
    return None, None, cluster


def _materializar_usar(
    cluster: dict[str, Any],
    cluster_id: str,
    redes_iniciales: list[str],
    generar: bool,
    autor: str,
) -> tuple[int, dict[str, Any]]:
    """Crea la pieza en el tablero a partir de la historia (ya traducida) y marca el cluster usado."""
    from ...pipeline_contenido import _admitir as _pc_ingesta

    marca = cluster.get("marca") or ""
    items = repos.items_de_cluster(cluster_id, limite=_MAX_ENLACES_HISTORIA)
    # Título/resumen en español (traducido a MX si existe), nunca el original extranjero.
    titulo = _pc_ingesta._titulo_es(cluster) or (items[0]["url"] if items else "")
    if not titulo:
        return 400, {"error": "La historia no tiene título ni enlace."}
    descripcion = _pc_ingesta._resumen_es(cluster)
    # Enlaces corroborantes en la nota, para trazar las fuentes de la historia.
    fuentes = [it.get("url") for it in items if it.get("url")][:_MAX_ENLACES_HISTORIA]
    if fuentes:
        descripcion = (descripcion + "\n\nFuentes:\n" + "\n".join(fuentes)).strip()

    url_fuente = items[0].get("url_canonica") if items else ""
    fecha_fuente = cluster.get("primer_visto") or ""

    contenido = repos.crear_publicacion(
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
        autor=autor,
        origen=estados.ORIGEN_HISTORIA,
        tipo_contenido="fuente",
        fecha_fuente=fecha_fuente,
        url_fuente=url_fuente or "",
    )
    for red in redes_iniciales:
        repos.crear_pieza_fila(
            publicacion_id=contenido["id"], red=red, falta_copy=True, falta_imagen=True
        )

    genero = False
    if marca and generar:
        try:
            genero = autogen_redactar.lanzar_para_topic(contenido) is not None
        except Exception:  # noqa: BLE001 -- la generación es opcional; nunca tumba el uso
            genero = False

    repos.actualizar_noticia_cluster(cluster_id, estado="usado", publicacion_id=contenido["id"])
    repos.marcar_items_cluster_usados(cluster_id, contenido["id"])
    plataformas = repos.listar_piezas_fila(contenido["id"])
    return 200, {
        "contenido": {**contenido, "plataformas": plataformas},
        "copy_en_proceso": genero,
    }


async def usar_historia(request: Request) -> Response:
    """POST /api/noticias/historias/{id}/usar: lleva la historia al tablero (borrador).

    Cuerpo `{redes?: [ids], generar?: bool}`. Reusa el camino de la aportación manual: crea un
    `contenido` (`flujo='importante'`, `origen='historia'`, `tipo_contenido='fuente'`) con el
    título/resumen representativos de la historia y sus enlaces corroborantes en la nota; si
    hay marca y `generar` (def True), encola copy. Marca el cluster `usado` + `publicacion_id` y
    todos sus items `usado`. Idempotente-amistoso: si ya estaba usado, devuelve lo enlazado.
    """
    cluster_id = request.path_params["cluster_id"]
    status, cuerpo, cluster = await run_in_threadpool(_cargar_usar, cluster_id)
    if status is not None:
        return JSONResponse(cuerpo, status_code=status)

    from ...pipeline_contenido import _admitir as _pc_ingesta

    # Una historia extranjera aún sin traducir NO baja al tablero en inglés: la traducimos EN EL
    # ACTO (y la persistimos) antes de crear la pieza, en vez de esperar al barrido del daemon.
    # Es extranjera si su `idioma` lo declara O si el TEXTO del título lo delata (cubre el idioma
    # vacío y el mal etiquetado 'es'). Sin `titulo_es` aún -> hay que traducir.
    idioma_l = (cluster.get("idioma") or "").strip().lower()
    extranjera = (bool(idioma_l) and not idioma_l.startswith("es")) or _pc_ingesta._texto_es_extranjero(
        cluster.get("titulo") or ""
    )
    if not (cluster.get("titulo_es") or "").strip() and extranjera:
        traducido = await run_in_threadpool(_pc_ingesta.traducir_cluster_ahora, cluster)
        if traducido is None:
            return JSONResponse(
                {"error": "No se pudo traducir la historia ahora mismo. Inténtalo en unos segundos."},
                status_code=503,
            )
        cluster = traducido

    datos = await leer_json(request)
    redes_iniciales = _redes_iniciales(datos.get("redes"))
    generar = datos.get("generar", True)
    autor = autor_de_peticion(request)

    status, cuerpo = await run_in_threadpool(
        _materializar_usar, cluster, cluster_id, redes_iniciales, generar, autor
    )
    return JSONResponse(cuerpo, status_code=status)


def _descartar_historia(cluster_id: str) -> tuple[int, dict[str, Any]]:
    cluster = repos.obtener_noticia_cluster(cluster_id)
    if cluster is None:
        return 404, {"error": "Esa historia ya no existe."}
    # Descartar BORRA la historia (no la marca): la fila del cluster se elimina y sus items quedan
    # como lápida `descartado` para que no reaparezca al re-recolectar. La respuesta devuelve la
    # historia tal como quedó (sin fila ya), con `estado='descartado'` por contrato del front.
    repos.descartar_cluster(cluster_id)
    historia = _historia_a_dict(
        {**cluster, "estado": "descartado"}, [], pieza_estado="descartada"
    )
    return 200, {"historia": historia}


async def descartar_historia(request: Request) -> Response:
    """POST /api/noticias/historias/{id}/descartar: BORRA la historia (irreversible, sin reaparición).

    Elimina la fila del cluster y deja sus items como lápida `descartado` (bloquea la re-ingesta y
    el clustering). El front pide confirmación; aquí solo se es idempotente (404 si ya no existe).
    """
    cluster_id = request.path_params["cluster_id"]
    status, cuerpo = await run_in_threadpool(_descartar_historia, cluster_id)
    return JSONResponse(cuerpo, status_code=status)


# Tope de ids por lote, para que un cuerpo enorme no dispare un barrido de updates sin control.
_MAX_LOTE_DESCARTE = 500


def _descartar_historias_lote(ids: list) -> dict[str, Any]:
    descartadas = 0
    for cid in dict.fromkeys(ids):  # dedup preservando orden; evita doble borrado del mismo id
        if not isinstance(cid, str) or not cid:
            continue
        if descartadas >= _MAX_LOTE_DESCARTE:
            break
        if repos.descartar_cluster(cid):
            descartadas += 1
    return {"descartadas": descartadas}


async def descartar_historias_lote(request: Request) -> Response:
    """POST /api/noticias/historias/descartar-lote: descarta VARIAS historias de una (papelera).

    Cuerpo `{ids: [cluster_id, ...]}`. BORRA cada cluster existente (sus items quedan como lápida
    `descartado` anti-reaparición); idempotente: ignora ids vacíos, repetidos o que ya no existen.
    Es el motor del multi-selección estilo correo de Investigación: seleccionar (o "todos") +
    descartar. Devuelve `{descartadas: n}` (cuántas se borraron de verdad).
    """
    datos = await leer_json(request)
    ids = datos.get("ids")
    if not isinstance(ids, list):
        return JSONResponse({"error": "Se esperaba una lista de ids."}, status_code=400)
    cuerpo = await run_in_threadpool(_descartar_historias_lote, ids)
    return JSONResponse(cuerpo)


async def borrar_historias_lote(request: Request) -> Response:
    """POST /api/noticias/historias/borrar-lote: BORRA HARD (irreversible) varias historias + artículos.

    Cuerpo `{ids: [cluster_id, ...]}`. A diferencia de `descartar-lote` (que solo marca el estado),
    esto ELIMINA del archivo el cluster Y sus `noticias_items` (si no, el agrupado los reagrupa y
    la historia reaparece). Idempotente; tope de seguridad `_MAX_LOTE_DESCARTE`. Devuelve `{borradas:n}`.
    """
    datos = await leer_json(request)
    ids = datos.get("ids")
    if not isinstance(ids, list):
        return JSONResponse({"error": "Se esperaba una lista de ids."}, status_code=400)
    limpios = [c for c in ids if isinstance(c, str) and c][:_MAX_LOTE_DESCARTE]
    borradas = await run_in_threadpool(repos.borrar_clusters_con_items, limpios)
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
    borradas = await run_in_threadpool(repos.vaciar_clusters, marca, estado)
    return JSONResponse({"borradas": borradas})
