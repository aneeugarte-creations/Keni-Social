"""Tests de la lógica PURA de Algoritmos (clasificación + semilla). SIN red ni BD.

`clasificar`, `_detectar_plataforma`, `texto_propuesta_ficha`, `fuentes_pendientes` y la
lista `FUENTES_SEMILLA` son deterministas y no tocan persistencia: se prueban directos.
La ingesta end-to-end (descarga + persistencia) vive en `test_api_algoritmos.py`.
"""

from __future__ import annotations

from keni_consola import algoritmos
from keni_consola.api import rss


def _fuente(plataforma: str = "general", tipo: str = "agregador") -> dict[str, str]:
    return {"id": "f1", "nombre": "Fuente", "url": "x", "plataforma": plataforma, "tipo": tipo}


def test_clasifica_cambio_de_algoritmo_como_alta():
    item = {
        "titulo": "Instagram updates its ranking algorithm: Reels reach changes",
        "resumen": "The platform changes how the feed ranks Reels and distribution.",
    }
    clasif = algoritmos.clasificar(item, _fuente())
    # Detecta la red por el texto (agregador → plataforma específica).
    assert clasif["plataforma"] == "instagram"
    # Señal fuerte presente => candidato a la ficha.
    assert clasif["es_cambio"] is True
    assert clasif["nivel"] == "alta"
    assert clasif["importancia"] > 0
    # Las señales son las palabras que dispararon el score (el "por qué" honesto).
    assert "algoritmo" in clasif["senales"]
    assert "ranking" in clasif["senales"]


def test_clasifica_nota_menor_como_baja_sin_cambio():
    item = {
        "titulo": "Messenger gets a small design tweak",
        "resumen": "A minor visual change for chats.",
    }
    clasif = algoritmos.clasificar(item, _fuente())
    assert clasif["plataforma"] == "meta"  # "messenger" => Meta
    assert clasif["es_cambio"] is False
    assert clasif["nivel"] in ("baja", "media")


def test_coincide_por_limite_de_palabra_no_subcadena():
    """La variante "new " (con espacio) ya no casa "news" por subcadena; los prefijos
    intencionados ("penaliz") siguen casando sus derivados."""
    assert algoritmos._coincide(algoritmos._normalizar("breaking news today"), ("new ",)) is False
    assert algoritmos._coincide(algoritmos._normalizar("a new feature arrives"), ("new ",)) is True
    assert algoritmos._coincide(algoritmos._normalizar("penalización confirmada"), ("penaliz",)) is True
    assert algoritmos._coincide(algoritmos._normalizar("crank it up"), ("rank ",)) is False


def test_titular_news_no_dispara_senal_de_cambio():
    # "News" en el titular no debe contar como la señal "new " (cambio): antes inflaba la
    # importancia de TODO agregador de noticias.
    item = {"titulo": "Platform news roundup", "resumen": "weekly industry summary"}
    clasif = algoritmos.clasificar(item, _fuente())
    assert "cambio" not in clasif["senales"]


def test_fuente_oficial_pesa_mas_que_agregador():
    item = {"titulo": "New update", "resumen": "feature"}
    base = algoritmos.clasificar(item, _fuente(tipo="agregador"))["importancia"]
    oficial = algoritmos.clasificar(item, _fuente(tipo="oficial"))["importancia"]
    assert oficial > base


def test_plataforma_de_fuente_se_respeta_si_texto_no_nombra_red():
    # Fuente oficial de YouTube; el texto no nombra otra red => se queda en youtube.
    item = {"titulo": "An announcement", "resumen": "details"}
    clasif = algoritmos.clasificar(item, _fuente(plataforma="youtube", tipo="oficial"))
    assert clasif["plataforma"] == "youtube"


def test_propuesta_ficha_incluye_titulo_y_plataforma():
    noticia = {
        "titulo": "Cambio en el feed",
        "plataforma": "tiktok",
        "fecha": "2026-05-01",
        "resumen": "resumen",
        "enlace": "https://example.com/x",
        "senales": ["feed", "alcance"],
    }
    texto = algoritmos.texto_propuesta_ficha(noticia)
    assert "Cambio en el feed" in texto
    assert "TikTok" in texto
    assert "https://example.com/x" in texto


def test_fuentes_pendientes_declara_los_huecos_sin_feed_oficial():
    pendientes = {p["plataforma"] for p in algoritmos.fuentes_pendientes()}
    # TikTok / Instagram / X no publican feed oficial: el hueco se declara, no se inventa.
    assert {"tiktok", "instagram", "x"} <= pendientes


def test_fuentes_semilla_tienen_url_valida_y_vocabulario_correcto():
    for s in algoritmos.FUENTES_SEMILLA:
        assert s["nombre"] and s["url"].startswith("https://")
        assert algoritmos.es_plataforma(s["plataforma"])
        assert algoritmos.es_tipo(s["tipo"])
        # La URL semilla pasa la validación de esquema del guard (sin tocar DNS aquí:
        # solo comprobamos que el esquema es http/https, no la resolución).
        assert s["url"].split("://", 1)[0] in ("http", "https")


def test_descargador_inyectable_compartido_con_rss():
    # La ingesta reusa el MISMO punto inyectable del RSS (los tests lo parchean).
    assert hasattr(rss, "_DESCARGADOR")
