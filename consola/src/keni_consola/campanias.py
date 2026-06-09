"""Apartado CAMPAÑAS: agrupa piezas por uno o varios HASHTAGS configurables.

Una campaña define un FILTRO (marca + hashtags) sobre las piezas YA publicadas; su
analítica —KPIs (visualizaciones, interacciones, engagement), tendencia diaria, tabla de
piezas del periodo y comparativa contra el periodo anterior— se computa AL VUELO sobre el
listado del periodo (`servicio.construir_listado_piezas`), cruzando por los hashtags
presentes en el caption de cada pieza (`Pieza.texto`, el caption ÍNTEGRO: los hashtags
suelen ir al final y se perderían en el `titulo` truncado).

No monitoriza piezas sueltas ni guarda snapshots propios (eso era el viejo apartado de
publicaciones comerciales, retirado): reúsa lo que el dashboard de Métricas ya descarga.
Las cifras salen de la fuente activa de Métricas (Metricool real en prod; muestra en
demo) y se marcan con `es_muestra`, igual que el resto de la consola.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from keni_metricas import servicio

from . import marcas, repos
from .comercial import es_muestra, fuente_actual

_log = logging.getLogger("keni_consola.campanias")

# Rango por defecto de la analítica (ventana rodante de 30 días, igual que Métricas).
RANGO_DEF = "mes"

# Un hashtag es '#' + caracteres de palabra (incluye acentos y dígitos bajo re.UNICODE).
_PAT_HASHTAG = re.compile(r"#(\w+)", re.UNICODE)


class CampaniaInvalida(ValueError):
    """Datos de campaña inválidos (marca/nombre/hashtags). La API la mapea a 400."""


def normalizar_hashtag(tag: str) -> str:
    """Normaliza un hashtag para comparar: sin '#' inicial, sin espacios, en minúsculas.

    No quita acentos a propósito: '#Mañana' y '#Manana' son hashtags distintos en las
    redes. Devuelve "" si tras limpiar no queda nada (lo descarta el llamante).
    """
    limpio = tag.strip().lstrip("#").strip().lower()
    return limpio


def _normalizar_lista(tags: list[str]) -> list[str]:
    """Normaliza y deduplica una lista de hashtags, preservando el orden de entrada."""
    vistos: list[str] = []
    for t in tags or []:
        n = normalizar_hashtag(str(t))
        if n and n not in vistos:
            vistos.append(n)
    return vistos


def hashtags_de(texto: str) -> set[str]:
    """Conjunto de hashtags NORMALIZADOS presentes en un texto (caption)."""
    return {m.lower() for m in _PAT_HASHTAG.findall(texto or "")}


def _enriquecer(cam: dict[str, Any]) -> dict[str, Any]:
    """Añade el nombre legible de la marca a un dict de campaña."""
    return {
        **cam,
        "marca_nombre": marcas.etiqueta_de(cam["marca"]) if cam.get("marca") else "",
    }


# --- CRUD de configuración ----------------------------------------------------


def crear_campania(*, marca: str, nombre: str, hashtags: list[str]) -> dict[str, Any]:
    """Crea una campaña validando marca, nombre y al menos un hashtag."""
    if not marcas.es_marca(marca):
        raise CampaniaInvalida(f"Marca desconocida: {marca!r}.")
    nombre = (nombre or "").strip()
    if not nombre:
        raise CampaniaInvalida("La campaña necesita un nombre.")
    tags = _normalizar_lista(hashtags)
    if not tags:
        raise CampaniaInvalida("La campaña necesita al menos un hashtag.")
    cam = repos.crear_campania_comercial(marca=marca, nombre=nombre, hashtags=tags)
    return _enriquecer(cam)


def listar_campanias(marca: str | None = None) -> list[dict[str, Any]]:
    """Campañas (más recientes primero), opcionalmente filtradas por marca."""
    return [_enriquecer(c) for c in repos.listar_campanias_comerciales(marca=marca)]


def obtener_campania(campania_id: str) -> dict[str, Any] | None:
    """Una campaña por id (None si no existe)."""
    cam = repos.obtener_campania_comercial(campania_id)
    return _enriquecer(cam) if cam is not None else None


def actualizar_campania(campania_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente una campaña (nombre/hashtags/activa); None si el id no existe."""
    cambios: dict[str, Any] = {}
    if "nombre" in campos:
        nombre = (campos["nombre"] or "").strip()
        if not nombre:
            raise CampaniaInvalida("La campaña necesita un nombre.")
        cambios["nombre"] = nombre
    if "hashtags" in campos:
        tags = _normalizar_lista(campos["hashtags"])
        if not tags:
            raise CampaniaInvalida("La campaña necesita al menos un hashtag.")
        cambios["hashtags"] = tags
    if "activa" in campos:
        cambios["activa"] = bool(campos["activa"])
    cam = repos.actualizar_campania_comercial(campania_id, cambios)
    return _enriquecer(cam) if cam is not None else None


def borrar_campania(campania_id: str) -> bool:
    """Borra una campaña; True si existía."""
    return repos.borrar_campania_comercial(campania_id)


# --- Analítica al vuelo -------------------------------------------------------


def _piezas_filtradas(id_metricas: str, rango: str, tags: set[str]) -> list[dict[str, Any]]:
    """Piezas del periodo cuyo caption contiene alguno de los hashtags de la campaña.

    Degrada a `[]` si la fuente no puede listar (config incompleto / rango raro), para que
    la vista nunca reviente.
    """
    try:
        piezas = servicio.construir_listado_piezas(rango, id_metricas)
    except Exception:  # noqa: BLE001 -- sin fuente/cuenta válida: subconjunto vacío
        _log.exception("campanias: no se pudo listar piezas (marca=%s rango=%s).", id_metricas, rango)
        return []
    return [p for p in piezas if tags & hashtags_de(p.get("texto", ""))]


