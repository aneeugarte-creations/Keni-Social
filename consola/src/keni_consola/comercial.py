"""Apartado COMERCIAL: seguimiento de UN post real de Metricool + captura + reporte.

Es un apartado SEPARADO del rendimiento diario (Metricas): una cosa es el pulso de
las publicaciones del dia a dia y otra el reporte que se entrega de UNA pieza (o una
serie de un cliente) cuando llega su KPI. Aqui se monitoriza una pieza ya publicada:

  1. Se SELECCIONA de la lista de posts reales de Metricool (por su `id_post_metricool`,
     marca y red); no se pegan enlaces a mano (ver `listar_posts_seleccionables`).
  2. Se le toman SNAPSHOTS periodicos de interacciones y visualizaciones (serie
     temporal): una captura programada en segundo plano (ver
     `iniciar_captura_programada`) los llena aunque nadie este mirando.
  3. Si se fijo un objetivo/umbral, se marca el instante en que se alcanza (aviso).
  4. Al llegar el KPI se arma el REPORTE de la pieza o de la campania completa.

PROCEDENCIA DE LAS CIFRAS: cada captura LEE EL DATO REAL del post desde la API de
Metricool (reusando `metricas_pieza`, el mismo camino del tablero). Metricool NO guarda
el historico por post (solo el valor actual): por eso la serie de Comercial ARRANCA
VACIA y crece hacia delante con cada captura real — ese acumulado es justo el valor que
Metricool no ofrece. Sin Metricool configurado NO se inventan cifras: la serie queda
vacia y el resumen en ceros (aqui no hay datos sinteticos ni de demostracion).

El alcance no viene por pieza en Metricool (solo agregado de plataforma): se monitorizan
visualizaciones + interacciones (el alcance queda en 0; series antiguas pueden traerlo).

Solo LECTURA del mundo: nunca publica ni toca las redes; los snapshots se guardan en
Postgres (via `db`), igual que el resto de la consola.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from keni_metricas import servicio

from . import config, marcas, metricas_pieza, redes, repos
from .tiempo import ahora_iso, iso_utc

_log = logging.getLogger("keni_consola.comercial")

# Cadencia por defecto de la captura programada (horas).
INTERVALO_HORAS_DEF = 6.0
# Rango por defecto para listar los posts seleccionables de una marca (ventana amplia:
# se eligen piezas ya publicadas, no necesariamente recientes).
RANGO_LISTADO_DEF = "mes"

def fuente_actual() -> str:
    """Nombre de la fuente activa de las cifras (procedencia, p. ej. "metricool").

    Deriva de la configuracion de metricas (la misma fuente que alimenta el tablero).
    "" si la fuente no se puede resolver (config incompleto): aqui NUNCA se inventan
    cifras, asi que la procedencia desconocida no degrada a datos de demostracion.
    """
    try:
        return servicio.nombre_fuente()
    except Exception:  # noqa: BLE001 -- sin fuente valida, procedencia desconocida
        return ""


def listar_posts_seleccionables(
    marca: str = "", red: str = "", rango: str = RANGO_LISTADO_DEF
) -> list[dict[str, Any]]:
    """Posts reales ya publicados para ELEGIR cual monitorizar (sin pegar enlaces).

    Trae el listado en vivo de la fuente activa (Metricool en prod; piezas sinteticas en
    demo) via `servicio.construir_listado_piezas`, opcionalmente acotado a una `marca` y
    filtrado a una `red`. `marca` es el id de la Consola (slug-guion); se traduce a su
    `id_metricas` en la frontera. Degrada a `[]` si la fuente no puede listar (config
    incompleto), para que el dialogo de alta no reviente.
    """
    id_metricas = marcas.id_metricas_de(marca) if marca else None
    try:
        piezas = servicio.construir_listado_piezas(rango, id_metricas)
    except Exception:  # noqa: BLE001 -- sin fuente/cuenta valida: lista vacia, sin romper
        _log.exception("comercial: no se pudo listar posts (marca=%s red=%s).", marca, red)
        return []
    if red:
        piezas = [p for p in piezas if p.get("red") == red]
    return piezas


# Metricas GRANULARES por pieza que el snapshot persiste ademas de interacciones/
# visualizaciones. Son las claves del dict de `metricas_pieza.recalcular` (que viene de
# `servicio.construir_metricas_pieza`). `db.registrar_snapshot_comercial` las degrada a 0
# defensivamente, asi que basta con pasarle lo que haya (un `.get` por clave).
_CAMPOS_GRANULARES = (
    "likes",
    "comentarios",
    "compartidos",
    "guardados",
    "video_views",
    "tiempo_medio_vis_s",
    "clics_enlace",
    "seguidores_netos_atribuidos",
)


def _granulares_de(rend: dict[str, Any]) -> dict[str, Any]:
    """Extrae el desglose granular del dict de rendimiento (None/ausente -> se omite)."""
    return {campo: rend.get(campo) for campo in _CAMPOS_GRANULARES}


def _leer_real(pub: dict[str, Any]) -> dict[str, Any] | None:
    """Lectura REAL del post (dict de rendimiento), o None si no hay dato todavia.

    Reusa `metricas_pieza.recalcular` (mismo camino que el tablero: va a la fuente activa
    y degrada honestamente). Devuelve None si falta la identidad del post o si Metricool
    aun no tiene datos (post recien publicado): el llamante NO inserta un snapshot falso.
    El dict trae interacciones/visualizaciones, el desglose granular (likes/comentarios/...)
    y el `formato` estatico de la pieza; el llamante decide que persiste.
    """
    marca = pub.get("marca") or ""
    red = pub.get("red") or ""
    id_post = pub.get("id_post_metricool") or ""
    if not (marca and red and id_post):
        return None
    rend = metricas_pieza.recalcular(marca, red, id_post)
    if not rend.get("encontrado"):
        return None
    return rend


# --------------------------------------------------------------------------- #
# Captura de snapshots                                                         #
# --------------------------------------------------------------------------- #


def _capturar_en(pub: dict[str, Any], en: datetime) -> bool:
    """Toma y guarda un snapshot de `pub` en el instante `en`. True si inserto.

    Lee el valor actual del post en Metricool (el instante real es "ahora"; Metricool
    no da historico, asi que `en` solo fija el `ts` del punto) y guarda interacciones +
    visualizaciones + el desglose granular (likes/comentarios/...; alcance = 0, no
    disponible por pieza). Si Metricool aun no tiene datos del post, NO inserta nada
    (sin ceros falsos). De paso captura el `formato` ESTATICO de la pieza la primera
    vez que la fuente lo expone.
    """
    ts = iso_utc(en)
    rend = _leer_real(pub)
    if rend is None:
        return False
    _persistir_formato(pub, rend)
    return repos.registrar_snapshot_comercial(
        pub["id"],
        ts,
        int(rend.get("interacciones", 0)),
        alcance=0,
        visualizaciones=int(rend.get("visualizaciones", 0)),
        granulares=_granulares_de(rend),
    )


def _persistir_formato(pub: dict[str, Any], rend: dict[str, Any]) -> None:
    """Guarda el `formato` estatico de la pieza si aun no lo tiene y la fuente lo expone.

    El formato (reel/foto/carrusel/video/link/texto) es propiedad de la pieza, no del
    snapshot: se persiste UNA vez en `comercial_publicaciones`. Best-effort: si ya esta o
    la fuente no lo da, no hace nada. Muta `pub` en memoria para que el mismo barrido no
    reintente el UPDATE en cada captura.
    """
    if pub.get("formato"):
        return
    formato = (rend.get("formato") or "").strip()
    if not formato:
        return
    repos.actualizar_publicacion_comercial(pub["id"], {"formato": formato})
    pub["formato"] = formato


def sembrar_historico(pub: dict[str, Any], *, hasta: datetime | None = None) -> int:
    """Arranca la serie con su primer punto real ("ahora"). Devuelve cuantos inserto.

    No se puede reconstruir el pasado (Metricool solo da el valor actual del post):
    se captura UN punto y la serie crece hacia delante. Sin datos en la fuente no se
    inserta nada (la serie arranca vacia, sin ceros falsos).
    """
    return int(_capturar_en(pub, hasta or datetime.now()))


def capturar(pub: dict[str, Any]) -> dict[str, Any] | None:
    """Toma un snapshot AHORA, reevalua el aviso y devuelve el ultimo snapshot."""
    _capturar_en(pub, datetime.now())
    evaluar_aviso(pub)
    return repos.ultimo_snapshot_comercial(pub["id"])


def capturar_pendientes() -> int:
    """Captura un snapshot de TODAS las piezas activas. Devuelve cuantas proceso.

    Es lo que corre la captura programada y tambien el refresco manual global.
    """
    activas = repos.listar_publicaciones_comerciales(estado=repos.ESTADO_COMERCIAL_ACTIVA)
    for pub in activas:
        capturar(pub)
    return len(activas)


# --------------------------------------------------------------------------- #
# Objetivo / aviso                                                             #
# --------------------------------------------------------------------------- #


def _metrica_objetivo(pub: dict[str, Any]) -> str:
    """Metrica del objetivo, normalizada a una de las permitidas (def: interacciones)."""
    metrica = pub.get("metrica_objetivo") or "interacciones"
    return metrica if metrica in repos.METRICAS_COMERCIAL else "interacciones"


def evaluar_aviso(pub: dict[str, Any]) -> bool:
    """Marca el instante (real) en que la pieza alcanzo su objetivo, si procede.

    Recorre la serie y busca el PRIMER snapshot cuyo valor de la metrica objetivo
    supera la meta: ese `ts` es el momento del cruce. Solo marca la primera vez
    (idempotente en `db`). Devuelve True si el objetivo esta alcanzado.
    """
    objetivo = int(pub.get("objetivo") or 0)
    if objetivo <= 0:
        return False
    metrica = _metrica_objetivo(pub)
    cruce: str | None = None
    # `limite=0` => serie COMPLETA: buscamos el PRIMER cruce del objetivo en TODO el histórico, no
    # solo en el intervalo reciente (un cap aquí podría perder el cruce real si fue hace mucho).
    for snap in repos.listar_snapshots_comerciales(pub["id"], limite=0):
        if snap[metrica] >= objetivo:
            cruce = snap["ts"]
            break
    if cruce is None:
        return False
    if not pub.get("aviso_en"):
        repos.marcar_aviso_comercial(pub["id"], cruce)
    return True


# --------------------------------------------------------------------------- #
# Alta + derivados para la UI                                                  #
# --------------------------------------------------------------------------- #


def registrar(url: str = "", *, id_post_metricool: str = "", **campos: Any) -> dict[str, Any]:
    """Da de alta una pieza a monitorear, arranca su serie y evalua el aviso.

    En produccion la pieza se identifica por `id_post_metricool` (+ marca + red en
    `campos`) y la `url` es derivada/opcional. `campos` acepta: titulo, marca, cliente,
    campania, red, formato, metrica_objetivo, objetivo, estado, publicado, notas (la API ya
    valido allowlists). Si `formato` no llega en `campos`, lo resuelve la primera captura
    REAL desde la fuente (`_capturar_en`). Devuelve la pieza ya con `aviso_en` resuelto.
    """
    pub = repos.crear_publicacion_comercial(url, id_post_metricool=id_post_metricool, **campos)
    sembrar_historico(pub)
    evaluar_aviso(pub)
    return repos.obtener_publicacion_comercial(pub["id"]) or pub


def resumen_actual(pub: dict[str, Any]) -> dict[str, Any]:
    """Ultimo valor consultable de la pieza (del ultimo snapshot, o calculado ahora).

    Sin snapshots aun devuelve ceros (la serie no arranco / Metricool no tiene datos):
    nunca cifras inventadas. El engagement se calcula sobre visualizaciones o, si no
    hay (series antiguas con alcance), sobre alcance.
    """
    snap = repos.ultimo_snapshot_comercial(pub["id"])
    if snap is None:
        snap = {
            "ts": ahora_iso(),
            "interacciones": 0,
            "visualizaciones": 0,
            "alcance": 0,
        }
    vis = snap.get("visualizaciones", 0)
    alc = snap.get("alcance", 0)
    base = vis or alc  # base del engagement: visualizaciones o, si no hay, alcance
    eng = round(snap["interacciones"] / base * 100, 2) if base else 0.0
    return {
        "ts": snap["ts"],
        "interacciones": snap["interacciones"],
        "visualizaciones": vis,
        "alcance": alc,
        "engagement_pct": eng,
    }


def progreso_pct(pub: dict[str, Any], actual: dict[str, Any]) -> float:
    """Avance (%) hacia el objetivo segun su metrica; 0 si no hay objetivo."""
    objetivo = int(pub.get("objetivo") or 0)
    if objetivo <= 0:
        return 0.0
    valor = actual.get(_metrica_objetivo(pub), 0)
    return round(valor / objetivo * 100, 1)


def serie(publicacion_id: str) -> list[dict[str, Any]]:
    """Serie temporal de la pieza (mas antiguo primero), lista para graficar."""
    return repos.listar_snapshots_comerciales(publicacion_id)


# --------------------------------------------------------------------------- #
# Reporte (una pieza o una campania)                                           #
# --------------------------------------------------------------------------- #


def _pub_publica(pub: dict[str, Any]) -> dict[str, Any]:
    """Forma publica de una pieza (nombres de marca/red resueltos en servidor)."""
    return {
        "id": pub["id"],
        "titulo": pub.get("titulo") or "",
        "url": pub.get("url") or "",
        "id_post_metricool": pub.get("id_post_metricool") or "",
        "cliente": pub.get("cliente") or "",
        "campania": pub.get("campania") or "",
        "marca": pub.get("marca") or "",
        "marca_nombre": marcas.etiqueta_de(pub["marca"]) if pub.get("marca") else "",
        "red": pub.get("red") or "",
        "red_nombre": redes.nombre_por_id(pub["red"]) if pub.get("red") else "",
        "publicado": pub.get("publicado") or "",
        "estado": pub.get("estado") or "activa",
    }


def _objetivo_publico(pub: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Forma publica del objetivo + progreso + si esta alcanzado (y cuando)."""
    objetivo = int(pub.get("objetivo") or 0)
    return {
        "metrica": _metrica_objetivo(pub),
        "valor": objetivo,
        "progreso_pct": progreso_pct(pub, actual),
        "alcanzado": bool(pub.get("aviso_en")) or (objetivo > 0 and progreso_pct(pub, actual) >= 100),
        "aviso_en": pub.get("aviso_en") or "",
    }


