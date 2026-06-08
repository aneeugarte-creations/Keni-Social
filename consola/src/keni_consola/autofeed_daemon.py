"""Daemon AUTO-FEED (Ola E): pool único → dedup → feed automático.

PROBLEMA QUE RESUELVE
=====================
Todas las notas (cajones del equipo, investigación, feeds RSS) caen al MISMO pool
(`noticias_items`) y el clustering las deduplica en HISTORIAS (`noticias_clusters`). Hasta
ahora, llevar una historia al feed era MANUAL (botón "usar/empujar"). Este daemon (espejo de
`pipeline_contenido` / `autogen_copy`) lo automatiza: cada N minutos y POR MARCA, toma las
historias RELEVANTES del pool (score >= umbral), descarta las caducas para líneas no-evergreen,
respeta un TOPE DIARIO POR MARCA, y por cada una crea la pieza del feed (borrador) y encola su
copy+QA por el MISMO camino de 1 agente que el botón manual (`autogen_copy.lanzar_para_topic`).
El borrador cae en el feed para imagen + aprobación humana.

SEGURO POR DISEÑO (CONSERVADOR)
===============================
  - GATEADO: barre solo con `KENI_MAQUINA=1` (maestro) Y `KENI_AUTOFEED=1` (def OFF). Sin
    ambos, nada fluye solo (el equipo empuja a mano). El hilo arranca SIEMPRE y comprueba el
    gate en cada ciclo (toggle en caliente).
  - TOPE DIARIO POR MARCA (`KENI_AUTOFEED_CAP`, def 20; override `::marca`): resta lo ya
    draftado HOY (`origen='autofeed'`) y toma hasta el cupo restante. Evita avalanchas.
  - UMBRAL DE RELEVANCIA (`KENI_AUTOFEED_UMBRAL`, def 0.5): solo historias por encima entran.
  - FRESCURA: descarta historias caducas para líneas no-evergreen (reusa `dominio/frescura`).
  - DEDUP: solo clusters `estado='nuevo'` y sin `contenido_id`; tras draftar se marca el
    cluster `estado='usado'` + `contenido_id` (no se re-draftan). Idempotente.
  - NO PUBLICA: el borrador nace en el feed; la publicación real sigue gated por
    `KENI_PUBLICAR_REAL`. Este daemon NUNCA llama a Metricool.

La SELECCIÓN (`historias_para_feed`) es PURA y testeable (umbral + frescura + tope/dedup,
sin BD ni reloj). El LANZAMIENTO reutiliza el camino probado sin tocar su contrato: bajo riesgo.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from . import autogen_copy, config, daemon_util, generaciones, marcas, redes, repos
from .dominio import frescura

_log = logging.getLogger("keni_consola.autofeed_daemon")

# Origen reservado de las piezas que el auto-feed crea en el feed. El tope diario por marca se
# cuenta sobre este origen; la UI/dedup lo distinguen de lo manual/otro auto.
ORIGEN_AUTOFEED = "autofeed"

# El auto-feed no sabe de antemano si un ítem será FOTO o VIDEO, así que crea piezas de FOTO
# (regla del dueño: foto -> 3 redes IG/X/FB). El mapeo formato->redes vive en
# `redes.redes_de_formato` (fuente única); video -> las 5 queda definido para flujos futuros.
_FORMATO_AUTOFEED = redes.FORMATO_FOTO

# Cuántos clusters recientes se examinan por marca y barrido (cota de seguridad). El listado
# viene ordenado por score desc, así que los más relevantes entran primero.
_REVISAR_MAX = 100


# --------------------------------------------------------------------------- #
# Selección PURA (umbral + frescura + tope/dedup)                              #
# --------------------------------------------------------------------------- #


def historias_para_feed(
    clusters: list[dict[str, Any]],
    *,
    umbral: float,
    cupo: int,
    es_fresca: Callable[[dict[str, Any]], bool] | None = None,
) -> list[dict[str, Any]]:
    """Subconjunto de historias que se deben llevar al feed (PURA, testeable).

    Reglas, en orden:
      - estado 'nuevo' (no usadas/descartadas),
      - SIN `contenido_id` (no ya draftadas: dedup),
      - `score >= umbral` (relevancia),
      - FRESCA según `es_fresca(cluster)` si se pasa (líneas no-evergreen caducas se descartan;
        evergreen nunca caduca). Sin `es_fresca`, no se filtra por frescura.
      - se RECORTA a `cupo` (tope diario por marca menos lo ya draftado hoy).

    Conserva el orden de entrada (el listado ya viene por score desc). Determinista: depende
    solo de sus argumentos. Con `cupo <= 0` devuelve [] (la marca está al tope o desactivada).
    """
    if cupo <= 0:
        return []
    elegidos: list[dict[str, Any]] = []
    for c in clusters:
        if len(elegidos) >= cupo:
            break
        if (c.get("estado") or "nuevo") != "nuevo":
            continue
        if (c.get("contenido_id") or "").strip():
            continue
        if float(c.get("score") or 0.0) < umbral:
            continue
        if es_fresca is not None and not es_fresca(c):
            continue
        elegidos.append(c)
    return elegidos


def cupo_restante(cap: int, ya_hoy: int) -> int:
    """Cupo restante del tope diario de una marca: `max(0, cap - ya_hoy)` (PURO)."""
    return max(0, int(cap) - int(ya_hoy))


# --------------------------------------------------------------------------- #
# Frescura (I/O: resuelve línea → TTL/evergreen; envuelve la lógica pura)          #
# --------------------------------------------------------------------------- #


def _es_fresca(cluster: dict[str, Any], *, hoy: str) -> bool:
    """True si la historia está FRESCA para su línea (best-effort; reusa `dominio/frescura`).

    La línea de la historia es su `categoria` (el pool guarda la línea editorial ahí). La fecha
    del ítem es su `ultimo_visto` (o `primer_visto`), recortada a día. Resuelve (ttl, evergreen) de
    la línea en la marca de la historia y aplica `estado_frescura`. Ante cualquier fallo (línea
    desconocida, BD ilegible) → True (nunca ocultar por dato malo / no romper el barrido).
    """
    linea = (cluster.get("categoria") or "").strip()
    if not linea:
        return True  # sin línea no hay TTL aplicable: se considera fresca (evergreen por defecto)
    fecha = (cluster.get("ultimo_visto") or cluster.get("primer_visto") or "").strip()[:10]
    try:
        ttl, evergreen = frescura.resolver_linea(linea, cluster.get("marca") or "")
        return frescura.estado_frescura(fecha, ttl, evergreen, hoy=hoy) == "fresco"
    except Exception:  # noqa: BLE001 -- la frescura es un filtro; un fallo no descarta ni rompe
        _log.warning("autofeed: no se pudo resolver la frescura de un cluster", exc_info=True)
        return True


# --------------------------------------------------------------------------- #
# Lanzamiento por historia (I/O: crea la pieza + encola copy+QA)               #
# --------------------------------------------------------------------------- #


def _nota_de(cluster: dict[str, Any], items: list[dict[str, Any]]) -> str:
    """Nota de partida del copy: título + resumen de la historia + enlaces corroborantes."""
    titulo = (cluster.get("titulo") or "").strip()
    resumen = (cluster.get("resumen") or "").strip()
    nota = f"{titulo}\n\n{resumen}".strip() if resumen else titulo
    fuentes = [it.get("url") for it in items if it.get("url")][:10]
    if fuentes:
        nota = (nota + "\n\nFuentes:\n" + "\n".join(fuentes)).strip()
    return nota


def llevar_al_feed(cluster: dict[str, Any]) -> dict[str, Any] | None:
    """Crea la pieza del feed para una historia y encola su copy+QA. Devuelve la pieza o None.

    Reusa el camino probado del botón manual: `repos.crear_contenido(flujo='importante',
    origen='autofeed', tipo_contenido='fuente')` + `contenido_plataforma` (falta_copy/imagen) y
    `autogen_copy.lanzar_para_topic` (1 agente → copy + veredicto IA). Marca el cluster `usado`
    + `contenido_id` para no re-draftarlo. Best-effort: None si la historia no tiene título.
    La `ColaLlenaError` se PROPAGA (el barrido la captura para cortar la marca).
    """
    cluster_id = (cluster.get("id") or "").strip()
    if not cluster_id:
        return None
    marca = (cluster.get("marca") or "").strip()
    items = repos.items_de_cluster(cluster_id, limite=10)
    titulo = (cluster.get("titulo") or "").strip() or (items[0]["url"] if items else "")
    if not titulo:
        return None
    descripcion = _nota_de(cluster, items)
    url_fuente = (items[0].get("url_canonica") if items else "") or ""
    fecha_fuente = cluster.get("primer_visto") or ""

    contenido = repos.crear_contenido(
        clase="contenido",
        flujo="importante",
        titulo=titulo[:300],
        descripcion=descripcion[:5000],
        marca=marca,
        prioridad="media",
        fecha_objetivo=date.today().isoformat(),
        origen=ORIGEN_AUTOFEED,
        tipo_contenido="fuente",
        # FOTO explícito: el auto-feed no sabe si el ítem será foto o video, así que crea
        # un post de FOTO (3 redes IG/X/FB). El humano puede pasarlo a video más adelante.
        formato=_FORMATO_AUTOFEED,
        fecha_fuente=fecha_fuente,
        url_fuente=url_fuente,
    )
    for red in redes.redes_de_formato(_FORMATO_AUTOFEED):
        repos.crear_contenido_plataforma(
            contenido_id=contenido["id"], red=red, falta_copy=True, falta_imagen=True
        )

    # Copy+QA (1 agente), mismo camino que el botón manual. Solo si hay marca (sin marca no hay
    # voz/tropicalización; la pieza queda en el feed para que el equipo asigne marca y genere).
    if marca and marcas.es_marca(marca):
        autogen_copy.lanzar_para_topic(contenido)

    # Dedup: marca el cluster usado + sus items, para no re-draftarlo en el próximo barrido.
    repos.actualizar_noticia_cluster(cluster_id, estado="usado", contenido_id=contenido["id"])
    repos.marcar_items_cluster_usados(cluster_id, contenido["id"])
    return contenido


# --------------------------------------------------------------------------- #
# Barrido por marca                                                            #
# --------------------------------------------------------------------------- #


def _inicio_dia_iso(hoy: str) -> str:
    """ISO UTC del inicio del día `hoy` (YYYY-MM-DD) para contar lo draftado hoy."""
    try:
        d = date.fromisoformat(hoy)
    except ValueError:
        d = datetime.now(UTC).date()
    return datetime(d.year, d.month, d.day, tzinfo=UTC).isoformat()


def barrer_marca(marca: str, *, hoy: str | None = None) -> list[dict[str, Any]]:
    """Un barrido del auto-feed para UNA marca. Devuelve las piezas creadas. Best-effort por item.

    Selecciona historias recientes de la marca (`estado='nuevo'`, score >= umbral), descarta las
    caducas, calcula el cupo restante (cap diario − lo draftado hoy) y lleva hasta ese cupo al
    feed. Un fallo por historia se loguea y se sigue; si la cola de generación se llena, corta
    el barrido de esta marca (reintenta el siguiente).
    """
    hoy = hoy or datetime.now(UTC).date().isoformat()
    cap = config.autofeed_cap(marca)
    if cap <= 0:
        return []  # marca con cap 0 (override): no auto-feed
    try:
        ya_hoy = repos.contar_contenido_origen_desde(marca, ORIGEN_AUTOFEED, _inicio_dia_iso(hoy))
    except Exception:  # noqa: BLE001 -- sin la cuenta de hoy, conservador: no draftamos esta marca
        _log.warning("autofeed: no se pudo contar lo draftado hoy (%s)", marca, exc_info=True)
        return []
    cupo = cupo_restante(cap, ya_hoy)
    if cupo <= 0:
        return []
    try:
        clusters, _total = repos.listar_noticia_clusters(
            marca=marca, estado="nuevo", limite=_REVISAR_MAX
        )
    except Exception:  # noqa: BLE001 -- sin historias legibles, esta marca no produce nada
        _log.warning("autofeed: no se pudieron leer las historias (%s)", marca, exc_info=True)
        return []
    elegidas = historias_para_feed(
        clusters,
        umbral=config.autofeed_umbral(),
        cupo=cupo,
        es_fresca=lambda c: _es_fresca(c, hoy=hoy),
    )
    creadas: list[dict[str, Any]] = []
    for cluster in elegidas:
        try:
            pieza = llevar_al_feed(cluster)
        except generaciones.ColaLlenaError:
            _log.info("autofeed: cola llena (%s); el resto entra en el próximo barrido.", marca)
            break
        except Exception:  # noqa: BLE001 -- un fallo por historia no debe matar el barrido
            _log.exception("autofeed: fallo al llevar una historia al feed (%s).", marca)
            continue
        if pieza:
            creadas.append(pieza)
    return creadas


def ejecutar_barrido() -> list[dict[str, Any]]:
    """Un barrido del auto-feed por TODAS las marcas activas. Devuelve las piezas creadas.

    SINGLE-FLIGHT cross-proceso (advisory lock): el dedup (marcar el cluster usado) es
    leer-luego-escribir, así que dos barridos solapados podrían draftar la MISMA historia dos
    veces. El lock hace que un segundo barrido concurrente salga de inmediato con lista vacía.
    """
    from . import db

    with db.lock_barrido("autofeed") as ok:
        if not ok:
            _log.debug("autofeed: otro barrido en curso; se omite este.")
            return []
        return _ejecutar_barrido()


def _ejecutar_barrido() -> list[dict[str, Any]]:
    """Cuerpo del barrido (ya bajo el single-flight de `ejecutar_barrido`)."""
    hoy = datetime.now(UTC).date().isoformat()
    creadas: list[dict[str, Any]] = []
    for marca in marcas.ids():
        # Exclusión por marca: si el auto-feed de ESTA marca se apagó (cap 0 vía override) ya se
        # corta en `barrer_marca`. No hay toggle bool por-marca para auto-feed; el cap por marca
        # es el mecanismo de exclusión (cap 0 = desactivado para esa marca).
        try:
            creadas.extend(barrer_marca(marca, hoy=hoy))
        except Exception:  # noqa: BLE001 -- un fallo de una marca no aborta el barrido
            _log.exception("autofeed: fallo el barrido de la marca %s", marca)
            continue
    if creadas:
        _log.info("autofeed: %d historia(s) llevada(s) al feed.", len(creadas))
    return creadas


# --------------------------------------------------------------------------- #
# Hilo demonio                                                                 #
# --------------------------------------------------------------------------- #


def _intervalo_segundos() -> float:
    return config.autofeed_intervalo_min() * 60.0


def iniciar_autofeed(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del auto-feed (GATEADO EN VIVO por el maestro + su toggle).

    Pensado para el servidor real (`daemons`/`__main__`), NO para `crear_app` (los tests no lo
    arrancan). El hilo arranca SIEMPRE y comprueba `KENI_MAQUINA and KENI_AUTOFEED` en cada
    ciclo: apagar/encender en runtime aplica sin reiniciar. El hilo es daemon; un fallo de
    barrido se loguea y NO lo mata.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.autofeed_activo),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="autofeed-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.autofeed_activo() else "EN ESPERA (KENI_AUTOFEED off)"
    _log.info(
        "Auto-feed %s, cada %.0f min (umbral=%.2f, cap/marca/día=%d).",
        estado, intervalo / 60.0, config.autofeed_umbral(), config.autofeed_cap(),
    )
    return hilo
