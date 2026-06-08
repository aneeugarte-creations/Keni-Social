"""Tests del catálogo de presets de fuentes (dominio/fuentes_presets.py). OFFLINE/PURO.

No requiere Postgres ni red: fuentes_presets es un módulo de datos puro.
Cubre:
  - listar_presets() y categorias(): conteo, campos obligatorios, ids únicos.
  - filtro por categoría.
  - obtener_preset() por id (existe / no existe).
"""

from __future__ import annotations

from keni_consola.dominio import fuentes_presets

# --------------------------------------------------------------------------- #
# Listado y categorías                                                          #
# --------------------------------------------------------------------------- #


def test_listar_todos_devuelve_un_catalogo_grande():
    """Tras la ampliación (Ola C) el catálogo es de cientos de feeds verificados."""
    todos = fuentes_presets.listar_presets()
    assert len(todos) >= 120, f"Se esperaban ≥120 presets, hay {len(todos)}"


def test_categorias_contiene_las_esperadas():
    cats = fuentes_presets.categorias()
    esperadas = {
        "mx",
        "regional",
        "internacional",
        "negocios",
        "deportes",
        "ciencia-tech",
        "gaming",
        "tendencias",
    }
    assert esperadas <= set(cats), f"Categorías faltantes: {esperadas - set(cats)}"


# Mínimos por categoría: garantizan cobertura amplia y que ninguna quede vacía.
_MINIMOS_POR_CATEGORIA = {
    "mx": 8,
    "regional": 10,
    "internacional": 12,
    "negocios": 4,
    "deportes": 20,
    "ciencia-tech": 15,
    "gaming": 20,
    "tendencias": 10,
}


def test_conteo_minimo_por_categoria():
    for cat, minimo in _MINIMOS_POR_CATEGORIA.items():
        n = len(fuentes_presets.listar_presets(categoria=cat))
        assert n >= minimo, f"Categoría '{cat}' tiene {n} presets, se esperaban ≥{minimo}"


def test_ids_unicos():
    todos = fuentes_presets.listar_presets()
    ids = [p["id"] for p in todos]
    assert len(ids) == len(set(ids)), "Hay ids duplicados en el catálogo"


_IDIOMAS_VALIDOS = {"es", "en", "pt", "fr"}
_CATEGORIAS_VALIDAS = {
    "mx",
    "regional",
    "internacional",
    "negocios",
    "deportes",
    "ciencia-tech",
    "gaming",
    "tendencias",
}


def test_campos_obligatorios_presentes():
    campos = {"id", "nombre", "url", "categoria", "idioma", "region", "descripcion"}
    for preset in fuentes_presets.listar_presets():
        for campo in campos:
            assert campo in preset, f"Preset '{preset.get('id')}' le falta el campo '{campo}'"
        # La URL debe ser http(s)
        url = preset["url"]
        assert url.startswith(("http://", "https://")), (
            f"Preset '{preset['id']}' tiene URL sin esquema: {url!r}"
        )
        # categoría e idioma válidos
        assert preset["categoria"] in _CATEGORIAS_VALIDAS, (
            f"Preset '{preset['id']}' tiene categoría inválida: {preset['categoria']!r}"
        )
        assert preset["idioma"] in _IDIOMAS_VALIDOS, (
            f"Preset '{preset['id']}' tiene idioma inválido: {preset['idioma']!r}"
        )


def test_presets_no_plantilla_sin_placeholders_en_url():
    """Los presets que NO son plantilla deben llevar la URL concreta lista para sondear."""
    placeholders = ("TEMA", "SUBREDDIT", "CHANNEL_ID", "<query>", "{")
    for preset in fuentes_presets.listar_presets():
        if "[PLANTILLA]" in preset["nombre"]:
            continue
        for ph in placeholders:
            assert ph not in preset["url"], (
                f"Preset '{preset['id']}' (no plantilla) deja placeholder {ph!r} en la URL"
            )