def reporte_publicacion(pub: dict[str, Any]) -> dict[str, Any]:
    """Reporte de UNA pieza: datos, periodo, resultados actuales y objetivo."""
    actual = resumen_actual(pub)
    serie_ = serie(pub["id"])
    return {
        "tipo": "publicacion",
        "generado": ahora_iso(),
        "fuente": fuente_actual(),
        "publicacion": _pub_publica(pub),
        "periodo": {
            "desde": pub.get("publicado") or "",
            "hasta": serie_[-1]["ts"] if serie_ else actual["ts"],
        },
        "actual": actual,
        "objetivo": _objetivo_publico(pub, actual),
        "puntos": len(serie_),
    }


def reporte_campania(
    pubs: list[dict[str, Any]], *, campania: str = "", cliente: str = ""
) -> dict[str, Any]:
    """Reporte de una SERIE de piezas (campania de un cliente): filas + totales."""
    filas: list[dict[str, Any]] = []
    tot_inter = tot_vis = tot_alc = 0
    for pub in pubs:
        actual = resumen_actual(pub)
        tot_inter += actual["interacciones"]
        tot_vis += actual["visualizaciones"]
        tot_alc += actual["alcance"]
        filas.append(
            {
                "publicacion": _pub_publica(pub),
                "actual": actual,
                "objetivo": _objetivo_publico(pub, actual),
            }
        )
    base = tot_vis or tot_alc  # engagement sobre visualizaciones o, si no hay, alcance
    eng = round(tot_inter / base * 100, 2) if base else 0.0
    return {
        "tipo": "campania",
        "generado": ahora_iso(),
        "fuente": fuente_actual(),
        "campania": campania,
        "cliente": cliente,
        "piezas": filas,
        "total": {
            "interacciones": tot_inter,
            "visualizaciones": tot_vis,
            "alcance": tot_alc,
            "engagement_pct": eng,
            "piezas": len(filas),
        },
    }


