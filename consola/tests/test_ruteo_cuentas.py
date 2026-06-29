"""Tests del reparto marca -> cuenta de Claude (A/B) y de los helpers de carril por cuenta.

PUROS (OFFLINE): no tocan Postgres ni subprocess. Cubren `ruteo_cuentas` (mapa + override + cuenta
por defecto) y los helpers de `jobspec` que el encolado/worker usan para rutar por cuenta y para
decidir si un job gasta tokens del presupuesto.
"""

from __future__ import annotations

import pytest

from keni_consola import ruteo_cuentas as rc
from keni_consola.dominio import jobspec


@pytest.fixture(autouse=True)
def _sin_overrides(monkeypatch):
    """Limpia los env de reparto para partir del mapa por defecto en cada test."""
    monkeypatch.delenv(rc.ENV_CUENTA_CLAUDE_DEFECTO, raising=False)
    for marca in ("unotv", "claro-sports", "nacion-gamer", "fundacion", "piso-15", "unotv-us"):
        monkeypatch.delenv(f"{rc.ENV_CUENTA_CLAUDE}::{marca}", raising=False)


def test_reparto_por_defecto():
    # Cuenta A: deportes + fundacion; Cuenta B: unotv + gamer (+ unotv-us).
    assert rc.cuenta_de_marca("claro-sports") == jobspec.CUENTA_A
    assert rc.cuenta_de_marca("fundacion") == jobspec.CUENTA_A
    assert rc.cuenta_de_marca("unotv") == jobspec.CUENTA_B
    assert rc.cuenta_de_marca("nacion-gamer") == jobspec.CUENTA_B
    assert rc.cuenta_de_marca("unotv-us") == jobspec.CUENTA_B


def test_marca_sin_reparto_y_sin_marca_caen_a_defecto():
    # piso-15 no esta en el reparto -> cuenta por defecto (A); idem un job SIN marca / cross.
    assert rc.cuenta_de_marca("piso-15") == jobspec.CUENTA_A
    assert rc.cuenta_de_marca("") == jobspec.CUENTA_A
    assert rc.cuenta_de_marca("desconocida") == jobspec.CUENTA_A


def test_cuenta_por_defecto_configurable(monkeypatch):
    monkeypatch.setenv(rc.ENV_CUENTA_CLAUDE_DEFECTO, "b")
    assert rc.cuenta_por_defecto() == jobspec.CUENTA_B
    # Lo SIN reparto sigue al nuevo defecto; lo repartido NO se mueve.
    assert rc.cuenta_de_marca("piso-15") == jobspec.CUENTA_B
    assert rc.cuenta_de_marca("") == jobspec.CUENTA_B
    assert rc.cuenta_de_marca("claro-sports") == jobspec.CUENTA_A


def test_cuenta_por_defecto_valor_invalido_cae_a_a(monkeypatch):
    monkeypatch.setenv(rc.ENV_CUENTA_CLAUDE_DEFECTO, "zzz")
    assert rc.cuenta_por_defecto() == jobspec.CUENTA_A


def test_override_por_marca_gana_al_reparto(monkeypatch):
    # Un override explicito reasigna la marca a la otra cuenta.
    monkeypatch.setenv(f"{rc.ENV_CUENTA_CLAUDE}::unotv", "a")
    assert rc.cuenta_de_marca("unotv") == jobspec.CUENTA_A
    monkeypatch.setenv(f"{rc.ENV_CUENTA_CLAUDE}::claro-sports", "b")
    assert rc.cuenta_de_marca("claro-sports") == jobspec.CUENTA_B


def test_override_invalido_se_ignora(monkeypatch):
    monkeypatch.setenv(f"{rc.ENV_CUENTA_CLAUDE}::unotv", "xyz")
    assert rc.cuenta_de_marca("unotv") == jobspec.CUENTA_B  # cae al reparto por defecto


def test_cuentas_visibles_admin_ve_ambas():
    # admin / superadmin (es_admin=True) -> ambas cuentas, ignorando las marcas.
    assert rc.cuentas_visibles(es_admin=True, marcas=[]) == list(jobspec.CUENTAS)
    assert rc.cuentas_visibles(es_admin=True, marcas=["unotv"]) == list(jobspec.CUENTAS)


def test_cuentas_visibles_editor_por_sus_marcas():
    # editor -> la(s) cuenta(s) de sus marcas (en orden A->B).
    assert rc.cuentas_visibles(es_admin=False, marcas=["unotv"]) == [jobspec.CUENTA_B]
    assert rc.cuentas_visibles(es_admin=False, marcas=["claro-sports"]) == [jobspec.CUENTA_A]
    assert rc.cuentas_visibles(
        es_admin=False, marcas=["unotv", "claro-sports"]
    ) == [jobspec.CUENTA_A, jobspec.CUENTA_B]


def test_cuentas_visibles_editor_sin_marcas_vacio():
    assert rc.cuentas_visibles(es_admin=False, marcas=[]) == []


def test_marcas_y_etiqueta_de_cuenta():
    # Las marcas del catálogo (amx por defecto) se reparten A/B; la etiqueta une sus nombres.
    marcas_b = rc.marcas_de_cuenta(jobspec.CUENTA_B)
    assert "unotv" in marcas_b and "nacion-gamer" in marcas_b
    assert "claro-sports" not in marcas_b
    etiqueta_b = rc.etiqueta_de_cuenta(jobspec.CUENTA_B)
    assert "UnoTV" in etiqueta_b and "Nación Gamer" in etiqueta_b
    assert "claro-sports" in rc.marcas_de_cuenta(jobspec.CUENTA_A)


def test_carril_de_marca_mapea_a_carril_de_cuenta():
    assert rc.carril_de_marca("claro-sports") == jobspec.CARRIL_CUENTA_A
    assert rc.carril_de_marca("unotv") == jobspec.CARRIL_CUENTA_B
    assert rc.carril_de_marca("") == jobspec.CARRIL_CUENTA_A  # sin marca -> cuenta por defecto


def test_carril_de_cuenta_helper():
    assert jobspec.carril_de_cuenta(jobspec.CUENTA_A) == jobspec.CARRIL_CUENTA_A
    assert jobspec.carril_de_cuenta(jobspec.CUENTA_B) == jobspec.CARRIL_CUENTA_B
    assert jobspec.carril_de_cuenta("desconocida") == jobspec.CARRIL_CUENTA_A


def test_carril_de_cuenta_es_explicito_en_el_spec():
    # Un job de investigacion estampa el carril de cuenta a nivel raiz; `carril()` lo respeta.
    spec = jobspec.construir(
        prompt="p", procesar=jobspec.construir_prompt_lib(), carril=jobspec.CARRIL_CUENTA_B
    )
    assert jobspec.carril(spec) == jobspec.CARRIL_CUENTA_B


def test_gasta_tokens_carril_de_cuenta_cuenta_para_presupuesto():
    # Un job de cuenta (investigacion via `claude`) SI gasta tokens (a diferencia de proceso).
    inv = jobspec.construir(
        prompt="p", procesar=jobspec.construir_prompt_lib(), carril=jobspec.CARRIL_CUENTA_A
    )
    assert jobspec.gasta_tokens(inv) is True
    inferencia = jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib())
    assert jobspec.gasta_tokens(inferencia) is True
    # Los jobs de PROCESO (render/ASR/imagen) quedan EXENTOS.
    render = jobspec.construir_proceso(jobspec.PROC_RENDER_VIDEO, {"composicion_id": "c1"})
    assert jobspec.gasta_tokens(render) is False