def test_filtro_categoria_mx():
    mx = fuentes_presets.listar_presets(categoria="mx")
    assert len(mx) >= 3
    assert all(p["categoria"] == "mx" for p in mx)


def test_filtro_categoria_deportes():
    dep = fuentes_presets.listar_presets(categoria="deportes")
    assert len(dep) >= 3
    assert all(p["categoria"] == "deportes" for p in dep)


def test_filtro_categoria_inexistente_devuelve_lista_vacia():
    assert fuentes_presets.listar_presets(categoria="noexiste") == []


def test_filtro_marca_oculta_otras_marcas_y_mantiene_genericos():
    """`marca=` (conservador): oculta presets de OTRA marca; conserva los sin marca + los de la marca."""
    de_unotv = fuentes_presets.listar_presets(marca="unotv")
    sugeridas = {(p.get("marca_sugerida") or "") for p in de_unotv}
    # No aparece ninguna preset sugerida a otra marca.
    assert sugeridas <= {"", "unotv"}
    # Los genéricos (sin marca sugerida) siguen presentes.
    assert any(not (p.get("marca_sugerida") or "") for p in de_unotv)
    # Las presets de unotv que existen en el catálogo se conservan.
    todas_unotv = {
        p["id"] for p in fuentes_presets.listar_presets() if p.get("marca_sugerida") == "unotv"
    }
    assert todas_unotv <= {p["id"] for p in de_unotv}
    # Sin marca -> catálogo completo (incluye presets de claro-sports).
    todos = fuentes_presets.listar_presets()
    assert any(p.get("marca_sugerida") == "claro-sports" for p in todos)
    assert all(p.get("marca_sugerida") != "claro-sports" for p in de_unotv)


def test_listar_devuelve_copia_superficial():
    """listar_presets devuelve copias: mutar el resultado no altera el catálogo."""
    antes = fuentes_presets.listar_presets()
    antes[0]["nombre"] = "MUTADO"
    despues = fuentes_presets.listar_presets()
    assert despues[0]["nombre"] != "MUTADO"


# --------------------------------------------------------------------------- #
# obtener_preset                                                                #
# --------------------------------------------------------------------------- #


def test_obtener_preset_existente():
    p = fuentes_presets.obtener_preset("bbc-world")
    assert p is not None
    assert p["id"] == "bbc-world"
    assert p["idioma"] == "en"
    assert p["categoria"] == "internacional"


def test_obtener_preset_inexistente_devuelve_none():
    assert fuentes_presets.obtener_preset("no-existe") is None


# --------------------------------------------------------------------------- #
# Ruteo del auto-seed por marca (bootstrap_lineas._preset_va_en_seed). PURO.    #
# --------------------------------------------------------------------------- #


def test_seed_rutea_categorias_correctas_por_marca():
    from keni_consola import bootstrap_lineas as bl

    seed = [p for p in fuentes_presets.listar_presets() if bl._preset_va_en_seed(p)]
    assert seed, "El subset de auto-seed no debería quedar vacío"

    cats_por_marca: dict[str, set[str]] = {}
    for p in seed:
        cats_por_marca.setdefault(p["marca_sugerida"], set()).add(p["categoria"])

    # UnoTV: noticias (mx/regional/internacional/negocios/ciencia-tech/tendencias), NUNCA gaming/deportes.
    assert "mx" in cats_por_marca["unotv"]
    assert "regional" in cats_por_marca["unotv"]
    assert "internacional" in cats_por_marca["unotv"]
    assert "ciencia-tech" in cats_por_marca["unotv"]
    assert "gaming" not in cats_por_marca["unotv"]
    assert "deportes" not in cats_por_marca["unotv"]

    # Claro Sports: deportes (todas las competiciones).
    assert cats_por_marca["claro-sports"] == {"deportes"} or "deportes" in cats_por_marca[
        "claro-sports"
    ]
    assert "gaming" not in cats_por_marca.get("claro-sports", set())

    # Nación Gamer: gaming + ciencia-tech.
    assert "gaming" in cats_por_marca["nacion-gamer"]
    assert "ciencia-tech" in cats_por_marca["nacion-gamer"]
    assert "deportes" not in cats_por_marca["nacion-gamer"]


