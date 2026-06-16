"""Recálculo de agregados de un cluster y verificación por CORROBORACIÓN (Ola D). PURA.

Timeline de outlets (quién abrió / quién se sumó), masa de corroboración ponderada,
señal de velocidad/breaking en ventana, clasificación corroborada/única/dudosa, y el
`recalcular` que recompone los agregados de un cluster a partir de sus items.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .. import dedup
from ._comun import (
    BREAKING_PESO_DEF,
    BREAKING_VENTANA_H_DEF,
    _parse_iso,
    _sin_acentos,
)
from .asignacion import clave_cluster

# Normalizador de la señal de velocidad (ver `_velocidad`).
_VEL_SATURA = 4.0  # masa en la ventana actual que satura la velocidad (= 2 potentes a la vez)


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
    Conserva `id`/`estado`/`publicacion_id`/`creado` del cluster existente.
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
