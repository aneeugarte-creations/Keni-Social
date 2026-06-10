"""Cache de métricas: lazy fill, refresco de combo y estado del refresco en 2º plano.

TODO OFFLINE: la fuente es de muestra (`KENI_METRICAS_CONFIG` inexistente, lo fija
`entorno`) y la persistencia va al Postgres de pruebas (`entorno` lo provisiona y trunca
`metricas_cache` entre tests). No hay red ni APIs externas.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

import pytest

from keni_consola import metricas_cache as mc
from keni_consola import repos


@pytest.fixture(autouse=True)
def _reset_estado():
    """Resetea el estado de refresco EN MEMORIA antes y después de cada test."""
    mc._ESTADO.update(corriendo=False, iniciado_en="", terminado_en="", ultimo_error="")
    yield
    mc._ESTADO.update(corriendo=False, iniciado_en="", terminado_en="", ultimo_error="")


def test_lazy_fill_guarda_la_primera_vez_y_relee_de_cache(entorno, monkeypatch):
    # 1ª lectura: no hay cache -> calcula vía servicio, guarda y devuelve.
    rep, generado_en = mc.reporte("mes", None)
    assert rep["fuente"] == "muestra"
    assert generado_en  # ISO no vacío

    # Quedó persistido en la tabla de cache.
    entrada = repos.leer_metricas_cache(mc._clave(mc.TIPO_REPORTE, "mes", None))
    assert entrada is not None
    assert entrada["generado_en"] == generado_en

    # 2ª lectura: NO debe recalcular (si lo hiciera, esta trampa explotaría).
    def _explota(*_a, **_k):
        raise AssertionError("no debería recalcular: el combo ya está en cache")

    monkeypatch.setattr(mc.servicio, "construir_reporte", _explota)
    rep2, generado_en2 = mc.reporte("mes", None)
    assert generado_en2 == generado_en
    assert rep2["fuente"] == "muestra"


def test_refrescar_combo_actualiza_generado_en(entorno, monkeypatch):
    # Timestamps deterministas: el lazy fill estampa 10:00; el refresco posterior, 11:00.
    reloj = {"valor": "2026-05-29T10:00:00"}
    monkeypatch.setattr(mc, "_ahora", lambda: reloj["valor"])

    rep1, gen1 = mc.reporte("semana", None)
    assert gen1 == "2026-05-29T10:00:00"

    # Refrescar el combo lo recalcula (bypass cache) y reestampa el timestamp.
    reloj["valor"] = "2026-05-29T11:00:00"
    mc.refrescar_combo("semana", None)
    entrada = repos.leer_metricas_cache(mc._clave(mc.TIPO_REPORTE, "semana", None))
    assert entrada["generado_en"] == "2026-05-29T11:00:00"


def test_refrescar_combo_marca_concreta_incluye_listado(entorno):
    """Una marca CONCRETA refresca también el listado de piezas (lo que leen las Campañas).

    Regresión: el listado solo se llenaba por lazy-fill y nunca se refrescaba, así que la
    primera versión cacheada (sin `texto`/reels tras un deploy) se servía para siempre y la
    campaña de hashtag quedaba en cero. El daemon debe mantenerlo fresco por marca.
    """
    mc.refrescar_combo("semana", "claro_sports")
    entrada = repos.leer_metricas_cache(mc._clave(mc.TIPO_PIEZAS_LISTADO, "semana", "claro_sports"))
    assert entrada is not None
    assert "piezas" in entrada["payload"]


def test_refrescar_combo_todas_incluye_el_combo_completo(entorno):
    """`marca=None` ("todas") también refresca el combo COMPLETO (listado y series).

    Regresión del dashboard global congelado: la alerta de ingesta lee el listado de
    "todas" y el gráfico de seguidores sin filtro lee la serie global; al quedar ambos
    fuera del barrido se llenaban una vez por lazy-fill y servían PARA SIEMPRE su primera
    versión (piezas de hace semanas como "última pieza", precipicios viejos en el chart).
    """
    mc.refrescar_combo("semana", None)
    for tipo in (mc.TIPO_REPORTE, mc.TIPO_PIEZAS_LISTADO, mc.TIPO_SEGUIDORES, mc.TIPO_DESGLOSE):
        assert repos.leer_metricas_cache(mc._clave(tipo, "semana", None)) is not None, tipo


def test_clave_lleva_version_de_esquema(entorno):
    """La clave lleva `v{N}:`: subir la versión invalida los payloads de forma vieja.

    Regresión "Piezas publicadas: 0": un reporte cacheado ANTES de añadir el campo
    `publicaciones` se servía tal cual y el serializador rellenaba el hueco con 0. Con la
    versión en la clave, el payload viejo simplemente deja de leerse y se recalcula.
    """
    assert mc._clave(mc.TIPO_REPORTE, "mes", None).startswith(f"v{mc._VERSION_ESQUEMA}:")
    # Una entrada escrita con OTRO esquema (clave sin versión) no la lee nadie.
    repos.guardar_metricas_cache(
        "reporte:mes:todas", mc.TIPO_REPORTE, "mes", "", {"fuente": "muestra"}, "muestra",
        "2026-05-01T00:00:00",
    )
    rep, gen = mc.reporte("mes", None)
    assert gen != "2026-05-01T00:00:00"  # recalculó: no sirvió la entrada huérfana


def test_purga_borra_huerfanas_y_rangos_adhoc_viejos(entorno, monkeypatch):
    """La purga del barrido borra claves de esquema viejo y rangos ad-hoc caducados,
    sin tocar la cache por-pieza del tablero (misma tabla, tipo `pieza_contenido`)."""
    monkeypatch.setattr(mc, "_ahora", lambda: "2026-06-10T12:00:00")
    # Huérfana de esquema viejo + rango ad-hoc caducado + pieza del tablero (intocable).
    repos.guardar_metricas_cache(
        "reporte:mes:todas", mc.TIPO_REPORTE, "mes", "", {}, "muestra", "2026-05-01T00:00:00"
    )
    repos.guardar_metricas_cache(
        mc._clave(mc.TIPO_REPORTE, "rango:2026-05-01_2026-05-07", None),
        mc.TIPO_REPORTE, "rango:2026-05-01_2026-05-07", "", {}, "muestra",
        "2026-06-01T00:00:00",  # > 48h respecto al reloj congelado
    )
    repos.guardar_metricas_cache(
        "pieza:claro-sports:tiktok:99", "pieza_contenido", "", "claro-sports", {}, "real",
        "2026-05-01T00:00:00",
    )
    mc._purgar_obsoletas()
    assert repos.leer_metricas_cache("reporte:mes:todas") is None
    assert (
        repos.leer_metricas_cache(mc._clave(mc.TIPO_REPORTE, "rango:2026-05-01_2026-05-07", None))
        is None
    )
    assert repos.leer_metricas_cache("pieza:claro-sports:tiktok:99") is not None


def test_lectura_caducada_se_sirve_y_revalida_en_fondo(entorno, monkeypatch):
    """Una entrada más vieja que el TTL se sirve al instante PERO se revalida en fondo.

    Red de seguridad para combos fuera del barrido (meses históricos) o con el daemon
    caído: ninguna vista se queda con datos viejos más de un ciclo. La revalidación se
    observa por el hook (sin hilos reales en el test)."""
    revalidados: list = []
    monkeypatch.setattr(mc, "_revalidar_en_fondo", lambda *a: revalidados.append(a))

    rep, gen = mc.reporte("mes", "claro_sports")  # lazy fill, fresca
    rep2, gen2 = mc.reporte("mes", "claro_sports")
    assert gen2 == gen and revalidados == []  # fresca: ni recalcula ni revalida

    # Envejece el reloj más allá del TTL: la lectura sirve la entrada vieja y revalida.
    futuro = datetime.fromisoformat(gen) + timedelta(seconds=mc._ttl_segundos() + 60)
    monkeypatch.setattr(mc, "_ahora", lambda: futuro.isoformat(timespec="seconds"))
    rep3, gen3 = mc.reporte("mes", "claro_sports")
    assert gen3 == gen  # sirvió la cacheada (instantáneo)
    assert revalidados == [(mc.TIPO_REPORTE, "mes", "claro_sports")]


def test_estado_reporta_generado_en_del_combo(entorno):
    _rep, gen = mc.reporte("mes", "claro_sports")
    est = mc.estado("mes", "claro_sports")
    assert est["corriendo"] is False
    assert est["generado_en"] == gen
    # Un combo aún sin cachear devuelve generado_en vacío.
    assert mc.estado("7d", "unotv")["generado_en"] == ""


def test_disparar_refresco_es_idempotente(entorno, monkeypatch):
    # Bloqueamos el barrido para observar el estado "corriendo" de forma determinista.
    bloqueo = threading.Event()
    llamadas: list = []

    def _fake_refrescar_todo(prioritario=None):
        llamadas.append(prioritario)
        # Timeout AMPLIO (red de seguridad anti-cuelgue), no un plazo de carrera: el test
        # libera con `bloqueo.set()` en cuanto hace las 2 llamadas. Con 2.0s, bajo carga alta
        # (suite -n6 lenta) el hilo podía AGOTAR el wait ANTES de la 2ª llamada -> el 1er
        # barrido terminaba, `corriendo` volvía a False y la 2ª llamada arrancaba OTRO barrido
        # -> `llamadas` con 2 -> flake. 30s da margen de sobra sin cambiar la intención.
        bloqueo.wait(30.0)
        return 1

    monkeypatch.setattr(mc, "refrescar_todo", _fake_refrescar_todo)

    e1 = mc.disparar_refresco("mes", None)
    assert e1["corriendo"] is True

    # 2ª llamada mientras corre: NO arranca otro barrido.
    e2 = mc.disparar_refresco("mes", None)
    assert e2["corriendo"] is True

    bloqueo.set()
    for _ in range(100):
        if not mc._ESTADO["corriendo"]:
            break
        time.sleep(0.02)
    assert mc._ESTADO["corriendo"] is False
    assert llamadas == [("mes", None)]  # un único barrido real, con el combo prioritario
