"""Clave de cluster y ASIGNACIÓN incremental item→cluster (capa pura).

Reglas de agrupación (`asignar`) — DEDUP EXACTO POR MARCA, sin léxico:
  - (a) MISMA `url_canonica_clustering` (host+path, SIN query) Y MISMA marca: es literalmente el
    mismo recurso para ese mercado → mismo cluster, sin ambigüedad.
  - (b) si no hay url, título normalizado IDÉNTICO (`t:<hash>` de `dedup`) Y misma marca: dos
    titulares equivalentes sin url colisionan por su hash dentro de la marca.
  - si nada casa EXACTO en la misma marca → cluster nuevo.

El clustering es POR MARCA: una fuente multimarca archiva el mismo artículo una vez por marca
(fan-out de la ingesta) y cada mercado forma su propia historia (score/estado/promoción propios).

La agrupación de historias del MISMO evento contadas con titulares DISTINTOS ya no la hace el
léxico (fuzzy): la resuelve la fusión semántica con Haiku (`paso_fusionar_semantica`, ON por
defecto). La formación de clusters se queda en el cruce EXACTO (url canónica o hash de título),
que es determinista y barato. Reutiliza la normalización/hash de `dominio.dedup`.
"""

from __future__ import annotations

from typing import Any

from .. import dedup


def url_canonica_clustering(url: str) -> str:
    """URL para CRUCE de clustering: host + path, SIN query ni fragmento ('' si no http).

    Más agresiva que `dedup.url_canonica` (que conserva los parámetros NO de tracking): aquí
    el contrato pide host+path sin query, porque dos enlaces a la MISMA nota con distintos
    parámetros (paginación, `?ref=`, ids de sección) son la misma historia. Reutiliza el
    canónico de dedup (quita esquema/`www.`/tracking) y le recorta la query.
    """
    base = dedup.url_canonica(url)
    if not base:
        return ""
    # `dedup.url_canonica` devuelve `host[/path][?query]`; recortamos en el primer '?'.
    return base.split("?", 1)[0]


def clave_cluster(item: dict[str, Any]) -> str:
    """Clave de identidad de un item para agrupación.

    `url:<host/path>` si el item tiene url canónica (cruce exacto entre fuentes que enlazan
    el mismo recurso); si no, `t:<hash>` del título normalizado (`dedup`), para que titulares
    equivalentes sin url colisionen. "" si el item no tiene ni url ni título útil (no se puede
    agrupar de forma estable: el llamante lo deja sin cluster).
    """
    url = url_canonica_clustering(str(item.get("url") or item.get("url_canonica") or ""))
    if url:
        return "url:" + url
    k = dedup.clave(str(item.get("titulo") or ""))
    if not k:
        return ""
    return "t:" + k


def asignar(
    item: dict[str, Any],
    clusters_recientes: list[dict[str, Any]],
) -> str | None:
    """Decide a qué cluster reciente unir `item`, o `None` para crear uno nuevo. PURA.

    DEDUP EXACTO: `clusters_recientes` son los clusters de la ventana (dicts con al menos `id`
    y `clave`). Une si la `clave` de cluster del item (url canónica host+path, o `t:<hash>` del
    título normalizado) coincide EXACTA con la `clave` de algún cluster — mismo recurso o título
    idéntico, sin ambigüedad. A varios casos iguales gana el primero (determinista). `None` si el
    item no tiene clave estable o ninguno casa: la fusión semántica (Haiku) agrupa después las
    historias del mismo evento con titulares distintos.
    """
    clave = clave_cluster(item)
    if not clave:
        return None
    # POR MARCA: un item solo se une a un cluster de SU marca. Una fuente multimarca archiva el
    # mismo artículo una vez por marca (fan-out); cada mercado forma su propia historia.
    marca = str(item.get("marca") or "")
    for c in clusters_recientes:
        if str(c.get("clave") or "") == clave and str(c.get("marca") or "") == marca:
            return str(c["id"])
    return None


class Asignador:
    """Índice incremental de asignación item→cluster por clave EXACTA. MISMA decisión que
    `asignar`, pero O(items) en vez de O(items × clusters): un único dict `clave → id`.

    `agregar` mantiene el índice vivo durante el barrido (los clusters nuevos del mismo barrido
    entran al índice). Determinista: a clave repetida gana el cluster agregado primero. PURO.
    """

    def __init__(self, clusters_recientes: list[dict[str, Any]]) -> None:
        # (marca, clave) -> id: el clustering es POR MARCA (un item solo se une a un cluster de su
        # marca). A clave repetida dentro de una marca gana el primer cluster agregado.
        self._por_clave: dict[tuple[str, str], str] = {}
        for c in clusters_recientes:
            self.agregar(c)

    def agregar(self, cluster: dict[str, Any]) -> None:
        """Añade un cluster al índice (no-op si ya está indexado por su (marca, clave) o sin id/clave)."""
        cid = str(cluster.get("id") or "")
        if not cid:
            return
        clave = str(cluster.get("clave") or "")
        if not clave:
            return
        k = (str(cluster.get("marca") or ""), clave)
        if k not in self._por_clave:
            self._por_clave[k] = cid

    def asignar(self, item: dict[str, Any]) -> str | None:
        """Cluster destino para `item` (misma decisión EXACTA que `asignar`), o None si ninguno casa."""
        clave = clave_cluster(item)
        if not clave:
            return None
        return self._por_clave.get((str(item.get("marca") or ""), clave))
