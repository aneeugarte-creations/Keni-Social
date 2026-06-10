"""Tests del catalogo de ajustes (`keni_consola.ajustes_catalogo`) + precedencia en config.

Cubre la serializacion (valor efectivo + fuente con store/env/defecto), `validar_valor`
por tipo/min/max, y la precedencia STORE > ENV > DEFECTO via `config._crudo`. Todo
aislado con monkeypatch de env y del store (sin DB ni red).

Modelo de máquina de contenido: 1 master (KENI_MAQUINA) + 6 etapas con nombres consolidados
(`KENI_PIPELINE_<ETAPA>`: Fusión/Ranking/Selección/Validación/Copy/Arte/Avance). Todas tienen
excepción por marca (1 toggle = 1 etapa).
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
        # Los DOS interruptores de la máquina: «Generar» (virtual: agrupa las cinco etapas
        # del tramo noticia→copy) y «Arte» (la única etapa con coste externo).
        config.ENV_GENERAR, config.ENV_PIPELINE_ARTE,
        # Automatismos generales (barridos de mantenimiento).
        config.ENV_ALERTAS_ACTIVAS, config.ENV_EVENTOS_VENCIMIENTOS,
        config.ENV_AUTO_PREAPROBACION, config.ENV_MEDIA_GC,
        config.ENV_NOTICIAS_GC,
        config.ENV_TRENDS, config.ENV_ALGORITMOS_AUTO, config.ENV_SUGERENCIAS_EDITORIALES,
        config.ENV_RENDIMIENTO_RANKING,
        config.ENV_PUBLICAR_REAL,
        # Admisión del flujo continuo (sin intervalo ni topes por etapa: ya no existen).
        config.ENV_PIPELINE_MAX, config.ENV_PIPELINE_EN_VUELO_MAX,
        # Tuning.
        config.ENV_AUTOGEN_ARTE_MAX,
        config.ENV_ALERTAS_INTERVALO_HORAS, config.ENV_ALERTAS_UMBRAL_ENGAGEMENT,
        config.ENV_MAX_JOBS,
        config.ENV_MEDIA_GC_INTERVALO_HORAS, config.ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
        config.ENV_NOTICIAS_GC_INTERVALO_HORAS, config.ENV_NOTICIAS_GC_SCORE_UMBRAL,
        config.ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
        config.ENV_PERFIL_EDITORIAL_TTL_HORAS, config.ENV_FUSION_SEMANTICA_MAX,
        config.ENV_SCORE_PESO_RENDIMIENTO, config.ENV_RENDIMIENTO_TOP_N,
        config.ENV_RENDIMIENTO_MIN_PIEZAS,
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
        # Economía de tokens de la generación (presupuesto_ia): kill switch + presupuesto
        # diario + margen manual + tope de contexto. Editables en caliente desde el Monitor.
        config.ENV_GENERACION_PAUSADA,
        config.ENV_PRESUPUESTO_TOKENS_DIA, config.ENV_PRESUPUESTO_MARGEN_MANUAL,
        config.ENV_PROMPT_MAX_CHARS,
        # Listón de auto-producción del ranking de noticias (umbrales de promoción a tema)
        # + maduración y cupos de volumen (día móvil / franja horaria).
        config.ENV_PROMOVER_MIN_SCORE, config.ENV_PROMOVER_MIN_MARCA,
        config.ENV_PROMOVER_MADURACION_MIN,
        config.ENV_CUPO_DIA, config.ENV_PLAN_DIA,
        # Filtro de ENTRADA por agenda de marca (la puerta del pool).
        config.ENV_INGESTA_FILTRO,
        # Caducidad del pool: TTL (lo viejo expira solo) + retención (techo del archivo).
        config.ENV_NOTICIAS_TTL_H, config.ENV_NOTICIAS_RETENCION_H,
    }
    # Los toggles por marca (clave `ENV::marca`) se generan en caliente; el resto del catálogo
    # son exactamente las claves globales esperadas.
    por_marca = {c for c in claves if config.SEP_MARCA in c}
    assert claves - por_marca == esperadas
    assert por_marca, "deben existir toggles de copy/arte por marca"


_MAESTROS_ENV = {config.ENV_GENERAR, config.ENV_PIPELINE_ARTE}


def test_maestros_son_generar_y_arte(store):
    """El grupo `maestros_etapa` tiene EXACTAMENTE dos interruptores: «Generar» y «Arte».

    «Generar» es la clave VIRTUAL `KENI_GENERAR`: agrupa las cinco etapas internas del tramo
    noticia→copy (la API la escribe con fan-out, ver `claves_fisicas`). Las etapas dejaron de
    ser botones; la única con interruptor propio es Arte (coste externo real)."""
    maestros = [a for a in ajustes_catalogo.catalogo() if a.grupo == "maestros_etapa"]
    claves = {a.clave for a in maestros}
    assert claves == _MAESTROS_ENV
    for a in maestros:
        assert a.tipo == "bool"
        assert a.defecto is False
    etiquetas = {a.clave: a.etiqueta for a in maestros}
    assert etiquetas[config.ENV_GENERAR] == "Generar"
    assert etiquetas[config.ENV_PIPELINE_ARTE] == "Arte IA"


def test_generar_fan_out_a_las_cinco_etapas(store):
    """`claves_fisicas`: la virtual «Generar» escribe las CINCO etapas del tramo (global y
    por marca); cualquier otra clave se escribe a sí misma."""
    assert ajustes_catalogo.claves_fisicas(config.ENV_GENERAR) == list(config.ETAPAS_GENERAR)
    con_marca = ajustes_catalogo.claves_fisicas(
        config.clave_por_marca(config.ENV_GENERAR, "unotv")
    )
    assert con_marca == [config.clave_por_marca(e, "unotv") for e in config.ETAPAS_GENERAR]
    assert config.ENV_PIPELINE_ARTE not in config.ETAPAS_GENERAR  # Arte va aparte
    assert ajustes_catalogo.claves_fisicas(config.ENV_CUPO_DIA) == [config.ENV_CUPO_DIA]


def test_generar_se_lee_desde_la_etapa_de_copy(store):
    """El valor mostrado de «Generar» es el de la etapa de Copy (el final del embudo)."""
    ajustes.guardar(config.ENV_PIPELINE_COPY, "1")
    a = _ajuste(config.ENV_GENERAR)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert valor is True and fuente == "store"



def test_toggles_por_marca_son_generar_y_arte(store):
    """Las excepciones por marca del grupo `automatizacion_marca` son Generar y Arte."""
    por_marca = [
        a for a in ajustes_catalogo.catalogo()
        if a.grupo == "automatizacion_marca" and config.SEP_MARCA in a.clave
    ]
    bases = {a.clave.split(config.SEP_MARCA, 1)[0] for a in por_marca}
    assert bases == _MAESTROS_ENV


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
    """Los ids de grupo se mantienen (el frontend reparte páginas/secciones por estos ids)."""
    ids = {g[0] for g in ajustes_catalogo.GRUPOS}
    assert ids == {
        "maquina_global", "maestros_etapa", "automatizacion_marca", "pipeline_topes",
        "publicacion", "publicacion_marca", "automatismos_generales",
        "noticias_entrada", "noticias_orden", "noticias_rendimiento",
        "noticias_breaking", "noticias_produccion", "noticias_produccion_marca",
        "noticias_tecnico",
        "tuning",
    }
    # GRUPOS_NOTICIAS (las secciones de la subpágina de Noticias) referencia grupos reales.
    assert set(ajustes_catalogo.GRUPOS_NOTICIAS) <= ids


def test_noticias_reparto_en_secciones(store):
    """Los ajustes del motor de noticias se reparten EXACTAMENTE en las secciones de la
    subpágina de Noticias: entrada → orden → rendimiento → última hora → producción → técnico.
    Lo editorial queda visible y lo de capacidad/ritmo en `noticias_tecnico` (colapsado)."""
    reparto = {
        "noticias_entrada": {
            config.ENV_INGESTA_FILTRO,
            config.ENV_INGESTA_MAX_ERRORES,
            config.ENV_TRAD_MIN_SCORE,
            config.ENV_FEED_SLA_MIN,
        },
        "noticias_orden": {
            config.ENV_SCORE_PESO_CORROBORACION,
            config.ENV_SCORE_PESO_MARCA,
            config.ENV_SCORE_PESO_FRESCURA,
            config.ENV_SCORE_PESO_VIRALIDAD,
        },
        "noticias_rendimiento": {
            config.ENV_RENDIMIENTO_RANKING,
            config.ENV_SCORE_PESO_RENDIMIENTO,
            config.ENV_RENDIMIENTO_TOP_N,
            config.ENV_RENDIMIENTO_MIN_PIEZAS,
        },
        "noticias_breaking": {
            config.ENV_CLUSTER_BREAKING_FUENTES,
            config.ENV_CLUSTER_BREAKING_VENTANA_H,
            config.ENV_SCORE_BONUS_BREAKING,
        },
        # Listón de auto-producción (dominio.clustering.evaluar_liston): umbrales que deciden
        # qué historias del pool disparan QA+copy automáticos (coste real de tokens).
        "noticias_produccion": {
            config.ENV_PROMOVER_MIN_SCORE,
            config.ENV_PROMOVER_MIN_MARCA,
            config.ENV_PROMOVER_MADURACION_MIN,
            config.ENV_CUPO_DIA,
            config.ENV_PLAN_DIA,
        },
        "noticias_tecnico": {
            config.ENV_INGESTA_BATCH,
            config.ENV_INGESTA_WORKERS,
            config.ENV_INGESTA_MAX_ITEMS,
            config.ENV_CLUSTER_VENTANA_H,
            config.ENV_TRAD_LOTE,
            config.ENV_PERFIL_EDITORIAL_TTL_HORAS,
            config.ENV_FUSION_SEMANTICA_MAX,
        },
    }
    for gid, esperadas in reparto.items():
        en_grupo = {a.clave for a in ajustes_catalogo.catalogo() if a.grupo == gid}
        assert en_grupo == esperadas, f"reparto inesperado en {gid}"
        # Todo numérico de estas secciones declara mínimo (la UI pinta inputs acotados).
        for clave in esperadas:
            a = ajustes_catalogo.por_clave(clave)
            assert a is not None, f"falta la clave {clave}"
            if a.tipo in ("int", "float"):
                assert a.minimo is not None, f"{clave} debe tener minimo"
    # El master de rendimiento es un bool; ya no es un daemon de `automatismos_generales`.
    master = ajustes_catalogo.por_clave(config.ENV_RENDIMIENTO_RANKING)
    assert master is not None and master.tipo == "bool" and master.grupo == "noticias_rendimiento"


def test_tuning_solo_operacional(store):
    """`tuning` queda solo con los finos operacionales (jobs, limpieza GC, alertas), int/float min>=0."""
    claves = [
        config.ENV_MAX_JOBS,
        config.ENV_ALERTAS_INTERVALO_HORAS,
        config.ENV_ALERTAS_UMBRAL_ENGAGEMENT,
        config.ENV_MEDIA_GC_INTERVALO_HORAS,
        config.ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
        config.ENV_NOTICIAS_GC_INTERVALO_HORAS,
        config.ENV_NOTICIAS_GC_SCORE_UMBRAL,
        config.ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
        # Caducidad del pool de noticias (TTL + retención): limpieza, vive con el resto de GC.
        config.ENV_NOTICIAS_TTL_H,
        config.ENV_NOTICIAS_RETENCION_H,
    ]
    en_grupo = {a.clave for a in ajustes_catalogo.catalogo() if a.grupo == "tuning"}
    assert en_grupo == set(claves)


# La admisión del flujo continuo vive en su propio grupo `pipeline_topes` (sección «Máquina de
# contenido» del Monitor), NO en `tuning` de Configuración. FLUJO CONTINUO: sin intervalo del
# barrido ni topes por etapa (QA/Copy/autogen/revisar); solo admisión + WIP + cap de Arte.
_PIPELINE_TOPES_INT = {
    config.ENV_PIPELINE_MAX,
    config.ENV_PIPELINE_EN_VUELO_MAX,
    config.ENV_AUTOGEN_ARTE_MAX,
}


# Economía de tokens (presupuesto_ia): viven TAMBIÉN en `pipeline_topes` (el Monitor, junto a
# la cola que gobiernan) pero su mínimo es 0 a propósito: 0 = «sin límite/sin tope» (apagado),
# a diferencia de los knobs de admisión, donde 0 no tiene sentido (algo debe entrar).
_PIPELINE_ECONOMIA_INT = {
    config.ENV_PRESUPUESTO_TOKENS_DIA,
    config.ENV_PRESUPUESTO_MARGEN_MANUAL,
    config.ENV_PROMPT_MAX_CHARS,
}


def test_pipeline_topes_en_grupo_propio(store):
    """Los knobs de admisión (int, min >= 1) y los de economía de tokens (int, min 0 =
    apagado) viven EXACTAMENTE en el grupo `pipeline_topes`."""
    for clave in _PIPELINE_TOPES_INT:
        a = ajustes_catalogo.por_clave(clave)
        assert a is not None, f"falta la clave {clave}"
        assert a.tipo == "int", f"{clave} debe ser int"
        assert a.grupo == "pipeline_topes", f"{clave} debe estar en grupo pipeline_topes"
        assert a.minimo is not None and a.minimo >= 1, f"{clave} debe tener minimo >= 1"
    for clave in _PIPELINE_ECONOMIA_INT:
        a = ajustes_catalogo.por_clave(clave)
        assert a is not None, f"falta la clave {clave}"
        assert a.tipo == "int", f"{clave} debe ser int"
        assert a.grupo == "pipeline_topes", f"{clave} debe estar en grupo pipeline_topes"
        assert a.minimo == 0, f"{clave} debe tener minimo 0 (0 = sin límite)"
    en_grupo = {a.clave for a in ajustes_catalogo.catalogo() if a.grupo == "pipeline_topes"}
    assert en_grupo == _PIPELINE_TOPES_INT | _PIPELINE_ECONOMIA_INT


def test_generacion_pausada_es_kill_switch_de_maquina(store):
    """El kill switch de generación es bool, defecto False, en `maquina_global` (junto al
    interruptor general) y NO peligroso (el Monitor pinta su toggle editable)."""
    a = ajustes_catalogo.por_clave(config.ENV_GENERACION_PAUSADA)
    assert a is not None, "falta el kill switch KENI_GENERACION_PAUSADA"
    assert a.tipo == "bool"
    assert a.defecto is False
    assert a.grupo == "maquina_global"
    assert a.peligroso is False


def test_grupos_maquina_son_los_del_monitor(store):
    """`GRUPOS_MAQUINA` referencia grupos REALES; son los que el front saca de Configuración y pinta
    en la sección «Máquina de contenido» del Monitor (master + etapas + por marca + topes)."""
    ids_grupo = {g[0] for g in ajustes_catalogo.GRUPOS}
    assert set(ajustes_catalogo.GRUPOS_MAQUINA) <= ids_grupo
    assert set(ajustes_catalogo.GRUPOS_MAQUINA) == {
        "maquina_global", "maestros_etapa", "automatizacion_marca", "pipeline_topes",
    }


def test_motor_noticias_trad_min_score_float(store):
    """KENI_TRAD_MIN_SCORE es float en la sección de entrada al pool con minimo 0."""
    a = ajustes_catalogo.por_clave(config.ENV_TRAD_MIN_SCORE)
    assert a is not None
    assert a.tipo == "float"
    assert a.grupo == "noticias_entrada"
    assert a.minimo == 0


def test_publicar_real_es_peligroso(store):
    assert _ajuste(config.ENV_PUBLICAR_REAL).peligroso is True
    assert _ajuste(config.ENV_GENERAR).peligroso is False


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
    monkeypatch.setenv(config.ENV_PIPELINE_ARTE, "1")
    a = _ajuste(config.ENV_PIPELINE_ARTE)
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
    d = ajustes_catalogo.a_dict(_ajuste(config.ENV_PIPELINE_ARTE))
    assert d["tipo"] == "bool" and "min" not in d and "opciones" not in d


# --------------------------------------------------------------------------- #
# validar_valor por tipo                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entrada,guardado", [
    (True, "1"), (False, "0"), (1, "1"), (0, "0"),
    ("true", "1"), ("0", "0"), ("YES", "1"), ("off", "0"),
])
def test_validar_bool_ok(store, entrada, guardado):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PIPELINE_ARTE), entrada)
    assert err is None and val == guardado


def test_validar_bool_invalido(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PIPELINE_ARTE), "quizas")
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
    monkeypatch.setenv(config.ENV_PIPELINE_COPY, "0")
    ajustes.guardar(config.ENV_PIPELINE_COPY, "1")
    assert config._crudo(config.ENV_PIPELINE_COPY) == "1"
    assert config.pipeline_activo() is True  # accesor bool ve el store


def test_config_crudo_cae_a_env_sin_store(store, monkeypatch):
    monkeypatch.setenv(config.ENV_PIPELINE_COPY, "1")
    assert config._crudo(config.ENV_PIPELINE_COPY) == "1"
    assert config.pipeline_activo() is True


def test_config_entero_pasa_por_store(store, monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_JOBS, "8")
    ajustes.guardar(config.ENV_MAX_JOBS, "2")
    assert config.max_jobs() == 2  # _entero -> _crudo -> store


def test_config_float_pasa_por_store(store):
    ajustes.guardar(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT, "4.5")
    assert config.alertas_umbral_engagement() == 4.5