def _agregar(piezas: list[dict[str, Any]]) -> dict[str, Any]:
    """Totales del subconjunto: visualizaciones, interacciones, engagement %, nº piezas."""
    vis = sum(int(p.get("visualizaciones") or 0) for p in piezas)
    inter = sum(int(p.get("interacciones") or 0) for p in piezas)
    eng = round(inter / vis * 100, 2) if vis else 0.0
    return {
        "visualizaciones": vis,
        "interacciones": inter,
        "engagement_pct": eng,
        "piezas": len(piezas),
    }


def _comparar(actual: dict[str, Any], anterior: dict[str, Any]) -> dict[str, Any]:
    """Delta y variación % de cada KPI entre el periodo actual y el anterior.

    `variacion_pct` es None cuando el periodo anterior es 0 (no hay base contra la que
    comparar): la UI lo muestra como "—" en vez de un ∞ engañoso.
    """
    salida: dict[str, Any] = {}
    for clave in ("visualizaciones", "interacciones", "engagement_pct", "piezas"):
        a = actual.get(clave) or 0
        b = anterior.get(clave) or 0
        delta = round(a - b, 2) if isinstance(a, float) or isinstance(b, float) else a - b
        salida[clave] = {
            "actual": a,
            "anterior": b,
            "delta": delta,
            "variacion_pct": round((a - b) / b * 100, 1) if b else None,
        }
    return salida


def _rango_anterior(rango: str) -> str:
    """Token de rango del periodo INMEDIATAMENTE anterior, de la misma duración."""
    desde, _hasta, dias = servicio.resolver_rango(rango)
    prev_hasta = desde - timedelta(days=1)
    prev_desde = prev_hasta - timedelta(days=dias - 1)
    return f"rango:{prev_desde.isoformat()}_{prev_hasta.isoformat()}"


def _tendencia(piezas: list[dict[str, Any]], rango: str) -> list[dict[str, Any]]:
    """Serie diaria del periodo: por día, visualizaciones e interacciones de las piezas
    PUBLICADAS ese día. Rellena con 0 los días sin piezas (eje continuo).

    Atribuir cada pieza a su día de publicación hace que la suma de la serie sea
    exactamente el total de los KPIs (cada pieza cuenta una vez), coherente con las
    tarjetas. Para una campaña de ~5-10 piezas es la lectura honesta y computable: el
    histórico diario por pieza no existe para posts ajenos a la Consola.
    """
    desde, hasta, _dias = servicio.resolver_rango(rango)
    por_dia: dict[str, dict[str, int]] = {}
    for p in piezas:
        dia = str(p.get("publicado") or "")[:10]
        if not dia:
            continue
        acc = por_dia.setdefault(dia, {"visualizaciones": 0, "interacciones": 0})
        acc["visualizaciones"] += int(p.get("visualizaciones") or 0)
        acc["interacciones"] += int(p.get("interacciones") or 0)
    puntos: list[dict[str, Any]] = []
    cursor = desde
    while cursor <= hasta:
        iso = cursor.isoformat()
        acc = por_dia.get(iso, {"visualizaciones": 0, "interacciones": 0})
        puntos.append({"fecha": iso, **acc})
        cursor += timedelta(days=1)
    return puntos


def _pieza_tabla(p: dict[str, Any]) -> dict[str, Any]:
    """Adapta una pieza del listado a la fila de la tabla de campaña."""
    return {
        "id": p.get("id", ""),
        "red": p.get("red", ""),
        "titulo": p.get("titulo", ""),
        "publicado": str(p.get("publicado") or "")[:10],
        "visualizaciones": int(p.get("visualizaciones") or 0),
        "interacciones": int(p.get("interacciones") or 0),
        "engagement_pct": round(float(p.get("engagement_pct") or 0.0), 2),
        "url": p.get("url") or "",
        "formato": p.get("formato") or "",
    }


def analitica_campania(campania_id: str, rango: str = RANGO_DEF) -> dict[str, Any] | None:
    """Analítica completa de una campaña en un periodo (None si la campaña no existe).

    Devuelve KPIs, tabla de piezas del periodo, tendencia diaria y comparativa contra el
    periodo anterior, todo restringido a las piezas cuyo caption lleva sus hashtags.
    """
    cam = obtener_campania(campania_id)
    if cam is None:
        return None
    tags = set(cam["hashtags"])
    id_metricas = marcas.id_metricas_de(cam["marca"])
    desde, hasta, _dias = servicio.resolver_rango(rango)

    piezas = _piezas_filtradas(id_metricas, rango, tags)
    piezas_prev = _piezas_filtradas(id_metricas, _rango_anterior(rango), tags)
    actual = _agregar(piezas)
    anterior = _agregar(piezas_prev)

    # Tabla ordenada por visualizaciones desc (las piezas que más rindieron arriba).
    tabla = sorted(
        (_pieza_tabla(p) for p in piezas),
        key=lambda f: f["visualizaciones"],
        reverse=True,
    )
    return {
        "campania": cam,
        "rango": rango,
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "fuente": fuente_actual(),
        "es_muestra": es_muestra(),
        "kpis": actual,
        "comparativa": _comparar(actual, anterior),
        "tendencia": {"puntos": _tendencia(piezas, rango)},
        "piezas": tabla,
        "generado_en": datetime.now().isoformat(timespec="seconds"),
    }
