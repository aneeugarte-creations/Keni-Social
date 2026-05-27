"""Tests de la API Configuracion (/api/config). OFFLINE.

Aisla el config de metricas en tmp via `KENI_METRICAS_CONFIG` y limpia las env
vars que pisan fuente/marcas, para que el archivo sea la unica fuente de verdad.
Nada de red, nada de tokens reales.
"""

from __future__ import annotations

import tomllib

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo

_TOKEN_FALSO = "ABC123secretoquenodebeaparecer"
_CONFIG_CON_CREDENCIALES = f"""\
fuente = "muestra"
marcas = ["unotv"]

[[cuenta]]
id = "unotv"
nombre = "UnoTV"

[cuenta.plataformas]
facebook = "unotv.oficial"

[credenciales.meta]
access_token = "{_TOKEN_FALSO}"
tipo_token = "system_user"
"""


@pytest.fixture
def cfg_metricas(monkeypatch, tmp_path):
    """Aisla el config de metricas en tmp; sin env vars que pisen fuente/marcas."""
    ruta = tmp_path / "config.toml"
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_PREFERENCIAS", str(tmp_path / "preferencias.toml"))
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    return ruta


def _cli() -> TestClient:
    # Token de sesion (#134): fijamos el de prueba y lo mandamos por defecto, igual que
    # el `_cliente` de conftest, para que la API pase la barrera de auth.
    from .conftest import TOKEN_PRUEBA

    return TestClient(
        app_modulo.crear_app(abrir=lambda _r: "ok-mock", token=TOKEN_PRUEBA),
        headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"},
    )


def _escribir(ruta, contenido: str) -> None:
    ruta.write_text(contenido, encoding="utf-8")


# --------------------------------------------------------------------------- #
# GET /api/config                                                             #
# --------------------------------------------------------------------------- #


def test_get_config_contrato(cfg_metricas):
    _escribir(cfg_metricas, _CONFIG_CON_CREDENCIALES)
    datos = _cli().get("/api/config").json()
    assert set(datos) == {
        "fuente",
        "fuentes_validas",
        "marcas",
        "marcas_disponibles",
        "credenciales_presentes",
    }
    assert datos["fuente"] == "muestra"
    assert set(datos["fuentes_validas"]) == {"muestra", "real"}
    assert datos["marcas"] == ["unotv"]
    # marcas_disponibles: lista de {id, nombre}.
    ids = {m["id"] for m in datos["marcas_disponibles"]}
    assert "unotv" in ids
    # credenciales_presentes: bool por bloque.
    creds = datos["credenciales_presentes"]
    assert set(creds) == {"meta", "youtube", "x", "tiktok"}
    assert creds["meta"] is True
    assert creds["youtube"] is False


def test_get_config_no_expone_token(cfg_metricas):
    _escribir(cfg_metricas, _CONFIG_CON_CREDENCIALES)
    texto = _cli().get("/api/config").text
    assert _TOKEN_FALSO not in texto


def test_get_config_marcas_con_etiqueta_humana(cfg_metricas):
    _escribir(
        cfg_metricas,
        'fuente = "muestra"\n\n[[cuenta]]\nid = "nacion_gamer"\nnombre = "Nacion Gamer"\n',
    )
    datos = _cli().get("/api/config").json()
    nombres = {m["id"]: m["nombre"] for m in datos["marcas_disponibles"]}
    assert nombres["nacion_gamer"] == "Nación Gamer"


def test_placeholder_no_cuenta_como_conectada(cfg_metricas):
    _escribir(
        cfg_metricas,
        'fuente = "real"\n\n[credenciales.meta]\naccess_token = "PENDIENTE_PON_TU_TOKEN_AQUI"\n',
    )
    datos = _cli().get("/api/config").json()
    assert datos["credenciales_presentes"]["meta"] is False


# --------------------------------------------------------------------------- #
# POST /api/config                                                            #
# --------------------------------------------------------------------------- #


def test_post_cambia_fuente_y_alcance(cfg_metricas):
    _escribir(cfg_metricas, 'fuente = "muestra"\n')
    c = _cli()
    r = c.post("/api/config", json={"fuente": "real", "marcas": ["unotv", "claro_sports"]})
    assert r.status_code == 200
    assert "guardada" in r.json()["mensaje"].lower()
    datos = tomllib.loads(cfg_metricas.read_text(encoding="utf-8"))
    assert datos["fuente"] == "real"
    assert datos["marcas"] == ["unotv", "claro_sports"]