def test_seed_excluye_plantillas():
    from keni_consola import bootstrap_lineas as bl

    plantillas = [p for p in fuentes_presets.listar_presets() if "[PLANTILLA]" in p["nombre"]]
    assert plantillas, "Debe haber plantillas en el catálogo"
    for p in plantillas:
        assert not bl._preset_va_en_seed(p), f"Plantilla '{p['id']}' no debe entrar al auto-seed"


def test_seed_excluye_presets_sin_marca():
    from keni_consola import bootstrap_lineas as bl

    preset_sin_marca = {
        "id": "x",
        "nombre": "X",
        "url": "https://e.com/f.xml",
        "categoria": "mx",
        "marca_sugerida": "",
        "idioma": "es",
        "region": "MX",
        "descripcion": "",
    }
    assert not bl._preset_va_en_seed(preset_sin_marca)


def test_seed_subset_es_menor_que_catalogo_completo():
    """El auto-seed activa un subset, no los cientos de presets (evita ruido)."""
    from keni_consola import bootstrap_lineas as bl

    todos = fuentes_presets.listar_presets()
    seed = [p for p in todos if bl._preset_va_en_seed(p)]
    assert 0 < len(seed) <= len(todos)
    assert len(seed) < len(todos), "El seed debe excluir al menos las plantillas"


# --------------------------------------------------------------------------- #
# API de presets via HTTP (requiere Postgres)                                   #
# --------------------------------------------------------------------------- #


def test_get_presets_sin_filtro(cliente):
    r = cliente.get("/api/fuentes/presets")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert "presets" in datos
    assert "categorias" in datos
    assert len(datos["presets"]) >= 30
    assert set(datos["categorias"]) >= {"mx", "internacional", "deportes"}
    # Todos tienen el campo `activa`
    for p in datos["presets"]:
        assert "activa" in p


def test_get_presets_filtro_categoria(cliente):
    r = cliente.get("/api/fuentes/presets?categoria=gaming")
    assert r.status_code == 200
    presets = r.json()["presets"]
    assert len(presets) >= 3
    assert all(p["categoria"] == "gaming" for p in presets)


def test_get_presets_filtro_marca(cliente):
    """`?marca=unotv` oculta presets de otra marca; conserva genéricos y los de unotv."""
    r = cliente.get("/api/fuentes/presets?marca=unotv")
    assert r.status_code == 200, r.text
    presets = r.json()["presets"]
    assert all((p.get("marca_sugerida") or "") in ("", "unotv") for p in presets)
    # No se cuela ninguna sugerida a claro-sports.
    assert all(p.get("marca_sugerida") != "claro-sports" for p in presets)


def test_get_presets_marca_invalida_400(cliente):
    assert cliente.get("/api/fuentes/presets?marca=marca_falsa").status_code == 400


def test_get_presets_activa_refleja_fuentes_existentes(cliente, monkeypatch):
    """Un preset cuya URL ya tiene fuente RSS sale con activa=True."""
    from keni_consola.api import rss

    # Añadir fuente RSS con la URL de un preset conocido (BBC World).
    url_bbc = "https://feeds.bbci.co.uk/news/world/rss.xml"
    # `crear_fuente` usa el binding `rss.validar_url` (re-exportado en import), no
    # `http_feed.validar_url`: parcheamos ESE para evitar DNS/SSRF real en tests.
    monkeypatch.setattr(rss, "validar_url", lambda u: (u, None))
    cliente.post("/api/rss/fuentes", json={"nombre": "BBC Test", "url": url_bbc})

    r = cliente.get("/api/fuentes/presets?categoria=internacional")
    presets = r.json()["presets"]
    bbc = next((p for p in presets if p["id"] == "bbc-world"), None)
    assert bbc is not None
    assert bbc["activa"] is True

    # Otros presets de la misma categoría deben estar inactivos.
    otros = [p for p in presets if p["id"] != "bbc-world"]
    assert all(not p["activa"] for p in otros)


