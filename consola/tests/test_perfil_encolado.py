"""Tests del ENCOLADO del refresco de perfil editorial (paso de Recolección -> job del worker).

OFFLINE: no llama a `claude` ni a la BD. Monkeypatchea `cola.encolar`/`generaciones` y el gate de
dominio (`necesita_refresco`/`refresco_en_curso`) para afirmar QUÉ se encola (carril de la cuenta de
la marca, proceso de investigación, Haiku, prioridad de fondo), la IDEMPOTENCIA (marcar en curso
antes de encolar; no re-encolar en vuelo) y la reapertura cuando la admisión rechaza el encolado.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from keni_consola import config, generaciones, ruteo_cuentas
from keni_consola.dominio import jobspec
from keni_consola.dominio import perfil_editorial as pe
from keni_consola.produccion.recolectar_daemon.pasos import agrupar


@pytest.fixture(autouse=True)
def _sin_intentos_bd(monkeypatch):
    """Los tests de este módulo son OFFLINE; mockea las llamadas a Postgres del contador de intentos."""
    from keni_consola.pipeline_contenido import _intentos as _int
    monkeypatch.setattr(_int, "tope_alcanzado", lambda *_: False)
    monkeypatch.setattr(_int, "en_backoff", lambda *_: False)
    monkeypatch.setattr(_int, "anotar", lambda *_: 1)


def _capturar_encolado(monkeypatch):
    """Instala stubs de `generaciones.crear`/`borrar_registro` y `cola.encolar`. Devuelve la captura."""
    from keni_consola import cola

    capt: dict[str, object] = {"encolados": [], "creados": [], "borrados": []}
    monkeypatch.setattr(generaciones, "crear",
                        lambda reg: capt["creados"].append(reg) or {"id": "g1"})
    monkeypatch.setattr(generaciones, "borrar_registro",
                        lambda gid: capt["borrados"].append(gid))
    monkeypatch.setattr(cola, "encolar",
                        lambda gid, spec, **kw: capt["encolados"].append((gid, spec, kw)))
    return capt


def test_encola_por_marca_con_carril_de_cuenta_e_investigacion(monkeypatch):
    capt = _capturar_encolado(monkeypatch)
    # Gate: hace falta refrescar y NO hay job en vuelo.
    monkeypatch.setattr(pe, "necesita_refresco", lambda *a, **k: True)
    monkeypatch.setattr(pe, "refresco_en_curso", lambda *a, **k: False)
    monkeypatch.setattr(pe, "construir_prompt_perfil", lambda m: f"PROMPT {m}")
    marcados: list[str] = []
    monkeypatch.setattr(pe, "marcar_refresco_encolado", lambda m, **k: marcados.append(m))

    agrupar._encolar_perfil("unotv", ttl_horas=24, ahora=datetime.now(UTC))

    assert marcados == ["unotv"]  # marcó en vuelo ANTES de encolar (idempotencia)
    assert len(capt["encolados"]) == 1
    gid, spec, kw = capt["encolados"][0]
    assert gid == "g1"
    # Carril de la CUENTA de la marca + proceso de investigación.
    assert jobspec.carril(spec) == ruteo_cuentas.carril_de_marca("unotv")
    assert kw["proceso"] == generaciones.PROCESO_INVESTIGACION
    assert kw["marca"] == "unotv"
    # Post-procesado de perfil + Haiku + fondo del pipeline.
    assert spec["procesar"] == jobspec.construir_perfil(marca="unotv")
    assert spec["endurecer"]["modelo"] == config.insumos_modelo()  # Haiku
    assert jobspec.prioridad(spec) == jobspec.PRIORIDAD_AUTOMATICO
    # El registro de actividad de Priorizar queda creado al encolar (lo completa el worker).
    assert capt["creados"][0]["etapa"] == "Priorizar"


def test_no_encola_si_no_hace_falta(monkeypatch):
    capt = _capturar_encolado(monkeypatch)
    monkeypatch.setattr(pe, "necesita_refresco", lambda *a, **k: False)
    monkeypatch.setattr(pe, "refresco_en_curso", lambda *a, **k: False)
    agrupar._encolar_perfil("unotv", ttl_horas=24, ahora=datetime.now(UTC))
    assert capt["encolados"] == []


def test_no_re_encola_con_refresco_en_vuelo(monkeypatch):
    capt = _capturar_encolado(monkeypatch)
    monkeypatch.setattr(pe, "necesita_refresco", lambda *a, **k: True)
    monkeypatch.setattr(pe, "refresco_en_curso", lambda *a, **k: True)  # ya hay un job en vuelo
    agrupar._encolar_perfil("unotv", ttl_horas=24, ahora=datetime.now(UTC))
    assert capt["encolados"] == []


def test_admision_rechazada_reabre_la_marca(monkeypatch):
    """Si `cola.encolar` rechaza (presupuesto/pausa): borra el registro y RE-ABRE el marcador."""
    from keni_consola import cola

    capt = _capturar_encolado(monkeypatch)
    monkeypatch.setattr(pe, "necesita_refresco", lambda *a, **k: True)
    monkeypatch.setattr(pe, "refresco_en_curso", lambda *a, **k: False)
    monkeypatch.setattr(pe, "construir_prompt_perfil", lambda m: "PROMPT")
    monkeypatch.setattr(pe, "marcar_refresco_encolado", lambda m, **k: None)
    limpiados: list[str] = []
    monkeypatch.setattr(pe, "limpiar_refresco_encolado", lambda m: limpiados.append(m))

    def _rechaza(*_a, **_k):
        raise generaciones.ColaLlenaError("llena")
    monkeypatch.setattr(cola, "encolar", _rechaza)

    agrupar._encolar_perfil("unotv", ttl_horas=24, ahora=datetime.now(UTC))

    assert limpiados == ["unotv"]      # marca re-abierta para reintentar
    assert capt["borrados"] == ["g1"]  # registro cadáver borrado


def test_sin_editorial_no_encola(monkeypatch):
    capt = _capturar_encolado(monkeypatch)
    monkeypatch.setattr(pe, "necesita_refresco", lambda *a, **k: True)
    monkeypatch.setattr(pe, "refresco_en_curso", lambda *a, **k: False)
    monkeypatch.setattr(pe, "construir_prompt_perfil", lambda m: "")  # sin editorial -> sin prompt
    agrupar._encolar_perfil("unotv", ttl_horas=24, ahora=datetime.now(UTC))
    assert capt["encolados"] == []
