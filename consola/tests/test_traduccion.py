"""Tests del módulo dominio/traduccion.py. OFFLINE: nunca llama a `claude` real.

Cubre:
  - `traducir_items` con ejecutor falso que devuelve JSON válido.
  - Best-effort: fallo del ejecutor -> devuelve originales.
  - Best-effort: JSON inválido -> devuelve originales.
  - Best-effort: ítem faltante en la respuesta -> devuelve el original para ese ítem.
  - Lista vacía -> devuelve lista vacía.
  - Textos largos se truncan en el payload (no en la respuesta final).
  - El Radar EN VIVO ya NO traduce (#desacoplo del back): solo etiqueta `idioma` y nunca
    llama a `traducir_items`. La traducción de historias persistidas la hace el daemon de
    ingesta (tests del daemon, no aquí).
"""

from __future__ import annotations

import json

from keni_consola.dominio import traduccion

# --------------------------------------------------------------------------- #
# Ejecutores falsos                                                             #
# --------------------------------------------------------------------------- #


def _ejecutor_ok(prompt: str, dir_permitido: str) -> str:
    """Ejecutor que extrae los ids del prompt y devuelve traducciones al español."""
    # Extrae el JSON de ítems del prompt para construir una respuesta coherente.
    import re

    # Aísla la lista REAL de ítems (va tras "Lista de ítems:"); el prompt también
    # contiene un ejemplo con corchetes en las instrucciones que confundía al regex.
    cola = prompt.partition("Lista de ítems:")[2] or prompt
    m = re.search(r"\[.*\]", cola, re.DOTALL)
    if not m:
        return json.dumps({"traducciones": []})
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"traducciones": []})
    traducciones = [
        {
            "id": it["id"],
            "titulo_es": f"[ES] {it['titulo']}",
            "resumen_es": f"[ES] {it.get('resumen', '')}",
        }
        for it in items
    ]
    return json.dumps({"traducciones": traducciones})


def _ejecutor_falla(prompt: str, dir_permitido: str) -> str:
    raise RuntimeError("Fallo simulado del subproceso claude")


def _ejecutor_json_invalido(prompt: str, dir_permitido: str) -> str:
    return "esto no es JSON para nada"


def _ejecutor_respuesta_parcial(prompt: str, dir_permitido: str) -> str:
    """Solo devuelve traducción para el primer ítem."""
    import re

    # Aísla la lista REAL de ítems (va tras "Lista de ítems:"); el prompt también
    # contiene un ejemplo con corchetes en las instrucciones que confundía al regex.
    cola = prompt.partition("Lista de ítems:")[2] or prompt
    m = re.search(r"\[.*\]", cola, re.DOTALL)
    if not m:
        return json.dumps({"traducciones": []})
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"traducciones": []})
    if not items:
        return json.dumps({"traducciones": []})
    primer = items[0]
    return json.dumps({
        "traducciones": [{"id": primer["id"], "titulo_es": "[ES] primero", "resumen_es": ""}]
    })


# --------------------------------------------------------------------------- #
# Casos base                                                                    #
# --------------------------------------------------------------------------- #


def test_lista_vacia_devuelve_lista_vacia():
    assert traduccion.traducir_items([], ejecutor=_ejecutor_ok) == []


def test_traduccion_correcta():
    items = [
        {"id": "t1", "titulo": "Breaking news", "resumen": "Summary here"},
        {"id": "t2", "titulo": "Sport update", "resumen": ""},
    ]
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_ok)
    assert len(resultado) == 2
    ids = {r["id"] for r in resultado}
    assert ids == {"t1", "t2"}
    # El ejecutor fake añade "[ES]" al principio.
    t1 = next(r for r in resultado if r["id"] == "t1")
    assert "[ES]" in t1["titulo_es"]
    assert "titulo_es" in t1
    assert "resumen_es" in t1


# --------------------------------------------------------------------------- #
# Best-effort ante fallos                                                       #
# --------------------------------------------------------------------------- #


def test_fallo_ejecutor_devuelve_originales():
    items = [
        {"id": "x1", "titulo": "Original title", "resumen": "Original summary"},
    ]
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_falla)
    assert len(resultado) == 1
    assert resultado[0]["titulo_es"] == "Original title"
    assert resultado[0]["resumen_es"] == "Original summary"


def test_json_invalido_devuelve_originales():
    items = [{"id": "x2", "titulo": "Hello", "resumen": "World"}]
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_json_invalido)
    assert resultado[0]["titulo_es"] == "Hello"


def test_respuesta_parcial_rellena_con_originales():
    items = [
        {"id": "a", "titulo": "A title", "resumen": "A summary"},
        {"id": "b", "titulo": "B title", "resumen": "B summary"},
    ]
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_respuesta_parcial)
    assert len(resultado) == 2
    a_res = next(r for r in resultado if r["id"] == "a")
    b_res = next(r for r in resultado if r["id"] == "b")
    # El primer ítem fue traducido.
    assert a_res["titulo_es"] == "[ES] primero"
    # El segundo ítem no llegó en la respuesta -> devuelve original.
    assert b_res["titulo_es"] == "B title"
    assert b_res["resumen_es"] == "B summary"