def _fmt(n: float) -> str:
    """Entero con separador de miles (lectura humana en el reporte)."""
    return f"{int(round(n)):,}"


def _alcanzado_texto(obj: dict[str, Any]) -> str:
    if not obj.get("valor"):
        return "sin objetivo definido"
    if obj.get("alcanzado"):
        cuando = obj.get("aviso_en") or ""
        return f"alcanzado{f' el {cuando}' if cuando else ''}"
    return f"en progreso ({obj.get('progreso_pct', 0)} %)"


def render_markdown_reporte(rep: dict[str, Any]) -> str:
    """Renderiza un reporte (pieza o campania) a Markdown listo para entregar."""
    if rep["tipo"] == "campania":
        return _render_campania_md(rep)
    return _render_publicacion_md(rep)


def _volumen(actual: dict[str, Any]) -> tuple[str, int]:
    """Etiqueta y valor de la metrica de volumen: visualizaciones o, si no hay, alcance."""
    vis = actual.get("visualizaciones", 0)
    if vis:
        return "Visualizaciones", vis
    return "Alcance", actual.get("alcance", 0)


def _render_publicacion_md(rep: dict[str, Any]) -> str:
    p = rep["publicacion"]
    a = rep["actual"]
    o = rep["objetivo"]
    titulo = p["titulo"] or p["url"] or p.get("id_post_metricool") or "pieza"
    vol_etq, vol_val = _volumen(a)
    lineas = [
        f"# Reporte comercial — {titulo}",
        "",
        f"Generado: {rep['generado']}",
        "",
        f"- Cliente: {p['cliente'] or '—'}",
        f"- Campaña: {p['campania'] or '—'}",
        f"- Marca: {p['marca_nombre'] or '—'}",
        f"- Red: {p['red_nombre'] or '—'}",
        f"- Publicado: {p['publicado'] or '—'}",
        f"- Enlace: {p['url'] or '—'}",
        "",
        f"## Resultados (al {rep['periodo']['hasta']})",
        "",
        f"- {vol_etq}: {_fmt(vol_val)}",
        f"- Interacciones: {_fmt(a['interacciones'])}",
        f"- Engagement: {a['engagement_pct']} %",
        "",
        "## Objetivo",
        "",
        f"- Métrica: {o['metrica']}",
        f"- Meta: {_fmt(o['valor']) if o['valor'] else '—'}",
        f"- Estado: {_alcanzado_texto(o)}",
        "",
        f"_Basado en {rep['puntos']} lectura(s) desde {rep['periodo']['desde'] or '—'}._",
    ]
    return "\n".join(lineas) + "\n"


