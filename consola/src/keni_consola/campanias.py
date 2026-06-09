"""Apartado CAMPAÑAS: agrupa piezas por uno o varios HASHTAGS configurables.

Una campaña define un FILTRO (una o varias MARCAS + hashtags) sobre las piezas YA
publicadas; su analítica —KPIs (visualizaciones, interacciones, engagement), tendencia
diaria, tabla de piezas del periodo y comparativa contra el periodo anterior— se computa AL
VUELO sobre el listado del periodo de cada marca (`servicio.construir_listado_piezas`),
cruzando por los hashtags presentes en el caption de cada pieza (`Pieza.texto`, el caption
ÍNTEGRO: los hashtags suelen ir al final y se perderían en el `titulo` truncado). Las
campañas son MULTIMARCA: agregan las piezas de todas sus marcas.

No monitoriza piezas sueltas ni guarda snapshots propios (eso era el viejo apartado de
publicaciones comerciales, retirado): reúsa lo que el dashboard de Métricas ya descarga.
Las cifras salen de la fuente activa de Métricas (Metricool real en prod; muestra en
demo) y se marcan con `es_muestra`, igual que el resto de la consola.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

from keni_metricas import servicio

from . import marcas, metricas_cache, repos
from .comercial import es_muestra, fuente_actual
from .tiempo import ahora_iso

_log = logging.getLogger("keni_consola.campanias")

# Rango por defecto de la analítica (ventana rodante de 30 días, igual que Métricas).
RANGO_DEF = "mes"

# Un hashtag es '#' + caracteres de palabra (incluye acentos y dígitos bajo re.UNICODE).
_PAT_HASHTAG = re.compile(r"#(\w+)", re.UNICODE)


class CampaniaInvalida(ValueError):
    """Datos de campaña inválidos (marca/nombre/hashtags). La API la mapea a 400."""


def normalizar_hashtag(tag: str) -> str:
    """Limpia un hashtag CONSERVANDO su casing: sin '#' inicial ni espacios.

    Se preserva el case tal cual lo escribió la persona ('#Chihuahua' se guarda y se
    muestra '#Chihuahua', no '#chihuahua'): el casing es decisión editorial. El MATCHING
    contra los posts sí es case-insensitive (en las redes los hashtags lo son); eso lo
    resuelve la comparación, no el almacenamiento. No quita acentos a propósito: '#Mañana'
    y '#Manana' son hashtags distintos. Devuelve "" si tras limpiar no queda nada.
    """
    return tag.strip().lstrip("#").strip()


def _normalizar_lista(tags: list[str]) -> list[str]:
    """Limpia y deduplica una lista de hashtags, preservando orden y casing de entrada.

    La deduplicación es case-insensitive (no se guardan '#Chihuahua' y '#chihuahua' a la
    vez), pero conserva el casing de la PRIMERA aparición.
    """
    vistos: list[str] = []
    claves: set[str] = set()
    for t in tags or []:
        n = normalizar_hashtag(str(t))
        if n and n.lower() not in claves:
            vistos.append(n)
            claves.add(n.lower())
    return vistos


def hashtags_de(texto: str) -> set[str]:
    """Conjunto de hashtags de un texto, en MINÚSCULAS (para comparar sin importar case)."""
    return {m.lower() for m in _PAT_HASHTAG.findall(texto or "")}


def _enriquecer(cam: dict[str, Any]) -> dict[str, Any]:
    """Añade los nombres legibles de las marcas de la campaña."""
    return {
        **cam,
        "marcas_nombres": [marcas.etiqueta_de(m) for m in cam.get("marcas", [])],
    }


def _validar_marcas(marcas_ids: list[str]) -> list[str]:
    """Deduplica (preservando orden) y valida que cada marca exista. >=1 obligatoria."""
    vistas: list[str] = []
    for m in marcas_ids or []:
        if not isinstance(m, str) or not marcas.es_marca(m):
            raise CampaniaInvalida(f"Marca desconocida: {m!r}.")
        if m not in vistas:
            vistas.append(m)
    if not vistas:
        raise CampaniaInvalida("La campaña necesita al menos una marca.")
    return vistas


# --- CRUD de configuración ----------------------------------------------------


def crear_campania(*, marcas_ids: list[str], nombre: str, hashtags: list[str]) -> dict[str, Any]:
    """Crea una campaña (multimarca) validando marcas, nombre y al menos un hashtag."""
    marcas_validas = _validar_marcas(marcas_ids)
    nombre = (nombre or "").strip()
    if not nombre:
        raise CampaniaInvalida("La campaña necesita un nombre.")
    tags = _normalizar_lista(hashtags)
    if not tags:
        raise CampaniaInvalida("La campaña necesita al menos un hashtag.")
    cam = repos.crear_campania_comercial(marcas=marcas_validas, nombre=nombre, hashtags=tags)
    return _enriquecer(cam)


def listar_campanias(marca: str | None = None) -> list[dict[str, Any]]:
    """Campañas (más recientes primero); `marca` filtra a las que la INCLUYEN."""
    return [_enriquecer(c) for c in repos.listar_campanias_comerciales(marca=marca)]


def obtener_campania(campania_id: str) -> dict[str, Any] | None:
    """Una campaña por id (None si no existe)."""
    cam = repos.obtener_campania_comercial(campania_id)
    return _enriquecer(cam) if cam is not None else None


def actualizar_campania(campania_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente una campaña (nombre/marcas/hashtags/activa); None si no existe."""
    cambios: dict[str, Any] = {}
    if "nombre" in campos:
        nombre = (campos["nombre"] or "").strip()
        if not nombre:
            raise CampaniaInvalida("La campaña necesita un nombre.")
        cambios["nombre"] = nombre
    if "marcas" in campos:
        cambios["marcas"] = _validar_marcas(campos["marcas"])
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


