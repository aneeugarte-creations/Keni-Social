"""Tests UNITARIOS del buscador de fotos LICENCIADAS de AFP. OFFLINE, sin red.

Cubre la lógica PURA (`normalizar_afp_fotos`, tolerante a la forma del array de medios), la
degradación honesta (`estado_fuente` / `buscar` gateados por credencial) y que `buscar` delega
en el transporte INYECTABLE `_BUSCADOR` (parcheado, sin tocar la red).
"""

from __future__ import annotations

import pytest

from keni_consola import agencias, agencias_fotos, config


# --------------------------------------------------------------------------- #
# normalizar_afp_fotos (PURO, tolerante a la forma)                            #
# --------------------------------------------------------------------------- #


def test_normalizar_afp_fotos_varios_tamanos_de_medios():
    datos = {
        "response": {
            "docs": [
                {
                    "uno": "doc1",
                    "title": "Final del Mundial",
                    "creator": "Jean Photographer",
                    "creditline": "AFP / Stringer",
                    "creditUrl": "https://afp.com/doc1",
                    "medias": [
                        {"role": "Preview", "href": "https://afp/preview.jpg"},
                        {"role": "HighDef", "href": "https://afp/highdef.jpg"},
                        {"sizeName": "Thumbnail", "href": "https://afp/thumb.jpg"},
                    ],
                }
            ]
        }
    }
    cands = agencias_fotos.normalizar_afp_fotos(datos)
    assert len(cands) == 1
    c = cands[0]
    assert c["proveedor"] == "afp"
    assert c["url"] == "https://afp/highdef.jpg"  # eligió el tamaño grande
    assert c["thumb"] == "https://afp/thumb.jpg"  # eligió la miniatura
    assert c["autor"] == "Jean Photographer"
    assert c["licencia"] == "AFP / Stringer"  # ya contiene "AFP": no se duplica
    assert c["credito_url"] == "https://afp.com/doc1"
    assert c["titulo"] == "Final del Mundial"


def test_normalizar_afp_fotos_thumb_cae_a_url_si_falta():
    datos = {"docs": [{"title": "T", "medias": [{"role": "large", "href": "https://afp/x.jpg"}]}]}
    cands = agencias_fotos.normalizar_afp_fotos(datos)
    assert cands[0]["url"] == "https://afp/x.jpg"
    assert cands[0]["thumb"] == "https://afp/x.jpg"  # sin miniatura -> cae a la url grande


def test_normalizar_afp_fotos_creditline_sin_afp_se_compone():
    datos = {"docs": [{"title": "T", "creditline": "Stringer", "medias": [{"href": "https://a/x.jpg"}]}]}
    cands = agencias_fotos.normalizar_afp_fotos(datos)
    assert cands[0]["licencia"] == "AFP — Stringer"


def test_normalizar_afp_fotos_omite_doc_sin_imagen():
    datos = {"docs": [{"title": "Sin foto", "creator": "X"}]}
    assert agencias_fotos.normalizar_afp_fotos(datos) == []


def test_normalizar_afp_fotos_tolera_basura():
    assert agencias_fotos.normalizar_afp_fotos(None) == []
    assert agencias_fotos.normalizar_afp_fotos({}) == []
    assert agencias_fotos.normalizar_afp_fotos({"response": {"docs": [None, 7, "x", {}]}}) == []


def test_normalizar_afp_fotos_renditions_anidadas():
    # El href puede venir en una lista anidada dentro del medio (renditions/sizes).
    datos = {
        "docs": [
            {
                "title": "T",
                "bagItem": [
                    {"renditions": [{"sizeName": "thumbnail", "uri": "https://a/t.jpg"},
                                    {"sizeName": "highDef", "uri": "https://a/h.jpg"}]}
                ],
            }
        ]
    }
    cands = agencias_fotos.normalizar_afp_fotos(datos)
    assert cands[0]["url"] == "https://a/h.jpg"
    assert cands[0]["thumb"] == "https://a/t.jpg"