def _render_campania_md(rep: dict[str, Any]) -> str:
    t = rep["total"]
    encabezado = rep["campania"] or rep["cliente"] or "campaña"
    lineas = [
        f"# Reporte comercial — {encabezado}",
        "",
        f"Generado: {rep['generado']}",
        "",
    ]
    if rep["cliente"]:
        lineas.append(f"- Cliente: {rep['cliente']}")
    if rep["campania"]:
        lineas.append(f"- Campaña: {rep['campania']}")
    vol_etq, vol_val = _volumen(t)
    lineas += [
        f"- Piezas: {t['piezas']}",
        "",
        "## Totales",
        "",
        f"- {vol_etq}: {_fmt(vol_val)}",
        f"- Interacciones: {_fmt(t['interacciones'])}",
        f"- Engagement: {t['engagement_pct']} %",
        "",
        "## Detalle por pieza",
        "",
        f"| Pieza | Red | {vol_etq} | Interacciones | Objetivo |",
        "|---|---|--:|--:|---|",
    ]
    for fila in rep["piezas"]:
        p = fila["publicacion"]
        a = fila["actual"]
        o = fila["objetivo"]
        titulo = (p["titulo"] or p["url"] or p.get("id_post_metricool") or "pieza").replace("|", "/")
        _, fila_vol = _volumen(a)
        lineas.append(
            f"| {titulo} | {p['red_nombre'] or '—'} | {_fmt(fila_vol)} "
            f"| {_fmt(a['interacciones'])} | {_alcanzado_texto(o)} |"
        )
    return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------- #
