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
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from .. import radar
from . import dedup

# Longitud mínima de una clave normalizada para entrar al fuzzy. Títulos muy cortos
# ("nfl", "f1") disparan ratios altos espurios entre sí: solo casan por url exacta.
_MIN_LONGITUD_FUZZY = 8

# Umbral de scoring "breaking" por defecto si no se inyecta otro (lo fija el daemon vía
# config). Una historia es "breaking" si junta >= N fuentes distintas en < M horas.
BREAKING_FUENTES_DEF = 3
BREAKING_VENTANA_H_DEF = 6

# Pesos del score (ver `puntuar`). Suman 1.0: el score vive en [0, 1] y es comparable
# entre marcas/categorías para el ranking.
_PESO_CORROBORACION = 0.35
_PESO_FRESCURA = 0.25
_PESO_VIRALIDAD = 0.20
_PESO_MARCA = 0.20

# Normalizadores de cada señal (ver fórmula).
_FUENTES_SATURA = 6  # 6+ fuentes distintas saturan la corroboración a 1.0
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


def _ratio_titulos(a: str, b: str) -> float:
    """Ratio fuzzy [0,1] entre dos títulos usando la clave normalizada + sinónimos del Radar.

    Reutiliza `radar._clave_fuzzy` (minúsculas, sin acentos, sin signos, sinónimos del dominio
    colapsados a su forma canónica) antes de comparar con `SequenceMatcher`. Claves cortas
    devuelven 0.0 (no entran al fuzzy): evita falsos positivos entre títulos triviales.
    """
    ka = radar._clave_fuzzy(a)
    kb = radar._clave_fuzzy(b)
    if len(ka) < _MIN_LONGITUD_FUZZY or len(kb) < _MIN_LONGITUD_FUZZY:
        return 0.0
    return SequenceMatcher(None, ka, kb).ratio()


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

    # (b) Fuzzy del título contra el título representativo de cada cluster.
    titulo = str(item.get("titulo") or "")
    if not titulo.strip():
        return None
    mejor_id: str | None = None
    mejor_ratio = umbral
    for c in clusters_recientes:
        ratio = _ratio_titulos(titulo, str(c.get("titulo") or ""))
        if ratio >= mejor_ratio:
            mejor_ratio = ratio
            mejor_id = str(c["id"])
    return mejor_id


