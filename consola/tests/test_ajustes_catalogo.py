"""Tests del catalogo de ajustes (`keni_consola.ajustes_catalogo`) + precedencia en config.

Cubre la serializacion (valor efectivo + fuente con store/env/defecto), `validar_valor`
por tipo/min/max/select, y la precedencia STORE > ENV > DEFECTO via `config._crudo`. Todo
aislado con monkeypatch de env y del store (sin DB ni red).
"""

from __future__ import annotations

import pytest

from keni_consola import ajustes, ajustes_catalogo, config


@pytest.fixture
def store(monkeypatch, tmp_path):
    """Aisla el store en tmp y limpia su cache de modulo."""
    ruta = tmp_path / "ajustes.toml"
    monkeypatch.setenv("KENI_CONSOLA_AJUSTES", str(ruta))
    ajustes._CACHE_RUTA = None
    ajustes._CACHE_MTIME = -1.0
    ajustes._CACHE_DATOS = {}
    return ruta


def _ajuste(clave):
    a = ajustes_catalogo.por_clave(clave)
    assert a is not None
    return a


# --------------------------------------------------------------------------- #
# Catalogo basico                                                              #
# --------------------------------------------------------------------------- #


def test_catalogo_tiene_las_claves_esperadas(store):
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    esperadas = {
        # Interruptor general de la máquina de contenido (kill-switch global).
        config.ENV_MAQUINA,
        # Maestros de etapa (uno por etapa de auto-producción).
        config.ENV_PIPELINE, config.ENV_AUTOGEN, config.ENV_AUTOGEN_ARTE, config.ENV_AUTO_AVANCE,
        config.ENV_ALERTAS_ACTIVAS, config.ENV_EVENTOS_VENCIMIENTOS,
        config.ENV_AUTO_PREAPROBACION, config.ENV_PUBLICAR_REAL,
        config.ENV_AUTOGEN_INTERVALO_HORAS, config.ENV_AUTOGEN_MAX,
        config.ENV_AUTOGEN_ARTE_INTERVALO_HORAS, config.ENV_AUTOGEN_ARTE_MAX,
        config.ENV_RADAR_AUTO_GEO,
        config.ENV_ALERTAS_INTERVALO_HORAS, config.ENV_ALERTAS_UMBRAL_ENGAGEMENT,
        config.ENV_MAX_JOBS,
        config.ENV_MEDIA_GC, config.ENV_MEDIA_GC_INTERVALO_HORAS,
        config.ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
        config.ENV_PIPELINE_LINEAS,
        # Motor de noticias (Olas A–D + Ola 6) — toggles bool.
        config.ENV_INGESTA,
        config.ENV_TRADUCCION,
        config.ENV_BREAKING,
        config.ENV_INVESTIGACION,
        # Auto-feed (Ola E) — toggle bool + tuning int/float (el tope por marca se genera aparte).
        config.ENV_AUTOFEED,
        config.ENV_AUTOFEED_INTERVALO_MIN, config.ENV_AUTOFEED_UMBRAL, config.ENV_AUTOFEED_CAP,
        # (El motor de video — render ffmpeg + transcripción ASR — es local/gratuito/bajo-demanda:
        #  NO tiene toggles en el catálogo.)
        # Motor de noticias — tuning int/float.
        config.ENV_INGESTA_BATCH, config.ENV_INGESTA_WORKERS,
        config.ENV_INGESTA_MAX_ITEMS, config.ENV_INGESTA_MAX_ERRORES,
        config.ENV_CLUSTER_VENTANA_H, config.ENV_CLUSTER_BREAKING_FUENTES,
        config.ENV_CLUSTER_BREAKING_VENTANA_H,
        config.ENV_BREAKING_INTERVALO_MIN, config.ENV_BREAKING_MAX,
        config.ENV_TRAD_MIN_SCORE, config.ENV_TRAD_LOTE,
        config.ENV_FEED_SLA_MIN,
        config.ENV_INVESTIGACION_INTERVALO_HORAS, config.ENV_INVESTIGACION_MAX,
    }
    # Los toggles por marca (clave `ENV::marca`) se generan en caliente; el resto del catálogo
    # son exactamente las claves globales esperadas.
    por_marca = {c for c in claves if config.SEP_MARCA in c}
    assert claves - por_marca == esperadas
    assert por_marca, "deben existir toggles de auto-producción por marca"


