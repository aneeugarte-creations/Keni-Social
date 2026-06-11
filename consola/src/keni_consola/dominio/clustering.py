"""Clustering de HISTORIAS sobre el archivo de artículos (Ola B) — capa PURA/testeable.

El motor de ingesta (Ola A) archiva miles de artículos crudos en `noticias_items`. Esta
capa los agrupa en HISTORIAS: la misma noticia contada por varias fuentes y a lo largo del
tiempo. Una historia (cluster) es la unidad newsroom — deduplicada, corroborada por N
fuentes distintas, puntuada y rankeable.

PURA: no toca BD ni red. El daemon de ingesta le pasa el item recién insertado y los
clusters de la ventana reciente (que cargó de `db`), decide a cuál unir (o crear uno
nuevo), y persiste el resultado. Determinista y testeable sin I/O.

Reutiliza la lógica de cruce de títulos del Radar (`radar._clave_fuzzy` + sinónimos +
`SequenceMatcher`) y la normalización/hash de `dominio.dedup`, para no reinventar el
fuzzy-matching ni divergir de cómo el Radar consolida temas.

Reglas de agrupación (`asignar`):
  - (a) MISMA `url_canonica_clustering` (host+path, SIN query): es literalmente el mismo
    recurso → mismo cluster, sin ambigüedad.
  - (b) si no, FUZZY del título normalizado del item contra el `titulo`/`clave` del cluster
    con ratio `SequenceMatcher` ≥ `umbral` (def `KENI_CLUSTER_UMBRAL` = 0.82). Conservador:
    títulos muy cortos no entran al fuzzy (ratios espurios).
  - si nada casa → cluster nuevo.

Scoring (`puntuar`): ver la fórmula documentada en su docstring.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from . import dedup, similitud

# Longitud mínima de una clave normalizada para entrar al fuzzy. Títulos muy cortos
# ("nfl", "f1") disparan ratios altos espurios entre sí: solo casan por url exacta.
_MIN_LONGITUD_FUZZY = 8

# Umbral de "breaking" PONDERADO por defecto (lo fija el daemon vía config). Una historia es
# breaking si la MASA de fuentes (Σ peso por outlet) que se sumaron en la ventana ACTUAL
# alcanza este mínimo: 3 normales, 1 potente + 1 normal, o 2 potentes. Como la ventana se
# ancla en AHORA, el flag DECAE solo (un breaking de ayer deja de serlo): breaking es una
# consecuencia del ranking (corroboración ponderada × velocidad), no un carril aparte.
BREAKING_PESO_DEF = 3.0
BREAKING_VENTANA_H_DEF = 6

# Pesos del score (ver `puntuar`). Suman 1.0: el score vive en [0, 1] y es comparable
# entre marcas/categorías para el ranking. Son los DEFAULTS; el daemon los puede inyectar
# desde la configuración (ajustes editables por la consola), de ahí la dataclass `PesosScore`.
_PESO_CORROBORACION = 0.30
_PESO_VELOCIDAD = 0.20
_PESO_FRESCURA = 0.20
_PESO_VIRALIDAD = 0.10
_PESO_MARCA = 0.20
# Empujón aditivo si la historia es breaking. DEFAULT 0.0 = SIN bonus: breaking ya emerge del
# ranking (2 fuentes potentes a la vez ⇒ corroboración 0.67 + velocidad 1.0 ⇒ top del pool);
# el knob queda por compatibilidad/rollback (config puede reactivarlo sin tocar código).
_BONUS_BREAKING = 0.0
# Peso de la señal de RENDIMIENTO (líneas que mejor funcionan). DEFAULT 0.0 = INERTE: la señal
# (Fase 2c) solo cuenta cuando el equipo le da peso desde config; así no cambia nada por defecto.
_PESO_RENDIMIENTO = 0.0


@dataclass(frozen=True)
class PesosScore:
    """Pesos del algoritmo de ponderación del score de cluster (inyectables desde config).

    `corroboracion/velocidad/frescura/viralidad/marca` son la combinación lineal (idealmente
    suman ~1.0); `breaking` es el empujón aditivo (def 0.0: breaking ya emerge del ranking);
    `rendimiento` es la señal de líneas que mejor funcionan (Fase 2c), INERTE por defecto
    (peso 0). `puntuar()` usa estos; el daemon construye una instancia desde
    `config.score_pesos()`. Sin inyección, `puntuar()` cae a `_PESOS_DEF`.
    """

    corroboracion: float = _PESO_CORROBORACION
    velocidad: float = _PESO_VELOCIDAD
    frescura: float = _PESO_FRESCURA
    viralidad: float = _PESO_VIRALIDAD
    marca: float = _PESO_MARCA
    breaking: float = _BONUS_BREAKING
    rendimiento: float = _PESO_RENDIMIENTO


_PESOS_DEF = PesosScore()

# Normalizadores de cada señal (ver fórmula).
_PESO_SATURA = 8.0  # masa ponderada (Σ peso por outlet) que satura la corroboración a 1.0
_VEL_SATURA = 4.0  # masa en la ventana actual que satura la velocidad (= 2 potentes a la vez)
_SENAL_SATURA = 1_000_000  # escala log de viralidad (alineada con parrilla)
_FRESCURA_VIDA_H = 72.0  # a las 72h la frescura cae a ~0 (lineal acotada)


# --------------------------------------------------------------------------- #
# Clave de cluster                                                              #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Asignación incremental (item -> cluster reciente)                             #
# --------------------------------------------------------------------------- #


def _tokens_ordenados(clave: str) -> str:
    """Forma TOKEN-SORT de una clave fuzzy: mismos tokens, orden alfabético, deduplicados.

    El mismo EVENTO se titula con las mismas palabras en distinto orden ("América vence a
    Chivas en el clásico" / "Clásico: Chivas cae y América vence"): el `SequenceMatcher`
    posicional castiga la reordenación aunque el contenido sea idéntico. Comparar además las
    claves con tokens ordenados (estilo token-sort-ratio) recupera esos pares sin relajar el
    umbral global.
    """
    return " ".join(sorted(set(clave.split())))


_RE_NUMEROS = re.compile(r"\d+")


def _numeros_incompatibles(ka: str, kb: str) -> bool:
    """True si AMBAS claves traen números y NO comparten ninguno (eventos distintos).

    Veto de seguridad del fuzzy: "sismo de 6.2" y "sismo de 7.1" comparten casi todo el
    texto (ratio alto) pero son acontecimientos DISTINTOS; igual con jornadas, marcadores o
    fechas. Solo veta cuando los dos lados tienen números y son disjuntos: un titular sin
    números nunca se penaliza (no se castiga la ausencia de dato).
    """
    na = frozenset(_RE_NUMEROS.findall(ka))
    if not na:
        return False
    nb = frozenset(_RE_NUMEROS.findall(kb))
    return bool(nb) and not (na & nb)


def _ratio_claves(ka: str, kb: str) -> float:
    """Ratio fuzzy [0,1] entre dos claves YA normalizadas: el MÁXIMO del directo y el token-sort.

    El directo respeta el orden (titulares casi idénticos); el token-sort tolera la
    reordenación (mismo evento, sintaxis distinta). Tomar el máximo solo puede UNIR más pares
    del mismo evento, nunca menos (monótono respecto al comportamiento anterior). VETO de
    números incompatibles (`_numeros_incompatibles`): dos titulares con cifras disjuntas son
    eventos distintos por mucho texto que compartan → ratio 0.
    """
    if _numeros_incompatibles(ka, kb):
        return 0.0
    directo = SequenceMatcher(None, ka, kb).ratio()
    ordenado = SequenceMatcher(None, _tokens_ordenados(ka), _tokens_ordenados(kb)).ratio()
    return max(directo, ordenado)


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


# Longitud mínima de un token para el BLOCKING del índice de asignación: el fuzzy solo se
# evalúa contra clusters que comparten ≥1 token "significativo" con el item (dos títulos sin
# tokens en común no alcanzan el umbral 0.82 en la práctica).
_MIN_TOKEN_BLOCKING = 3


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


# --------------------------------------------------------------------------- #
# Recálculo de los agregados de un cluster                                      #
# --------------------------------------------------------------------------- #


def _parse_iso(valor: str) -> datetime | None:
    """Parsea un ISO 8601 a datetime aware (UTC); None si no parsea. Best-effort."""
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(valor)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _instante_item(item: dict[str, Any]) -> str:
    """Instante representativo de un item: `publicado_en` si lo hay, si no `capturado_en`."""
    return str(item.get("publicado_en") or item.get("capturado_en") or "")


def _marca_dominante(items: list[dict[str, Any]]) -> str:
    """Marca más frecuente entre los items (con marca no vacía); '' si ninguna tiene marca.

    A empate, gana la primera vista (orden de entrada) para ser determinista.
    """
    conteo: dict[str, int] = {}
    orden: list[str] = []
    for it in items:
        m = str(it.get("marca") or "").strip()
        if not m:
            continue
        if m not in conteo:
            orden.append(m)
        conteo[m] = conteo.get(m, 0) + 1
    if not conteo:
        return ""
    return max(orden, key=lambda m: conteo[m])


def _es_curado(item: dict[str, Any]) -> bool:
    """True si el item es material CURADO de cajón (fuente `cajon[-*]`, señal artificial alta).

    Los curados llevan `senal = SENAL_CURADO` (1e6) para que su historia supere el umbral del
    auto-feed, pero esa señal es ARTIFICIAL: no debe secuestrar el título representativo de un
    cluster con prensa real ni saturar la viralidad de la historia mixta.
    """
    return str(item.get("fuente_id") or "").startswith("cajon")


def _representativo(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Item representativo: prefiere idioma 'es', luego mayor señal, luego título más largo.

    El título/resumen de la historia salen de aquí (el más informativo en el idioma del
    piloto). Se prefiere el TITULAR PERIODÍSTICO real: los insumos curados de cajón (señal
    artificial 1e6) solo representan la historia si no hay otra cosa. Determinista.
    """
    def llave(it: dict[str, Any]) -> tuple[int, int, int]:
        es = 1 if str(it.get("idioma") or "").lower().startswith("es") else 0
        return (es, int(it.get("senal") or 0), len(str(it.get("titulo") or "")))

    candidatos = [it for it in items if not _es_curado(it)] or items
    return max(candidatos, key=llave)


# --------------------------------------------------------------------------- #
# Verificación por corroboración (Ola D)                                        #
# --------------------------------------------------------------------------- #

# Señales de CLICKBAIT en un titular (sin acentos, minúsculas): si la ÚNICA fuente además
# dispara una de estas, la historia se marca 'dudosa'. Conservador: lista corta y específica.
_SENALES_CLICKBAIT: frozenset[str] = frozenset({
    "no vas a creer", "te sorprendera", "lo que paso despues", "esto es lo que",
    "shocking", "you wont believe", "increible lo que", "mira lo que",
})


def _host_de(url: str) -> str:
    """Host (sin esquema/www/path) de una url para cruzarlo con la lista de baja confianza."""
    base = dedup.url_canonica(url)
    if not base:
        return ""
    return base.split("?", 1)[0].split("/", 1)[0]


def _es_baja_confianza(item: dict[str, Any], fuentes_baja: frozenset[str]) -> bool:
    """True si el item viene de una fuente de baja confianza (host o `fuente_nombre` listado)."""
    if not fuentes_baja:
        return False
    host = _host_de(str(item.get("url") or item.get("url_canonica") or "")).lower()
    nombre = str(item.get("fuente_nombre") or "").lower()
    for marca in fuentes_baja:
        if not marca:
            continue
        if (host and marca in host) or (nombre and marca in nombre):
            return True
    return False


def _hay_clickbait(items: list[dict[str, Any]]) -> bool:
    """True si algún titular de los items dispara una señal de clickbait conocida."""
    for it in items:
        titulo = _sin_acentos(str(it.get("titulo") or ""))
        if any(senal in titulo for senal in _SENALES_CLICKBAIT):
            return True
    return False


def fuentes_detalle(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """TIMELINE de OUTLETS de una historia: quién la abrió y quién se fue sumando. PURA.

    Deduplica por OUTLET (host de la url; cae a `fuente_id` sin url — mismo criterio que
    `clasificar_verificacion`: dos enlaces del mismo medio no son dos fuentes). Por outlet:
      - `fuente_id` / `fuente` (nombre humano) / `host`,
      - `peso` (el MÁXIMO de sus items: el peso editorial de la fuente),
      - `primer_visto` (el instante más temprano de sus items: cuándo se sumó),
      - `n_items` (cuántos artículos aportó).
    Orden CRONOLÓGICO por `primer_visto` (el primero ABRIÓ la historia); outlets sin
    timestamp van al final. Es la base de la corroboración PONDERADA (`peso_fuentes` =
    Σ peso por outlet) y de la señal de velocidad del scoring.
    """
    por_outlet: dict[str, dict[str, Any]] = {}
    for it in items:
        host = _host_de(str(it.get("url") or it.get("url_canonica") or "")).lower()
        clave = host or str(it.get("fuente_id") or "")
        if not clave:
            continue
        instante = _instante_item(it)
        try:
            peso = float(it.get("fuente_peso") or 1.0)
        except (TypeError, ValueError):
            peso = 1.0
        d = por_outlet.get(clave)
        if d is None:
            por_outlet[clave] = {
                "fuente_id": str(it.get("fuente_id") or ""),
                "fuente": str(it.get("fuente_nombre") or ""),
                "host": host,
                "peso": peso,
                "primer_visto": instante,
                "n_items": 1,
            }
            continue
        d["n_items"] += 1
        d["peso"] = max(d["peso"], peso)
        if instante and (not d["primer_visto"] or instante < d["primer_visto"]):
            d["primer_visto"] = instante
    # ISO canon UTC: el orden lexicográfico ES el cronológico. Sin timestamp -> al final.
    return sorted(
        por_outlet.values(), key=lambda d: (d["primer_visto"] or "9999", d["fuente"])
    )


def peso_corroboracion(detalle: list[dict[str, Any]]) -> float:
    """Masa de corroboración PONDERADA: Σ peso por outlet distinto (de `fuentes_detalle`)."""
    return round(sum(float(d.get("peso") or 1.0) for d in detalle), 3)


def peso_ventana_actual(
    detalle: list[dict[str, Any]],
    *,
    ventana_h: int = BREAKING_VENTANA_H_DEF,
    ahora: datetime | None = None,
) -> tuple[float, int]:
    """Masa ponderada de los outlets que SE SUMARON en la ventana actual. `(masa, n_outlets)`.

    Cuenta los outlets de `fuentes_detalle` cuyo `primer_visto` cae en las últimas
    `ventana_h` horas (anclado en `ahora`): es la señal de VELOCIDAD del ranking y la base
    del flag breaking. Como se computa desde el timeline PERSISTIDO, el re-score periódico
    la hace decaer sin releer items. Outlets sin timestamp no cuentan (no se inventa señal).
    """
    ref = ahora or datetime.now(UTC)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)
    desde = ref - timedelta(hours=max(1, int(ventana_h)))
    masa = 0.0
    n = 0
    for d in detalle:
        dt = _parse_iso(str(d.get("primer_visto") or ""))
        if dt is None or dt < desde:
            continue
        try:
            masa += float(d.get("peso") or 1.0)
        except (TypeError, ValueError):
            masa += 1.0
        n += 1
    return round(masa, 3), n


def _velocidad(masa_ventana: float, n_outlets_ventana: int) -> float:
    """Señal de VELOCIDAD [0,1]: masa ponderada que se sumó en la ventana actual.

    0 con menos de 2 outlets (una sola fuente no es corroboración rápida, por potente que
    sea); satura en `_VEL_SATURA` (= 2 fuentes potentes a la vez ⇒ 1.0). Decae sola: al
    envejecer la historia, los outlets salen de la ventana y la señal cae a 0.
    """
    if n_outlets_ventana < 2:
        return 0.0
    return min(1.0, masa_ventana / _VEL_SATURA)


def clasificar_verificacion(
    items: list[dict[str, Any]],
    *,
    fuentes_baja: frozenset[str] = frozenset(),
) -> str:
    """Verificación por CORROBORACIÓN de una historia (PURA). Devuelve uno de:

      - `corroborada`: >= 2 fuentes con dominios/outlets DISTINTOS (la misma noticia, confirmada
        por medios independientes).
      - `dudosa`: una sola fuente Y esa fuente es de baja confianza (agregador/foro), o hay señal
        de clickbait en los titulares (no fiable aunque haya enlace).
      - `unica_fuente`: una sola fuente fiable (sin corroborar todavía, pero no sospechosa).

    Distingue "outlets distintos" por host de url (cae a `fuente_id` si no hay url), para no
    contar dos enlaces del MISMO medio como corroboración.
    """
    if not items:
        return "unica_fuente"
    outlets: set[str] = set()
    for it in items:
        host = _host_de(str(it.get("url") or it.get("url_canonica") or "")).lower()
        clave = host or str(it.get("fuente_id") or "")
        if clave:
            outlets.add(clave)
    if len(outlets) >= 2:
        return "corroborada"
    # Una sola fuente: dudosa si es de baja confianza o hay clickbait; si no, única fuente.
    if any(_es_baja_confianza(it, fuentes_baja) for it in items) or _hay_clickbait(items):
        return "dudosa"
    return "unica_fuente"


def recalcular(
    cluster: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
    fuentes_baja_confianza: frozenset[str] = frozenset(),
    ahora: datetime | None = None,
) -> dict[str, Any]:
    """Recomputa los agregados de un cluster a partir de TODOS sus items. PURA.

    Devuelve un dict listo para `upsert` (sin `score`, que lo pone `puntuar`):
      - `n_items`, `n_fuentes` (fuente_id distintos = corroboración).
      - `idiomas` (lista ordenada de idiomas distintos presentes); `idioma` (el del item
        representativo: idioma "principal" de la historia, para decidir si traducir).
      - `senal` (máximo de las señales de los items: la viralidad de la fuente más fuerte).
      - `titulo`/`resumen` representativos (idioma es / mayor señal), `clave` del cluster,
        `categoria`/`geo`/`marca` (marca dominante).
      - `primer_visto`/`ultimo_visto` (min/máx instante de los items).
      - `fuentes_detalle`/`peso_fuentes`/`primera_fuente(_nombre)`: timeline de outlets y
        masa de corroboración PONDERADA por el peso editorial de cada fuente.
      - `breaking`: 1 si la masa ponderada de outlets que se sumaron en la ventana ACTUAL
        (`breaking_ventana_h` horas hasta `ahora`) alcanza `breaking_peso` (2 potentes, o
        1 potente + 1 normal, o 3 normales). Anclado en AHORA: decae solo al envejecer.
      - `velocidad`: la señal [0,1] de esa misma masa (la lee el scoring y la UI).
      - `verificacion`: corroborada / unica_fuente / dudosa (corroboración multi-outlet).
    Conserva `id`/`estado`/`contenido_id`/`creado` del cluster existente.
    """
    if not items:
        # Cluster sin items: deja los agregados a cero pero conserva identidad.
        return {
            **cluster,
            "n_items": 0,
            "n_fuentes": 0,
            "idiomas": [],
            "idioma": "",
            "senal": 0,
            "breaking": 0,
            "velocidad": 0.0,
            "verificacion": "unica_fuente",
            "fuentes_detalle": [],
            "peso_fuentes": 0.0,
            "primera_fuente": "",
            "primera_fuente_nombre": "",
        }

    rep = _representativo(items)
    fuentes = {str(it.get("fuente_id") or "") for it in items if str(it.get("fuente_id") or "")}
    idiomas = sorted({str(it.get("idioma") or "").lower() for it in items if it.get("idioma")})
    # Señal de viralidad: el máximo de los items NO curados (la señal de los curados es
    # artificial — SENAL_CURADO — y no debe saturar la viralidad de una historia mixta).
    # Si la historia es SOLO curada, conserva su señal alta (es el diseño del auto-feed).
    no_curados = [it for it in items if not _es_curado(it)]
    senal = max(int(it.get("senal") or 0) for it in (no_curados or items))

    instantes = sorted(i for i in (_instante_item(it) for it in items) if i)
    primer_visto = instantes[0] if instantes else (cluster.get("primer_visto") or "")
    ultimo_visto = instantes[-1] if instantes else (cluster.get("ultimo_visto") or "")

    # Timeline de outlets (quién abrió / quién se sumó) + masa de corroboración ponderada.
    # Se PERSISTEN en el cluster para que el re-score periódico (que repuntúa sin releer
    # items) pueda envejecer la señal de velocidad y la UI explique la corroboración.
    detalle_fuentes = fuentes_detalle(items)
    masa_ventana, n_ventana = peso_ventana_actual(
        detalle_fuentes, ventana_h=breaking_ventana_h, ahora=ahora
    )

    return {
        **cluster,
        "titulo": str(rep.get("titulo") or "")[:300],
        "resumen": str(rep.get("resumen") or "")[:2000],
        "marca": _marca_dominante(items),
        "categoria": str(rep.get("categoria") or ""),
        "geo": str(rep.get("geo") or ""),
        "clave": clave_cluster(rep),
        "n_items": len(items),
        "n_fuentes": len(fuentes),
        "idiomas": idiomas,
        "idioma": str(rep.get("idioma") or "").lower(),
        "senal": senal,
        "primer_visto": primer_visto,
        "ultimo_visto": ultimo_visto,
        "breaking": 1 if (n_ventana >= 2 and masa_ventana >= breaking_peso) else 0,
        "velocidad": round(_velocidad(masa_ventana, n_ventana), 3),
        "verificacion": clasificar_verificacion(items, fuentes_baja=fuentes_baja_confianza),
        "fuentes_detalle": detalle_fuentes,
        "peso_fuentes": peso_corroboracion(detalle_fuentes),
        "primera_fuente": detalle_fuentes[0]["fuente_id"] if detalle_fuentes else "",
        "primera_fuente_nombre": detalle_fuentes[0]["fuente"] if detalle_fuentes else "",
    }


# --------------------------------------------------------------------------- #
# Scoring                                                                        #
# --------------------------------------------------------------------------- #


def _log_norm(valor: int, satura: int) -> float:
    """Escala logarítmica [0,1]: 0 → 0, `satura` → 1.0 (alineada con `parrilla`)."""
    if valor <= 0:
        return 0.0
    return min(1.0, math.log10(max(1, valor)) / math.log10(max(10, satura)))


def _sin_acentos(texto: str) -> str:
    """Minúsculas sin acentos (delega en el helper de similitud)."""
    return similitud.sin_acentos((texto or "").lower())


# Saturación SUAVE de la señal de marca: ~3 coincidencias de vocabulario ≈ señal plena.
# Antes la señal era ESCALONADA (1 keyword puntuaba igual que 12) y SATURADA (un vocabulario
# genérico daba ~1.0 casi siempre); ahora el conteo gradúa y las frases casan por LÍMITE de
# palabra (no por subcadena).
_MARCA_SATURA_COINCIDENCIAS = 3.0
_PESO_MARCA_RESUMEN = 0.6


def _relevancia_marca(cluster: dict[str, Any], palabras_marca: frozenset[str]) -> float:
    """Relevancia GRADUADA de la historia para una marca [0,1] según sus palabras clave.

    Cuenta las coincidencias de vocabulario (las del TÍTULO a peso pleno; las del resumen a
    0.6) y satura suave: `min(1, n_ponderado / 3)`. 0.0 sin vocabulario o sin coincidencias.
    El texto se normaliza sin acentos para casar 'fútbol' con la keyword 'futbol'. Monótona:
    más coincidencias ⇒ más relevancia (hasta saturar).
    """
    return relevancia_marca_detalle(cluster, palabras_marca)[0]


def relevancia_marca_detalle(
    cluster: dict[str, Any], palabras_marca: frozenset[str]
) -> tuple[float, tuple[str, ...]]:
    """Relevancia de marca [0,1] MÁS las palabras del vocabulario que casaron (explicable).

    Misma graduación que `_relevancia_marca` (título a peso pleno, resumen a 0.6, saturación
    suave a 3 coincidencias). Las `palabras` devueltas son los términos del vocabulario
    presentes en título o resumen (orden alfabético, sin duplicar): son la EXPLICACIÓN de la
    señal de marca que la UI/el listón muestran al equipo. PURA y determinista.

    Historias EXTRANJERAS: el vocabulario es español, así que un titular en inglés solo casa
    los términos neutrales (nintendo, nfl…). Si la historia trae TRADUCCIÓN (`titulo_es` /
    `resumen_es`, Ola D), se evalúa ADEMÁS sobre ella: la relevancia no penaliza el idioma de
    origen. Un término que casa en ambos idiomas cuenta una sola vez por campo.
    """
    if not palabras_marca:
        return 0.0, ()
    titulo = _sin_acentos(
        " ".join(str(cluster.get(k) or "") for k in ("titulo", "titulo_es")).strip()
    )
    resumen = _sin_acentos(
        " ".join(str(cluster.get(k) or "") for k in ("resumen", "resumen_es")).strip()
    )
    en_titulo = _coincidencias(titulo, palabras_marca)
    en_resumen = _coincidencias(resumen, palabras_marca)
    n = len(en_titulo) + _PESO_MARCA_RESUMEN * len(en_resumen)
    if n <= 0:
        return 0.0, ()
    casadas = tuple(sorted(set(en_titulo) | set(en_resumen)))
    return min(1.0, n / _MARCA_SATURA_COINCIDENCIAS), casadas


def _coincidencias(texto: str, vocabulario: frozenset[str]) -> list[str]:
    """Entradas del vocabulario presentes en el texto normalizado (orden alfabético).

    Tokens sueltos casan por igualdad de token; FRASES por límite de palabra (regex), no por
    subcadena: 'liga mx' ya no se cuela dentro de otra palabra. La tokenización separa por
    NO-alfanuméricos (antes era `split()` y la puntuación pegada — "méxico:" — impedía casar
    el token "mexico" en titulares reales). Determinista.
    """
    if not texto or not vocabulario:
        return []
    tokens = set(re.findall(r"\w+", texto))
    casadas: list[str] = []
    for termino in sorted(vocabulario):
        if " " in termino:
            if re.search(rf"(?<!\w){re.escape(termino)}(?!\w)", texto):
                casadas.append(termino)
        elif termino in tokens:
            casadas.append(termino)
    return casadas


# Umbral por defecto para ASIGNAR marca por vocabulario a una historia sin marca dominante.
# Equivale a ≥1 keyword en el título (1/3 con la saturación suave); coincidencias solo de
# resumen (0.2) no bastan. Si ninguna marca lo alcanza, la historia queda sin marca (honesto).
UMBRAL_MARCA_VOCABULARIO = 0.3


def marca_por_vocabulario(
    cluster: dict[str, Any],
    vocabularios: dict[str, frozenset[str]],
    *,
    umbral: float = UMBRAL_MARCA_VOCABULARIO,
) -> str:
    """Mejor marca para una historia SIN marca dominante, por matching de vocabulario. PURA.

    Los clusters formados solo por items sin marca (Trends, agencias) quedaban con `marca=''`
    y eran INVISIBLES para la promoción por marca. Esto evalúa la relevancia del título/resumen
    contra el vocabulario de CADA marca y devuelve la mejor por encima de `umbral`; "" si
    ninguna pasa (se queda sin marca, como antes). Determinista: a empate gana la marca
    alfabéticamente menor.
    """
    mejor = ""
    mejor_s = 0.0
    for marca in sorted(vocabularios):
        s = _relevancia_marca(cluster, vocabularios.get(marca) or frozenset())
        if s >= umbral and s > mejor_s:
            mejor_s = s
            mejor = marca
    return mejor


def seleccionar_diversos(
    clusters: list[dict[str, Any]], *, maximo: int, umbral: float = 0.80
) -> list[dict[str, Any]]:
    """Top-N con DIVERSIDAD (MMR simple) sobre una lista YA ordenada por score. PURA.

    Recorre en orden y SALTA las historias cuyo título es muy parecido (ratio fuzzy ≥ `umbral`)
    a alguna ya elegida en esta pasada, para que un macro-tema no se coma todas las plazas.
    SUAVE: si al final faltan plazas, rellena con las saltadas en orden de score (nunca
    devuelve menos historias por diversificar). Títulos cortos no entran al fuzzy (no se
    penalizan entre sí). `umbral <= 0` desactiva (top-N puro).
    """
    if maximo <= 0:
        return []
    if umbral <= 0:
        return clusters[:maximo]
    elegidos: list[dict[str, Any]] = []
    saltados: list[dict[str, Any]] = []
    claves: list[str] = []
    for c in clusters:
        if len(elegidos) >= maximo:
            break
        kf = similitud.clave_fuzzy(str(c.get("titulo") or ""))
        parecido = len(kf) >= _MIN_LONGITUD_FUZZY and any(
            k and _ratio_claves(kf, k) >= umbral for k in claves
        )
        if parecido:
            saltados.append(c)
            continue
        elegidos.append(c)
        claves.append(kf)
    for c in saltados:
        if len(elegidos) >= maximo:
            break
        elegidos.append(c)
    return elegidos


def _frescura(ultimo_visto: str, *, ahora: datetime | None = None) -> float:
    """Frescura [0,1]: 1.0 si la historia es de ahora mismo, cae lineal a 0 en `_FRESCURA_VIDA_H`.

    Sin `ultimo_visto` parseable → 0.0 (sin señal de recencia, no se premia). `ahora`
    inyectable para tests deterministas.
    """
    dt = _parse_iso(ultimo_visto)
    if dt is None:
        return 0.0
    ref = ahora or datetime.now(UTC)
    horas = (ref - dt).total_seconds() / 3600.0
    if horas <= 0:
        return 1.0
    return max(0.0, 1.0 - horas / _FRESCURA_VIDA_H)


def puntuar(
    cluster: dict[str, Any],
    *,
    palabras_marca: frozenset[str] = frozenset(),
    ahora: datetime | None = None,
    pesos: PesosScore | None = None,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> tuple[float, str]:
    """Puntúa una historia para el ranking newsroom. Devuelve `(score, razon)`. PURA.

    Atajo de `puntuar_detalle` para los llamantes que no necesitan el desglose por señal.
    """
    score, razon, _desglose = puntuar_detalle(
        cluster, palabras_marca=palabras_marca, ahora=ahora, pesos=pesos,
        breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
    )
    return score, razon


def puntuar_detalle(
    cluster: dict[str, Any],
    *,
    palabras_marca: frozenset[str] = frozenset(),
    ahora: datetime | None = None,
    pesos: PesosScore | None = None,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> tuple[float, str, dict[str, Any]]:
    """Puntúa una historia y EXPLICA el porqué. Devuelve `(score, razon, desglose)`. PURA.

    FÓRMULA — score en [0, 1], combinación lineal ponderada de cinco señales independientes:

        W     = peso_fuentes (Σ peso editorial por outlet; potente 2.0 / normal 1.0 / baja 0.5;
                cae a n_fuentes si el cluster aún no trae timeline — pre-migración)
        score = 0.30 · corroboracion    (log(W)/log(8): 1 fuente→0; 2 potentes→0.67; satura 8)
              + 0.20 · velocidad        (masa que SE SUMÓ en la ventana actual / 4; 2 potentes
                                         a la vez = 1.0; DECAE sola al envejecer)
              + 0.20 · frescura         (recencia de `ultimo_visto`; lineal, 0 a las 72h)
              + 0.10 · viralidad        (`senal` agregada, escala log; satura a 1e6)
              + 0.20 · relevancia_marca (palabras de la marca en título/resumen; 0 sin marca)

    BREAKING emerge de aquí, no es un carril aparte: 2 fuentes potentes a la vez ⇒
    corroboración 0.67 + velocidad 1.0 + frescura ≈ 1 ⇒ ~0.6+, top del pool, y el flag
    `breaking` (masa en ventana ≥ `breaking_peso`) exime de maduración en el listón ⇒ sale
    al feed en el siguiente barrido. El bonus aditivo (`pesos.breaking`) queda en 0.0 por
    defecto (knob de rollback). Es MONÓTONA en cada señal (los tests lo verifican).

    `desglose` es la EXPLICACIÓN estructurada (se persiste junto al score, la lee la UI):
    cada señal CRUDA en [0,1] (`corroboracion`/`velocidad`/`frescura`/`viralidad`/`marca`/
    `rendimiento`), `peso_fuentes` (la masa W), `breaking` (0/1, computado EN VIVO: decae) y
    `palabras` (los términos del vocabulario que casaron). Señales crudas, no ponderadas: el
    desglose explica QUÉ tiene la historia; los pesos (editables en caliente) cuánto cuenta.
    """
    p = pesos or _PESOS_DEF
    n_fuentes = int(cluster.get("n_fuentes") or 0)
    senal = int(cluster.get("senal") or 0)

    # Corroboración PONDERADA por el peso editorial de cada outlet. Fallback honesto para
    # clusters sin timeline (pre-migración / stubs): la masa es el conteo de fuentes.
    try:
        masa = float(cluster.get("peso_fuentes") or 0.0)
    except (TypeError, ValueError):
        masa = 0.0
    if masa <= 0.0:
        masa = float(n_fuentes)
    s_corro = 0.0
    if masa > 1.0:
        s_corro = min(1.0, math.log(masa) / math.log(_PESO_SATURA))

    # Velocidad + breaking EN VIVO desde el timeline persistido (decaen con el reloj). Sin
    # timeline no se inventa señal: velocidad 0 y el flag persistido se respeta tal cual.
    detalle = cluster.get("fuentes_detalle") or []
    if isinstance(detalle, list) and detalle:
        masa_ventana, n_ventana = peso_ventana_actual(
            detalle, ventana_h=breaking_ventana_h, ahora=ahora
        )
        s_vel = _velocidad(masa_ventana, n_ventana)
        es_breaking = n_ventana >= 2 and masa_ventana >= breaking_peso
    else:
        s_vel = min(1.0, max(0.0, float(cluster.get("velocidad") or 0.0)))
        es_breaking = bool(int(cluster.get("breaking") or 0))

    s_fresca = _frescura(str(cluster.get("ultimo_visto") or ""), ahora=ahora)
    s_viral = _log_norm(senal, _SENAL_SATURA)
    s_marca, palabras_casadas = relevancia_marca_detalle(cluster, palabras_marca)
    # Señal de RENDIMIENTO (Fase 2c): 0..1 que el daemon precalcula (1 si la historia cae en una
    # línea top por engagement). INERTE salvo que `pesos.rendimiento` > 0. Acota a [0,1] por defensa.
    s_rend = min(1.0, max(0.0, float(cluster.get("bonus_rendimiento") or 0.0)))

    score = (
        p.corroboracion * s_corro
        + p.velocidad * s_vel
        + p.frescura * s_fresca
        + p.viralidad * s_viral
        + p.marca * s_marca
        + p.rendimiento * s_rend
    )
    if es_breaking and p.breaking:
        score = min(1.0, score + p.breaking)
    score = min(1.0, score)

    razones: list[str] = []
    if es_breaking:
        razones.append("última hora: varias fuentes casi a la vez")
    if n_fuentes > 1:
        potentes = sum(
            1 for d in detalle if isinstance(d, dict) and float(d.get("peso") or 1.0) >= 1.5
        ) if isinstance(detalle, list) else 0
        if potentes:
            razones.append(f"{n_fuentes} fuentes ({potentes} potente{'s' if potentes > 1 else ''})")
        else:
            razones.append(f"{n_fuentes} fuentes")
    if s_fresca >= 0.5:
        razones.append("reciente")
    if senal > 0:
        razones.append(f"señal {senal}")
    if s_marca > 0:
        # Las palabras casadas EXPLICAN la relevancia (qué del vocabulario de la marca casó).
        muestra = ", ".join(palabras_casadas[:4])
        razones.append(f"relevante para la marca ({muestra})" if muestra else "relevante para la marca")
    razon = " · ".join(razones) if razones else "historia única"
    desglose: dict[str, Any] = {
        "corroboracion": round(s_corro, 3),
        "velocidad": round(s_vel, 3),
        "frescura": round(s_fresca, 3),
        "viralidad": round(s_viral, 3),
        "marca": round(s_marca, 3),
        "rendimiento": round(s_rend, 3),
        "peso_fuentes": round(masa, 3),
        "breaking": 1 if es_breaking else 0,
        "palabras": list(palabras_casadas),
    }
    return round(score, 6), razon, desglose


# --------------------------------------------------------------------------- #
# Listón de promoción (auto-producción)                                         #
# --------------------------------------------------------------------------- #

# El score que LISTA el panel y el listón que DISPARA producción automática son dos niveles
# distintos a propósito: el panel muestra el pool jerarquizado (todo lo que pasó la entrada),
# pero encolar QA+copy (`claude -p`, coste real de tokens) exige un listón MÁS ALTO y
# EXPLICABLE. Defaults conservadores; editables en caliente desde la consola.
LISTON_MIN_SCORE_DEF = 0.35
LISTON_MIN_MARCA_DEF = 0.2


def evaluar_liston(
    cluster: dict[str, Any],
    *,
    palabras_marca: frozenset[str] = frozenset(),
    min_score: float = LISTON_MIN_SCORE_DEF,
    min_marca: float = LISTON_MIN_MARCA_DEF,
    min_maduracion_min: int = 0,
    ahora: datetime | None = None,
    breaking_peso: float = BREAKING_PESO_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> tuple[bool, str]:
    """¿Esta historia supera el LISTÓN de producción automática? `(supera, motivo)`. PURA.

    Reglas, en orden (el motivo explica la PRIMERA que falla):
      1. VERIFICACIÓN: una historia `dudosa` (única fuente de baja confianza / clickbait)
         jamás dispara producción automática, puntúe lo que puntúe.
      2. MADURACIÓN: la historia debe llevar al menos `min_maduracion_min` minutos en el
         pool (desde `primer_visto`) antes de competir por plaza. Promover al primer
         avistamiento elige con UNA fuente y señal a medio acumular; esperar deja que la
         corroboración/viralidad separen lo grande del ruido y la selección compare
         historias maduras entre sí. Exentas: CURADAS por el equipo y BREAKING
         corroboradas (la urgencia real no espera). `0` desactiva la regla; sin
         `primer_visto` parseable no se retiene (no se castiga un dato ausente).
      3. SCORE: el score RECALCULADO AHORA (no el persistido, que envejece entre re-scores)
         debe alcanzar `min_score`.
      4. ENCAJE DE MARCA: la relevancia por vocabulario debe alcanzar `min_marca`. Exentas:
         las historias CURADAS por el equipo (señal artificial de cajón: el humano ya decidió)
         y las BREAKING CORROBORADAS (evento mayor confirmado por varias fuentes a la vez,
         cuyo vocabulario puede ser nuevo).
    Devuelve siempre un motivo legible (también al superar): es la explicación que se muestra.
    """
    from .ingesta import SENAL_CURADO

    if (cluster.get("verificacion") or "") == "dudosa":
        return False, "verificación dudosa (única fuente no fiable o clickbait)"
    curada = int(cluster.get("senal") or 0) >= SENAL_CURADO
    # Breaking EN VIVO si hay timeline (misma derivación que el scoring: masa ponderada en la
    # ventana actual, decae sola); sin timeline se respeta el flag persistido. Así el listón
    # no depende de un flag desfasado entre re-scores.
    detalle_liston = cluster.get("fuentes_detalle") or []
    if isinstance(detalle_liston, list) and detalle_liston:
        masa_v, n_v = peso_ventana_actual(
            detalle_liston, ventana_h=breaking_ventana_h, ahora=ahora
        )
        es_breaking_vivo = n_v >= 2 and masa_v >= breaking_peso
    else:
        es_breaking_vivo = bool(int(cluster.get("breaking") or 0))
    breaking_corroborada = es_breaking_vivo and (
        (cluster.get("verificacion") or "") == "corroborada"
    )
    if min_maduracion_min > 0 and not curada and not breaking_corroborada:
        visto = _parse_iso(str(cluster.get("primer_visto") or ""))
        if visto is not None:
            momento = ahora or datetime.now(UTC)
            if momento.tzinfo is None:
                momento = momento.replace(tzinfo=UTC)
            edad_min = (momento - visto).total_seconds() / 60.0
            if edad_min < min_maduracion_min:
                return False, (
                    f"madurando ({edad_min:.0f} de {min_maduracion_min} min en el pool): "
                    "se promueve cuando la corroboración haya tenido tiempo de acumularse"
                )
    score, _razon, desglose = puntuar_detalle(
        cluster, palabras_marca=palabras_marca, ahora=ahora,
        breaking_peso=breaking_peso, breaking_ventana_h=breaking_ventana_h,
    )
    if score < min_score:
        return False, f"score {score:.2f} < {min_score:.2f} (listón de producción)"
    s_marca = float(desglose["marca"])
    if s_marca < min_marca:
        if not curada and not breaking_corroborada:
            return False, (
                f"encaje con la marca {s_marca:.2f} < {min_marca:.2f} "
                "(no casa el vocabulario de la marca)"
            )
    palabras = ", ".join(desglose["palabras"][:4])
    detalle = f" — casa: {palabras}" if palabras else ""
    return True, f"score {score:.2f} ≥ {min_score:.2f}{detalle}"
