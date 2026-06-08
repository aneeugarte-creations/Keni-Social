"""Tests del catalogo de ajustes (`keni_consola.ajustes_catalogo`) + precedencia en config.

Cubre la serializacion (valor efectivo + fuente con store/env/defecto), `validar_valor`
por tipo/min/max, y la precedencia STORE > ENV > DEFECTO via `config._crudo`. Todo
aislado con monkeypatch de env y del store (sin DB ni red).

Modelo de máquina de contenido: 1 master (KENI_MAQUINA) + 4 etapas (KENI_INGESTA "Crear
noticias", KENI_QA "Validar (QA)", KENI_PIPELINE "Generar copy", KENI_AUTOGEN_ARTE "Generar
arte"). Las cuatro tienen excepción por marca (1 toggle = 1 etapa).
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
        # Las 4 etapas (maestros): Crear noticias / Validar (QA) / Generar copy / Generar arte.
        config.ENV_INGESTA, config.ENV_QA, config.ENV_PIPELINE, config.ENV_AUTOGEN_ARTE,
        # Automatismos generales (barridos de mantenimiento).
        config.ENV_ALERTAS_ACTIVAS, config.ENV_EVENTOS_VENCIMIENTOS,
        config.ENV_AUTO_PREAPROBACION, config.ENV_MEDIA_GC,
        config.ENV_PUBLICAR_REAL,
        # Tuning.
        config.ENV_AUTOGEN_ARTE_MAX,
        config.ENV_ALERTAS_INTERVALO_HORAS, config.ENV_ALERTAS_UMBRAL_ENGAGEMENT,
        config.ENV_MAX_JOBS,
        config.ENV_MEDIA_GC_INTERVALO_HORAS, config.ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
        config.ENV_INGESTA_BATCH, config.ENV_INGESTA_WORKERS,
        config.ENV_INGESTA_MAX_ITEMS, config.ENV_INGESTA_MAX_ERRORES,
        config.ENV_CLUSTER_VENTANA_H, config.ENV_CLUSTER_BREAKING_FUENTES,
        config.ENV_CLUSTER_BREAKING_VENTANA_H,
        # Pesos del algoritmo de ponderación del ranking de noticias.
        config.ENV_SCORE_PESO_CORROBORACION, config.ENV_SCORE_PESO_MARCA,
        config.ENV_SCORE_PESO_FRESCURA, config.ENV_SCORE_PESO_VIRALIDAD,
        config.ENV_SCORE_BONUS_BREAKING,
        config.ENV_TRAD_MIN_SCORE, config.ENV_TRAD_LOTE,
        config.ENV_FEED_SLA_MIN,
    }
    # Los toggles por marca (clave `ENV::marca`) se generan en caliente; el resto del catálogo
    # son exactamente las claves globales esperadas.
    por_marca = {c for c in claves if config.SEP_MARCA in c}
    assert claves - por_marca == esperadas
    assert por_marca, "deben existir toggles de copy/arte por marca"


def test_maestros_etapa_son_las_cuatro(store):
    """El grupo `maestros_etapa` tiene EXACTAMENTE las 4 etapas, todas bool, defecto False."""
    maestros = [a for a in ajustes_catalogo.catalogo() if a.grupo == "maestros_etapa"]
    claves = {a.clave for a in maestros}
    assert claves == {config.ENV_INGESTA, config.ENV_QA, config.ENV_PIPELINE, config.ENV_AUTOGEN_ARTE}
    for a in maestros:
        assert a.tipo == "bool"
        assert a.defecto is False
    etiquetas = {a.clave: a.etiqueta for a in maestros}
    assert etiquetas[config.ENV_INGESTA] == "Crear noticias"
    assert etiquetas[config.ENV_QA] == "Validar (QA)"
    assert etiquetas[config.ENV_PIPELINE] == "Generar copy"
    assert etiquetas[config.ENV_AUTOGEN_ARTE] == "Generar arte"


def test_etapas_tienen_excepcion_por_marca(store):
    """Las CUATRO etapas (Crear noticias + QA + copy + arte) generan excepciones por marca."""
    por_marca = [
        a for a in ajustes_catalogo.catalogo()
        if a.grupo == "automatizacion_marca" and config.SEP_MARCA in a.clave
    ]
    bases = {a.clave.split(config.SEP_MARCA, 1)[0] for a in por_marca}
    assert config.ENV_INGESTA in bases
    assert bases == {config.ENV_INGESTA, config.ENV_QA, config.ENV_PIPELINE, config.ENV_AUTOGEN_ARTE}


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


def test_grupos_estables(store):
    """Los ids de grupo se mantienen (el frontend rutea Básica/Avanzado por estos ids)."""
    ids = {g[0] for g in ajustes_catalogo.GRUPOS}
    assert ids == {
        "maquina_global", "maestros_etapa", "automatizacion_marca",
        "publicacion", "publicacion_marca", "automatismos_generales", "tuning",
    }


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
        config.ENV_TRAD_LOTE,
        config.ENV_FEED_SLA_MIN,
        config.ENV_AUTOGEN_ARTE_MAX,
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
    assert _ajuste(config.ENV_PIPELINE).peligroso is False


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
    monkeypatch.setenv(config.ENV_PIPELINE, "1")
    a = _ajuste(config.ENV_PIPELINE)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert valor is True and fuente == "env"


def test_float_efectivo_tipado(store):
    ajustes.guardar(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT, "2.5")
    a = _ajuste(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert valor == 2.5 and fuente == "store"


# --------------------------------------------------------------------------- #
# a_dict: forma del contrato                                                   #
# --------------------------------------------------------------------------- #


def test_a_dict_int_tiene_min(store):
    d = ajustes_catalogo.a_dict(_ajuste(config.ENV_MAX_JOBS))
    assert d["tipo"] == "int" and d["min"] == 1 and "opciones" not in d
    assert set(d) >= {"clave", "tipo", "etiqueta", "ayuda", "grupo", "peligroso",
                      "valor", "fuente", "defecto"}


def test_a_dict_bool_sin_min_ni_opciones(store):
    d = ajustes_catalogo.a_dict(_ajuste(config.ENV_PIPELINE))
    assert d["tipo"] == "bool" and "min" not in d and "opciones" not in d


# --------------------------------------------------------------------------- #
# validar_valor por tipo                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entrada,guardado", [
    (True, "1"), (False, "0"), (1, "1"), (0, "0"),
    ("true", "1"), ("0", "0"), ("YES", "1"), ("off", "0"),
])
def test_validar_bool_ok(store, entrada, guardado):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PIPELINE), entrada)
    assert err is None and val == guardado


def test_validar_bool_invalido(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PIPELINE), "quizas")
    assert val is None and err is not None


def test_validar_int_ok(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_ARTE_MAX), 5)
    assert err is None and val == "5"


def test_validar_int_acepta_str(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_ARTE_MAX), " 7 ")
    assert err is None and val == "7"


def test_validar_int_bajo_minimo(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_ARTE_MAX), 0)
    assert val is None and "≥ 1" in err


def test_validar_int_rechaza_bool(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_ARTE_MAX), True)
    assert val is None and err is not None


def test_validar_int_no_numerico(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_AUTOGEN_ARTE_MAX), "x")
    assert val is None and err is not None


def test_validar_float_ok(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT), 3.0)
    assert err is None and float(val) == 3.0


def test_validar_float_bajo_minimo(store):
    val, err = ajustes_catalogo.validar_valor(
        _ajuste(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT), -1
    )
    assert val is None and err is not None


# --------------------------------------------------------------------------- #
# Precedencia efectiva via config._crudo (lo que ven los accesores)            #
# --------------------------------------------------------------------------- #


def test_config_crudo_store_gana_a_env(store, monkeypatch):
    monkeypatch.setenv(config.ENV_PIPELINE, "0")
    ajustes.guardar(config.ENV_PIPELINE, "1")
    assert config._crudo(config.ENV_PIPELINE) == "1"
    assert config.pipeline_activo() is True  # accesor bool ve el store


def test_config_crudo_cae_a_env_sin_store(store, monkeypatch):
    monkeypatch.setenv(config.ENV_PIPELINE, "1")
    assert config._crudo(config.ENV_PIPELINE) == "1"
    assert config.pipeline_activo() is True


def test_config_entero_pasa_por_store(store, monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_JOBS, "8")
    ajustes.guardar(config.ENV_MAX_JOBS, "2")
    assert config.max_jobs() == 2  # _entero -> _crudo -> store


def test_config_float_pasa_por_store(store):
    ajustes.guardar(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT, "4.5")
    assert config.alertas_umbral_engagement() == 4.5
