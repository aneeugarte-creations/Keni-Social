"""Catálogo estático de fuentes RSS de confianza, listo para activar con un clic.

Módulo PURO de datos (sin red, sin BD). Ofrece dos funciones de consulta:
  - `listar_presets(categoria=None)` -> lista de dicts de preset.
  - `categorias()` -> lista de strings con las categorías disponibles.

Cada preset tiene los campos del contrato (04-fuentes-externas.md):
  id, nombre, url, categoria, marca_sugerida, linea_sugerida, idioma, region,
  descripcion.

Las plantillas (Google News, Reddit, GDELT, YouTube) se incluyen tal cual: el equipo
copiará y ajustará la URL antes de activarlas. Se documentan con `{variable}` en el
campo `descripcion` para que la UI las pueda distinguir y mostrar un aviso.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- #
# Catálogo curado                                                               #
# --------------------------------------------------------------------------- #

_PRESETS: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ MX --
    {
        "id": "reforma-mx",
        "nombre": "Reforma — México",
        "url": "https://www.reforma.com/rss/portada.xml",
        "categoria": "mx",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Noticias México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Feed principal de Reforma, diario mexicano de referencia.",
    },
    {
        "id": "eluniversal-mx",
        "nombre": "El Universal — México",
        "url": "https://www.eluniversal.com.mx/rss.xml",
        "categoria": "mx",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Noticias México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Feed principal de El Universal, uno de los diarios más leídos de México.",
    },
    {
        "id": "milenio-mx",
        "nombre": "Milenio — México",
        "url": "https://www.milenio.com/rss",
        "categoria": "mx",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Noticias México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Feed de Milenio, diario nacional mexicano.",
    },
    {
        "id": "animalpolitico-mx",
        "nombre": "Animal Político — México",
        "url": "https://www.animalpolitico.com/feed",
        "categoria": "mx",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Política México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Periodismo de datos e investigación en México.",
    },
    {
        "id": "infobae-mx",
        "nombre": "Infobae — México",
        "url": "https://www.infobae.com/feeds/rss/noticias/mexico/",
        "categoria": "mx",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Noticias México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Sección México de Infobae.",
    },
    # -------------------------------------------------------- Internacional --
    {
        "id": "reuters-world",
        "nombre": "Reuters — World News",
        "url": "https://feeds.reuters.com/reuters/worldNews",
        "categoria": "internacional",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Internacional",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Feed de noticias mundiales de Reuters (inglés).",
    },
    {
        "id": "ap-top-news",
        "nombre": "AP — Top News",
        "url": "https://feeds.apnews.com/apnews/topnews",
        "categoria": "internacional",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Internacional",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Titulares principales de Associated Press (inglés).",
    },
    {
        "id": "bbc-world",
        "nombre": "BBC — World",
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "categoria": "internacional",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Internacional",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Noticias mundiales de BBC News (inglés).",
    },
    {
        "id": "elpais-internacional",
        "nombre": "El País — Internacional",
        "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada",
        "categoria": "internacional",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Internacional",
        "idioma": "es",
        "region": "ES",
        "descripcion": "Sección Internacional de El País (español).",
    },
    {
        "id": "dw-espanol",
        "nombre": "DW — Español",
        "url": "https://rss.dw.com/rdf/rss-es-all",
        "categoria": "internacional",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Internacional",
        "idioma": "es",
        "region": "GLOBAL",
        "descripcion": "Deutsche Welle en español, cobertura mundial.",
    },
    {
        "id": "lemonde-fr",
        "nombre": "Le Monde — Internacional",
        "url": "https://www.lemonde.fr/international/rss_full.xml",
        "categoria": "internacional",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Internacional",
        "idioma": "fr",
        "region": "GLOBAL",
        "descripcion": "Sección internacional de Le Monde (francés).",
    },
    {
        "id": "gnews-mx-portada",
        "nombre": "Google News — Portada MX",
        "url": "https://news.google.com/rss?hl=es-419&gl=MX&ceid=MX:es-419",
        "categoria": "internacional",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Noticias México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Portada de Google News edición México.",
    },
    {
        "id": "gnews-plantilla",
        "nombre": "Google News — Búsqueda por tema [PLANTILLA]",
        "url": "https://news.google.com/rss/search?q=TEMA&hl=es-419&gl=MX&ceid=MX:es-419",
        "categoria": "internacional",
        "marca_sugerida": "unotv",
        "linea_sugerida": "",
        "idioma": "es",
        "region": "MX",
        "descripcion": (
            "Plantilla: sustituye TEMA por tu búsqueda antes de activar. "
            "Ejemplo: ?q=Liga+MX&hl=es-419&gl=MX&ceid=MX:es-419"
        ),
    },
    # --------------------------------------------------------------- Deportes --
    {
        "id": "espn-deportes",
        "nombre": "ESPN — Deportes",
        "url": "https://www.espn.com/espn/rss/news",
        "categoria": "deportes",
        "marca_sugerida": "claro-sports",
        "linea_sugerida": "Deportes",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Feed de noticias deportivas de ESPN (inglés).",
    },
    {
        "id": "marca-espana",
        "nombre": "Marca — Portada",
        "url": "https://e00-marca.uecdn.es/rss/portada.xml",
        "categoria": "deportes",
        "marca_sugerida": "claro-sports",
        "linea_sugerida": "Deportes",
        "idioma": "es",
        "region": "ES",
        "descripcion": "Portada del diario Marca (fútbol y deportes, español).",
    },
    {
        "id": "as-deportes",
        "nombre": "AS — Portada",
        "url": "https://as.com/rss/tags/ultimas_noticias.xml",
        "categoria": "deportes",
        "marca_sugerida": "claro-sports",
        "linea_sugerida": "Deportes",
        "idioma": "es",
        "region": "ES",
        "descripcion": "Últimas noticias del diario AS (fútbol y deportes, español).",
    },
    {
        "id": "record-mx",
        "nombre": "Récord — México",
        "url": "https://www.record.com.mx/rss",
        "categoria": "deportes",
        "marca_sugerida": "claro-sports",
        "linea_sugerida": "Deportes México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Diario deportivo mexicano Récord.",
    },
    {
        "id": "fifa-news",
        "nombre": "FIFA — Noticias",
        "url": "https://www.fifa.com/index/rss/news.rss",
        "categoria": "deportes",
        "marca_sugerida": "claro-sports",
        "linea_sugerida": "Fútbol Internacional",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Noticias oficiales de FIFA (inglés).",
    },
    {
        "id": "reddit-soccer",
        "nombre": "Reddit — r/soccer top del día",
        "url": "https://www.reddit.com/r/soccer/top/.rss?t=day",
        "categoria": "deportes",
        "marca_sugerida": "claro-sports",
        "linea_sugerida": "Fútbol Internacional",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Posts top del día en r/soccer (inglés). Señal de viralidad en redes.",
    },
    {
        "id": "reddit-ligamx",
        "nombre": "Reddit — r/LigaMX top del día",
        "url": "https://www.reddit.com/r/LigaMX/top/.rss?t=day",
        "categoria": "deportes",
        "marca_sugerida": "claro-sports",
        "linea_sugerida": "Liga MX",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Posts top del día en r/LigaMX.",
    },
    # --------------------------------------------------------- Ciencia / Tech --
    {
        "id": "nasa-news",
        "nombre": "NASA — Breaking News",
        "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "categoria": "ciencia-tech",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Ciencia y Tecnología",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Noticias de última hora de NASA (inglés).",
    },
    {
        "id": "mit-tech-review",
        "nombre": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "categoria": "ciencia-tech",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Ciencia y Tecnología",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Tecnología e innovación del MIT (inglés).",
    },
    {
        "id": "xataka-es",
        "nombre": "Xataka — Portada",
        "url": "https://feeds.weblogssl.com/xataka2",
        "categoria": "ciencia-tech",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Ciencia y Tecnología",
        "idioma": "es",
        "region": "ES",
        "descripcion": "Tecnología y gadgets de Xataka (español).",
    },
    {
        "id": "xataka-mx",
        "nombre": "Xataka México",
        "url": "https://feeds.weblogssl.com/xatakamexico",
        "categoria": "ciencia-tech",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Ciencia y Tecnología",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Tecnología con enfoque México de Xataka.",
    },
    {
        "id": "gdelt-ciencia",
        "nombre": "GDELT — Ciencia/Tecnología [PLANTILLA]",
        "url": (
            "https://api.gdeltproject.org/api/v2/doc/doc"
            "?query=science+technology&format=rss&sort=datedesc"
        ),
        "categoria": "ciencia-tech",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Ciencia y Tecnología",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": (
            "Plantilla GDELT por tema. Ajusta el parámetro `query` antes de activar. "
            "Fuente mundial multi-idioma, cobertura de medios en tiempo real."
        ),
    },
    # --------------------------------------------------------------- Gaming --
    {
        "id": "ign-latam",
        "nombre": "IGN — Latinoamérica",
        "url": "https://es.ign.com/rss/articles",
        "categoria": "gaming",
        "marca_sugerida": "nacion-gamer",
        "linea_sugerida": "Gaming",
        "idioma": "es",
        "region": "LATAM",
        "descripcion": "Noticias de videojuegos de IGN Latinoamérica (español).",
    },
    {
        "id": "ign-en",
        "nombre": "IGN — English",
        "url": "https://feeds.ign.com/ign/all",
        "categoria": "gaming",
        "marca_sugerida": "nacion-gamer",
        "linea_sugerida": "Gaming",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Noticias de videojuegos de IGN en inglés (señal global).",
    },
    {
        "id": "polygon",
        "nombre": "Polygon — Gaming",
        "url": "https://www.polygon.com/rss/index.xml",
        "categoria": "gaming",
        "marca_sugerida": "nacion-gamer",
        "linea_sugerida": "Gaming",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Noticias y análisis de videojuegos de Polygon (inglés).",
    },
    {
        "id": "eurogamer-es",
        "nombre": "Eurogamer — Español",
        "url": "https://www.eurogamer.es/?format=rss",
        "categoria": "gaming",
        "marca_sugerida": "nacion-gamer",
        "linea_sugerida": "Gaming",
        "idioma": "es",
        "region": "ES",
        "descripcion": "Videojuegos de Eurogamer en español.",
    },
    {
        "id": "reddit-gaming",
        "nombre": "Reddit — r/gaming top del día",
        "url": "https://www.reddit.com/r/gaming/top/.rss?t=day",
        "categoria": "gaming",
        "marca_sugerida": "nacion-gamer",
        "linea_sugerida": "Gaming",
        "idioma": "en",
        "region": "GLOBAL",
        "descripcion": "Posts top del día en r/gaming. Señal de viralidad.",
    },
    {
        "id": "reddit-mexico-gaming",
        "nombre": "Reddit — r/MexicoGaming top del día",
        "url": "https://www.reddit.com/r/MexicoGaming/top/.rss?t=day",
        "categoria": "gaming",
        "marca_sugerida": "nacion-gamer",
        "linea_sugerida": "Gaming México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Posts top del día en r/MexicoGaming.",
    },
    # ----------------------------------------------------------- Tendencias --
    {
        "id": "reddit-mx-tendencias",
        "nombre": "Reddit — r/mexico top del día",
        "url": "https://www.reddit.com/r/mexico/top/.rss?t=day",
        "categoria": "tendencias",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Tendencias México",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Posts top del día en r/mexico. Señal de tendencias en redes.",
    },
    {
        "id": "reddit-plantilla",
        "nombre": "Reddit — Subreddit personalizado [PLANTILLA]",
        "url": "https://www.reddit.com/r/SUBREDDIT/top/.rss?t=day",
        "categoria": "tendencias",
        "marca_sugerida": "",
        "linea_sugerida": "",
        "idioma": "es",
        "region": "GLOBAL",
        "descripcion": "Plantilla: sustituye SUBREDDIT por el subreddit deseado antes de activar.",
    },
    {
        "id": "gdelt-mx",
        "nombre": "GDELT — México [PLANTILLA]",
        "url": (
            "https://api.gdeltproject.org/api/v2/doc/doc"
            "?query=Mexico&format=rss&sort=datedesc"
        ),
        "categoria": "tendencias",
        "marca_sugerida": "unotv",
        "linea_sugerida": "Tendencias México",
        "idioma": "en",
        "region": "MX",
        "descripcion": (
            "GDELT por tema México. Ajusta el `query` antes de activar. "
            "Cobertura mundial de medios, multi-idioma."
        ),
    },
    {
        "id": "youtube-plantilla",
        "nombre": "YouTube — Canal [PLANTILLA]",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID",
        "categoria": "tendencias",
        "marca_sugerida": "",
        "linea_sugerida": "",
        "idioma": "es",
        "region": "GLOBAL",
        "descripcion": (
            "Plantilla: sustituye CHANNEL_ID por el id del canal de YouTube antes de activar. "
            "El id está en la URL del canal (/channel/UC...)."
        ),
    },
]

# Índice por id para búsqueda O(1).
_PRESETS_POR_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in _PRESETS}

# Categorías en orden de presentación (el mismo orden en que aparecen en el catálogo).
_CATEGORIAS: list[str] = []
_vistas: set[str] = set()
for _p in _PRESETS:
    _cat = _p["categoria"]
    if _cat not in _vistas:
        _CATEGORIAS.append(_cat)
        _vistas.add(_cat)
del _p, _cat, _vistas


# --------------------------------------------------------------------------- #
# API pública                                                                   #
# --------------------------------------------------------------------------- #


def listar_presets(categoria: str | None = None) -> list[dict[str, Any]]:
    """Lista de presets del catálogo, opcionalmente filtrada por `categoria`.

    Devuelve una copia superficial de cada preset (sin mutar el catálogo).
    """
    if categoria is not None:
        return [dict(p) for p in _PRESETS if p["categoria"] == categoria]
    return [dict(p) for p in _PRESETS]


def categorias() -> list[str]:
    """Categorías disponibles en el catálogo, en orden de aparición."""
    return list(_CATEGORIAS)


def obtener_preset(preset_id: str) -> dict[str, Any] | None:
    """Devuelve el preset por id, o None si no existe."""
    p = _PRESETS_POR_ID.get(preset_id)
    return dict(p) if p is not None else None