# Captura programada (servidor real; NO se arranca en los tests)               #
# --------------------------------------------------------------------------- #


def _intervalo_segundos() -> float:
    """Intervalo de la captura programada en segundos (configurable por entorno).

    `KENI_COMERCIAL_INTERVALO_SEGUNDOS` (util para demo/tests) tiene prioridad sobre
    `KENI_COMERCIAL_INTERVALO_HORAS`. Por defecto, `INTERVALO_HORAS_DEF` horas.
    """
    seg = config.comercial_intervalo_segundos()
    if seg is not None:
        return seg
    horas = config.comercial_intervalo_horas()
    if horas is not None:
        return max(60.0, horas * 3600.0)
    return INTERVALO_HORAS_DEF * 3600.0


def iniciar_captura_programada(
    intervalo_segundos: float | None = None,
) -> threading.Thread:
    """Arranca un hilo demonio que captura snapshots de las piezas activas en bucle.

    Pensado para el servidor real (`__main__`), NO para `crear_app`: los tests crean
    la app sin arrancar esto. Cada operacion de `db` abre/cierra su propia conexion
    SQLite, asi que correr en un hilo aparte es seguro. El hilo es daemon: muere al
    cerrar el proceso. Captura una vez al arrancar y luego cada `intervalo`.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        from . import latidos  # import tardio: solo lo paga el hilo del servidor real

        while True:
            t0 = time.monotonic()
            try:
                n = capturar_pendientes()
                if n:
                    _log.info("Captura comercial: %d pieza(s) actualizada(s).", n)
                latidos.barrido(
                    "comercial", ok=True, intervalo_seg=intervalo, tick_seg=intervalo,
                    duracion_ms=int((time.monotonic() - t0) * 1000),
                    resumen=(f"{n} snapshot(s) capturado(s)" if n else "sin novedad"),
                )
            except Exception as e:  # noqa: BLE001 -- un fallo de captura no debe matar el hilo
                _log.exception("Fallo en la captura comercial programada.")
                latidos.barrido(
                    "comercial", ok=False, intervalo_seg=intervalo, tick_seg=intervalo,
                    duracion_ms=int((time.monotonic() - t0) * 1000), error=repr(e),
                )
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="comercial-captura", daemon=True)
    hilo.start()
    _log.info("Captura comercial programada cada %.0f s.", intervalo)
    return hilo
