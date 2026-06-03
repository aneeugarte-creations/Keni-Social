"""Tests PUROS (sin DB) de `dominio.dedup.url_canonica` y `dominio.dedup.es_similar`.

`url_canonica` normaliza un enlace para cruce exacto (host minusculas, sin esquema/www/
fragmento/tracking/`/` final). `es_similar` decide si un titulo casa (exacto o fuzzy
SequenceMatcher >= umbral) contra un conjunto de claves ya normalizadas. Ambas son funciones
puras: no necesitan Postgres ni la fixture `entorno`.
"""

from __future__ import annotations

from keni_consola.dominio import dedup


# --------------------------------------------------------------------------- #
# url_canonica                                                                 #
# --------------------------------------------------------------------------- #


def test_url_canonica_quita_esquema_www_y_barra_final():
    assert dedup.url_canonica("https://www.UnoTV.com/nota/") == "unotv.com/nota"
    assert dedup.url_canonica("http://example.com/a/b/") == "example.com/a/b"


def test_url_canonica_minusculas_en_host_no_en_camino():
    # El host se baja a minusculas; el path se conserva tal cual (case-sensitive).
    assert dedup.url_canonica("https://EXAMPLE.com/Ruta") == "example.com/Ruta"


def test_url_canonica_quita_fragmento():
    assert dedup.url_canonica("https://example.com/nota#seccion") == "example.com/nota"


def test_url_canonica_quita_tracking_conserva_resto():
    # utm_*, fbclid y gclid se quitan; un parametro real (`id`) se conserva.
    assert (
        dedup.url_canonica("https://example.com/nota?utm_source=fb&id=5&fbclid=xyz&gclid=q")
        == "example.com/nota?id=5"
    )


def test_url_canonica_solo_tracking_queda_sin_query():
    assert (
        dedup.url_canonica("https://example.com/nota?utm_source=tw&utm_medium=social")
        == "example.com/nota"
    )


def test_url_canonica_equivalentes_cruzan():
    a = dedup.url_canonica("https://www.example.com/nota/?utm_source=fb#top")
    b = dedup.url_canonica("http://example.com/nota")
    assert a == b == "example.com/nota"


def test_url_canonica_vacia_o_no_http():
    assert dedup.url_canonica("") == ""
    assert dedup.url_canonica("ftp://example.com/x") == ""
    assert dedup.url_canonica("mailto:a@b.com") == ""
    assert dedup.url_canonica("javascript:void(0)") == ""


# --------------------------------------------------------------------------- #
# es_similar                                                                   #
# --------------------------------------------------------------------------- #


def test_es_similar_exacto_por_clave_normalizada():
    # Acentos/mayusculas/puntuacion no importan: comparan por `clave(...)`.
    norm = {dedup.clave("Increíble remontada del América")}
    assert dedup.es_similar("¡INCREIBLE remontada del america!", norm) is True


def test_es_similar_fuzzy_sobre_umbral():
    norm = {dedup.clave("El América gana el clásico ante Chivas en el Azteca")}
    # Casi identico (una palabra cambia) -> ratio alto -> casa.
    assert (
        dedup.es_similar("El America gana el clasico ante Chivas en Azteca", norm) is True
    )


def test_es_similar_no_match_titulo_distinto():
    norm = {dedup.clave("Resultados de la Liga MX jornada 10")}
    assert dedup.es_similar("Pronostico del clima para mañana en CDMX", norm) is False


def test_es_similar_vacios_devuelven_false():
    assert dedup.es_similar("", {dedup.clave("algo")}) is False
    assert dedup.es_similar("algo", set()) is False
    assert dedup.es_similar("", set()) is False


def test_es_similar_respeta_umbral_explicito():
    norm = {dedup.clave("gol de penal en el minuto noventa")}
    titulo = "gol de tiro libre en el minuto ochenta"
    # Umbral muy alto -> no casa; umbral bajo -> casa.
    assert dedup.es_similar(titulo, norm, umbral=0.99) is False
    assert dedup.es_similar(titulo, norm, umbral=0.3) is True