# --------------------------------------------------------------------------- #
# Truncado de texto largo (el cap por ítem no rompe la funcionalidad)          #
# --------------------------------------------------------------------------- #


def test_texto_largo_no_rompe():
    titulo_largo = "X" * 2000
    resumen_largo = "Y" * 2000
    items = [{"id": "big", "titulo": titulo_largo, "resumen": resumen_largo}]
    # Con el ejecutor que devuelve "[ES] ..." el resultado debe ser válido.
    resultado = traduccion.traducir_items(items, ejecutor=_ejecutor_ok)
    assert len(resultado) == 1
    assert "titulo_es" in resultado[0]


# --------------------------------------------------------------------------- #
# Integración con el Radar EN VIVO (#desacoplo del back: el back NO ejecuta     #
# `claude`, así que el Radar en vivo YA NO traduce). Cada tema queda con su     #
# `idioma` etiquetado pero `traducido` se mantiene False en el camino en vivo.  #
# La traducción de historias PERSISTIDAS ocurre en el DAEMON de ingesta (que    #
# corre en `daemons` con `claude`), cubierta por los tests del daemon, NO aquí.  #
# --------------------------------------------------------------------------- #


def test_radar_en_vivo_no_traduce_y_etiqueta_idioma(cliente, monkeypatch):
    """El Radar en vivo NO llama a `traducir_items` ni marca `traducido`; etiqueta `idioma`."""
    from keni_consola.api import rss
    from keni_consola.dominio import http_feed
    from keni_consola.dominio import traduccion as dom_trad

    # Feed RSS en inglés (idioma=en según el preset bbc-world del catálogo).
    _FEED_EN = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item>
        <title>Breaking English News</title>
        <description>Summary in English</description>
        <link>https://93.184.216.34/article1</link>
        <guid>article1</guid>
      </item>
    </channel></rss>"""

    _TRENDS_VACÍO = """<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
    <channel></channel></rss>"""

    # Registra una fuente con la URL exacta de un preset idioma=en del catálogo (bbc-world):
    # el Radar deduce el idioma del feed por su URL en el catálogo de presets.
    url_en = "https://feeds.bbci.co.uk/news/world/rss.xml"
    # Hay DOS validar_url que tocar para evitar DNS/SSRF real en tests: `rss.validar_url`
    # (lo usa `crear_fuente` al dar de alta) y `http_feed.validar_url` (lo usa
    # `leer_items_fuente` al descargar el feed dentro del Radar). Parcheamos ambos.
    monkeypatch.setattr(rss, "validar_url", lambda u: (u, None))
    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))
    cliente.post("/api/rss/fuentes", json={"nombre": "BBC EN", "url": url_en})

    def fake_descargador(url: str) -> str:
        if "bbci" in url:
            return _FEED_EN
        return _TRENDS_VACÍO

    monkeypatch.setattr(rss, "_DESCARGADOR", fake_descargador)

    # El flag de traducción puede estar ON: el Radar EN VIVO ya no traduce de todos modos.
    monkeypatch.setenv("KENI_TRADUCCION", "1")

    # Centinela: si el Radar en vivo llamara a `traducir_items`, este fake lo delataría.
    llamadas: list[int] = []

    def fake_traducir(items, *, ejecutor=None):
        llamadas.append(1)
        return []

    monkeypatch.setattr(dom_trad, "traducir_items", fake_traducir)

    datos = cliente.get("/api/radar?feeds=1").json()

    temas = datos["temas"]
    # Debe haber al menos el tema del feed en inglés.
    assert len(temas) >= 1
    # El Radar en vivo NUNCA llama a traducir_items (el back no ejecuta `claude`).
    assert llamadas == []
    # El tema extranjero queda con `idioma` etiquetado pero SIN traducir en vivo.
    extranjeros = [t for t in temas if t.get("idioma") and t.get("idioma") != "es"]
    assert len(extranjeros) >= 1
    assert all(not t.get("traducido") for t in temas)


def test_radar_sin_traduccion_no_llama_traducir(cliente, monkeypatch):
    """Con KENI_TRADUCCION=0, el Radar tampoco llama a traducir_items (igual que con el flag ON)."""
    from keni_consola.api import rss
    from keni_consola.dominio import traduccion as dom_trad

    _TRENDS_VACÍO = """<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
    <channel></channel></rss>"""

    monkeypatch.setattr(rss, "_DESCARGADOR", lambda url: _TRENDS_VACÍO)
    monkeypatch.setenv("KENI_TRADUCCION", "0")

    llamadas: list[int] = []

    def fake_traducir(items, *, ejecutor=None):
        llamadas.append(1)
        return []

    monkeypatch.setattr(dom_trad, "traducir_items", fake_traducir)

    cliente.get("/api/radar?feeds=0")
    assert len(llamadas) == 0
