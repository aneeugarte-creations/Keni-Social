"""Exclusiones por marca de las etapas de auto-producción (`config.marca_apagada`).

Semántica: una marca se EXCLUYE de una etapa con un override falsy en el store (`ENV::marca`);
sin override no está apagada (la etapa corre para ella, gateada por el global como siempre). Se
monkeypatchea el store (`ajustes.obtener`), sin tocar Postgres ni el fichero de ajustes.
"""

from __future__ import annotations

from keni_consola import ajustes_catalogo, config


def _store(monkeypatch, datos: dict[str, str]):
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda clave: datos.get(clave))


def test_sin_override_no_esta_apagada(monkeypatch):
    _store(monkeypatch, {})
    assert config.marca_apagada(config.ENV_PIPELINE_REDACTAR, "claro-sports") is False
    assert config.marca_apagada(config.ENV_PIPELINE_ILUSTRAR, "nacion-gamer") is False


def test_override_falsy_apaga_la_marca(monkeypatch):
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE_REDACTAR, "nacion-gamer"): "0"})
    assert config.marca_apagada(config.ENV_PIPELINE_REDACTAR, "nacion-gamer") is True   # excluida
    assert config.marca_apagada(config.ENV_PIPELINE_REDACTAR, "claro-sports") is False  # sin override


def test_override_truthy_no_apaga(monkeypatch):
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE_ILUSTRAR, "claro-sports"): "1"})
    assert config.marca_apagada(config.ENV_PIPELINE_ILUSTRAR, "claro-sports") is False


def test_autogen_copy_max_default_global_sin_override(monkeypatch):
    """Sin override por marca, `autogen_copy_max` cae al env/default global (store > env > def 12)."""
    _store(monkeypatch, {})  # sin store: cae a env; sin env: default 12
    monkeypatch.delenv(config.ENV_AUTOGEN_COPY_MAX, raising=False)
    assert config.autogen_copy_max("unotv") == 12
    _store(monkeypatch, {config.ENV_AUTOGEN_COPY_MAX: "7"})  # global por store
    assert config.autogen_copy_max("unotv") == 7


def test_autogen_copy_max_override_por_marca_manda(monkeypatch):
    """El override por marca (`KENI_AUTOGEN_COPY_MAX::marca`) MANDA sobre el global; min 1."""
    _store(monkeypatch, {
        config.ENV_AUTOGEN_COPY_MAX: "5",  # global
        config.clave_por_marca(config.ENV_AUTOGEN_COPY_MAX, "unotv"): "20",  # override unotv
        config.clave_por_marca(config.ENV_AUTOGEN_COPY_MAX, "claro-sports"): "0",  # min 1
    })
    assert config.autogen_copy_max("unotv") == 20  # override gana al global
    assert config.autogen_copy_max("claro-sports") == 1  # min 1
    assert config.autogen_copy_max("nacion-gamer") == 5  # sin override -> global


def test_ritmo_default_global_sin_override(monkeypatch):
    """Sin override por marca ni env, `ritmo` cae al default global (100 = sin freno)."""
    _store(monkeypatch, {})
    monkeypatch.delenv(config.ENV_RITMO, raising=False)
    assert config.ritmo("unotv") == 100
    assert config.ritmo("") == 100
    _store(monkeypatch, {config.ENV_RITMO: "50"})  # global por store
    assert config.ritmo("unotv") == 50
    assert config.ritmo("") == 50


def test_ritmo_override_por_marca_manda(monkeypatch):
    """El override por marca (`KENI_RITMO::marca`) MANDA sobre el global."""
    _store(monkeypatch, {
        config.ENV_RITMO: "80",  # global
        config.clave_por_marca(config.ENV_RITMO, "unotv"): "25",  # override unotv
    })
    assert config.ritmo("unotv") == 25  # override gana al global
    assert config.ritmo("nacion-gamer") == 80  # sin override -> global
    assert config.ritmo("") == 80  # global


def test_ritmo_clamp_a_10_100(monkeypatch):
    """El ritmo se CLAMPa a [10, 100]: nunca congela del todo ni excede el 100% de fábrica."""
    _store(monkeypatch, {
        config.ENV_RITMO: "500",  # > 100 -> 100
        config.clave_por_marca(config.ENV_RITMO, "unotv"): "1",  # < 10 -> 10
        config.clave_por_marca(config.ENV_RITMO, "claro-sports"): "-9",  # < 10 -> 10
    })
    assert config.ritmo("") == 100
    assert config.ritmo("unotv") == 10
    assert config.ritmo("claro-sports") == 10