def test_motor_noticias_bool_toggles(store):
    """Los cuatro toggles del motor de noticias son bool, pertenecen al grupo correcto
    y tienen el defecto esperado (toda la máquina de contenido OFF por defecto)."""
    esperados = {
        config.ENV_INGESTA: (False, "automatismos_generales"),
        config.ENV_TRADUCCION: (False, "automatismos_generales"),
        config.ENV_BREAKING: (False, "automatismos_generales"),
        config.ENV_INVESTIGACION: (False, "automatismos_generales"),
    }
    for clave, (defecto, grupo) in esperados.items():
        a = ajustes_catalogo.por_clave(clave)
        assert a is not None, f"falta la clave {clave}"
        assert a.tipo == "bool", f"{clave} debe ser bool"
        assert a.defecto == defecto, f"{clave} defecto esperado {defecto}, got {a.defecto}"
        assert a.grupo == grupo, f"{clave} grupo esperado {grupo}"


def test_maquina_global_kill_switch(store):
    """El interruptor general es un bool en el grupo `maquina_global`, defecto False, y ese
    grupo va PRIMERO en GRUPOS (se pinta arriba del todo en la pestaña Básica)."""
    a = ajustes_catalogo.por_clave(config.ENV_MAQUINA)
    assert a is not None, "falta el interruptor general KENI_MAQUINA"
    assert a.tipo == "bool"
    assert a.defecto is False
    assert a.grupo == "maquina_global"
    assert ajustes_catalogo.GRUPOS[0][0] == "maquina_global", (
        "el grupo del interruptor general debe ir primero en GRUPOS"
    )


def test_motor_noticias_tuning_int(store):
    """Los knobs de tuning del motor de noticias son int con minimo >= 1."""
    claves_int = [
        config.ENV_INGESTA_BATCH,
        config.ENV_INGESTA_WORKERS,
        config.ENV_INGESTA_MAX_ITEMS,
        config.ENV_INGESTA_MAX_ERRORES,
        config.ENV_CLUSTER_VENTANA_H,
        config.ENV_CLUSTER_BREAKING_FUENTES,
        config.ENV_CLUSTER_BREAKING_VENTANA_H,
        config.ENV_BREAKING_INTERVALO_MIN,
        config.ENV_BREAKING_MAX,
        config.ENV_TRAD_LOTE,
        config.ENV_FEED_SLA_MIN,
        config.ENV_INVESTIGACION_INTERVALO_HORAS,
        config.ENV_INVESTIGACION_MAX,
    ]
    for clave in claves_int:
        a = ajustes_catalogo.por_clave(clave)
        assert a is not None, f"falta la clave {clave}"
        assert a.tipo == "int", f"{clave} debe ser int"
        assert a.grupo == "tuning", f"{clave} debe estar en grupo tuning"
        assert a.minimo is not None and a.minimo >= 1, f"{clave} debe tener minimo >= 1"


def test_motor_noticias_trad_min_score_float(store):
    """KENI_TRAD_MIN_SCORE es float en el grupo tuning con minimo 0."""
    a = ajustes_catalogo.por_clave(config.ENV_TRAD_MIN_SCORE)
    assert a is not None
    assert a.tipo == "float"
    assert a.grupo == "tuning"
    assert a.minimo == 0


def test_publicar_real_es_peligroso(store):
    assert _ajuste(config.ENV_PUBLICAR_REAL).peligroso is True
    assert _ajuste(config.ENV_AUTOGEN).peligroso is False


def test_por_clave_desconocida(store):
    assert ajustes_catalogo.por_clave("KENI_NO_EXISTE") is None


# --------------------------------------------------------------------------- #
# valor_y_fuente: precedencia store > env > defecto                            #
# --------------------------------------------------------------------------- #


def test_valor_defecto_sin_store_ni_env(store, monkeypatch):
    monkeypatch.delenv(config.ENV_MAX_JOBS, raising=False)
    a = _ajuste(config.ENV_MAX_JOBS)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert (valor, fuente) == (config.MAX_JOBS_DEF, "defecto")


def test_valor_desde_env(store, monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_JOBS, "8")
    a = _ajuste(config.ENV_MAX_JOBS)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert (valor, fuente) == (8, "env")


def test_valor_desde_store_gana_a_env(store, monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_JOBS, "8")
    ajustes.guardar(config.ENV_MAX_JOBS, "2")
    a = _ajuste(config.ENV_MAX_JOBS)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert (valor, fuente) == (2, "store")


