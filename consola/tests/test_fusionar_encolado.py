"""Tests del ENCOLADO de la fusión semántica (paso de Recolección -> job del worker POR MARCA).

OFFLINE: no llama a `claude` ni a la BD. Monkeypatchea `cola.encolar`/`generaciones` y el marcador de
dominio (`fusion_en_curso`/`marcar_fusion_encolada`/`limpiar_fusion_encolada`) para afirmar QUÉ se
encola (carril de la cuenta de la marca, proceso de investigación, modelo de la fusión, prioridad de
fondo), la IDEMPOTENCIA (marcar en curso antes de encolar; no re-encolar en vuelo) y la reapertura
cuando la admisión rechaza el encolado.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from keni_consola import config, generaciones, ruteo_cuentas
from keni_consola.produccion import recolectar_daemon
from keni_consola.dominio import fusionar_semantica as fs
from keni_consola.dominio import jobspec
from keni_consola.produccion.recolectar_daemon import _comun
from keni_consola.produccion.recolectar_daemon.pasos import fusionar_semantica as paso


@pytest.fixture(autouse=True)
def _sin_intentos_bd(monkeypatch):
    """Los tests de este módulo son OFFLINE; mockea las llamadas a Postgres del contador de intentos."""
    from keni_consola.pipeline_contenido import _intentos as _int
    monkeypatch.setattr(_int, "tope_alcanzado", lambda *_: False)
    monkeypatch.setattr(_int, "en_backoff", lambda *_: False)
    monkeypatch.setattr(_int, "anotar", lambda *_: 1)


@pytest.fixture(autouse=True)
def _reset_throttle_fusionar():
    """Resetea el throttle/huella globales: ni una pasada sellada por otro test la frena, ni una
    huella previa la hace saltar por skip-if-unchanged."""
    _comun._ultimo_fusionar = 0.0
    _comun._ultima_huella_fusionar = None
    yield
    _comun._ultimo_fusionar = 0.0
    _comun._ultima_huella_fusionar = None


@pytest.fixture(autouse=True)
def _sin_filtro_score_fusion(monkeypatch):
    """El filtro de relevancia (`KENI_FUSION_MIN_SCORE`, def 0.3) se apaga por defecto en estos tests
    de ENCOLADO: prueban el ruteo/idempotencia, no el filtro (que tiene su propio test más abajo, que
    lo re-activa con `monkeypatch.setenv`)."""
    monkeypatch.setenv("KENI_FUSION_MIN_SCORE", "0")


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


_CLUSTERS = [
    {"id": "c1", "titulo": "Remontada épica", "marca": "unotv", "n_fuentes": 2, "score": 0.6},
    {"id": "c2", "titulo": "Remontada increíble", "marca": "unotv", "n_fuentes": 1, "score": 0.2},
]


def test_encola_por_marca_con_carril_de_cuenta_e_investigacion(monkeypatch):
    capt = _capturar_encolado(monkeypatch)
    marcados: list[str] = []
    monkeypatch.setattr(fs, "marcar_fusion_encolada", lambda m, **k: marcados.append(m))

    ok = paso._encolar_fusion("unotv", list(_CLUSTERS), ahora=datetime.now(UTC))

    assert ok is True
    assert marcados == ["unotv"]  # marcó en vuelo ANTES de encolar (idempotencia)
    assert len(capt["encolados"]) == 1
    gid, spec, kw = capt["encolados"][0]
    assert gid == "g1"
    # Carril de la CUENTA de la marca + proceso de investigación.
    assert jobspec.carril(spec) == ruteo_cuentas.carril_de_marca("unotv")
    assert kw["proceso"] == generaciones.PROCESO_INVESTIGACION
    assert kw["marca"] == "unotv"
    # Post-procesado de fusión (lleva la marca + el lote serializado) + modelo de la fusión + fondo.
    assert spec["procesar"]["kind"] == jobspec.PROC_FUSIONAR
    assert spec["procesar"]["marca"] == "unotv"
    assert {r["id"] for r in spec["procesar"]["recientes"]} == {"c1", "c2"}
    assert spec["endurecer"]["modelo"] == config.fusion_modelo()
    # JSON-in/JSON-out: corre como sus etapas hermanas (sin esquemas de tools, un solo turno) para no
    # inflar entrada (~17k de tools) ni salida (~4000 de razonamiento agéntico).
    assert spec["endurecer"]["sin_tools"] is True
    assert spec["endurecer"]["max_turns"] == 1
    assert jobspec.prioridad(spec) == jobspec.PRIORIDAD_AUTOMATICO
    # El registro de actividad de Fusionar queda creado al encolar (lo completa el worker).
    assert capt["creados"][0]["etapa"] == "Fusionar"


def test_lote_sin_dos_validos_no_encola(monkeypatch):
    capt = _capturar_encolado(monkeypatch)
    monkeypatch.setattr(fs, "marcar_fusion_encolada", lambda m, **k: None)
    uno = [{"id": "c1", "titulo": "Solo una", "marca": "unotv"}]
    assert paso._encolar_fusion("unotv", uno, ahora=datetime.now(UTC)) is False
    assert capt["encolados"] == []


def test_admision_rechazada_reabre_la_marca(monkeypatch):
    """Si `cola.encolar` rechaza (presupuesto/pausa): borra el registro y RE-ABRE el marcador."""
    from keni_consola import cola

    capt = _capturar_encolado(monkeypatch)
    monkeypatch.setattr(fs, "marcar_fusion_encolada", lambda m, **k: None)
    limpiados: list[str] = []
    monkeypatch.setattr(fs, "limpiar_fusion_encolada", lambda m: limpiados.append(m))

    def _rechaza(*_a, **_k):
        raise generaciones.ColaLlenaError("llena")
    monkeypatch.setattr(cola, "encolar", _rechaza)

    ok = paso._encolar_fusion("unotv", list(_CLUSTERS), ahora=datetime.now(UTC))

    assert ok is False
    assert limpiados == ["unotv"]      # marca re-abierta para reintentar
    assert capt["borrados"] == ["g1"]  # registro cadáver borrado


def test_paso_no_re_encola_marca_con_fusion_en_vuelo(monkeypatch):
    """Idempotencia: una marca con marcador `fusion_en_curso` fresco NO se re-encola este barrido."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [dict(c, estado="nuevo") for c in _CLUSTERS]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: [dict(c) for c in recientes])
    monkeypatch.setattr(fs, "fusion_en_curso", lambda *a, **k: True)  # ya hay un job en vuelo
    encolados: list[str] = []
    monkeypatch.setattr(paso, "_encolar_fusion", lambda m, c, **k: encolados.append(m))

    res = recolectar_daemon.paso_fusionar_semantica(forzar=True)
    assert encolados == []
    assert res == {"encolados": 0, "marcas": 0, "candidatos": 2}


