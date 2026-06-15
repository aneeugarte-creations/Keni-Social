"""Peso editorial de las FUENTES de noticias — módulo PURO de dominio.

El ranking de historias pondera la corroboración por la POTENCIA de cada fuente: que una
nota salga en Reuters y BBC no vale lo mismo que salir en dos agregadores. El peso es un
número (no un enum) para que la fórmula lo sume directo; el `tier` (potente/normal/baja)
es la ETIQUETA derivada que ve el equipo en la UI y se puede editar fuente a fuente.

Anclas de peso (el rango editable va de PESO_MIN a PESO_MAX):
  - PESO_POTENTE (2.0): agencias y cabeceras de primer nivel (Reuters, AP, BBC, NYT…).
  - PESO_NORMAL  (1.0): cualquier fuente sin señal especial (el default del esquema).
  - PESO_BAJO    (0.5): fuentes de baja confiabilidad (coherente con la verificación
    `dudosa` de clustering, que ya castiga aparte).

`PESOS_HOST_INICIAL` es el seed por HOST: al crear una fuente (o backfillear las
existentes) se le asigna el peso de su host si está en la lista; el equipo puede
corregirlo después desde la UI de Fuentes. Lista corta y editable a propósito: solo
cabeceras donde la potencia es indiscutible.
"""

from __future__ import annotations

from . import dedup

# Anclas de peso. El esquema (`fuentes_rss.peso`) nace en 1.0.
PESO_POTENTE = 2.0
PESO_NORMAL = 1.0
PESO_BAJO = 0.5

# Rango admisible al editar (la API clampa): evita pesos absurdos que rompan el ranking.
PESO_MIN = 0.1
PESO_MAX = 3.0

# Umbrales del tier derivado: >=1.5 potente, <=0.6 baja, resto normal.
_UMBRAL_POTENTE = 1.5
_UMBRAL_BAJO = 0.6

# Seed de peso por HOST (sin esquema ni `www.`; casa también subdominios). Solo cabeceras
# de potencia indiscutible: agencias globales + primer nivel internacional/nacional MX.
PESOS_HOST_INICIAL: dict[str, float] = {
    # Agencias globales.
    "reuters.com": PESO_POTENTE,
    "apnews.com": PESO_POTENTE,
    "afp.com": PESO_POTENTE,
    "efe.com": PESO_POTENTE,
    # Primer nivel internacional.
    "bbc.com": PESO_POTENTE,
    "bbc.co.uk": PESO_POTENTE,
    "nytimes.com": PESO_POTENTE,
    "theguardian.com": PESO_POTENTE,
    "washingtonpost.com": PESO_POTENTE,
    "cnn.com": PESO_POTENTE,
    "elpais.com": PESO_POTENTE,
    "ft.com": PESO_POTENTE,
    "bloomberg.com": PESO_POTENTE,
    "wsj.com": PESO_POTENTE,
    "aljazeera.com": PESO_POTENTE,
    "dw.com": PESO_POTENTE,
    # Primer nivel deportivo.
    "espn.com": PESO_POTENTE,
    "skysports.com": PESO_POTENTE,
}


def tier_de_peso(peso: float) -> str:
    """Etiqueta editorial del peso: 'potente' (>=1.5), 'baja' (<=0.6) o 'normal'."""
    try:
        p = float(peso)
    except (TypeError, ValueError):
        return "normal"
    if p >= _UMBRAL_POTENTE:
        return "potente"
    if p <= _UMBRAL_BAJO:
        return "baja"
    return "normal"


def normalizar_peso(valor: float) -> float:
    """Peso clampado al rango admisible [PESO_MIN, PESO_MAX]; 1.0 si no es numérico."""
    try:
        p = float(valor)
    except (TypeError, ValueError):
        return PESO_NORMAL
    return max(PESO_MIN, min(PESO_MAX, p))


def _host_de_url(url: str) -> str:
    """Host (sin esquema/`www.`) de una URL http(s); '' si no es válida."""
    canonica = dedup.url_canonica(url or "")
    if not canonica:
        return ""
    return canonica.split("/", 1)[0].split(":", 1)[0]


def peso_de_url(url: str) -> float:
    """Peso inicial por el HOST de la url ('' o desconocido -> PESO_NORMAL).

    Casa el host exacto o cualquier subdominio (`feeds.reuters.com` -> reuters.com).
    """
    host = _host_de_url(url)
    if not host:
        return PESO_NORMAL
    for inicial, peso in PESOS_HOST_INICIAL.items():
        if host == inicial or host.endswith("." + inicial):
            return peso
    return PESO_NORMAL
