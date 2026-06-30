"""Tests del catalogo de ajustes (`keni_consola.ajustes_catalogo`) + precedencia en config.

Cubre la serializacion (valor efectivo + fuente con store/env/defecto), `validar_valor`
por tipo/min/max, y la precedencia STORE > ENV > DEFECTO via `config._crudo`. Todo
aislado con monkeypatch de env y del store (sin DB ni red).

Modelo de máquina de contenido: 1 master (KENI_MAQUINA) + 6 etapas con nombres consolidados
(`KENI_PIPELINE_<ETAPA>`: Fusionar/Priorizar/Recolectar/Verificar/Redactar/Ilustrar/Revisar).
Todas tienen excepción por marca (1 toggle = 1 etapa).
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
        # Los maestros de la máquina (ADR 0011): una etapa FÍSICA por toggle
        # (Recolectar/Verificar/Redactar/Ilustrar/Stock; Ilustrar siempre tuvo interruptor propio).
        config.ENV_PIPELINE_RECOLECTAR, config.ENV_PIPELINE_VERIFICAR,
        # Traducir + Admitir: etapas físicas con toggle propio (ON por defecto).
        config.ENV_PIPELINE_TRADUCIR, config.ENV_PIPELINE_ADMITIR,
        # Fusionar/Priorizar (investigación) + Decisor/Keywords/Revisar (producción): etapas
        # físicas con toggle GLOBAL propio (Fusionar y Keywords ON por defecto; el resto OFF).
        config.ENV_PIPELINE_FUSIONAR, config.ENV_PRIORIZAR_PERFIL_IA,
        config.ENV_PIPELINE_DECISOR, config.ENV_PIPELINE_SUGERIR_HASHTAGS,
        config.ENV_PIPELINE_REVISAR,
        # Google Trends: fuente de ingesta del pool (con Investigación, no con los automatismos).
        config.ENV_TRENDS,
        config.ENV_PIPELINE_REDACTAR, config.ENV_PIPELINE_ILUSTRAR,
        # Stock: baja una foto de AYUDA (atenuada, sin licencia) a los temas con copy y sin imagen.
        config.ENV_PIPELINE_STOCK,
        # Crítica IA: nivel opcional de la cadena de aprobación (OFF por defecto).
        config.ENV_CRITICA_IA,
        # Automatismos generales (barridos de mantenimiento; SOLO toggles on/off).
        config.ENV_ALERTAS_ACTIVAS,
        config.ENV_AUTO_PREAPROBACION, config.ENV_MEDIA_GC,
        config.ENV_NOTICIAS_GC,
        config.ENV_ALGORITMOS_AUTO,
        config.ENV_PATRONES_AUTO,
        config.ENV_RENDIMIENTO_RANKING,
        config.ENV_PUBLICAR_REAL,
        # Economía de tokens de la generación (presupuesto_ia): kill switch + presupuesto
        # diario + margen manual. Se editan en la página de Economía (por clave).
        config.ENV_GENERACION_PAUSADA,
        config.ENV_PRESUPUESTO_USD_DIA,
        # Topes diarios de tokens POR MOTOR, separando entrada/salida (investigación / producción).
        config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA,
        config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA,
        config.ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA,
        config.ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA,
        config.ENV_PRESUPUESTO_MARGEN_MANUAL,
        # Umbral de auto-producción del ranking de noticias (score). El encaje de marca, el cupo
        # sin plan y el plan global se RETIRARON (el plan por marca, en Programación, es el gate);
        # la maduración, los caps de admisión, los umbrales de alertas/GC y las caducidades del
        # pool se DEGRADARON a solo-env: tunables de ingeniería, fuera de la UI.
        config.ENV_PROMOVER_MIN_SCORE,
        # Esfuerzo de razonamiento de la generación (palanca calidad/coste, se edita en Economía).
        config.ENV_ESFUERZO,
    }
    # Los toggles por marca (clave `ENV::marca`) se generan en caliente; el resto del catálogo
    # son exactamente las claves globales esperadas.
    por_marca = {c for c in claves if config.SEP_MARCA in c}
    assert claves - por_marca == esperadas
    assert por_marca, "deben existir toggles de copy/arte por marca"


_MAESTROS_ENV = {
    # Una etapa física por toggle (la vista Pipeline las opera de una en una).
    config.ENV_PIPELINE_RECOLECTAR, config.ENV_PIPELINE_VERIFICAR,
    # Traducir + Admitir: etapas físicas con toggle propio (ON por defecto).
    config.ENV_PIPELINE_TRADUCIR, config.ENV_PIPELINE_ADMITIR,
    # Fusionar/Priorizar (investigación) + Decisor/Keywords/Revisar (producción): etapas físicas
    # con toggle GLOBAL propio (Fusionar y Keywords ON por defecto; el resto OFF).
    config.ENV_PIPELINE_FUSIONAR, config.ENV_PRIORIZAR_PERFIL_IA,
    config.ENV_PIPELINE_DECISOR, config.ENV_PIPELINE_SUGERIR_HASHTAGS,
    config.ENV_PIPELINE_REVISAR,
    # Google Trends: fuente de ingesta del pool, paso del flujo de Investigación (no automatismo).
    config.ENV_TRENDS,
    config.ENV_PIPELINE_REDACTAR, config.ENV_PIPELINE_ILUSTRAR,
    # Stock: etapa física que baja una foto de ayuda a los temas con copy y sin imagen.
    config.ENV_PIPELINE_STOCK,
    # Crítica IA: nivel opcional de la cadena de aprobación (grupo `maestros_produccion`).
    config.ENV_CRITICA_IA,
}


def test_maestros_son_investigacion_produccion_y_arte(store):
    """Los maestros (grupos `maestros_investigacion`/`maestros_produccion`) son EXACTAMENTE
    las etapas FÍSICAS del pipeline + el paso GLOBAL de ingesta (Google Trends), que no va en el
    fan-out por marca.

    Cada etapa es su propia clave del store: la vista Pipeline las opera de una en una
    (Recolectar/Verificar/Redactar/Ilustrar…) y calcula la cascada a partir de sus estados."""
    maestros = [
        a for a in ajustes_catalogo.catalogo()
        if a.grupo in {"maestros_investigacion", "maestros_produccion"}
    ]
    claves = {a.clave for a in maestros}
    assert claves == _MAESTROS_ENV
    # Nacen OFF salvo las seguras/ya-en-marcha que arrancan ON: Stock (ayuda visual atenuada),
    # Traducir y Admitir (continúan el flujo actual), Fusionar (dedup semántico base) y Keywords
    # (sugerencia READ-ONLY barata). Todas def ON en sus gate fns.
    on_por_defecto = {
        config.ENV_PIPELINE_STOCK,
        config.ENV_PIPELINE_TRADUCIR,
        config.ENV_PIPELINE_ADMITIR,
        config.ENV_PIPELINE_FUSIONAR,
        config.ENV_PIPELINE_SUGERIR_HASHTAGS,
    }
    for a in maestros:
        assert a.tipo == "bool"
        assert a.defecto is (a.clave in on_por_defecto)
    etiquetas = {a.clave: a.etiqueta for a in maestros}
    assert etiquetas[config.ENV_PIPELINE_RECOLECTAR] == "Recolectar"
    assert etiquetas[config.ENV_PIPELINE_VERIFICAR] == "Verificar"
    assert etiquetas[config.ENV_PIPELINE_REDACTAR] == "Redactar"
    assert etiquetas[config.ENV_PIPELINE_ILUSTRAR] == "Ilustrar"
    assert etiquetas[config.ENV_PIPELINE_STOCK] == "Stock"


def test_toggles_por_marca_por_fase(store):
    """Las excepciones por marca son, por proceso (ADR 0011 rev. fase×marca): cada FASE editable
    por separado, para que apagar una fase en una marca NO afecte al resto. Investigación →
    `automatizacion_marca_investigacion`; Producción (incl. Arte y Crítica) →
    `automatizacion_marca_produccion`. Los pasos pre-marca (Cotejar) quedan SOLO globales: no
    se gatean por una marca que aún no existe."""
    def _bases(grupo: str) -> set[str]:
        return {
            a.clave.split(config.SEP_MARCA, 1)[0]
            for a in ajustes_catalogo.catalogo()
            if a.grupo == grupo and config.SEP_MARCA in a.clave
        }

    investigacion = _bases("automatizacion_marca_investigacion")
    produccion = _bases("automatizacion_marca_produccion")
    assert investigacion == {
        config.ENV_PIPELINE_RECOLECTAR, config.ENV_PIPELINE_FUSIONAR,
        config.ENV_PIPELINE_TRADUCIR,
        config.ENV_PRIORIZAR_PERFIL_IA, config.ENV_PIPELINE_VERIFICAR,
        config.ENV_PIPELINE_ADMITIR,
    }
    assert produccion == {
        config.ENV_PIPELINE_DECISOR, config.ENV_PIPELINE_REDACTAR,
        config.ENV_PIPELINE_SUGERIR_HASHTAGS, config.ENV_PIPELINE_ILUSTRAR,
        config.ENV_PIPELINE_STOCK, config.ENV_PIPELINE_REVISAR, config.ENV_CRITICA_IA,
    }
    # El grupo viejo unificado ya no existe.
    assert _bases("automatizacion_marca") == set()


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
    # `noticias_orden` y `noticias_breaking` se RETIRARON (auditoría 2026-06): solo
    # contenían pesos/umbrales del algoritmo, degradados a solo-env.
    assert ids == {
        "maquina_global", "maestros_investigacion", "maestros_produccion",
        "automatizacion_marca_investigacion", "automatizacion_marca_produccion",
        "pipeline_topes",
        "pieza", "publicacion_marca", "presupuesto_marca", "automatismos_generales",
        "noticias_rendimiento",
        "noticias_produccion", "noticias_produccion_marca",
        "tuning",
    }


def test_noticias_reparto_en_secciones(store):
    """Los ajustes del motor de noticias se reparten EXACTAMENTE en los grupos de la sección
    «Investigación» del drawer del Monitor. Solo quedan los controles de OPERACIÓN: el master de
    rendimiento y el umbral de score de producción automática. El filtro de entrada, el encaje de
    marca, el cupo y el plan global se RETIRARON; la maduración, el TTL del perfil editorial, los
    pesos del score, los umbrales de clustering y el batch/concurrencia de ingesta se degradaron a
    solo-env (siguen vivos en `config`, fuera de la UI)."""
    reparto = {
        "noticias_rendimiento": {
            config.ENV_RENDIMIENTO_RANKING,
        },
        # Umbral de auto-producción (dominio.agrupar.evaluar_umbral): el score mínimo que decide
        # qué historias del pool disparan verificación+copy automáticos (coste real de tokens).
        "noticias_produccion": {
            config.ENV_PROMOVER_MIN_SCORE,
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
    # El master de rendimiento es un bool.
    master = ajustes_catalogo.por_clave(config.ENV_RENDIMIENTO_RANKING)
    assert master is not None and master.tipo == "bool" and master.grupo == "noticias_rendimiento"


def test_tuning_solo_esfuerzo(store):
    """`tuning` queda SOLO con el esfuerzo de razonamiento (select), que se edita en la página
    de Economía (palanca calidad/coste). Los umbrales de alertas/GC, las caducidades del pool,
    los intervalos de daemons y la concurrencia (KENI_MAX_JOBS) se degradaron a solo-env."""
    en_grupo = {a.clave for a in ajustes_catalogo.catalogo() if a.grupo == "tuning"}
    assert en_grupo == {config.ENV_ESFUERZO}


# Economía de tokens (presupuesto_ia): viven en `pipeline_topes` (los caps de admisión
# —KENI_PIPELINE_MAX/_EN_PROCESO_MAX— se degradaron a solo-env). Mínimo 0 a propósito:
# 0 = «sin límite/sin tope» (apagado). Se editan en la página de Economía, no en el drawer.
_PIPELINE_ECONOMIA_INT = {
    config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA,
    config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA,
    config.ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA,
    config.ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA,
    config.ENV_PRESUPUESTO_MARGEN_MANUAL,
}


# El presupuesto de COSTE (USD) es float (admite céntimos), pero mismo grupo y misma semántica
# de 0 = apagado que el de tokens.
_PIPELINE_ECONOMIA_FLOAT = {
    config.ENV_PRESUPUESTO_USD_DIA,
}


def test_pipeline_topes_en_grupo_propio(store):
    """El grupo `pipeline_topes` queda EXACTAMENTE con la economía de tokens/coste (int/float,
    min 0 = apagado); los caps de admisión se degradaron a solo-env."""
    for clave in _PIPELINE_ECONOMIA_INT:
        a = ajustes_catalogo.por_clave(clave)
        assert a is not None, f"falta la clave {clave}"
        assert a.tipo == "int", f"{clave} debe ser int"
        assert a.grupo == "pipeline_topes", f"{clave} debe estar en grupo pipeline_topes"
        assert a.minimo == 0, f"{clave} debe tener minimo 0 (0 = sin límite)"
    for clave in _PIPELINE_ECONOMIA_FLOAT:
        a = ajustes_catalogo.por_clave(clave)
        assert a is not None, f"falta la clave {clave}"
        assert a.tipo == "float", f"{clave} debe ser float"
        assert a.grupo == "pipeline_topes", f"{clave} debe estar en grupo pipeline_topes"
        assert a.minimo == 0, f"{clave} debe tener minimo 0 (0 = sin límite)"
    en_grupo = {a.clave for a in ajustes_catalogo.catalogo() if a.grupo == "pipeline_topes"}
    assert en_grupo == _PIPELINE_ECONOMIA_INT | _PIPELINE_ECONOMIA_FLOAT


def test_generacion_pausada_es_kill_switch_de_maquina(store):
    """El kill switch de generación es bool, defecto False, en `maquina_global` (junto al
    interruptor general) y NO peligroso (el Monitor pinta su toggle editable)."""
    a = ajustes_catalogo.por_clave(config.ENV_GENERACION_PAUSADA)
    assert a is not None, "falta el kill switch KENI_GENERACION_PAUSADA"
    assert a.tipo == "bool"
    assert a.defecto is False
    assert a.grupo == "maquina_global"
    assert a.peligroso is False


def test_esfuerzo_es_select_del_catalogo(store, monkeypatch):
    """`KENI_ESFUERZO` (consolidación del esfuerzo): select en `tuning`, defecto "" =
    predeterminado del modelo, con los mismos niveles que expone `preferencias` y
    precedencia store > env. NO peligroso (toggle editable normal)."""
    from keni_consola import preferencias

    a = ajustes_catalogo.por_clave(config.ENV_ESFUERZO)
    assert a is not None, "falta el ajuste KENI_ESFUERZO"
    assert a.tipo == "select"
    assert a.grupo == "tuning"
    assert a.defecto == ""
    assert a.peligroso is False
    assert [o["id"] for o in a.opciones] == ["", *preferencias.ESFUERZOS_VALIDOS]
    # validación: solo ids del select (el "" incluido); lo demás, error legible.
    assert ajustes_catalogo.validar_valor(a, "high") == ("high", None)
    assert ajustes_catalogo.validar_valor(a, "") == ("", None)
    valor, error = ajustes_catalogo.validar_valor(a, "turbo")
    assert valor is None and "KENI_ESFUERZO" in error
    # precedencia: store > env.
    monkeypatch.setenv(config.ENV_ESFUERZO, "low")
    assert ajustes_catalogo.valor_y_fuente(a) == ("low", "env")
    ajustes.guardar(config.ENV_ESFUERZO, "max")
    assert ajustes_catalogo.valor_y_fuente(a) == ("max", "store")
    # serialización: el select lleva sus opciones en el dict de API.
    d = ajustes_catalogo.a_dict(a)
    assert [o["id"] for o in d["opciones"]] == ["", *preferencias.ESFUERZOS_VALIDOS]


def test_claves_degradadas_fuera_del_catalogo_pero_vivas_en_config(store, monkeypatch):
    """Las claves DEGRADADAS (auditoría 2026-06) ya no son editables (fuera del catálogo:
    `por_clave` -> None, así POST /api/ajustes las rechaza con 400), pero el código las
    sigue leyendo: env aplica, y un valor PREEXISTENTE en el store también (config._crudo
    no consulta el catálogo; degradar solo quita la clave de la UI/escritura)."""
    degradadas = [
        # Auditoría 2026-06 (panel «Ajustes de la máquina»): caps de admisión, umbrales/cadencias
        # de barrido y caducidades del pool — tunables de ingeniería, fuera de la UI.
        config.ENV_PIPELINE_MAX, config.ENV_PIPELINE_EN_PROCESO_MAX,
        config.ENV_PROMOVER_MADURACION_MIN,
        config.ENV_ALERTAS_UMBRAL_ENGAGEMENT, config.ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
        config.ENV_NOTICIAS_GC_SCORE_UMBRAL, config.ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
        config.ENV_NOTICIAS_TTL_H, config.ENV_NOTICIAS_RETENCION_H,
        config.ENV_PERFIL_EDITORIAL_TTL_HORAS,
        config.ENV_AUTOGEN_ARTE_MAX, config.ENV_AUTOGEN_COPY_MAX, config.ENV_PROMPT_MAX_CHARS,
        config.ENV_MAX_JOBS,
        config.ENV_ALERTAS_INTERVALO_HORAS,
        config.ENV_MEDIA_GC_INTERVALO_HORAS, config.ENV_NOTICIAS_GC_INTERVALO_HORAS,
        config.ENV_SCORE_PESO_RENDIMIENTO, config.ENV_RENDIMIENTO_TOP_N,
        config.ENV_RENDIMIENTO_MIN_PIEZAS,
        config.ENV_INGESTA_BATCH, config.ENV_INGESTA_WORKERS,
        config.ENV_INGESTA_MAX_ITEMS, config.ENV_INGESTA_MAX_ERRORES,
        config.ENV_CLUSTER_VENTANA_H,
        config.ENV_CLUSTER_BREAKING_PESO, config.ENV_CLUSTER_BREAKING_VENTANA_H,
        config.ENV_SCORE_PESO_CORROBORACION, config.ENV_SCORE_PESO_MARCA,
        config.ENV_SCORE_PESO_FRESCURA, config.ENV_SCORE_PESO_VELOCIDAD,
        config.ENV_SCORE_PESO_VIRALIDAD, config.ENV_SCORE_BONUS_BREAKING,
        config.ENV_TRAD_MIN_SCORE, config.ENV_TRAD_LOTE,
        config.ENV_FEED_SLA_MIN,
        config.ENV_FUSION_SEMANTICA_MAX,
    ]
    for clave in degradadas:
        assert ajustes_catalogo.por_clave(clave) is None, f"{clave} debía estar degradada"
    # env sigue aplicando para una clave degradada...
    monkeypatch.setenv(config.ENV_MAX_JOBS, "7")
    assert config.max_jobs() == 7
    # ...y un valor preexistente del store TAMBIÉN (caso real: KENI_SCORE_PESO_VELOCIDAD=0.0
    # quedó escrito en producción antes de la degradación y debe seguir aplicando).
    ajustes.guardar(config.ENV_SCORE_PESO_VELOCIDAD, "0.0")
    assert config._crudo(config.ENV_SCORE_PESO_VELOCIDAD) == "0.0"


def test_patrones_auto_es_toggle_de_automatismos(store, monkeypatch):
    """`KENI_PATRONES_AUTO` (antes solo-env) es un bool del grupo `automatismos_generales`,
    defecto False, y su accesor `config.patrones_auto_activo` respeta store > env."""
    a = ajustes_catalogo.por_clave(config.ENV_PATRONES_AUTO)
    assert a is not None, "falta el gate KENI_PATRONES_AUTO"
    assert a.tipo == "bool"
    assert a.grupo == "automatismos_generales"
    assert a.defecto is False
    assert a.peligroso is False
    monkeypatch.delenv(config.ENV_PATRONES_AUTO, raising=False)
    assert config.patrones_auto_activo() is False
    monkeypatch.setenv(config.ENV_PATRONES_AUTO, "1")
    assert config.patrones_auto_activo() is True
    ajustes.guardar(config.ENV_PATRONES_AUTO, "0")  # el store (UI) gana al env
    assert config.patrones_auto_activo() is False


def test_publicar_real_es_peligroso(store):
    assert _ajuste(config.ENV_PUBLICAR_REAL).peligroso is True
    assert _ajuste(config.ENV_PIPELINE_RECOLECTAR).peligroso is False
    assert _ajuste(config.ENV_PIPELINE_REDACTAR).peligroso is False


def test_por_clave_desconocida(store):
    assert ajustes_catalogo.por_clave("KENI_NO_EXISTE") is None


# --------------------------------------------------------------------------- #
# valor_y_fuente: precedencia store > env > defecto                            #
# --------------------------------------------------------------------------- #


def test_valor_defecto_sin_store_ni_env(store, monkeypatch):
    monkeypatch.delenv(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA, raising=False)
    a = _ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert (valor, fuente) == (config.PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA_DEF, "defecto")


def test_valor_desde_env(store, monkeypatch):
    monkeypatch.setenv(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA, "8")
    a = _ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert (valor, fuente) == (8, "env")


def test_valor_desde_store_gana_a_env(store, monkeypatch):
    monkeypatch.setenv(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA, "8")
    ajustes.guardar(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA, "2")
    a = _ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert (valor, fuente) == (2, "store")


def test_bool_efectivo_tipado(store, monkeypatch):
    monkeypatch.setenv(config.ENV_PIPELINE_ILUSTRAR, "1")
    a = _ajuste(config.ENV_PIPELINE_ILUSTRAR)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert valor is True and fuente == "env"


def test_float_efectivo_tipado(store):
    ajustes.guardar(config.ENV_PRESUPUESTO_USD_DIA, "2.5")
    a = _ajuste(config.ENV_PRESUPUESTO_USD_DIA)
    valor, fuente = ajustes_catalogo.valor_y_fuente(a)
    assert valor == 2.5 and fuente == "store"


# --------------------------------------------------------------------------- #
# a_dict: forma del contrato                                                   #
# --------------------------------------------------------------------------- #


def test_a_dict_int_tiene_min(store):
    d = ajustes_catalogo.a_dict(_ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA))
    assert d["tipo"] == "int" and d["min"] == 0 and "opciones" not in d
    assert set(d) >= {"clave", "tipo", "etiqueta", "ayuda", "grupo", "peligroso",
                      "valor", "fuente", "defecto"}


def test_a_dict_bool_sin_min_ni_opciones(store):
    d = ajustes_catalogo.a_dict(_ajuste(config.ENV_PIPELINE_ILUSTRAR))
    assert d["tipo"] == "bool" and "min" not in d and "opciones" not in d


# --------------------------------------------------------------------------- #
# validar_valor por tipo                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entrada,guardado", [
    (True, "1"), (False, "0"), (1, "1"), (0, "0"),
    ("true", "1"), ("0", "0"), ("YES", "1"), ("off", "0"),
])
def test_validar_bool_ok(store, entrada, guardado):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PIPELINE_ILUSTRAR), entrada)
    assert err is None and val == guardado


def test_validar_bool_invalido(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PIPELINE_ILUSTRAR), "quizas")
    assert val is None and err is not None


def test_validar_int_ok(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA), 5)
    assert err is None and val == "5"


def test_validar_int_acepta_str(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA), " 7 ")
    assert err is None and val == "7"


def test_validar_int_bajo_minimo(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA), -1)
    assert val is None and "≥ 0" in err


def test_validar_int_rechaza_bool(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA), True)
    assert val is None and err is not None


def test_validar_int_no_numerico(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA), "x")
    assert val is None and err is not None


def test_validar_float_ok(store):
    val, err = ajustes_catalogo.validar_valor(_ajuste(config.ENV_PRESUPUESTO_USD_DIA), 3.0)
    assert err is None and float(val) == 3.0


def test_validar_float_bajo_minimo(store):
    val, err = ajustes_catalogo.validar_valor(
        _ajuste(config.ENV_PRESUPUESTO_USD_DIA), -1
    )
    assert val is None and err is not None


# --------------------------------------------------------------------------- #
# Precedencia efectiva via config._crudo (lo que ven los accesores)            #
# --------------------------------------------------------------------------- #


def test_config_crudo_store_gana_a_env(store, monkeypatch):
    monkeypatch.setenv(config.ENV_PIPELINE_REDACTAR, "0")
    ajustes.guardar(config.ENV_PIPELINE_REDACTAR, "1")
    assert config._crudo(config.ENV_PIPELINE_REDACTAR) == "1"
    assert config.pipeline_activo() is True  # accesor bool ve el store


def test_config_crudo_cae_a_env_sin_store(store, monkeypatch):
    monkeypatch.setenv(config.ENV_PIPELINE_REDACTAR, "1")
    assert config._crudo(config.ENV_PIPELINE_REDACTAR) == "1"
    assert config.pipeline_activo() is True


def test_config_entero_pasa_por_store(store, monkeypatch):
    monkeypatch.setenv(config.ENV_MAX_JOBS, "8")
    ajustes.guardar(config.ENV_MAX_JOBS, "2")
    assert config.max_jobs() == 2  # _entero -> _crudo -> store


def test_config_float_pasa_por_store(store):
    ajustes.guardar(config.ENV_ALERTAS_UMBRAL_ENGAGEMENT, "4.5")
    assert config.alertas_umbral_engagement() == 4.5


# --------------------------------------------------------------------------- #
# Redes del plan por marca (`KENI_PLAN_REDES::marca`): clave dinámica del catálogo #
# --------------------------------------------------------------------------- #


def _primera_marca() -> str:
    from keni_consola import marcas

    return marcas.opciones()[0][0]


def test_plan_redes_por_marca_en_catalogo(store):
    """Cada marca aporta un ajuste `KENI_PLAN_REDES::marca` (texto, grupo del plan diario);
    `por_clave` resuelve la clave dinámica igual que `KENI_PLAN_DIA::marca`."""
    mid = _primera_marca()
    clave = config.clave_por_marca(config.ENV_PLAN_REDES, mid)
    a = ajustes_catalogo.por_clave(clave)
    assert a is not None
    assert a.tipo == "texto"
    assert a.grupo == "noticias_produccion_marca"


def test_validar_plan_redes_acepta_csv_de_redes(store):
    """`validar_valor` acepta una CSV de ids de red válidos y normaliza espacios."""
    mid = _primera_marca()
    a = _ajuste(config.clave_por_marca(config.ENV_PLAN_REDES, mid))
    val, err = ajustes_catalogo.validar_valor(a, "facebook,instagram")
    assert err is None and val == "facebook,instagram"
    val, err = ajustes_catalogo.validar_valor(a, "")
    assert err is None and val == ""


def test_validar_plan_redes_rechaza_id_no_red(store):
    """`validar_valor` rechaza una CSV con un id que no es una red canónica."""
    mid = _primera_marca()
    a = _ajuste(config.clave_por_marca(config.ENV_PLAN_REDES, mid))
    val, err = ajustes_catalogo.validar_valor(a, "facebook,marte")
    assert val is None and err is not None
