"""API `/api/fotos`: el lanzador de la herramienta local + el endpoint del auto-update Tauri.

Cubre el contrato del updater (`tauri-plugin-updater`):
  - 204 si la versión instalada ya es la última (o mayor); 200 con el JSON Tauri si va por detrás.
  - 204 para una plataforma que no servimos (solo `darwin-aarch64` hoy).
  - Es PUBLICO: la app lo poletea SIN sesión (no debe dar 401).

El manifiesto de release se aísla en `tmp_path` con `KENI_FOTOS_RELEASE` (no depende del
placeholder versionado). Reusa `entorno` para el aislamiento estándar de la Consola.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

_BEARER = {"Authorization": f"Bearer {TOKEN_PRUEBA}"}
# Origin del mismo host (TestClient): pasa la barrera CSRF de las mutaciones.
_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba-123"

_RELEASE = {
    "version": "0.2.0",
    "notes": "Segunda versión.",
    "pub_date": "2026-06-24T00:00:00Z",
    "darwin-aarch64": {
        "signature": "FIRMA-MINISIGN",
        "url": "https://social.kenitech.io/media/fotos/releases/0.2.0/keni-fotos.app.tar.gz",
    },
}


def _con_release(monkeypatch, tmp_path: Path, datos: dict) -> None:
    """Escribe un manifiesto de release en tmp y apunta `KENI_FOTOS_RELEASE` a él."""
    ruta = tmp_path / "release.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    monkeypatch.setenv("KENI_FOTOS_RELEASE", str(ruta))


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA), headers=_BEARER)


def test_actualizacion_version_vieja_da_json_tauri(entorno, monkeypatch, tmp_path):
    """Instalada por detrás del manifiesto -> 200 con el JSON Tauri de la plataforma."""
    _con_release(monkeypatch, tmp_path, _RELEASE)
    r = _cli().get("/api/fotos/actualizacion/darwin/aarch64/0.1.0")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["version"] == "0.2.0"
    assert cuerpo["notes"] == "Segunda versión."
    assert cuerpo["pub_date"] == "2026-06-24T00:00:00Z"
    plat = cuerpo["platforms"]["darwin-aarch64"]
    assert plat["signature"] == "FIRMA-MINISIGN"
    assert plat["url"].endswith("/keni-fotos.app.tar.gz")


def test_actualizacion_misma_version_da_204(entorno, monkeypatch, tmp_path):
    """Instalada == manifiesto -> 204 (no hay update)."""
    _con_release(monkeypatch, tmp_path, _RELEASE)
    assert _cli().get("/api/fotos/actualizacion/darwin/aarch64/0.2.0").status_code == 204


def test_actualizacion_version_mas_nueva_da_204(entorno, monkeypatch, tmp_path):
    """Instalada > manifiesto (build adelantada) -> 204, no se ofrece un downgrade."""
    _con_release(monkeypatch, tmp_path, _RELEASE)
    assert _cli().get("/api/fotos/actualizacion/darwin/aarch64/0.3.0").status_code == 204


def test_actualizacion_plataforma_desconocida_da_204(entorno, monkeypatch, tmp_path):
    """Plataforma que no servimos (p.ej. windows-x86_64) -> 204, aunque haya versión nueva."""
    _con_release(monkeypatch, tmp_path, _RELEASE)
    assert _cli().get("/api/fotos/actualizacion/windows/x86_64/0.1.0").status_code == 204


def test_actualizacion_version_no_numerica_da_204(entorno, monkeypatch, tmp_path):
    """Una versión instalada ilegible se trata como «sin update» (204), no casca."""
    _con_release(monkeypatch, tmp_path, _RELEASE)
    assert _cli().get("/api/fotos/actualizacion/darwin/aarch64/no-es-version").status_code == 204


def test_actualizacion_es_publica_sin_sesion(entorno, monkeypatch, tmp_path):
    """La app poletea el updater SIN sesión: nunca 401. Aquí, con versión vieja -> 200."""
    _con_release(monkeypatch, tmp_path, _RELEASE)
    cli = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))  # sin cabecera de auth
    r = cli.get("/api/fotos/actualizacion/darwin/aarch64/0.1.0")
    assert r.status_code == 200


def test_fotos_descarga_sigue_exigiendo_sesion(entorno, monkeypatch, tmp_path):
    """El resto de `/api/fotos` NO es público: sin sesión -> 401 (solo lo abre el updater)."""
    _con_release(monkeypatch, tmp_path, _RELEASE)
    cli = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))  # sin cabecera de auth
    assert cli.get("/api/fotos/app").status_code == 401


# --------------------------------------------------------------------------- #
# Login OPCIONAL del escritorio keni-fotos (flujo loopback)                     #
# --------------------------------------------------------------------------- #


def _cli_sesion(usuario: str = "ale") -> TestClient:
    """TestClient con SESION real (login) para los endpoints que exigen usuario."""
    auth.crear_usuario(usuario, _CLAVE, "editor")
    cli = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = cli.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return cli


def test_autorizar_emite_token_validable_por_el_escritorio(entorno):
    """`POST /fotos/autorizar` con sesión emite un token y devuelve la URL loopback de retorno;
    ese token identifica al escritorio en `GET /fotos/sesion` SIN credencial de Consola."""
    cli = _cli_sesion()
    r = cli.post(
        "/api/fotos/autorizar",
        json={"cb": "http://127.0.0.1:54321/cb", "state": "abc123"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    redirect = r.json()["redirect"]
    assert redirect.startswith("http://127.0.0.1:54321/cb?")
    consulta = parse_qs(urlsplit(redirect).query)
    assert consulta["state"] == ["abc123"]
    token = consulta["token"][0]

    # Cliente del ESCRITORIO: sin cookie de sesión ni token de Consola, solo el token opaco.
    escritorio = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    s = escritorio.get("/api/fotos/sesion", headers={"Authorization": f"Bearer {token}"})
    assert s.status_code == 200
    assert s.json()["usuario"]["usuario"] == "ale"


def test_autorizar_rechaza_cb_no_loopback(entorno):
    """Un `cb` con host remoto (anti open-redirect) -> 400, no se emite token."""
    cli = _cli_sesion()
    r = cli.post(
        "/api/fotos/autorizar",
        json={"cb": "https://evil.example.com/cb", "state": "abc123"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_autorizar_exige_sesion_real(entorno):
    """Por el TOKEN de mantenimiento no hay usuario: no se puede emitir token de escritorio -> 401."""
    cli = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA), headers=_BEARER)
    r = cli.post(
        "/api/fotos/autorizar",
        json={"cb": "http://127.0.0.1:1/cb", "state": "x"},
        headers=_ORIGIN,
    )
    assert r.status_code == 401


def test_sesion_es_publica_pero_exige_token_valido(entorno):
    """`GET /fotos/sesion` no exige credencial de Consola (pasa el middleware), pero un token de
    escritorio ausente o inválido da su propio 401."""
    cli = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))  # sin auth de Consola
    assert cli.get("/api/fotos/sesion").status_code == 401
    assert cli.get(
        "/api/fotos/sesion", headers={"Authorization": "Bearer no-existe"}
    ).status_code == 401
