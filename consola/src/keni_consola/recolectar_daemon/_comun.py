"""Estado y helpers COMPARTIDOS del motor de recolección (refactor de pura reubicación).

Aquí viven, en UN SOLO sitio para no duplicar estado:
  - El logger del daemon (`_log`, nombre `keni_consola.recolectar_daemon`).
  - Los throttles globales de los pasos periódicos (`_ultimo_rescore`,
    `_ultimo_fusionar`, `_ultima_caducidad`) y sus intervalos. Los pasos los leen y
    los sellan vía `_comun.<var>` (no `global` cruzado de módulos): así el estado de
    throttling es único, sin copias divergentes por módulo.
  - Helpers de relevancia/rendimiento, registro de actividad IA, clasificación de marca
    por IA y fusionar un grupo de historias, que comparten varios pasos.

Las funciones que un test parchea sobre el FACADE (`recolectar_daemon._registrar_actividad_ia`,
`_clasificar_marca_ia`, `_fusionar_grupo`) y que se invocan desde OTRO módulo del paquete se
resuelven al vuelo a través del paquete (`_pkg.<nombre>`), para que el parcheo del facade
siga surtiendo efecto tras el troceado.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import keni_consola.recolectar_daemon as _pkg

from .. import config, generaciones, marcas, noticias_umbral, repos
from ..dominio import agrupar, traducir
from ..tiempo import ahora_iso, hoy_utc

_log = logging.getLogger("keni_consola.recolectar_daemon")

# --- Throttles de los pasos periódicos (estado ÚNICO, leído/sellado vía `_comun.<var>`) -----
# Re-score periódico de la ventana: como MÍNIMO cada tantos segundos se repuntúa la ventana
# completa, aunque no entren items nuevos (la frescura decae con el reloj).
_RESCORE_INTERVALO_SEG = 900.0
_ultimo_rescore = 0.0  # time.monotonic() de la última pasada completada

# Fusionar semántico (Haiku): como mucho una pasada por intervalo. Mandar la ventana a Haiku en
# cada tick de 30s sería coste de tokens redundante (las historias del mismo evento aparecen
# despacio); el throttle ligero deja que la dedup semántica corra sin re-llamar en cada barrido.
_FUSIONAR_INTERVALO_SEG = 90.0
_ultimo_fusionar = 0.0  # time.monotonic() de la última pasada completada
# Huella del lote candidato evaluado en la última pasada (skip-if-unchanged): si el lote no
# cambió desde entonces, no se vuelve a llamar al LLM (no habría nada nuevo que fusionar). En
# memoria: al reiniciar el daemon vuelve a None y se re-evalúa una vez (aceptable).
_ultima_huella_fusionar: str | None = None


def _huella_lote(clusters: list[dict[str, Any]]) -> str:
    """Huella ESTABLE del conjunto candidato: ids ordenados + su marcador de cambio (`ultimo_visto`).

    Cambia cuando entra un cluster nuevo, sale uno o uno recibe items nuevos (su `ultimo_visto`
    avanza); idéntica si el lote no se movió. PURA: dos lotes equivalentes dan la misma huella
    sin importar el orden de entrada.
    """
    partes = sorted(f"{c.get('id')}\t{c.get('ultimo_visto') or ''}" for c in clusters)
    return "\n".join(partes)

# Caducidad del pool (TTL): como mucho una pasada cada tantos segundos (la caducidad se mide
# en horas; pasarla en cada tick de 30s sería escritura irrelevante en BD sin efecto).
_CADUCIDAD_INTERVALO_SEG = 900.0
_ultima_caducidad = 0.0  # time.monotonic() de la última pasada completada


def _palabras_relevancia(marca: str, perfil_activo: bool) -> frozenset[str]:
    """Keywords de relevancia de la marca (perfil editorial Haiku si está activo; si no, la base inicial).

    Delegado en `noticias_umbral.palabras_relevancia` (fuente única perfil-vs-base, la misma
    que usan el umbral de promoción y la API del panel; si divergieran, el panel explicaría un
    score que la priorización no calculó).
    """
    return noticias_umbral.palabras_relevancia(marca, perfil_activo)


def eventos_proximos(marca: str) -> list[dict[str, Any]]:
    """Eventos de la AGENDA de la marca en la ventana de encaje (ayer .. +7 días). Best-effort.

    Alimenta la señal de `evento` del scoring (`agrupar.encaje_evento_detalle`): una noticia que
    casa con un evento próximo de `rota_eventos` (p. ej. un partido del Mundial para Claro Sports)
    sube en el ranking. Ante cualquier fallo de lectura devuelve vacío y la señal queda inerte.
    """
    if not marca:
        return []
    try:
        hoy = hoy_utc()
        desde = (hoy - timedelta(days=1)).isoformat()
        hasta = (hoy + timedelta(days=7)).isoformat()
        return repos.listar_eventos_rota(desde=desde, hasta=hasta, marca=marca)
    except Exception:  # noqa: BLE001 -- sin agenda legible la señal de evento queda en 0
        _log.warning("recolectar_daemon: no se pudieron leer eventos de la marca %s.", marca)
        return []


def _rendimiento_top_lineas(marca: str) -> tuple[set[str], dict[str, str], list[dict[str, Any]]]:
    """Precalcula (1 vez por marca y barrido) las líneas TOP por engagement DE ESA MARCA.

    Por MARCA (antes era global: las líneas top se calculaban con las métricas de TODAS las
    marcas, y el éxito de una marca premiaba historias de otra). Gateado por
    `KENI_RENDIMIENTO_RANKING` (def OFF). Best-effort: ante cualquier fallo (sin métricas, sin
    Metricool) devuelve vacío y la señal queda inerte. Devuelve
    `(nombres_top, {etiqueta_id: nombre}, etiquetas_vertical)`.
    """
    if not config.rendimiento_ranking_activo():
        return set(), {}, []
    try:
        from .. import metricas_linea
        from ..dominio import rendimiento_tema

        data = metricas_linea.lineas_y_origenes(
            "mes", marca or None, marcas.id_metricas_de(marca) if marca else None
        )
        top = rendimiento_tema.lineas_top(
            data.get("lineas", []),
            minimo_piezas=config.rendimiento_min_piezas(),
            n=config.rendimiento_top_n(),
        )
        etiquetas = [e for e in repos.listar_etiquetas(clase="vertical") if e.get("id")]
        id_a_nombre = {e["id"]: (e.get("nombre") or "") for e in etiquetas}
        return top, id_a_nombre, etiquetas
    except Exception:  # noqa: BLE001 -- la señal de rendimiento es opcional; nunca rompe la recolección
        _log.warning("recolectar_daemon: no se pudo calcular el rendimiento por línea (señal inerte).", exc_info=True)
        return set(), {}, []


def _rendimiento_bonus(
    cluster: dict[str, Any],
    top_lineas: set[str],
    vert_id_a_nombre: dict[str, str],
    vert_etiquetas: list[dict[str, Any]],
) -> float:
    """Bonus [0,1] de una historia: 1.0 si su línea (clasificación léxica) está en el top. 0 si no."""
    from ..dominio import clasificador_lineas, rendimiento_tema

    texto = f"{cluster.get('titulo', '')} {cluster.get('resumen', '')}"
    lid = clasificador_lineas.clasificar(texto, vert_etiquetas)
    nombre = vert_id_a_nombre.get(lid or "", "")
    return rendimiento_tema.bonus_de_historia(nombre, top_lineas)


def _registrar_actividad_ia(
    marca: str, etiqueta: str, salida: str, *, prompt: str = "", etapa: str = ""
) -> None:
    """Sella una GENERACIÓN-actividad (`tipo='pipeline'`) de un paso IA INLINE del pool (best-effort).

    Hace VISIBLES en «Actividad IA» y en la economía POR ETAPA los pasos Haiku inline del pool
    —Fusionar, Clasificar, Priorizar, Traducir— que comparten `tipo='pipeline'`. Es un
    registro ya COMPLETADO (no encola trabajo: el Haiku ya corrió). `prompt` y `salida` son los
    REALES de la llamada a Haiku (transparencia: qué se pidió y qué respondió token a token); si no
    se pasan, queda solo el resumen. Las MÉTRICAS (tokens/coste/duración) son las acumuladas por el
    ejecutor síncrono desde la última toma (las llamadas Haiku de ESTE paso). `etapa` es la fase del
    pipeline EXPLÍCITA: la economía la usa para desglosar por etapa en vez de colapsar todo el
    `tipo='pipeline'` de investigación en «Verificar». Un fallo al registrar NUNCA aborta el barrido.
    """
    try:
        registro: dict[str, Any] = {
            "tipo": "pipeline",
            # Fusionar/Clasificar/Traducir del pool = INVESTIGACION (motor de noticias). Corre
            # INLINE (Haiku, ya completado: no encola), pero su coste cuenta del lado investigacion.
            "proceso": generaciones.PROCESO_INVESTIGACION,
            "etapa": etapa,
            "marca": marca,
            "etiqueta": etiqueta,
            "prompt": (prompt or "")[:20000],
            "salida": (salida or "")[:20000],
            "estado": generaciones.ESTADO_COMPLETADO,
            "fase": generaciones.FASE_COMPLETADO,
            "fecha_fin": ahora_iso(),
        }
        metricas = traducir.tomar_metricas_acumuladas()
        if metricas:
            registro["metricas"] = metricas
        pub = generaciones.crear(registro)
        # Vuelca su gasto al ledger `gasto_ia` con la ETAPA explícita: `crear` (a diferencia de
        # `actualizar`) no dispara el hook de cierre, así que lo hacemos aquí. Idempotente (UPSERT
        # por gen_id) y no-op sin métricas medibles: una fase sin coste no ensucia el ledger.
        if metricas:
            from .. import presupuesto_ia

            presupuesto_ia.registrar_cierre(pub)
    except Exception:  # noqa: BLE001 -- la actividad es best-effort; nunca rompe la recolección
        _log.warning("recolectar_daemon: no se pudo registrar actividad IA (%s).", etiqueta, exc_info=True)


def _clasificar_marca_ia(cluster: dict[str, Any]) -> str:
    """Asigna marca a un BREAKING sin marca con Haiku. '' si no hay candidatas válidas.

    Las candidatas son `config.marcas_activas()` restringidas a marcas de NOTICIAS
    (`marcas.es_noticias`: el contenido propio nunca recibe clasificación automática); el
    fallback es `config.marca_noticias()` (o la primera candidata). Best-effort: cualquier
    fallo del clasificador devuelve el fallback. Sella la actividad IA (coste visible en Producción).
    """
    from ..dominio import clasificador_marca

    activas = [m for m in config.marcas_activas() if marcas.es_noticias(m)]
    if not activas:
        return ""
    fallback = config.marca_noticias()
    if fallback not in activas:
        fallback = activas[0]
    candidatas = [(m, marcas.etiqueta_de(m)) for m in activas]
    try:
        marca = clasificador_marca.clasificar_marca(
            str(cluster.get("titulo") or ""),
            str(cluster.get("resumen") or ""),
            candidatas,
            fallback=fallback,
        )
    except Exception:  # noqa: BLE001 -- best-effort: nunca rompe el barrido de recolección
        _log.warning("recolectar_daemon: fallo el clasificador de marca IA.", exc_info=True)
        return ""
    _pkg._registrar_actividad_ia(
        marca,
        f"Encaje de marca — breaking → {marcas.etiqueta_de(marca)}",
        f'{{"marca": "{marca}"}}',
        prompt=str(cluster.get("titulo") or "")[:300],
        etapa="Clasificar",
    )
    return marca


def _fusionar_grupo(
    ids: list[str],
    por_id: dict[str, dict[str, Any]],
    *,
    pesos: Any,
    eventos: list[dict[str, Any]] | None = None,
    breaking_peso: float,
    breaking_ventana_h: int,
    fuentes_baja: frozenset[str],
    perfil_activo: bool,
    ahora: datetime,
) -> bool:
    """Funde un grupo de historias en la CANÓNICA (más fuentes, desempate por score).

    Reasigna los items de las absorbidas a la canónica, borra las absorbidas (vacías) y recalcula
    + repuntúa la canónica (n_fuentes/score reales). Devuelve True si fusionó (≥2 historias).

    Salvaguardas:
      - ANTI-TOCTOU: antes de absorber, RE-LEE cada cluster absorbible; si entre la lectura del
        lote y ahora adquirió `publicacion_id` o dejó de ser `nuevo` (el pipeline lo promovió),
        NO se absorbe (se conserva intacto).
      - SIN ITEMS SUELTOS: los items se reasignan en LOTES de 500 HASTA VACIAR el cluster (antes el
        tope de 500 dejaba items colgando del cluster borrado si había más).
    """
    clusters = [por_id[i] for i in ids if i in por_id]
    if len(clusters) < 2:
        return False
    canon = max(clusters, key=lambda c: (int(c.get("n_fuentes") or 0), float(c.get("score") or 0.0)))
    canon_id = str(canon["id"])
    absorbidas = 0
    for c in clusters:
        cid = str(c["id"])
        if cid == canon_id:
            continue
        # Re-verificación anti-TOCTOU: el absorbido pudo ser promovido entre lectura y fusionar.
        actual = repos.obtener_noticia_cluster(cid)
        if actual is None:
            continue
        if (actual.get("publicacion_id") or "") or (actual.get("estado") or "nuevo") != "nuevo":
            continue
        # Reasigna TODOS los items, por lotes, hasta vaciar (cota dura de seguridad: 100 lotes).
        for _ in range(100):
            lote = repos.items_de_cluster(cid, limite=500)
            if not lote:
                break
            repos.asignar_cluster_items({canon_id: [it["id"] for it in lote]})
        repos.borrar_noticia_cluster(cid)
        absorbidas += 1
    if not absorbidas:
        return False
    items = repos.items_de_cluster(canon_id, limite=500)
    if not items:
        return False
    base = repos.obtener_noticia_cluster(canon_id) or canon
    recalc = agrupar.recalcular(
        base, items,
        breaking_peso=breaking_peso,
        breaking_ventana_h=breaking_ventana_h,
        fuentes_baja_confianza=fuentes_baja,
        ahora=ahora,
    )
    palabras = _palabras_relevancia(recalc.get("marca") or "", perfil_activo)
    recalc["score"], recalc["score_razon"], recalc["score_desglose"] = agrupar.puntuar_detalle(
        recalc, palabras_marca=palabras, eventos=eventos, ahora=ahora, pesos=pesos,
        breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
    )
    repos.upsert_noticia_cluster(recalc)
    return True
