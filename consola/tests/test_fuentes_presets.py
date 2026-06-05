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


def test_listar_todos_devuelve_al_menos_30_presets():
    todos = fuentes_presets.listar_presets()
    assert len(todos) >= 30, f"Se esperaban ≥30 presets, hay {len(todos)}"


def test_categorias_contiene_las_6_esperadas():
    cats = fuentes_presets.categorias()
    esperadas = {"mx", "internacional", "deportes", "ciencia-tech", "gaming", "tendencias"}
    assert esperadas <= set(cats), f"Categorías faltantes: {esperadas - set(cats)}"


def test_ids_unicos():
    todos = fuentes_presets.listar_presets()
    ids = [p["id"] for p in todos]
    assert len(ids) == len(set(ids)), "Hay ids duplicados en el catálogo"


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
    p = fuentes_presets.obtener_preset("reuters-world")
    assert p is not None
    assert p["id"] == "reuters-world"
    assert p["idioma"] == "en"
    assert p["categoria"] == "internacional"


def test_obtener_preset_inexistente_devuelve_none():
    assert fuentes_presets.obtener_preset("no-existe") is None


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


def test_get_presets_activa_refleja_fuentes_existentes(cliente, monkeypatch):
    """Un preset cuya URL ya tiene fuente RSS sale con activa=True."""
    from keni_consola.api import rss

    # Añadir fuente RSS con URL de un preset conocido (Reuters).
    url_reuters = "https://feeds.reuters.com/reuters/worldNews"
    # `crear_fuente` usa el binding `rss.validar_url` (re-exportado en import), no
    # `http_feed.validar_url`: parcheamos ESE para evitar DNS/SSRF real en tests.
    monkeypatch.setattr(rss, "validar_url", lambda u: (u, None))
    cliente.post("/api/rss/fuentes", json={"nombre": "Reuters Test", "url": url_reuters})

    r = cliente.get("/api/fuentes/presets?categoria=internacional")
    presets = r.json()["presets"]
    reuters = next((p for p in presets if p["id"] == "reuters-world"), None)
    assert reuters is not None
    assert reuters["activa"] is True

    # Otros presets de la misma categoría deben estar inactivos.
    otros = [p for p in presets if p["id"] != "reuters-world"]
    assert all(not p["activa"] for p in otros)


def test_post_activar_presets_crea_fuentes(cliente, monkeypatch):
    """POST /api/fuentes/presets/activar crea fuentes RSS para los presets indicados."""
    from keni_consola.dominio import http_feed

    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))

    r = cliente.post(
        "/api/fuentes/presets/activar",
        json={"ids": ["reforma-mx", "ign-latam"]},
    )
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["creadas"] == 2
    assert len(datos["fuentes"]) == 2
    assert datos["omitidas"] == 0

    # Las fuentes tienen los campos esperados.
    nombres = {f["nombre"] for f in datos["fuentes"]}
    assert "Reforma — México" in nombres
    assert "IGN — Latinoamérica" in nombres


def test_post_activar_idempotente(cliente, monkeypatch):
    """Activar el mismo preset dos veces no duplica la fuente."""
    from keni_consola.dominio import http_feed

    monkeypatch.setattr(http_feed, "validar_url", lambda u: (u, None))

    cliente.post("/api/fuentes/presets/activar", json={"ids": ["reforma-mx"]})
    r2 = cliente.post("/api/fuentes/presets/activar", json={"ids": ["reforma-mx"]})
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
        json={"ids": ["reforma-mx"], "marca": "noexiste"},
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