def test_post_alcance_vacio_borra_marcas(cfg_metricas):
    _escribir(cfg_metricas, 'fuente = "muestra"\nmarcas = ["unotv"]\n')
    r = _cli().post("/api/config", json={"fuente": "muestra", "marcas": []})
    assert r.status_code == 200
    datos = tomllib.loads(cfg_metricas.read_text(encoding="utf-8"))
    assert "marcas" not in datos


def test_post_preserva_credenciales_y_cuentas(cfg_metricas):
    _escribir(cfg_metricas, _CONFIG_CON_CREDENCIALES)
    r = _cli().post("/api/config", json={"fuente": "real", "marcas": ["unotv"]})
    assert r.status_code == 200
    datos = tomllib.loads(cfg_metricas.read_text(encoding="utf-8"))
    assert datos["credenciales"]["meta"]["access_token"] == _TOKEN_FALSO
    assert datos["cuenta"][0]["id"] == "unotv"
    assert datos["fuente"] == "real"


def test_post_archivo_0600(cfg_metricas):
    _escribir(cfg_metricas, _CONFIG_CON_CREDENCIALES)
    _cli().post("/api/config", json={"fuente": "real", "marcas": ["unotv"]})
    assert (cfg_metricas.stat().st_mode & 0o777) == 0o600


def test_post_fuente_invalida_400(cfg_metricas):
    _escribir(cfg_metricas, 'fuente = "muestra"\n')
    r = _cli().post("/api/config", json={"fuente": "inventada", "marcas": []})
    assert r.status_code == 400
    assert "fuente" in r.json()["error"].lower()


def test_post_marca_desconocida_400(cfg_metricas):
    _escribir(cfg_metricas, 'fuente = "muestra"\n')
    r = _cli().post("/api/config", json={"fuente": "muestra", "marcas": ["marca_que_no_existe"]})
    assert r.status_code == 400
    assert "desconocida" in r.json()["error"].lower()


def test_post_body_invalido_400(cfg_metricas):
    r = _cli().post(
        "/api/config", content=b"no-json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400


def test_post_marcas_no_lista_400(cfg_metricas):
    _escribir(cfg_metricas, 'fuente = "muestra"\n')
    r = _cli().post("/api/config", json={"fuente": "muestra", "marcas": "unotv"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Esfuerzo de generacion (/api/config/esfuerzo)                               #
# --------------------------------------------------------------------------- #


def test_get_esfuerzo_contrato(cfg_metricas):
    datos = _cli().get("/api/config/esfuerzo").json()
    assert set(datos) == {"esfuerzo", "opciones"}
    assert datos["esfuerzo"] == ""  # predeterminado: sin --effort
    ids = [o["id"] for o in datos["opciones"]]
    assert ids == ["", "low", "medium", "high", "xhigh", "max"]
    # Cada opcion trae etiqueta y descripcion legibles.
    for o in datos["opciones"]:
        assert o["etiqueta"] and o["descripcion"]


def test_post_esfuerzo_guarda_y_se_refleja(cfg_metricas):
    c = _cli()
    r = c.post("/api/config/esfuerzo", json={"esfuerzo": "high"})
    assert r.status_code == 200
    assert r.json()["esfuerzo"] == "high"
    assert "Alto" in r.json()["mensaje"]
    assert c.get("/api/config/esfuerzo").json()["esfuerzo"] == "high"


def test_post_esfuerzo_vacio_vuelve_a_predeterminado(cfg_metricas):
    c = _cli()
    c.post("/api/config/esfuerzo", json={"esfuerzo": "max"})
    r = c.post("/api/config/esfuerzo", json={"esfuerzo": ""})
    assert r.status_code == 200
    assert r.json()["esfuerzo"] == ""
    assert c.get("/api/config/esfuerzo").json()["esfuerzo"] == ""


def test_post_esfuerzo_invalido_400(cfg_metricas):
    r = _cli().post("/api/config/esfuerzo", json={"esfuerzo": "turbo"})
    assert r.status_code == 400
    assert "inválido" in r.json()["error"].lower()


def test_post_esfuerzo_no_texto_400(cfg_metricas):
    r = _cli().post("/api/config/esfuerzo", json={"esfuerzo": 5})
    assert r.status_code == 400
