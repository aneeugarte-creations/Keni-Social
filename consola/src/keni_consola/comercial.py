"""Apartado COMERCIAL: seguimiento de UNA pieza por su link + captura + reporte.

Es un apartado SEPARADO del rendimiento diario (Metricas): una cosa es el pulso de
las publicaciones del dia a dia y otra el reporte que se entrega de UNA pieza (o una
serie de un cliente) cuando llega su KPI. Aqui se monitoriza una pieza ya publicada:

  1. Se registra su link (con cliente/campania/objetivo).
  2. Se le toman SNAPSHOTS periodicos de interacciones y alcance (serie temporal):
     una captura programada en segundo plano (ver `iniciar_captura_programada`) los
     llena aunque nadie este mirando, y al registrar se SIEMBRA el historico para
     verla crecer desde el primer momento.
  3. Si se fijo un objetivo/umbral, se marca el instante en que se alcanza (aviso).
  4. Al llegar el KPI se arma el REPORTE de la pieza o de la campania completa.

DATOS DE MUESTRA: mientras no esten conectadas las APIs reales por plataforma, los
valores salen de una curva sintetica DETERMINISTA por link (crece y se satura con el
tiempo). Cuando llegue la fuente real, basta sustituir `metrica_en` por la lectura
real de la pieza; el resto (persistencia, captura, aviso, reporte) no cambia.

Solo LECTURA del mundo: nunca publica ni toca las redes; los snapshots se guardan en
el SQLite local (via `db`), igual que el resto de la consola.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

from . import marcas, redes, repos

_log = logging.getLogger("keni_consola.comercial")

# Cadencia por defecto de la captura programada (horas).
INTERVALO_HORAS_DEF = 6.0
# Tope de puntos al sembrar el historico de una pieza: una curva fluida y acotada sin
# importar cuan antigua sea (para piezas viejas, los puntos se espacian mas).
MAX_PUNTOS_BACKFILL = 120

# Procedencia de las cifras. Mientras las APIs reales por plataforma no esten
# conectadas, todo sale del modelo sintetico de `metrica_en`: es DATO DE MUESTRA.
# Mismo centinela ("muestra") que usa Metricas, asi el frontend reutiliza `BadgeFuente`.
# Cuando se cablee la lectura real, `FUENTE_ACTUAL` pasara a la fuente real (p. ej.
# "meta") y `es_muestra()` devolvera False sin tocar el resto del flujo.
FUENTE_MUESTRA = "muestra"
FUENTE_ACTUAL = FUENTE_MUESTRA


def es_muestra() -> bool:
    """`True` mientras las cifras salgan del modelo sintetico (datos de muestra)."""
    return FUENTE_ACTUAL == FUENTE_MUESTRA


# --------------------------------------------------------------------------- #
# Modelo sintetico (muestra): curva determinista por link                      #
# --------------------------------------------------------------------------- #


def _parametros(url: str) -> tuple[int, float, float]:
    """Parametros deterministas de la curva de una pieza, derivados de su link.

    Devuelve `(alcance_max, engagement, tau_horas)`. Mientras no haya datos reales,
    esto da una curva representativa, creciente y ESTABLE por pieza (el mismo link
    siempre rinde igual), util para validar el flujo de extremo a extremo.
    """
    h = hashlib.sha256(url.encode("utf-8")).digest()
    n = int.from_bytes(h[0:8], "big")
    m = int.from_bytes(h[8:16], "big")
    k = int.from_bytes(h[16:24], "big")
    alcance_max = 50_000 + n % 1_950_001  # 50 mil .. 2.0 M
    engagement = 0.01 + (m % 700) / 10_000.0  # 1 % .. 8 %
    tau_horas = 24.0 + (k % 217)  # 24 h .. 240 h (constante de saturacion)
    return alcance_max, engagement, tau_horas


def _a_datetime(valor: str) -> datetime:
    """Parsea una fecha/fecha-hora ISO a `datetime`; cae a medianoche o a ahora."""
    if not valor:
        return datetime.now()
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(valor[:10]), datetime.min.time())
        except ValueError:
            return datetime.now()


def metrica_en(url: str, publicado: str, en: datetime) -> tuple[int, int]:
    """`(interacciones, alcance)` ACUMULADOS de una pieza en el instante `en` (muestra).

    Curva de saturacion exponencial sobre el alcance; las interacciones son una
    fraccion estable (engagement). Es monotona creciente, asi que sirve como serie
    acumulada (cada snapshot es >= al anterior).
    """
    alcance_max, engagement, tau = _parametros(url)
    inicio = _a_datetime(publicado)
    horas = max(0.0, (en - inicio).total_seconds() / 3600.0)
    alcance = alcance_max * (1.0 - math.exp(-horas / tau))
    interacciones = alcance * engagement
    return int(round(interacciones)), int(round(alcance))


# --------------------------------------------------------------------------- #
# Captura de snapshots                                                         #
# --------------------------------------------------------------------------- #


def _capturar_en(pub: dict[str, Any], en: datetime) -> bool:
    """Toma y guarda un snapshot de `pub` en el instante `en`. True si inserto."""
    inter, alc = metrica_en(pub["url"], pub["publicado"], en)
    return repos.registrar_snapshot_comercial(
        pub["id"], en.isoformat(timespec="seconds"), inter, alc
    )


def sembrar_historico(pub: dict[str, Any], *, hasta: datetime | None = None) -> int:
    """Siembra snapshots desde `publicado` hasta ahora (curva inmediata y demoable).

    Genera hasta `MAX_PUNTOS_BACKFILL` puntos equiespaciados y garantiza un punto
    exactamente "ahora" (el valor consultable). Devuelve cuantos snapshots inserto.
    """
    hasta = hasta or datetime.now()
    inicio = _a_datetime(pub["publicado"])
    if hasta <= inicio:
        # Pieza recien publicada (o fecha futura): al menos el punto "ahora".
        return int(_capturar_en(pub, hasta))
    total_horas = (hasta - inicio).total_seconds() / 3600.0
    paso_horas = max(INTERVALO_HORAS_DEF, total_horas / MAX_PUNTOS_BACKFILL)
    n_puntos = max(1, int(total_horas // paso_horas))
    insertados = 0
    for i in range(1, n_puntos + 1):
        en = min(inicio + timedelta(hours=paso_horas * i), hasta)
        insertados += int(_capturar_en(pub, en))
    insertados += int(_capturar_en(pub, hasta))
    return insertados


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
    """Metrica del objetivo, saneada a una de las permitidas (def: interacciones)."""
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
    for snap in repos.listar_snapshots_comerciales(pub["id"]):
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


def registrar(url: str, **campos: Any) -> dict[str, Any]:
    """Da de alta una pieza a monitorear, siembra su historico y evalua el aviso.

    `campos` acepta: titulo, marca, cliente, campania, red, metrica_objetivo,
    objetivo, estado, publicado, notas (la API ya valido allowlists). Devuelve la
    pieza ya con `aviso_en` resuelto.
    """
    pub = repos.crear_publicacion_comercial(url, **campos)
    sembrar_historico(pub)
    evaluar_aviso(pub)
    return repos.obtener_publicacion_comercial(pub["id"]) or pub


def resumen_actual(pub: dict[str, Any]) -> dict[str, Any]:
    """Ultimo valor consultable de la pieza (del ultimo snapshot, o calculado ahora)."""
    snap = repos.ultimo_snapshot_comercial(pub["id"])
    if snap is None:
        inter, alc = metrica_en(pub["url"], pub["publicado"], datetime.now())
        snap = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "interacciones": inter,
            "alcance": alc,
        }
    eng = round(snap["interacciones"] / snap["alcance"] * 100, 2) if snap["alcance"] else 0.0
    return {
        "ts": snap["ts"],
        "interacciones": snap["interacciones"],
        "alcance": snap["alcance"],
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
        "url": pub["url"],
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
        "generado": datetime.now().isoformat(timespec="seconds"),
        "fuente": FUENTE_ACTUAL,
        "es_muestra": es_muestra(),
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
    tot_inter = tot_alc = 0
    for pub in pubs:
        actual = resumen_actual(pub)
        tot_inter += actual["interacciones"]
        tot_alc += actual["alcance"]
        filas.append(
            {
                "publicacion": _pub_publica(pub),
                "actual": actual,
                "objetivo": _objetivo_publico(pub, actual),
            }
        )
    eng = round(tot_inter / tot_alc * 100, 2) if tot_alc else 0.0
    return {
        "tipo": "campania",
        "generado": datetime.now().isoformat(timespec="seconds"),
        "fuente": FUENTE_ACTUAL,
        "es_muestra": es_muestra(),
        "campania": campania,
        "cliente": cliente,
        "piezas": filas,
        "total": {
            "interacciones": tot_inter,
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


# Aviso de procedencia para el Markdown entregable: que nadie confunda las cifras
# sinteticas con datos reales del cliente mientras no haya APIs conectadas.
_AVISO_MUESTRA_MD = "> ⚠️ Datos de muestra (sintéticos): cifras de demostración, aún no reales."


def _aviso_muestra_md(rep: dict[str, Any]) -> list[str]:
    """Lineas del aviso de muestra (vacio si el reporte ya no es de muestra)."""
    return [_AVISO_MUESTRA_MD, ""] if rep.get("es_muestra") else []


def render_markdown_reporte(rep: dict[str, Any]) -> str:
    """Renderiza un reporte (pieza o campania) a Markdown listo para entregar."""
    if rep["tipo"] == "campania":
        return _render_campania_md(rep)
    return _render_publicacion_md(rep)


def _render_publicacion_md(rep: dict[str, Any]) -> str:
    p = rep["publicacion"]
    a = rep["actual"]
    o = rep["objetivo"]
    titulo = p["titulo"] or p["url"]
    lineas = [
        f"# Reporte comercial — {titulo}",
        "",
        f"Generado: {rep['generado']}",
        "",
        *_aviso_muestra_md(rep),
        f"- Cliente: {p['cliente'] or '—'}",
        f"- Campaña: {p['campania'] or '—'}",
        f"- Marca: {p['marca_nombre'] or '—'}",
        f"- Red: {p['red_nombre'] or '—'}",
        f"- Publicado: {p['publicado'] or '—'}",
        f"- Enlace: {p['url']}",
        "",
        f"## Resultados (al {rep['periodo']['hasta']})",
        "",
        f"- Alcance: {_fmt(a['alcance'])}",
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
        *_aviso_muestra_md(rep),
    ]
    if rep["cliente"]:
        lineas.append(f"- Cliente: {rep['cliente']}")
    if rep["campania"]:
        lineas.append(f"- Campaña: {rep['campania']}")
    lineas += [
        f"- Piezas: {t['piezas']}",
        "",
        "## Totales",
        "",
        f"- Alcance: {_fmt(t['alcance'])}",
        f"- Interacciones: {_fmt(t['interacciones'])}",
        f"- Engagement: {t['engagement_pct']} %",
        "",
        "## Detalle por pieza",
        "",
        "| Pieza | Red | Alcance | Interacciones | Objetivo |",
        "|---|---|--:|--:|---|",
    ]
    for fila in rep["piezas"]:
        p = fila["publicacion"]
        a = fila["actual"]
        o = fila["objetivo"]
        titulo = (p["titulo"] or p["url"]).replace("|", "/")
        lineas.append(
            f"| {titulo} | {p['red_nombre'] or '—'} | {_fmt(a['alcance'])} "
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
    seg = os.environ.get("KENI_COMERCIAL_INTERVALO_SEGUNDOS")
    if seg:
        try:
            return max(1.0, float(seg))
        except ValueError:
            pass
    horas = os.environ.get("KENI_COMERCIAL_INTERVALO_HORAS")
    if horas:
        try:
            return max(60.0, float(horas) * 3600.0)
        except ValueError:
            pass
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
        while True:
            try:
                n = capturar_pendientes()
                if n:
                    _log.info("Captura comercial: %d pieza(s) actualizada(s).", n)
            except Exception:  # noqa: BLE001 -- un fallo de captura no debe matar el hilo
                _log.exception("Fallo en la captura comercial programada.")
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="comercial-captura", daemon=True)
    hilo.start()
    _log.info("Captura comercial programada cada %.0f s.", intervalo)
    return hilo