async def _listado_cacheado(rango: str, idm: str) -> list[dict[str, Any]]:
    """Listado de piezas de una marca/periodo, vía la cache de Métricas (lazy fill).

    Reúsa `metricas_cache.piezas_listado_async`: el listado de cada (rango, marca) se
    calcula UNA vez (golpe caro a Metricool: miles de posts+reels) y se persiste; las
    siguientes lecturas —y el dashboard de Métricas del mismo combo— son instantáneas.
    Degrada a `[]` si la fuente falla, para que la campaña nunca reviente.
    """
    try:
        payload, _gen = await metricas_cache.piezas_listado_async(rango, idm)
    except Exception:  # noqa: BLE001 -- sin fuente/cuenta válida: esa marca aporta 0
        _log.exception("campanias: no se pudo listar piezas (marca=%s rango=%s).", idm, rango)
        return []
    return payload.get("piezas") or []


def _filtrar(piezas: list[dict[str, Any]], tags: set[str]) -> list[dict[str, Any]]:
    """Piezas cuyo caption (`texto`) contiene alguno de los hashtags de la campaña."""
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


def _desglose_por_red(piezas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrega las piezas por red: nº, visualizaciones, interacciones y el desglose de
    interacciones (likes/comentarios/compartidos/guardados), con engagement %. Ordenado por
    visualizaciones desc. Permite ver POR QUÉ RED rinde la campaña sin salir del panel.

    Los granulares ausentes (la fuente no siempre los trae por pieza) cuentan como 0: es una
    suma honesta del subconjunto, coherente con las tarjetas de KPIs.
    """
    por_red: dict[str, dict[str, Any]] = {}
    for p in piezas:
        red = p.get("red") or ""
        acc = por_red.setdefault(
            red,
            {
                "red": red, "piezas": 0, "visualizaciones": 0, "interacciones": 0,
                "likes": 0, "comentarios": 0, "compartidos": 0, "guardados": 0,
            },
        )
        acc["piezas"] += 1
        acc["visualizaciones"] += int(p.get("visualizaciones") or 0)
        acc["interacciones"] += int(p.get("interacciones") or 0)
        acc["likes"] += int(p.get("likes") or 0)
        acc["comentarios"] += int(p.get("comentarios") or 0)
        acc["compartidos"] += int(p.get("compartidos") or 0)
        acc["guardados"] += int(p.get("guardados") or 0)
    filas = list(por_red.values())
    for acc in filas:
        vis = acc["visualizaciones"]
        acc["engagement_pct"] = round(acc["interacciones"] / vis * 100, 2) if vis else 0.0
    filas.sort(key=lambda f: f["visualizaciones"], reverse=True)
    return filas


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


async def analitica_campania(campania_id: str, rango: str = RANGO_DEF) -> dict[str, Any] | None:
    """Analítica completa de una campaña en un periodo (None si la campaña no existe).

    Devuelve KPIs, tabla de piezas del periodo, tendencia diaria y comparativa contra el
    periodo anterior, todo restringido a las piezas cuyo caption lleva sus hashtags.

    Es ASÍNCRONA y descarga los listados de TODAS las marcas × (periodo actual + anterior)
    EN PARALELO y CACHEADOS: el coste de pared es la descarga más lenta, no la suma — clave
    para que una campaña multimarca de periodo amplio no agote el tiempo de la petición.
    """
    cam = obtener_campania(campania_id)
    if cam is None:
        return None
    # Matching case-insensitive: los hashtags se guardan con su casing, pero se comparan
    # en minúsculas (en las redes '#Chihuahua' y '#chihuahua' son el mismo hashtag).
    tags = {h.lower() for h in cam["hashtags"]}
    # Una marca puede no tener id_metricas (no conectada): se omite del agregado.
    ids_metricas = [m for m in (marcas.id_metricas_de(x) for x in cam["marcas"]) if m]
    desde, hasta, _dias = servicio.resolver_rango(rango)
    rango_prev = _rango_anterior(rango)

    # Todos los combos (periodo, marca) a la vez; cada uno cacheado e independiente.
    combos = [(rango, idm) for idm in ids_metricas] + [(rango_prev, idm) for idm in ids_metricas]
    crudos = await asyncio.gather(*(_listado_cacheado(r, idm) for r, idm in combos))
    por_combo = dict(zip(combos, crudos))

    def _piezas_de(r: str) -> list[dict[str, Any]]:
        unidas: list[dict[str, Any]] = []
        for idm in ids_metricas:
            unidas.extend(por_combo.get((r, idm), []))
        return _filtrar(unidas, tags)

    piezas = _piezas_de(rango)
    piezas_prev = _piezas_de(rango_prev)
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
        "desglose_red": _desglose_por_red(piezas),
        "piezas": tabla,
        "generado_en": ahora_iso(),
    }
