"""Tests del store EDITABLE de ajustes (`keni_consola.ajustes`).

Cubre leer/guardar/borrar, escritura atomica, lectura tolerante a TOML corrupto y la
cache invalidada por mtime. Todo aislado en tmp via `KENI_CONSOLA_AJUSTES` (sin DB ni red).
"""

from __future__ import annotations

import os

import pytest

from keni_consola import ajustes


@pytest.fixture
def store(monkeypatch, tmp_path):
    """Aisla el archivo de ajustes en tmp y limpia la cache de modulo entre tests."""
    ruta = tmp_path / "ajustes.toml"
    monkeypatch.setenv("KENI_CONSOLA_AJUSTES", str(ruta))
    # Invalida la cache de modulo (otros tests pudieron cebarla con otra ruta).
    ajustes._CACHE_RUTA = None
    ajustes._CACHE_MTIME = -1.0
    ajustes._CACHE_DATOS = {}
    return ruta


def test_leer_vacio_por_defecto(store):
    assert ajustes.leer() == {}
    assert ajustes.obtener("KENI_AUTOGEN") is None


def test_guardar_y_obtener(store):
    ajustes.guardar("KENI_AUTOGEN", "1")
    assert ajustes.obtener("KENI_AUTOGEN") == "1"
    assert ajustes.leer() == {"KENI_AUTOGEN": "1"}
    assert store.exists()


def test_guardar_clave_por_marca_no_corrompe_el_store(store):
    """Regresion: una clave con `::` (excepcion por marca, p.ej. `KENI_PIPELINE::unotv`)
    debe round-trippear por el FICHERO real. El bug: la clave se escribia desnuda, y `::`
    es invalido en una clave TOML -> `tomllib` fallaba al parsear TODO el fichero ->
    `_leer_disco` devolvia {} -> el siguiente guardado borraba las demas claves."""
    ajustes.guardar("KENI_MAQUINA", "1")
    ajustes.guardar("KENI_PIPELINE", "1")
    ajustes.guardar("KENI_PIPELINE::unotv", "1")
    # El fichero sigue siendo TOML valido y conserva las tres claves.
    assert ajustes.leer() == {
        "KENI_MAQUINA": "1",
        "KENI_PIPELINE": "1",
        "KENI_PIPELINE::unotv": "1",
    }
    # Y un guardado posterior NO borra las anteriores (antes: leer()->{}->wipe).
    ajustes.guardar("KENI_AUTOGEN_ARTE", "1")
    assert ajustes.obtener("KENI_MAQUINA") == "1"
    assert ajustes.obtener("KENI_PIPELINE::unotv") == "1"
    assert ajustes.obtener("KENI_AUTOGEN_ARTE") == "1"


def test_guardar_sobrescribe(store):
    ajustes.guardar("KENI_MAX_JOBS", "4")
    ajustes.guardar("KENI_MAX_JOBS", "8")
    assert ajustes.obtener("KENI_MAX_JOBS") == "8"


def test_guardar_varias_claves(store):
    ajustes.guardar("KENI_AUTOGEN", "1")
    ajustes.guardar("KENI_AUTOGEN_MAX", "5")
    assert ajustes.leer() == {"KENI_AUTOGEN": "1", "KENI_AUTOGEN_MAX": "5"}


def test_borrar(store):
    ajustes.guardar("KENI_AUTOGEN", "1")
    ajustes.borrar("KENI_AUTOGEN")
    assert ajustes.obtener("KENI_AUTOGEN") is None
    assert ajustes.leer() == {}


def test_borrar_inexistente_no_falla(store):
    ajustes.borrar("KENI_AUTOGEN")  # no-op
    assert ajustes.leer() == {}


def test_leer_devuelve_copia(store):
    ajustes.guardar("KENI_AUTOGEN", "1")
    d = ajustes.leer()
    d["KENI_AUTOGEN"] = "0"  # mutar la copia no toca el store
    assert ajustes.obtener("KENI_AUTOGEN") == "1"


def test_lectura_tolerante_a_toml_corrupto(store):
    store.write_text("esto no es toml = = =", encoding="utf-8")
    ajustes._CACHE_MTIME = -1.0  # fuerza relectura
    assert ajustes.leer() == {}


def test_ignora_valores_no_str(store):
    # Solo claves de nivel raiz con valor texto cuentan (lectura tolerante).
    store.write_text('KENI_AUTOGEN = "1"\nKENI_OTRO = 5\n', encoding="utf-8")
    ajustes._CACHE_MTIME = -1.0
    assert ajustes.leer() == {"KENI_AUTOGEN": "1"}


def test_serializa_con_escape(store):
    # Un valor con comillas/espacios se persiste y relee intacto (TOML basic string escapado).
    ajustes.guardar("KENI_RADAR_AUTO_MARCA", 'con "comillas"')
    ajustes._CACHE_MTIME = -1.0
    assert ajustes.obtener("KENI_RADAR_AUTO_MARCA") == 'con "comillas"'


def test_cache_invalida_por_mtime(store):
    ajustes.guardar("KENI_AUTOGEN", "1")
    assert ajustes.obtener("KENI_AUTOGEN") == "1"
    # Reescribe el fichero POR FUERA (otro proceso) con un mtime futuro y sin tocar la cache.
    store.write_text(ajustes._CABECERA + 'KENI_AUTOGEN = "0"\n', encoding="utf-8")
    futuro = store.stat().st_mtime + 100
    os.utime(store, (futuro, futuro))
    # La cache se invalida por el mtime distinto: ve el valor nuevo del disco.
    assert ajustes.obtener("KENI_AUTOGEN") == "0"


def test_cache_no_relee_si_mtime_igual(store, monkeypatch):
    ajustes.guardar("KENI_AUTOGEN", "1")
    ajustes.leer()  # ceba la cache
    # Si nadie tocara el disco, una segunda lectura NO debe volver a parsear el fichero.
    llamadas = {"n": 0}
    original = ajustes._leer_disco

    def espia(ruta):
        llamadas["n"] += 1
        return original(ruta)

    monkeypatch.setattr(ajustes, "_leer_disco", espia)
    ajustes.leer()
    ajustes.leer()
    assert llamadas["n"] == 0  # mtime no cambio: no se releyo el disco
