"""Tests de la API Plantilla de marca (/api/plantillas-marca). Usa `entorno` (Postgres).

Se SALTA en local (sin Postgres de pruebas) y corre en CI. El store de plantillas se aisla
en tmp via `KENI_PLANTILLAS_MARCA_DIR` para no tocar `~/.config`. Cubre GET (lista + una
marca), PUT (override gana + logo_url) y errores (marca desconocida, hex invalido).
"""

from __future__ import annotations

import pytest

from keni_consola import plantillas_marca

from .conftest import _cliente


@pytest.fixture
def cli(entorno, monkeypatch, tmp_path):
    """Cliente con el store de plantillas aislado en tmp (CI; local se salta por Postgres)."""
    monkeypatch.setenv(plantillas_marca.ENV_PLANTILLAS_MARCA_DIR, str(tmp_path / "plantillas"))
    return _cliente()


def test_listar_todas_las_marcas(cli):
    r = cli.get("/api/plantillas-marca")
    assert r.status_code == 200
    plantillas = r.json()["plantillas"]
    assert set(plantillas) == {"unotv", "claro-sports", "nacion-gamer", "piso-15", "fundacion"}
    # logo_url presente y vacio cuando no hay logo.
    assert plantillas["unotv"]["logo_url"] == ""
    assert plantillas["unotv"]["rojo"] == "#E30613"


def test_obtener_una_marca(cli):
    r = cli.get("/api/plantillas-marca/claro-sports")
    assert r.status_code == 200
    p = r.json()["plantilla"]
    assert p["titular_condensada"] is True
    assert p["logo_url"] == ""


def test_obtener_marca_desconocida_404(cli):
    r = cli.get("/api/plantillas-marca/no-existe")
    assert r.status_code == 404
    assert "error" in r.json()


def test_put_guarda_y_obtiene(cli):
    r = cli.put(
        "/api/plantillas-marca/unotv",
        json={"rojo": "#222222", "etiqueta_default": "EXCLUSIVA", "logo": "abc.png",
              "logo_posicion": "inferior-derecha"},
    )
    assert r.status_code == 200
    p = r.json()["plantilla"]
    assert p["rojo"] == "#222222"
    assert p["etiqueta_default"] == "EXCLUSIVA"
    assert p["logo"] == "abc.png"
    assert p["logo_url"] == "/api/media/abc.png"  # logo subido => url servible
    # Persistio: un GET posterior lo refleja.
    g = cli.get("/api/plantillas-marca/unotv").json()["plantilla"]
    assert g["logo_posicion"] == "inferior-derecha"


def test_put_marca_desconocida_400(cli):
    r = cli.put("/api/plantillas-marca/no-existe", json={"rojo": "#FFFFFF"})
    assert r.status_code == 400


def test_put_hex_invalido_400(cli):
    r = cli.put("/api/plantillas-marca/unotv", json={"rojo": "rojo-fuerte"})
    assert r.status_code == 400
    assert "error" in r.json()


def test_put_logo_posicion_invalida_400(cli):
    r = cli.put("/api/plantillas-marca/unotv", json={"logo_posicion": "centro"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# SPEC de capas del editor visual                                             #
# --------------------------------------------------------------------------- #


def test_get_spec_devuelve_cuatro_formatos(cli):
    r = cli.get("/api/plantillas-marca/unotv/spec")
    assert r.status_code == 200
    spec = r.json()["spec"]
    # `horizontal` (16:9 de X) se añadió cuando la placa de marca pasó a componer
    # también ese lienzo (follow-up #2); antes eran tres.
    assert sorted(spec["formatos"]) == ["cuadrado", "feed", "horizontal", "vertical"]


def test_put_spec_persiste(cli):
    spec = cli.get("/api/plantillas-marca/unotv/spec").json()["spec"]
    spec["formatos"]["feed"]["logo"]["x"] = 200
    r = cli.put("/api/plantillas-marca/unotv/spec", json={"spec": spec})
    assert r.status_code == 200
    releido = cli.get("/api/plantillas-marca/unotv/spec").json()["spec"]
    assert releido["formatos"]["feed"]["logo"]["x"] == 200


def test_put_spec_invalido_400(cli):
    spec = cli.get("/api/plantillas-marca/unotv/spec").json()["spec"]
    spec["formatos"]["feed"]["fondo"] = {"tipo": "color", "color": "rojo"}
    r = cli.put("/api/plantillas-marca/unotv/spec", json={"spec": spec})
    assert r.status_code == 400


def test_get_spec_marca_desconocida_404(cli):
    r = cli.get("/api/plantillas-marca/inexistente/spec")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /preview: previa EFÍMERA del diseñador (bytes + ETag, sin persistir)     #
# --------------------------------------------------------------------------- #


def test_preview_sirve_png_efimero_con_etag(cli, monkeypatch):
    from keni_consola.dominio import estudio_imagen

    # Render mockeado (no Node) que NO persiste: devuelve bytes.
    monkeypatch.setattr(estudio_imagen, "previsualizar_spec_bytes", lambda *a, **k: b"PNG")
    spec = cli.get("/api/plantillas-marca/unotv/spec").json()["spec"]
    r = cli.post("/api/plantillas-marca/unotv/preview", json={"spec": spec, "formato": "feed"})
    assert r.status_code == 200
    assert r.content == b"PNG"
    assert r.headers["content-type"].startswith("image/png")
    assert r.headers.get("etag")


def test_preview_304_si_etag_coincide(cli, monkeypatch):
    from keni_consola.dominio import estudio_imagen

    llamadas = {"n": 0}

    def _render(*a, **k):
        llamadas["n"] += 1
        return b"PNG"

    monkeypatch.setattr(estudio_imagen, "previsualizar_spec_bytes", _render)
    spec = cli.get("/api/plantillas-marca/unotv/spec").json()["spec"]
    cuerpo = {"spec": spec, "formato": "feed"}
    r1 = cli.post("/api/plantillas-marca/unotv/preview", json=cuerpo)
    etag = r1.headers["etag"]
    r2 = cli.post(
        "/api/plantillas-marca/unotv/preview", json=cuerpo, headers={"If-None-Match": etag}
    )
    assert r2.status_code == 304
    assert llamadas["n"] == 1  # el 304 NO recompuso


def test_preview_sin_spec_400(cli):
    r = cli.post("/api/plantillas-marca/unotv/preview", json={"formato": "feed"})
    assert r.status_code == 400