def test_paso_salta_marca_apagada(monkeypatch):
    """Excepción por marca (toggle "Fusionar"): una marca apagada no se encola."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [dict(c, estado="nuevo") for c in _CLUSTERS]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: [dict(c) for c in recientes])
    # Fusionar es POR MARCA (`etapa_activa`): se apaga con su override `::marca` falsy en el store.
    overrides = {config.clave_por_marca(config.ENV_PIPELINE_FUSIONAR, "unotv"): "0"}
    monkeypatch.setattr("keni_consola.ajustes.obtener", lambda clave: overrides.get(clave))
    encolados: list[str] = []
    monkeypatch.setattr(paso, "_encolar_fusion", lambda m, c, **k: encolados.append(m))

    res = recolectar_daemon.paso_fusionar_semantica(forzar=True)
    assert encolados == []
    assert res["marcas"] == 0


def test_paso_encola_por_marca(monkeypatch):
    """El barrido agrupa por marca y encola una marca con ≥2 historias frescas."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [dict(c, estado="nuevo") for c in _CLUSTERS]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: [dict(c) for c in recientes])
    monkeypatch.setattr(fs, "fusion_en_curso", lambda *a, **k: False)
    encolados: list[tuple[str, int]] = []
    monkeypatch.setattr(paso, "_encolar_fusion",
                        lambda m, c, **k: encolados.append((m, len(c))) or True)

    res = recolectar_daemon.paso_fusionar_semantica(forzar=True)
    assert encolados == [("unotv", 2)]
    assert res == {"encolados": 2, "marcas": 1, "candidatos": 2}


def test_paso_sin_novedad_no_encola(monkeypatch):
    """DELTA-AWARE (def ON): si TODOS los candidatos de la marca ya fueron vistos por la fusión
    (`fusion_vista` sellada), la pasada se salta («sin novedad»): 0 jobs, 0 llamadas al LLM."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [dict(c, estado="nuevo", fusion_vista="2026-07-01T00:00:00+00:00") for c in _CLUSTERS]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: [dict(c) for c in recientes])
    monkeypatch.setattr(fs, "fusion_en_curso", lambda *a, **k: False)
    encolados: list[str] = []
    monkeypatch.setattr(paso, "_encolar_fusion", lambda m, c, **k: encolados.append(m) or True)

    res = recolectar_daemon.paso_fusionar_semantica(forzar=True)
    assert encolados == []
    assert res == {"encolados": 0, "marcas": 0, "candidatos": 2}


def test_paso_sin_novedad_con_flag_off_encola_legacy(monkeypatch):
    """Con `KENI_FUSION_INCREMENTAL=0` vuelve el camino previo: el lote ya visto se re-encola igual."""
    monkeypatch.setenv("KENI_FUSION_INCREMENTAL", "0")
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [dict(c, estado="nuevo", fusion_vista="2026-07-01T00:00:00+00:00") for c in _CLUSTERS]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: [dict(c) for c in recientes])
    monkeypatch.setattr(fs, "fusion_en_curso", lambda *a, **k: False)
    encolados: list[tuple[str, int]] = []
    monkeypatch.setattr(paso, "_encolar_fusion",
                        lambda m, c, **k: encolados.append((m, len(c))) or True)

    res = recolectar_daemon.paso_fusionar_semantica(forzar=True)
    assert encolados == [("unotv", 2)]
    assert res == {"encolados": 2, "marcas": 1, "candidatos": 2}


def test_paso_con_novedad_encola_nuevos_primero(monkeypatch):
    """Con novedad parcial la marca SÍ se encola y el lote va NUEVOS-primero: el tope del lote nunca
    deja una historia sin ver fuera por contexto ya visto, y el lote del worker coincide con el prompt."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [
        dict(_CLUSTERS[0], estado="nuevo", fusion_vista="2026-07-01T00:00:00+00:00"),  # ya vista
        dict(_CLUSTERS[1], estado="nuevo"),                                            # sin ver
    ]
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: [dict(c) for c in recientes])
    monkeypatch.setattr(fs, "fusion_en_curso", lambda *a, **k: False)
    lotes: list[list[str]] = []
    monkeypatch.setattr(paso, "_encolar_fusion",
                        lambda m, c, **k: lotes.append([x["id"] for x in c]) or True)

    res = recolectar_daemon.paso_fusionar_semantica(forzar=True)
    assert lotes == [["c2", "c1"]]  # la nueva (c2) primero; la vista (c1) queda como contexto
    assert res["marcas"] == 1


