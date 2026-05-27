"""Tests de la raiz de estado UNICA (`keni_consola.rutas`) y su efecto en los modulos.

Cubre (#130, servicio en contenedor):
  - Diseno/precedencia de `data_dir()`: env especifica (la resuelve el modulo) >
    `KENI_DATA_DIR` > local (`${XDG_CONFIG_HOME:-~/.config}`).
  - Con `KENI_DATA_DIR` TODO el estado cuelga de esa raiz (config bajo `keni-social/`,
    contenido editorial bajo `keni-proyectos/`, generaciones bajo `keni-social/`).
  - Sin `KENI_DATA_DIR` las rutas LOCALES no cambian (no se orfanan datos existentes).
  - WAL activo en la conexion SQLite operacional (`db.conectar`).
  - Secreto de imagen inyectado por variable de entorno.

Todo OFFLINE. Estos tests NO usan la fixture `entorno` (que fija cada `KENI_CONSOLA_*`):
limpian esas vars a proposito para ejercitar el fallback de `data_dir()`.
"""

from __future__ import annotations

import pytest

from keni_consola import (
    db,
    ficheros,
    generaciones,
    indice,
    media,
    preferencias,
    proyectos,
    rutas,
    secretos,
    sugerencias,
    termometro,
)

# Vars especificas de cada recurso (override de maxima prioridad): se LIMPIAN para
# probar el fallback a `data_dir()`. Su prioridad se prueba aparte.
_VARS_ESPECIFICAS = (
    "KENI_CONSOLA_DB",
    "KENI_CONSOLA_TAREAS",
    "KENI_CONSOLA_RAIZ",
    "KENI_CONSOLA_INDICE",
    "KENI_CONSOLA_MEDIA",
    "KENI_CONSOLA_SECRETOS",
    "KENI_CONSOLA_PREFERENCIAS",
    "KENI_CONSOLA_SUGERENCIAS",
    "KENI_CONSOLA_TERMOMETRO",
    "KENI_CONSOLA_CONFIG",
    "KENI_CONSOLA_GENERACIONES",
)


@pytest.fixture
def sin_vars(monkeypatch):
    """Limpia todas las env vars de estado para ejercitar la resolucion por `data_dir()`."""
    for var in _VARS_ESPECIFICAS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv(rutas.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)


# --------------------------------------------------------------------------- #
# data_dir(): precedencia y forma                                             #
# --------------------------------------------------------------------------- #


def test_data_dir_usa_keni_data_dir(monkeypatch, sin_vars, tmp_path):
    """Con `KENI_DATA_DIR`, `data_dir()` es esa raiz (config bajo keni-social/)."""
    monkeypatch.setenv(rutas.ENV_DATA_DIR, str(tmp_path))
    assert rutas.data_dir() == tmp_path
    assert rutas.dir_config() == tmp_path / "keni-social"
    assert rutas.raiz_proyectos() == tmp_path / "keni-proyectos"