def test_autogen_copy_max_escala_con_el_ritmo(monkeypatch):
    """El ritmo escala el cap por barrido: 100 = sin regresión (12), 50 = la mitad (6)."""
    _store(monkeypatch, {})
    monkeypatch.delenv(config.ENV_AUTOGEN_COPY_MAX, raising=False)
    monkeypatch.delenv(config.ENV_RITMO, raising=False)
    assert config.autogen_copy_max("unotv") == 12  # ritmo 100: cap de fábrica
    _store(monkeypatch, {config.ENV_RITMO: "50"})  # ritmo global a la mitad
    assert config.autogen_copy_max("unotv") == 6  # 12 * 50%
    # El ritmo PROPIO de la marca manda sobre el global al escalar su cap.
    _store(monkeypatch, {
        config.ENV_RITMO: "50",
        config.clave_por_marca(config.ENV_RITMO, "unotv"): "25",
    })
    assert config.autogen_copy_max("unotv") == 3  # 12 * 25%
    assert config.autogen_copy_max("nacion-gamer") == 6  # global 50%


def test_autogen_arte_max_escala_con_el_ritmo_global(monkeypatch):
    """`autogen_arte_max` (GLOBAL, sin marca) responde al ritmo global: 100 = 3, 50 = 2 (round)."""
    _store(monkeypatch, {})
    monkeypatch.delenv(config.ENV_AUTOGEN_ARTE_MAX, raising=False)
    monkeypatch.delenv(config.ENV_RITMO, raising=False)
    assert config.autogen_arte_max() == 3  # ritmo 100: cap de fábrica
    _store(monkeypatch, {config.ENV_RITMO: "50"})
    assert config.autogen_arte_max() == 2  # round(3 * 50%) = round(1.5) = 2
    _store(monkeypatch, {config.ENV_RITMO: "10"})
    assert config.autogen_arte_max() == 1  # max(1, round(0.3)) = 1 (mínimo 1)


def test_catalogo_expone_ritmo_editable():
    """El ritmo es editable (no peligroso): global + un override por marca, tipo int [10,100]."""
    ritmo_global = ajustes_catalogo.por_clave(config.ENV_RITMO)
    assert ritmo_global is not None
    assert ritmo_global.tipo == "int" and ritmo_global.peligroso is False
    assert ritmo_global.minimo == 10 and ritmo_global.maximo == 100
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    assert config.clave_por_marca(config.ENV_RITMO, "unotv") in claves


def test_clave_por_marca_formato():
    assert config.clave_por_marca("KENI_PIPELINE_REDACTAR", "unotv") == "KENI_PIPELINE_REDACTAR::unotv"


def test_catalogo_expone_toggles_por_marca():
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    # Cada FASE editable es un toggle por marca (ADR 0011 rev. fase×marca): apagar una
    # fase en una marca no afecta al resto. La publicación va en su grupo `publicacion_marca`,
    # y el plan editorial diario (texto) en `noticias_produccion_marca`.
    assert config.clave_por_marca(config.ENV_PIPELINE_ILUSTRAR, "unotv") in claves
    assert config.clave_por_marca(config.ENV_PIPELINE_REDACTAR, "unotv") in claves
    assert config.clave_por_marca(config.ENV_PIPELINE_RECOLECTAR, "unotv") in claves
    assert config.clave_por_marca(config.ENV_CRITICA_IA, "unotv") in claves
    por_marca = [a for a in ajustes_catalogo.catalogo() if config.SEP_MARCA in a.clave]
    # Las excepciones de máquina por marca van REPARTIDAS por proceso (ADR 0011, C4):
    # Investigación en su grupo, Producción/Arte en el suyo.
    grupos_marca_maquina = {
        "automatizacion_marca_investigacion",
        "automatizacion_marca_produccion",
    }
    toggles = [
        a for a in por_marca if a.grupo in grupos_marca_maquina | {"publicacion_marca"}
    ]
    planes = [a for a in por_marca if a.grupo == "noticias_produccion_marca"]
    assert toggles and all(a.tipo == "bool" for a in toggles)
    assert planes and all(a.tipo == "texto" for a in planes)
    assert {a.grupo for a in por_marca} == grupos_marca_maquina | {
        "publicacion_marca", "noticias_produccion_marca", "presupuesto_marca"
    }
    assert config.clave_por_marca(config.ENV_PLAN_DIA, "unotv") in claves


def test_etapa_activa_critica_y_hashtags_por_marca(monkeypatch):
    """Crítica y Sugerir hashtags honran `::marca` vía `config.etapa_activa` (antes solo global):
    apagar la fase en una marca NO afecta a las demás."""
    # Crítica IA: global OFF por defecto → ninguna marca la lleva.
    _store(monkeypatch, {})
    assert config.etapa_activa(config.ENV_CRITICA_IA, "unotv") is False
    # Sugerir hashtags: global ON por defecto → todas, salvo override falsy por marca.
    assert config.etapa_activa(config.ENV_PIPELINE_SUGERIR_HASHTAGS, "unotv") is True
    _store(
        monkeypatch,
        {config.clave_por_marca(config.ENV_PIPELINE_SUGERIR_HASHTAGS, "unotv"): "0"},
    )
    assert config.etapa_activa(config.ENV_PIPELINE_SUGERIR_HASHTAGS, "unotv") is False  # excluida
    assert config.etapa_activa(config.ENV_PIPELINE_SUGERIR_HASHTAGS, "nacion-gamer") is True  # intacta