def test_post_activar_presets_crea_fuentes(cliente, monkeypatch):
    """POST /api/fuentes/presets/activar crea fuentes RSS para los presets indicados."""
    from keni_consola.dominio import http_feed

    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))

    r = cliente.post(
        "/api/fuentes/presets/activar",
        json={"ids": ["jornada-mx", "ign-latam"]},
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["creadas"] == 2
    assert len(datos["fuentes"]) == 2
    assert datos["omitidas"] == 0

    # Las fuentes tienen los campos esperados.
    nombres = {f["nombre"] for f in datos["fuentes"]}
    assert "La Jornada — Edición" in nombres
    assert "IGN — Latinoamérica" in nombres


def test_post_activar_idempotente(cliente, monkeypatch):
    """Activar el mismo preset dos veces no duplica la fuente."""
    from keni_consola.dominio import http_feed

    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))

    cliente.post("/api/fuentes/presets/activar", json={"ids": ["jornada-mx"]})
    r2 = cliente.post("/api/fuentes/presets/activar", json={"ids": ["jornada-mx"]})
    assert r2.status_code == 200
    datos = r2.json()
    assert datos["creadas"] == 0
    assert datos["omitidas"] == 1


def test_post_activar_marca_override(cliente, monkeypatch):
    """Si se pasa marca, sobrescribe la marca_sugerida del preset."""
    from keni_consola.dominio import http_feed

    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))

    r = cliente.post(
        "/api/fuentes/presets/activar",
        json={"ids": ["bbc-world"], "marca": "claro-sports"},
    )
    assert r.status_code == 200
    datos = r.json()
    assert datos["creadas"] == 1
    assert datos["fuentes"][0]["marca"] == "claro-sports"


def test_post_activar_ids_vacio_400(cliente):
    r = cliente.post("/api/fuentes/presets/activar", json={"ids": []})
    assert r.status_code == 400


def test_post_activar_ids_faltante_400(cliente):
    r = cliente.post("/api/fuentes/presets/activar", json={})
    assert r.status_code == 400


def test_post_activar_marca_invalida_400(cliente, monkeypatch):
    from keni_consola.dominio import http_feed

    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))

    r = cliente.post(
        "/api/fuentes/presets/activar",
        json={"ids": ["jornada-mx"], "marca": "noexiste"},
    )
    assert r.status_code == 400


def test_post_activar_ssrf_rechaza_ip_privada(cliente):
    """Un preset con URL de IP privada es rechazado por el guard SSRF."""
    # Forzamos un preset inventado que apunta a loopback: no debe crearse.
    # (Los presets del catálogo real NO apuntan a IPs privadas; este test verifica
    # que el guard SSRF se aplica al activar.)
    from keni_consola.dominio import fuentes_presets as fp

    # Parche temporal: añadimos un preset con URL interna.
    preset_malo = {
        "id": "_test_ssrf",
        "nombre": "Test SSRF",
        "url": "http://127.0.0.1/feed.xml",
        "categoria": "mx",
        "marca_sugerida": "",
        "linea_sugerida": "",
        "idioma": "es",
        "region": "MX",
        "descripcion": "Solo para tests",
    }
    original = fp._PRESETS[:]
    original_por_id = dict(fp._PRESETS_POR_ID)
    fp._PRESETS.append(preset_malo)
    fp._PRESETS_POR_ID["_test_ssrf"] = preset_malo
    try:
        r = cliente.post("/api/fuentes/presets/activar", json={"ids": ["_test_ssrf"]})
        assert r.status_code == 200
        datos = r.json()
        # No se creó ninguna fuente (el SSRF guard rechazó la URL).
        assert datos["creadas"] == 0
        assert "errores" in datos
    finally:
        fp._PRESETS[:] = original
        fp._PRESETS_POR_ID.clear()
        fp._PRESETS_POR_ID.update(original_por_id)