def test_data_dir_local_respeta_xdg(monkeypatch, sin_vars, tmp_path):
    """Sin `KENI_DATA_DIR`, en local `data_dir()` cae a `${XDG_CONFIG_HOME:-~/.config}`."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert rutas.data_dir() == tmp_path / "xdg"
    assert rutas.dir_config() == tmp_path / "xdg" / "keni-social"


def test_data_dir_local_sin_xdg_es_home_config(monkeypatch, sin_vars, tmp_path):
    """Sin XDG ni `KENI_DATA_DIR`, `data_dir()` es `~/.config` (HOME controlado)."""
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    assert rutas.data_dir() == tmp_path / "casa" / ".config"
    # El contenido editorial NO cuelga de .config en local: es `~/keni-proyectos`.
    assert rutas.raiz_proyectos() == tmp_path / "casa" / "keni-proyectos"


# --------------------------------------------------------------------------- #
# Con KENI_DATA_DIR, TODO el estado cuelga de esa raiz                         #
# --------------------------------------------------------------------------- #


def test_keni_data_dir_agrupa_todo_el_estado(monkeypatch, sin_vars, tmp_path):
    """Con `KENI_DATA_DIR=/raiz`, cada recurso resuelve bajo `/raiz`."""
    raiz = tmp_path / "data"
    monkeypatch.setenv(rutas.ENV_DATA_DIR, str(raiz))

    config = raiz / "keni-social"
    assert db.ruta_db() == config / "consola.db"
    assert indice.ruta_indice() == config / "indice.sqlite"
    assert media.dir_media() == config / "media"
    assert secretos.ruta_secretos() == config / "secretos.toml"
    assert preferencias.ruta_preferencias() == config / "preferencias.toml"
    assert sugerencias.ruta_sugerencias() == config / "sugerencias.json"
    assert termometro.ruta() == config / "termometro.json"
    assert proyectos.ruta_config_consola() == config / "consola.toml"
    assert generaciones.raiz() == config / "generaciones"
    # Contenido editorial por marca: bajo keni-proyectos/ de la misma raiz.
    assert ficheros.raiz_datos() == raiz / "keni-proyectos"

    # TODAS las rutas de estado cuelgan de la raiz unica.
    for ruta_recurso in (
        db.ruta_db(), indice.ruta_indice(), media.dir_media(), secretos.ruta_secretos(),
        preferencias.ruta_preferencias(), sugerencias.ruta_sugerencias(), termometro.ruta(),
        proyectos.ruta_config_consola(), generaciones.raiz(), ficheros.raiz_datos(),
    ):
        assert ruta_recurso.is_relative_to(raiz), ruta_recurso


# --------------------------------------------------------------------------- #
# Sin KENI_DATA_DIR, las rutas LOCALES no cambian (no orfanar datos)          #
# --------------------------------------------------------------------------- #


def test_local_no_cambia_subpaths(monkeypatch, sin_vars, tmp_path):
    """En local (HOME controlado, sin XDG ni `KENI_DATA_DIR`) cada subpath es el de siempre."""
    casa = tmp_path / "casa"
    monkeypatch.setenv("HOME", str(casa))
    cfg = casa / ".config" / "keni-social"

    assert db.ruta_db() == cfg / "consola.db"
    assert indice.ruta_indice() == cfg / "indice.sqlite"
    assert media.dir_media() == cfg / "media"
    assert secretos.ruta_secretos() == cfg / "secretos.toml"
    assert preferencias.ruta_preferencias() == cfg / "preferencias.toml"
    assert sugerencias.ruta_sugerencias() == cfg / "sugerencias.json"
    assert termometro.ruta() == cfg / "termometro.json"
    assert proyectos.ruta_config_consola() == cfg / "consola.toml"
    # generaciones NO honraba XDG: es exactamente ~/.config/keni-social/generaciones.
    assert generaciones.raiz() == cfg / "generaciones"
    # Contenido editorial: ~/keni-proyectos (NO bajo .config), igual que siempre.
    assert ficheros.raiz_datos() == casa / "keni-proyectos"


def test_var_especifica_gana_a_keni_data_dir(monkeypatch, sin_vars, tmp_path):
    """La env var ESPECIFICA es override de maxima prioridad (por encima de `KENI_DATA_DIR`)."""
    monkeypatch.setenv(rutas.ENV_DATA_DIR, str(tmp_path / "data"))
    propia = tmp_path / "propia" / "consola.db"
    monkeypatch.setenv("KENI_CONSOLA_DB", str(propia))
    assert db.ruta_db() == propia


# --------------------------------------------------------------------------- #
# Concurrencia SQLite: WAL + busy_timeout activos                             #
# --------------------------------------------------------------------------- #


def test_db_conectar_wal_activo(monkeypatch, sin_vars, tmp_path):
    """`db.conectar()` deja la base en journal_mode=WAL y con busy_timeout > 0 (#130)."""
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    con = db.conectar()
    try:
        modo = con.execute("PRAGMA journal_mode").fetchone()[0]
        timeout = con.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        con.close()
    assert modo.lower() == "wal"
    assert int(timeout) >= 1000


# --------------------------------------------------------------------------- #
# Secretos por entorno (#130): inyeccion de la clave de imagen                #
# --------------------------------------------------------------------------- #


# Claves FALSAS de prueba (no son secretos reales; valores de baja entropia para que
# el escaner de secretos no las marque). El sufijo conocido sirve para probar la pista.
_CLAVE_ENV = "clave-falsa-por-entorno"
_CLAVE_OPENAI = "clave-falsa-openai"
_CLAVE_FICHERO = "clave-falsa-de-fichero"


def test_secreto_de_imagen_por_entorno(monkeypatch, tmp_path):
    """Sin fichero, la clave de imagen se inyecta por `KENI_IMAGEN_API_KEY`."""
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv(secretos.ENV_IMAGEN_PROVEEDOR, raising=False)
    monkeypatch.setenv(secretos.ENV_IMAGEN_API_KEY, _CLAVE_ENV)

    assert secretos.obtener_clave_imagen() == _CLAVE_ENV
    estado = secretos.estado_imagen()
    assert estado["configurado"] is True
    assert estado["pista"] == "····" + _CLAVE_ENV[-4:]


def test_secreto_openai_env_es_fallback(monkeypatch, tmp_path):
    """`OPENAI_API_KEY` tambien inyecta la clave (fallback historico)."""
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.delenv(secretos.ENV_IMAGEN_API_KEY, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", _CLAVE_OPENAI)
    assert secretos.obtener_clave_imagen() == _CLAVE_OPENAI


def test_fichero_gana_al_entorno(monkeypatch, tmp_path):
    """Si el fichero tiene clave, gana a la del entorno (la UI configurada manda)."""
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv(secretos.ENV_IMAGEN_API_KEY, _CLAVE_ENV)
    secretos.guardar_clave_imagen("openai", _CLAVE_FICHERO)
    assert secretos.obtener_clave_imagen() == _CLAVE_FICHERO


def test_proveedor_por_entorno(monkeypatch, tmp_path):
    """`KENI_IMAGEN_PROVEEDOR` fija el proveedor cuando no hay fichero."""
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv(secretos.ENV_IMAGEN_PROVEEDOR, "OpenRouter")
    assert secretos.obtener_proveedor_imagen() == "openrouter"


def test_secreto_no_filtra_clave_en_estado(monkeypatch, tmp_path):
    """El estado por entorno NO expone la clave entera (solo presencia + pista)."""
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv(secretos.ENV_IMAGEN_API_KEY, _CLAVE_ENV)
    estado = secretos.estado_imagen()
    assert _CLAVE_ENV not in str(estado)


def test_secretos_fichero_sigue_0600(monkeypatch, tmp_path):
    """No degradar la seguridad del fichero: nace con permisos 0600 aunque exista env."""
    ruta = tmp_path / "secretos.toml"
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(ruta))
    monkeypatch.setenv(secretos.ENV_IMAGEN_API_KEY, _CLAVE_ENV)
    secretos.guardar_clave_imagen("openai", _CLAVE_FICHERO)
    assert (ruta.stat().st_mode & 0o777) == 0o600
