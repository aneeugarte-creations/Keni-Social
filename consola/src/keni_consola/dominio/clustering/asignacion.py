"""Clave de cluster y ASIGNACIÓN incremental item→cluster (capa pura).

Reglas de agrupación (`asignar`):
  - (a) MISMA `url_canonica_clustering` (host+path, SIN query): es literalmente el mismo
    recurso → mismo cluster, sin ambigüedad.
  - (b) si no, FUZZY del título normalizado del item contra el `titulo`/`clave` del cluster
    con ratio `SequenceMatcher` ≥ `umbral` (def `KENI_CLUSTER_UMBRAL` = 0.82). Conservador:
    títulos muy cortos no entran al fuzzy (ratios espurios).
  - si nada casa → cluster nuevo.

Reutiliza la lógica de cruce de títulos del Radar (`similitud.clave_fuzzy` + sinónimos +
`SequenceMatcher`) y la normalización/hash de `dominio.dedup`. Movido VERBATIM desde el
antiguo `clustering.py`.
"""

from __future__ import annotations

from typing import Any

from .. import dedup, similitud
from ._comun import (
    _MIN_LONGITUD_FUZZY,
    _MIN_TOKEN_BLOCKING,
    _ratio_claves,
)


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
    """Clave de identidad de un item para clustering.

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


def _ratio_titulos(a: str, b: str) -> float:
    """Ratio fuzzy [0,1] entre dos títulos usando la clave normalizada + sinónimos del Radar.

    Reutiliza `radar._clave_fuzzy` (minúsculas, sin acentos, sin signos, sinónimos del dominio
    colapsados a su forma canónica) antes de comparar con `_ratio_claves` (directo + token-sort).
    Claves cortas devuelven 0.0 (no entran al fuzzy): evita falsos positivos entre títulos
    triviales.
    """
    ka = similitud.clave_fuzzy(a)
    kb = similitud.clave_fuzzy(b)
    if len(ka) < _MIN_LONGITUD_FUZZY or len(kb) < _MIN_LONGITUD_FUZZY:
        return 0.0
    return _ratio_claves(ka, kb)


def asignar(
    item: dict[str, Any],
    clusters_recientes: list[dict[str, Any]],
    *,
    umbral: float = 0.82,
) -> str | None:
    """Decide a qué cluster reciente unir `item`, o `None` para crear uno nuevo. PURA.

    `clusters_recientes` son los clusters de la ventana (dicts con al menos `id`, `clave`,
    `titulo`). Une si:
      (a) la `clave` de cluster del item (url canónica host+path) coincide exacta con la
          `clave` de algún cluster — mismo recurso, sin ambigüedad; o
      (b) el fuzzy del título del item contra el `titulo` del cluster supera `umbral`.
    Si varios clusters casan por fuzzy, gana el de mayor ratio (el más parecido). `None` si
    el item no tiene clave estable o ninguno casa.
    """
    clave = clave_cluster(item)
    if not clave:
        return None

    # (a) Cruce EXACTO por clave de cluster (url canónica). Determinista, prioritario.
    if clave.startswith("url:"):
        for c in clusters_recientes:
            if str(c.get("clave") or "") == clave:
                return str(c["id"])

    # (b) Fuzzy del título contra el título representativo de cada cluster — y contra su
    # TRADUCCIÓN (`titulo_es`): un titular en español debe poder unirse a la historia
    # extranjera ya traducida (antes solo casaba contra el título original EN/PT/...).
    titulo = str(item.get("titulo") or "")
    if not titulo.strip():
        return None
    mejor_id: str | None = None
    mejor_ratio = umbral
    for c in clusters_recientes:
        ratio = max(
            _ratio_titulos(titulo, str(c.get("titulo") or "")),
            _ratio_titulos(titulo, str(c.get("titulo_es") or "")),
        )
        # A EMPATE exacto de ratio gana el PRIMER candidato visto (determinista); antes el
        # `>=` dejaba ganar al último, y el resultado dependía del orden de la lista.
        if ratio >= umbral and (mejor_id is None or ratio > mejor_ratio):
            mejor_ratio = ratio
            mejor_id = str(c["id"])
    return mejor_id


class Asignador:
    """Índice incremental de asignación item→cluster para un barrido. MISMA decisión que
    `asignar`, pero O(items × candidatos) en vez de O(items × clusters):

      - precomputa UNA vez la clave fuzzy del título de cada cluster (antes se recomputaba en
        cada comparación item×cluster), y
      - mantiene un índice invertido token→clusters (blocking): el ratio fuzzy solo se calcula
        contra los clusters que comparten ≥1 token significativo con el item.

    `agregar` mantiene el índice vivo durante el barrido (los clusters nuevos del mismo barrido
    entran al índice). Determinista: a empate de ratio gana el cluster agregado primero. PURO.
    """

    def __init__(
        self, clusters_recientes: list[dict[str, Any]], *, umbral: float = 0.82
    ) -> None:
        self.umbral = float(umbral)
        self._orden: dict[str, int] = {}        # id -> orden de entrada (desempate estable)
        self._por_clave_url: dict[str, str] = {}  # clave url -> id (cruce exacto)
        # id -> claves fuzzy del cluster (título representativo Y su traducción `titulo_es`,
        # si la hay): un titular en español casa contra la historia extranjera ya traducida.
        self._fuzzy: dict[str, list[str]] = {}
        self._por_token: dict[str, set[str]] = {}  # token significativo -> ids
        for c in clusters_recientes:
            self.agregar(c)

    def agregar(self, cluster: dict[str, Any]) -> None:
        """Añade un cluster al índice (no-op si ya está o no tiene id)."""
        cid = str(cluster.get("id") or "")
        if not cid or cid in self._orden:
            return
        self._orden[cid] = len(self._orden)
        clave = str(cluster.get("clave") or "")
        if clave.startswith("url:") and clave not in self._por_clave_url:
            self._por_clave_url[clave] = cid
        claves_fuzzy: list[str] = []
        for campo in ("titulo", "titulo_es"):
            kf = similitud.clave_fuzzy(str(cluster.get(campo) or ""))
            if len(kf) >= _MIN_LONGITUD_FUZZY and kf not in claves_fuzzy:
                claves_fuzzy.append(kf)
        if claves_fuzzy:
            self._fuzzy[cid] = claves_fuzzy
            for kf in claves_fuzzy:
                for token in set(kf.split()):
                    if len(token) >= _MIN_TOKEN_BLOCKING:
                        self._por_token.setdefault(token, set()).add(cid)

    def asignar(self, item: dict[str, Any]) -> str | None:
        """Cluster destino para `item` (mismas reglas que `asignar`), o None si ninguno casa."""
        clave = clave_cluster(item)
        if not clave:
            return None
        if clave.startswith("url:"):
            destino = self._por_clave_url.get(clave)
            if destino:
                return destino
        titulo = str(item.get("titulo") or "")
        if not titulo.strip():
            return None
        kf = similitud.clave_fuzzy(titulo)
        if len(kf) < _MIN_LONGITUD_FUZZY:
            return None
        candidatos: set[str] = set()
        for token in set(kf.split()):
            if len(token) >= _MIN_TOKEN_BLOCKING:
                candidatos |= self._por_token.get(token, set())
        mejor_id: str | None = None
        mejor_ratio = self.umbral
        for cid in sorted(candidatos, key=lambda c: self._orden.get(c, 0)):
            ratio = max(_ratio_claves(kf, k) for k in self._fuzzy[cid])
            if ratio >= self.umbral and (mejor_id is None or ratio > mejor_ratio):
                mejor_ratio = ratio
                mejor_id = cid
        return mejor_id


def grupos_lexicos(
    clusters: list[dict[str, Any]], *, umbral: float = 0.86
) -> list[list[str]]:
    """Grupos de historias que el LÉXICO descubre iguales TARDE (merge de ventana). PURA.

    La asignación incremental solo compara un item contra los clusters que existían en su
    momento: dos historias del mismo evento pueden nacer por separado (distinto orden de
    llegada, traducción tardía) y quedarse duplicadas. Esto barre los clusters de la ventana
    y agrupa los pares cuyo título (o su traducción `titulo_es`) casa con ratio >= `umbral`
    — MÁS ESTRICTO que el de asignación (0.86 vs 0.82: fundir historias ya formadas pide más
    certeza), con el veto de números incompatibles y sin cruzar categorías distintas (una
    categoría vacía casa con cualquiera). Devuelve listas de ids (≥2) para que el daemon las
    funda con `_fusionar_grupo` (que ya trae anti-TOCTOU). Determinista; `umbral<=0` apaga.
    """
    if umbral <= 0 or len(clusters) < 2:
        return []
    entradas: list[tuple[str, list[str], str]] = []
    for c in clusters:
        cid = str(c.get("id") or "")
        if not cid:
            continue
        claves: list[str] = []
        for campo in ("titulo", "titulo_es"):
            kf = similitud.clave_fuzzy(str(c.get(campo) or ""))
            if len(kf) >= _MIN_LONGITUD_FUZZY and kf not in claves:
                claves.append(kf)
        if claves:
            entradas.append((cid, claves, str(c.get("categoria") or "")))
    if len(entradas) < 2:
        return []

    # Blocking por token significativo (mismo criterio que `Asignador`): el ratio solo se
    # evalúa entre clusters que comparten >= 1 token.
    por_token: dict[str, set[int]] = {}
    for i, (_cid, claves, _cat) in enumerate(entradas):
        for kf in claves:
            for token in set(kf.split()):
                if len(token) >= _MIN_TOKEN_BLOCKING:
                    por_token.setdefault(token, set()).add(i)

    # Union-find con compresión de camino (los grupos pueden encadenarse: a~b, b~c).
    padre = list(range(len(entradas)))

    def _raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i, (_cid, claves, cat) in enumerate(entradas):
        candidatos: set[int] = set()
        for kf in claves:
            for token in set(kf.split()):
                if len(token) >= _MIN_TOKEN_BLOCKING:
                    candidatos |= por_token.get(token, set())
        for j in sorted(candidatos):
            if j <= i:
                continue
            _cid_j, claves_j, cat_j = entradas[j]
            if cat and cat_j and cat != cat_j:
                continue  # categorías declaradas y distintas: no se cruzan
            ratio = max(_ratio_claves(a, b) for a in claves for b in claves_j)
            if ratio >= umbral:
                ra, rb = _raiz(i), _raiz(j)
                if ra != rb:
                    padre[max(ra, rb)] = min(ra, rb)

    grupos: dict[int, list[str]] = {}
    for i, (cid, _claves, _cat) in enumerate(entradas):
        grupos.setdefault(_raiz(i), []).append(cid)
    return [g for g in grupos.values() if len(g) >= 2]
