"""API de patrones (perfil medido + verificación de voz, ADR 0009). Vía `cliente`."""

from __future__ import annotations


def test_indice_marcas_con_perfil(cliente):
    datos = cliente.get("/api/patrones").json()
    por_marca = {m["marca"]: m["tiene_perfil"] for m in datos["marcas"]}
    # Las marcas del piloto con datos en Metricool viajan con perfil semilla.
    assert por_marca["unotv"] is True
    assert por_marca["claro-sports"] is True
    # Fundación no tiene piezas en Metricool: sin perfil (honesto).
    assert por_marca["fundacion"] is False


def test_perfil_de_marca(cliente):
    r = cliente.get("/api/patrones", params={"marca": "unotv"})
    assert r.status_code == 200
    perfil = r.json()["perfil"]
    assert perfil["marca"] == "unotv" and perfil["redes"]


def test_perfil_marca_invalida_y_sin_perfil(cliente):
    assert cliente.get("/api/patrones", params={"marca": "acme"}).status_code == 400
    assert cliente.get("/api/patrones", params={"marca": "fundacion"}).status_code == 404


def test_verificar_voz_fuera_de_patron(cliente):
    # UnoTV publica sin emojis: un texto con emojis y hashtag (copy unificado) avisa.
    r = cliente.post(
        "/api/patrones/verificar-voz",
        json={"marca": "unotv", "texto": "¡Última hora! 🔥🔥🔥 Todo sobre el #Mundial2026."},
    )
    assert r.status_code == 200
    datos = r.json()
    assert datos["dentro_de_patron"] is False
    assert any("hashtag" in a for a in datos["avisos"])
    assert any("emoji" in a for a in datos["avisos"])


def test_verificar_voz_acota_redes_y_valida(cliente):
    r = cliente.post(
        "/api/patrones/verificar-voz",
        json={"marca": "unotv", "texto": "Texto sobrio.", "redes": ["myspace"]},
    )
    assert r.status_code == 400
    assert cliente.post(
        "/api/patrones/verificar-voz", json={"marca": "unotv", "texto": "   "}
    ).status_code == 400
    assert cliente.post(
        "/api/patrones/verificar-voz", json={"marca": "acme", "texto": "x"}
    ).status_code == 400