# --------------------------------------------------------------------------- #
# Recálculo de los agregados de un cluster                                      #
# --------------------------------------------------------------------------- #


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def _representativo(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Item representativo: prefiere idioma 'es', luego mayor señal, luego título más largo.

    El título/resumen de la historia salen de aquí (el más informativo en el idioma del
    piloto). Determinista para los mismos items.
    """
    def llave(it: dict[str, Any]) -> tuple[int, int, int]:
        es = 1 if str(it.get("idioma") or "").lower().startswith("es") else 0
        return (es, int(it.get("senal") or 0), len(str(it.get("titulo") or "")))

    return max(items, key=llave)


def recalcular(
    cluster: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    breaking_fuentes: int = BREAKING_FUENTES_DEF,
    breaking_ventana_h: int = BREAKING_VENTANA_H_DEF,
) -> dict[str, Any]:
    """Recomputa los agregados de un cluster a partir de TODOS sus items. PURA.

    Devuelve un dict listo para `upsert` (sin `score`, que lo pone `puntuar`):
      - `n_items`, `n_fuentes` (fuente_id distintos = corroboración).
      - `idiomas` (lista ordenada de idiomas distintos presentes).
      - `senal` (máximo de las señales de los items: la viralidad de la fuente más fuerte).
      - `titulo`/`resumen` representativos (idioma es / mayor señal), `clave` del cluster,
        `categoria`/`geo`/`marca` (marca dominante).
      - `primer_visto`/`ultimo_visto` (min/máx instante de los items).
      - `breaking`: 1 si junta >= `breaking_fuentes` fuentes distintas dentro de una ventana
        de `breaking_ventana_h` horas (aceleración real, no goteo lento).
    Conserva `id`/`estado`/`contenido_id`/`creado` del cluster existente.
    """
    if not items:
        # Cluster sin items: deja los agregados a cero pero conserva identidad.
        return {
            **cluster,
            "n_items": 0,
            "n_fuentes": 0,
            "idiomas": [],
            "senal": 0,
            "breaking": 0,
        }

    rep = _representativo(items)
    fuentes = {str(it.get("fuente_id") or "") for it in items if str(it.get("fuente_id") or "")}
    idiomas = sorted({str(it.get("idioma") or "").lower() for it in items if it.get("idioma")})
    senal = max(int(it.get("senal") or 0) for it in items)

    instantes = sorted(i for i in (_instante_item(it) for it in items) if i)
    primer_visto = instantes[0] if instantes else (cluster.get("primer_visto") or "")
    ultimo_visto = instantes[-1] if instantes else (cluster.get("ultimo_visto") or "")

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
        "senal": senal,
        "primer_visto": primer_visto,
        "ultimo_visto": ultimo_visto,
        "breaking": 1 if _es_breaking(
            items, fuentes_min=breaking_fuentes, ventana_h=breaking_ventana_h
        ) else 0,
    }


def _es_breaking(
    items: list[dict[str, Any]], *, fuentes_min: int, ventana_h: int
) -> bool:
    """True si >= `fuentes_min` fuentes DISTINTAS cubren la historia en < `ventana_h` horas.

    Heurística de aceleración: una historia que muchas fuentes recogen casi a la vez es
    "breaking", distinta de una que acumula fuentes a lo largo de días. Mira los instantes de
    los items (publicado/capturado) por fuente y busca una ventana deslizante de `ventana_h`
    que contenga >= `fuentes_min` fuentes distintas. Si faltan timestamps, no marca breaking.
    """
    if fuentes_min <= 1:
        return False
    eventos: list[tuple[datetime, str]] = []
    for it in items:
        dt = _parse_iso(_instante_item(it))
        fid = str(it.get("fuente_id") or "")
        if dt is not None and fid:
            eventos.append((dt, fid))
    if len({fid for _, fid in eventos}) < fuentes_min:
        return False
    eventos.sort(key=lambda e: e[0])
    ventana = timedelta(hours=max(1, ventana_h))
    # Ventana deslizante: por cada inicio, cuenta fuentes distintas dentro de [t, t+ventana].
    for i, (t0, _) in enumerate(eventos):
        distintas = {
            fid for dt, fid in eventos[i:] if dt - t0 <= ventana
        }
        if len(distintas) >= fuentes_min:
            return True
    return False


# --------------------------------------------------------------------------- #
# Scoring                                                                        #
# --------------------------------------------------------------------------- #


def _log_norm(valor: int, satura: int) -> float:
    """Escala logarítmica [0,1]: 0 → 0, `satura` → 1.0 (alineada con `parrilla`)."""
    if valor <= 0:
        return 0.0
    return min(1.0, math.log10(max(1, valor)) / math.log10(max(10, satura)))


def _sin_acentos(texto: str) -> str:
    """Minúsculas sin acentos (delega en el helper del Radar)."""
    return radar._sin_acentos((texto or "").lower())


def _relevancia_marca(cluster: dict[str, Any], palabras_marca: frozenset[str]) -> float:
    """Relevancia de la historia para una marca [0,1] según sus palabras clave.

    1.0 si una palabra de la marca está en el TÍTULO; 0.6 si está en el resumen; 0.0 si no o
    si no hay vocabulario. Mismo criterio que `parrilla._score_marca`, sobre el texto del
    cluster. El texto se normaliza sin acentos para casar 'fútbol' con la keyword 'futbol'.
    """
    if not palabras_marca:
        return 0.0
    titulo = _sin_acentos(str(cluster.get("titulo") or ""))
    if _contiene(titulo, palabras_marca):
        return 1.0
    resumen = _sin_acentos(str(cluster.get("resumen") or ""))
    if _contiene(resumen, palabras_marca):
        return 0.6
    return 0.0


def _contiene(texto: str, vocabulario: frozenset[str]) -> bool:
    """True si alguna entrada del vocabulario (token o frase) está en el texto normalizado."""
    if not texto:
        return False
    tokens = set(texto.split())
    for termino in vocabulario:
        if " " in termino:
            if termino in texto:
                return True
        elif termino in tokens:
            return True
    return False


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
) -> tuple[float, str]:
    """Puntúa una historia para el ranking newsroom. Devuelve `(score, razon)`. PURA.

    FÓRMULA — score en [0, 1], combinación lineal ponderada de cuatro señales independientes:

        score = 0.35 · corroboracion   (n_fuentes distintas, escala log; satura a 6 fuentes)
              + 0.25 · frescura         (recencia de `ultimo_visto`; lineal, 0 a las 72h)
              + 0.20 · viralidad        (`senal` agregada, escala log; satura a 1e6)
              + 0.20 · relevancia_marca (palabras de la marca en título/resumen; 0 sin marca)
        +breaking → score = min(1.0, score + 0.10)  (empujón si es breaking)

    Diseño: la CORROBORACIÓN pesa más (newsroom-grade: una historia que muchas fuentes
    distintas confirman es más fiable y noticiable que un único artículo viral). La frescura
    evita que historias viejas dominen. La viralidad y la marca inclinan el ranking. Es
    MONÓTONA en cada señal: a igualdad de lo demás, más fuentes / más fresca / más señal /
    más relevante ⇒ score mayor (los tests lo verifican). `razon` resume las señales activas.
    """
    n_fuentes = int(cluster.get("n_fuentes") or 0)
    senal = int(cluster.get("senal") or 0)
    s_corro = _log_norm(n_fuentes, _FUENTES_SATURA)
    s_fresca = _frescura(str(cluster.get("ultimo_visto") or ""), ahora=ahora)
    s_viral = _log_norm(senal, _SENAL_SATURA)
    s_marca = _relevancia_marca(cluster, palabras_marca)

    score = (
        _PESO_CORROBORACION * s_corro
        + _PESO_FRESCURA * s_fresca
        + _PESO_VIRALIDAD * s_viral
        + _PESO_MARCA * s_marca
    )
    if int(cluster.get("breaking") or 0):
        score = min(1.0, score + 0.10)

    razones: list[str] = []
    if n_fuentes > 1:
        razones.append(f"{n_fuentes} fuentes")
    if s_fresca >= 0.5:
        razones.append("reciente")
    if senal > 0:
        razones.append(f"señal {senal}")
    if s_marca > 0:
        razones.append("relevante para la marca")
    if int(cluster.get("breaking") or 0):
        razones.append("breaking")
    razon = " · ".join(razones) if razones else "historia única"
    return round(score, 6), razon
