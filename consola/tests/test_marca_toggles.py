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
    assert config.marca_apagada(config.ENV_PIPELINE_COPY, "claro-sports") is False
    assert config.marca_apagada(config.ENV_PIPELINE_ARTE, "nacion-gamer") is False


def test_override_falsy_apaga_la_marca(monkeypatch):
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE_COPY, "nacion-gamer"): "0"})
    assert config.marca_apagada(config.ENV_PIPELINE_COPY, "nacion-gamer") is True   # excluida
    assert config.marca_apagada(config.ENV_PIPELINE_COPY, "claro-sports") is False  # sin override


def test_override_truthy_no_apaga(monkeypatch):
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE_ARTE, "claro-sports"): "1"})
    assert config.marca_apagada(config.ENV_PIPELINE_ARTE, "claro-sports") is False


def test_clave_por_marca_formato():
    assert config.clave_por_marca("KENI_PIPELINE_COPY", "unotv") == "KENI_PIPELINE_COPY::unotv"


def test_catalogo_expone_toggles_por_marca():
    claves = {a.clave for a in ajustes_catalogo.catalogo()}
    # Por marca hay TRES toggles de máquina (ADR 0011): «Investigación» y «Producción»
    # (virtuales, agrupan sus etapas) y «Arte». La publicación va en su grupo `publicacion_marca`,
    # y el plan editorial diario (texto) en `noticias_produccion_marca`.
    assert config.clave_por_marca(config.ENV_INVESTIGACION, "nacion-gamer") in claves
    assert config.clave_por_marca(config.ENV_PRODUCCION, "nacion-gamer") in claves
    assert config.clave_por_marca(config.ENV_PIPELINE_ARTE, "unotv") in claves
    # Las etapas internas YA NO son toggles por marca (las agrupan los maestros).
    assert config.clave_por_marca(config.ENV_PIPELINE_COPY, "unotv") not in claves
    assert config.clave_por_marca(config.ENV_PIPELINE_SELECCION, "unotv") not in claves
    por_marca = [a for a in ajustes_catalogo.catalogo() if config.SEP_MARCA in a.clave]
    toggles = [a for a in por_marca if a.grupo in {"automatizacion_marca", "publicacion_marca"}]
    planes = [a for a in por_marca if a.grupo == "noticias_produccion_marca"]
    assert toggles and all(a.tipo == "bool" for a in toggles)
    assert planes and all(a.tipo == "texto" for a in planes)
    assert {a.grupo for a in por_marca} == {
        "automatizacion_marca", "publicacion_marca", "noticias_produccion_marca"
    }
    assert config.clave_por_marca(config.ENV_PLAN_DIA, "unotv") in claves


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
    monkeypatch.delenv(config.ENV_PIPELINE_COPY, raising=False)
    assert config.etapa_activa(config.ENV_PIPELINE_COPY, "unotv") is False

    # Maestro ON sin override: activa.
    monkeypatch.setenv(config.ENV_PIPELINE_COPY, "1")
    assert config.etapa_activa(config.ENV_PIPELINE_COPY, "unotv") is True

    # Override falsy por marca: apagada SOLO para esa marca.
    _store(monkeypatch, {config.clave_por_marca(config.ENV_PIPELINE_COPY, "unotv"): "0"})
    assert config.etapa_activa(config.ENV_PIPELINE_COPY, "unotv") is False
    assert config.etapa_activa(config.ENV_PIPELINE_COPY, "claro-sports") is True


def test_etapa_global_activa_cubre_las_seis_etapas(monkeypatch):
    # El AVANCE a revisión ya no es una etapa con toggle (corre incondicionalmente), así que
    # `etapa_global_activa` cubre solo las SEIS que sí se encienden/apagan.
    _store(monkeypatch, {})
    etapas = (
        config.ENV_PIPELINE_FUSION, config.ENV_RANKING_PERFIL_IA, config.ENV_PIPELINE_SELECCION,
        config.ENV_PIPELINE_VALIDACION, config.ENV_PIPELINE_COPY, config.ENV_PIPELINE_ARTE,
    )
    for env in etapas:
        monkeypatch.setenv(env, "1")
        assert config.etapa_global_activa(env) is True
        monkeypatch.setenv(env, "0")
        assert config.etapa_global_activa(env) is False


def test_etapa_global_activa_env_desconocida():
    import pytest

    with pytest.raises(ValueError):
        config.etapa_global_activa("KENI_NO_ES_UNA_ETAPA")