def test_bool_efectivo_tipado(store, monkeypatch):
    monkeypatch.setenv(config.ENV_AUTOGEN, "1")
    a = _ajuste(config.ENV_AUTOGEN)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert valor is True and fuente == "env"


def test_float_efectivo_tipado(store):
    ajustes.guardar(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT, "2.5")
    a = _ajuste(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert valor == 2.5 and fuente == "store"


def test_select_geo_efectivo(store):
    ajustes.guardar(config.ENV_RADAR_AUTO_GEO, "US")
    a = _ajuste(config.ENV_RADAR_AUTO_GEO)
    valor, _ = ajustes_catalogo.valor_y_fuente(a)
    assert valor == "US"


# --------------------------------------------------------------------------- #
# a_dict: forma del contrato                                                   #
# --------------------------------------------------------------------------- #


def test_a_dict_int_tiene_min(store):
    d = ajustes_catalogo.a_dict(_ajuste(config.ENV_MAX_JOBS))
    assert d["tipo"] == "int" and d["min"] == 1 and "opciones" not in d
    assert set(d) >= {"clave", "tipo", "etiqueta", "ayuda", "grupo", "peligroso",
                      "valor", "fuente", "defecto"}


def test_a_dict_select_tiene_opciones(store):
    d = ajustes_catalogo.a_dict(_ajuste(config.ENV_RADAR_AUTO_GEO))
    assert d["tipo"] == "select"
    assert {"id": "MX", "etiqueta": "México"} in d["opciones"]
    assert "min" not in d


def test_a_dict_bool_sin_min_ni_opciones(store):
    d = ajustes_catalogo.a_dict(_ajuste(config.ENV_AUTOGEN))
    assert d["tipo"] == "bool" and "min" not in d and "opciones" not in d


# --------------------------------------------------------------------------- #
# validar_valor por tipo                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entrada,guardado", [
    (True, "1"), (False, "0"), (1, "1"), (0, "0"),
    ("true", "1"), ("0", "0"), ("YES", "1"), ("off", "0"),
])
def test_validar_bool_ok(store, entrada, guardado):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN), entrada)
    assert err is None and val == guardado


def test_validar_bool_invalido(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN), "quizas")
    assert val is None and err is not None


def test_validar_int_ok(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_MAX), 5)
    assert err is None and val == "5"


def test_validar_int_acepta_str(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_MAX), " 7 ")
    assert err is None and val == "7"


def test_validar_int_bajo_minimo(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_MAX), 0)
    assert val is None and "≥ 1" in err


def test_validar_int_rechaza_bool(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_MAX), True)
    assert val is None and err is not None


def test_validar_int_no_numerico(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_MAX), "x")
    assert val is None and err is not None


def test_validar_float_ok(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT), 3.0)
    assert err is None and float(val) == 3.0


def test_validar_float_bajo_minimo(store):
    val, err = ajustes_catalogo.validar_valor(
        _ajuste(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT), -1
    )
    assert val is None and err is not None


def test_validar_select_ok(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_RADAR_AUTO_GEO), "AR")
    assert err is None and val == "AR"


def test_validar_select_normaliza_geo(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_RADAR_AUTO_GEO), "mx")
    assert err is None and val == "MX"


def test_validar_select_invalido(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_RADAR_AUTO_GEO), "ZZ")
    assert val is None and err is not None


# --------------------------------------------------------------------------- #
# Precedencia efectiva via config._crudo (lo que ven los accesores)            #
# --------------------------------------------------------------------------- #


def test_config_crudo_store_gana_a_env(store, monkeypatch):
    monkeypatch.setenv(config.ENV_AUTOGEN, "0")
    ajustes.guardar(config.ENV_AUTOGEN, "1")
    assert config._crudo(config.ENV_AUTOGEN) == "1"
    assert config.autogen_activo() is True  # accesor bool ve el store


def test_config_crudo_cae_a_env_sin_store(store, monkeypatch):
    monkeypatch.setenv(config.ENV_AUTOGEN, "1")
    assert config._crudo(config.ENV_AUTOGEN) == "1"
    assert config.autogen_activo() is True


def test_config_entero_pasa_por_store(store, monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_JOBS, "8")
    ajustes.guardar(config.ENV_MAX_JOBS, "2")
    assert config.max_jobs() == 2  # _entero -> _crudo -> store


def test_config_float_pasa_por_store(store):
    ajustes.guardar(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT, "4.5")
    assert config.alertas_umbral_engagement() == 4.5