def test_encolar_fusion_delta_manda_nuevas_y_contexto_compacto(monkeypatch):
    """Con parte del lote ya visto, el job se encola con el prompt DELTA (nuevas completas + contexto
    compacto) y el spec lleva el lote ENTERO (el worker valida/funde contra los mismos ids)."""
    capt = _capturar_encolado(monkeypatch)
    monkeypatch.setattr(fs, "marcar_fusion_encolada", lambda m, **k: None)
    clusters = [
        {"id": "n1", "titulo": "Historia nueva", "marca": "unotv", "n_fuentes": 1, "score": 0.5},
        {"id": "v1", "titulo": "Historia ya vista", "marca": "unotv", "n_fuentes": 2, "score": 0.6,
         "fusion_vista": "2026-07-01T00:00:00+00:00", "tema_macro": "Mundial 2026"},
    ]

    assert paso._encolar_fusion("unotv", clusters, ahora=datetime.now(UTC)) is True
    _gid, spec, _kw = capt["encolados"][0]
    prompt = capt["creados"][0]["prompt"]
    assert prompt == fs.construir_prompt_fusion_incremental([clusters[0]], [clusters[1]])
    assert "historias_previas" in prompt      # contexto compacto embebido
    assert "Historia nueva" in prompt         # la nueva viaja completa
    assert [r["id"] for r in spec["procesar"]["recientes"]] == ["n1", "v1"]  # lote entero al worker


def test_encolar_fusion_todo_nuevo_usa_pasada_completa(monkeypatch):
    """Un lote SIN nada visto aún (p. ej. tras un arranque) usa el prompt completo de siempre,
    también con el delta activo (no hay contexto que comprimir)."""
    capt = _capturar_encolado(monkeypatch)
    monkeypatch.setattr(fs, "marcar_fusion_encolada", lambda m, **k: None)

    assert paso._encolar_fusion("unotv", list(_CLUSTERS), ahora=datetime.now(UTC)) is True
    prompt = capt["creados"][0]["prompt"]
    assert prompt == fs.construir_prompt_fusion(list(_CLUSTERS))


def test_paso_filtra_clusters_bajo_min_score(monkeypatch):
    """El candidato a Fusionar excluye los clusters con `score` por debajo de `KENI_FUSION_MIN_SCORE`.
    SALVAGUARDA: si tras el filtro la marca queda con <2, no se encola ese ciclo; con un umbral más
    bajo ambos pasan y la marca se encola."""
    monkeypatch.setattr(recolectar_daemon.config, "fusionar_semantica_activo", lambda: True)
    recientes = [dict(c, estado="nuevo") for c in _CLUSTERS]  # c1 score 0.6, c2 score 0.2
    monkeypatch.setattr(recolectar_daemon.repos, "clusters_recientes",
                        lambda ventana_h, *a, **k: [dict(c) for c in recientes])
    monkeypatch.setattr(fs, "fusion_en_curso", lambda *a, **k: False)
    encolados: list[tuple[str, int]] = []
    monkeypatch.setattr(paso, "_encolar_fusion",
                        lambda m, c, **k: encolados.append((m, len(c))) or True)

    # Umbral 0.3: c2 (0.2) cae -> unotv queda con 1 -> no encola.
    monkeypatch.setenv("KENI_FUSION_MIN_SCORE", "0.3")
    res = recolectar_daemon.paso_fusionar_semantica(forzar=True)
    assert encolados == []
    assert res["marcas"] == 0

    # Umbral 0.1: c2 (0.2 >= 0.1) pasa -> unotv encola con 2.
    monkeypatch.setenv("KENI_FUSION_MIN_SCORE", "0.1")
    _comun._ultimo_fusionar = 0.0
    _comun._ultima_huella_fusionar = None
    res = recolectar_daemon.paso_fusionar_semantica(forzar=True)
    assert encolados == [("unotv", 2)]
    assert res == {"encolados": 2, "marcas": 1, "candidatos": 2}