# --------------------------------------------------------------------------- #
# estado_fuente (gating por credencial)                                        #
# --------------------------------------------------------------------------- #


def test_estado_fuente_disponible_con_credencial(monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: True)
    estado = agencias_fotos.estado_fuente()
    assert estado == {"proveedor": "afp", "nombre": "AFP", "disponible": True, "motivo": ""}


def test_estado_fuente_pendiente_sin_credencial(monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: False)
    estado = agencias_fotos.estado_fuente()
    assert estado["disponible"] is False
    assert "credenciales de AFP" in estado["motivo"]


# --------------------------------------------------------------------------- #
# buscar (transporte inyectado, sin red)                                       #
# --------------------------------------------------------------------------- #


def test_buscar_sin_credencial_devuelve_vacio_sin_red(monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: False)
    monkeypatch.setattr(
        agencias_fotos, "_BUSCADOR", lambda q, n: pytest.fail("no debe tocar red sin credencial")
    )
    assert agencias_fotos.buscar("mundial") == []


def test_buscar_query_vacio_devuelve_vacio(monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: True)
    assert agencias_fotos.buscar("   ") == []


def test_buscar_usa_buscador_inyectable(monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: True)
    captura: dict = {}

    def _falso_buscador(query, limite):
        captura["query"] = query
        captura["limite"] = limite
        return {"response": {"docs": [
            {"title": "Gol", "creator": "Foto AFP",
             "medias": [{"role": "highdef", "href": "https://afp/g.jpg"}]}
        ]}}

    monkeypatch.setattr(agencias_fotos, "_BUSCADOR", _falso_buscador)
    cands = agencias_fotos.buscar("gol mundial", limite=3)
    assert captura == {"query": "gol mundial", "limite": 3}
    assert len(cands) == 1
    assert cands[0]["url"] == "https://afp/g.jpg"
    assert cands[0]["proveedor"] == "afp"


def test_buscar_propaga_rsserror(monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: True)

    def _boom(query, limite):
        raise agencias.rss.RSSError("AFP caída")

    monkeypatch.setattr(agencias_fotos, "_BUSCADOR", _boom)
    with pytest.raises(agencias.rss.RSSError):
        agencias_fotos.buscar("x")


# --------------------------------------------------------------------------- #
# obtener_token_afp (transporte POST inyectado)                                #
# --------------------------------------------------------------------------- #


def test_obtener_token_afp_sin_credencial_lanza(monkeypatch):
    monkeypatch.setattr(config, "afp_client_id", lambda: None)
    monkeypatch.setattr(config, "afp_client_secret", lambda: None)
    with pytest.raises(agencias.rss.RSSError):
        agencias.obtener_token_afp()


def test_obtener_token_afp_devuelve_access_token(monkeypatch):
    monkeypatch.setattr(config, "afp_client_id", lambda: "id")
    monkeypatch.setattr(config, "afp_client_secret", lambda: "secret")
    capturado: dict = {}

    def _falso_post(url, cuerpo, headers):
        capturado["url"] = url
        # El secreto viaja en el cuerpo, NUNCA se loguea ni se devuelve fuera del token.
        return '{"access_token": "tok-123", "expires_in": 900}'

    monkeypatch.setattr(agencias, "_POSTEAR", _falso_post)
    assert agencias.obtener_token_afp() == "tok-123"
    assert capturado["url"].endswith("/oauth/token")


def test_obtener_token_afp_sin_token_lanza(monkeypatch):
    monkeypatch.setattr(config, "afp_client_id", lambda: "id")
    monkeypatch.setattr(config, "afp_client_secret", lambda: "secret")
    monkeypatch.setattr(agencias, "_POSTEAR", lambda u, c, h: '{"error": "invalid_client"}')
    with pytest.raises(agencias.rss.RSSError):
        agencias.obtener_token_afp()