def test_etapa_activa_traducir_y_admitir_por_marca(monkeypatch):
    """Traducir y Admitir (ON por defecto) honran global + `::marca` vía `config.etapa_activa`."""
    _store(monkeypatch, {})
    assert config.traducir_activo() is True
    assert config.admitir_activo() is True
    assert config.etapa_activa(config.ENV_PIPELINE_TRADUCIR, "unotv") is True
    assert config.etapa_activa(config.ENV_PIPELINE_ADMITIR, "unotv") is True
    # Override falsy por marca: apaga solo esa marca.
    _store(
        monkeypatch,
        {
            config.clave_por_marca(config.ENV_PIPELINE_TRADUCIR, "unotv"): "0",
            config.clave_por_marca(config.ENV_PIPELINE_ADMITIR, "unotv"): "0",
        },
    )
    assert config.etapa_activa(config.ENV_PIPELINE_TRADUCIR, "unotv") is False
    assert config.etapa_activa(config.ENV_PIPELINE_ADMITIR, "unotv") is False
    assert config.etapa_activa(config.ENV_PIPELINE_ADMITIR, "nacion-gamer") is True  # intacta
    # Global OFF explícito: apaga la etapa entera.
    _store(monkeypatch, {config.ENV_PIPELINE_TRADUCIR: "0", config.ENV_PIPELINE_ADMITIR: "0"})
    assert config.traducir_activo() is False
    assert config.admitir_activo() is False


def test_catalogo_expone_publicacion_por_marca():
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    assert config.clave_por_marca(config.ENV_PUBLICAR_REAL, "fundacion") in claves
    pub_marca = [a for a in ajustes_catalogo.catalogo() if a.grupo == "publicacion_marca"]
    assert pub_marca and all(config.ENV_PUBLICAR_REAL in a.clave for a in pub_marca)


def test_publicar_real_para_maestro_y_excepcion(monkeypatch):
    # Maestro OFF: ninguna marca publica de verdad.
    _store(monkeypatch, {})
    monkeypatch.delenv(config.ENV_PUBLICAR_REAL, raising=False)
    assert config.publicar_real_para("claro-sports") is False

    # Maestro ON: publican todas salvo las excluidas con override falsy por marca.
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PUBLICAR_REAL, "fundacion"): "0"})
    monkeypatch.setenv(config.ENV_PUBLICAR_REAL, "1")
    assert config.publicar_real_para("claro-sports") is True   # sin override: sigue al maestro
    assert config.publicar_real_para("fundacion") is False     # excluida explícitamente


def test_etapa_activa_es_la_fuente_unica(monkeypatch):
    """`config.etapa_activa` = maestro global ON y marca no excluida (la MISMA lectura para
    daemon, vista Pipelines y catalogo de ajustes)."""
    # Maestro OFF: apagada para todas las marcas aunque no haya override.
    _store(monkeypatch, {})
    monkeypatch.delenv(config.ENV_PIPELINE_REDACTAR, raising=False)
    assert config.etapa_activa(config.ENV_PIPELINE_REDACTAR, "unotv") is False

    # Maestro ON sin override: activa.
    monkeypatch.setenv(config.ENV_PIPELINE_REDACTAR, "1")
    assert config.etapa_activa(config.ENV_PIPELINE_REDACTAR, "unotv") is True

    # Override falsy por marca: apagada SOLO para esa marca.
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE_REDACTAR, "unotv"): "0"})
    assert config.etapa_activa(config.ENV_PIPELINE_REDACTAR, "unotv") is False
    assert config.etapa_activa(config.ENV_PIPELINE_REDACTAR, "claro-sports") is True


def test_etapa_default_es_el_suelo_de_fabrica(monkeypatch):
    # `etapa_default` es el suelo de fábrica de una etapa (lo que ve una marca sin override por
    # marca). Lo siembra el env `KENI_PIPELINE_<ETAPA>`; ya no es un maestro editable en la UI.
    _store(monkeypatch, {})
    etapas = (
        config.ENV_PIPELINE_FUSIONAR, config.ENV_PRIORIZAR_PERFIL_IA, config.ENV_PIPELINE_RECOLECTAR,
        config.ENV_PIPELINE_VERIFICAR, config.ENV_PIPELINE_REDACTAR, config.ENV_PIPELINE_ILUSTRAR,
    )
    for env in etapas:
        monkeypatch.setenv(env, "1")
        assert config.etapa_default(env) is True
        monkeypatch.setenv(env, "0")
        assert config.etapa_default(env) is False


def test_etapa_default_env_desconocida():
    import pytest

    with pytest.raises(ValueError):
        config.etapa_default("KENI_NO_ES_UNA_ETAPA")
