"""Fixtures compartidas de los tests de la Consola Keni (API JSON). Todo OFFLINE.

Aisla en `tmp_path` (env vars) toda la persistencia y configuracion para que
ningun test toque el disco real del usuario:
  - `KENI_CONSOLA_CONFIG`  -> consola.toml (allowlist de proyectos)
  - `KENI_CONSOLA_DB`      -> consola.db (SQLite: tareas + historial de skills)
  - `KENI_CONSOLA_RAIZ`    -> raiz de datos del backend de ficheros (YAML por marca)
  - `KENI_CONSOLA_INDICE`  -> indice SQLite regenerable del backend de ficheros
  - `KENI_CONSOLA_TAREAS`  -> tareas.json (solo para probar la migracion)
  - `KENI_CONSOLA_MEDIA`   -> dir de media (imagenes) aislado en tmp
  - `KENI_CONSOLA_SECRETOS`-> almacen de secretos (clave de imagen) aislado en tmp
  - `KENI_METRICAS_CONFIG` -> apunta a un archivo inexistente => fuente de muestra
  - `KENI_SKILLS_CWD`      -> cwd valido para skills (no toca el repo real)

Tambien BORRA `OPENAI_API_KEY` para que, por defecto, la generacion de imagen este
"no configurada" (camino 400). Los tests que prueban un proveedor lo parchean.

Nada de red, nada de tokens reales, nunca se llama a `claude` (el runner se mockea).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Config + DB aisladas en tmp; metricas offline (fuente de muestra)."""
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(tmp_path / "datos"))
    monkeypatch.setenv("KENI_CONSOLA_INDICE", str(tmp_path / "indice.sqlite"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    monkeypatch.setenv("KENI_SKILLS_CWD", str(tmp_path))
    return tmp_path


def _cliente(abrir=None) -> TestClient:
    """TestClient de la app. `abrir` por defecto NO lanza nada real (mock)."""
    if abrir is None:
        def abrir(_ruta):  # noqa: ANN001
            return "ok-mock"

    return TestClient(app_modulo.crear_app(abrir=abrir))


@pytest.fixture
def cliente(entorno):
    """TestClient listo con el entorno aislado (mock de `abrir` inofensivo)."""
    return _cliente()
