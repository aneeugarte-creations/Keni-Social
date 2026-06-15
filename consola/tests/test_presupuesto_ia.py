"""Tests de la ECONOMIA DE TOKENS (presupuesto_ia): ledger, niveles de corte y gates.

TODO OFFLINE (nunca toca `claude` ni red). Cubre:
  - Ledger `gasto_ia`: UPSERT idempotente por gen_id; agregados por dia.
  - Hook de cierre del almacen de generaciones: un terminal con metricas deja fila; un
    terminal sin consumo no ensucia el ledger; re-cerrar no duplica gasto.
  - Niveles de corte: normal (sin presupuesto), solo_manual (presupuesto agotado),
    agotado (presupuesto + margen) y pausado (kill switch manda sobre todo).
  - Gate de ADMISION (`cola.encolar`): pausado corta todo; agotado corta lo que gasta
    tokens (un job de PROCESO queda exento); solo_manual corta SOLO el fondo. Las
    excepciones son subclase de ColaLlenaError (el 429 central y el backpressure del
    pipeline las tratan sin cambios).
  - Gate de RECLAMO (`cola.reclamar(prioridad_minima=...)`): la avalancha de fondo YA
    encolada deja de salir; lo manual sigue. El worker elige el gate segun el nivel.
  - API: `/api/actividad/cola` expone `presupuesto` y `/series` expone `gasto`.
"""

from __future__ import annotations

import pytest

from keni_consola import cola, generaciones, presupuesto_ia, repos
from keni_consola.dominio import jobspec
from keni_consola.tiempo import ahora_iso

_MARCA = "unotv"

# Referencia GENUINA al encolado real: `crear_app` REASIGNA `generaciones.encolar_job_claude`
# por una fake (y persiste entre tests); la capturamos al importar (patron de test_worker_cola).
_ENCOLAR_REAL = generaciones.encolar_job_claude


def _hoy() -> str:
    return ahora_iso()[:10]


def _gen(tipo: str = "copy", etiqueta: str = "X") -> str:
    return generaciones.crear({"tipo": tipo, "marca": _MARCA, "etiqueta": etiqueta})["id"]


def _cerrar(gen_id: str, *, tokens_in: int = 0, tokens_out: int = 0, coste: float = 0.0,
            estado: str = "completado") -> None:
    """Lleva el registro a terminal con metricas (dispara el hook del ledger)."""
    generaciones.actualizar(gen_id, {
        "estado": estado,
        "metricas": {"tokens_in": tokens_in, "tokens_out": tokens_out, "total_cost_usd": coste},
        "fecha_fin": ahora_iso(),
    })


def _encolar(prioridad: int) -> str:
    gen_id = _gen()
    spec = jobspec.construir(
        prompt="p", procesar=jobspec.construir_hashtags(), prioridad=prioridad
    )
    return cola.encolar(gen_id, spec)


# --------------------------------------------------------------------------- #
# Ledger gasto_ia                                                              #
# --------------------------------------------------------------------------- #


def test_ledger_upsert_idempotente(entorno):
    repos.registrar_gasto_ia("g1", dia=_hoy(), tokens_in=100, tokens_out=50, coste_usd=0.1)
    repos.registrar_gasto_ia("g1", dia=_hoy(), tokens_in=120, tokens_out=60, coste_usd=0.2)
    gasto = repos.gasto_ia_del_dia(_hoy())
    # Una sola fila, con los ULTIMOS valores (re-cierre actualiza, no suma dos veces).
    assert gasto["generaciones"] == 1
    assert gasto["tokens"] == 180
    assert gasto["coste_usd"] == pytest.approx(0.2)


def test_ledger_agrega_por_dia(entorno):
    repos.registrar_gasto_ia("a", dia=_hoy(), tokens_in=10, tokens_out=5)
    repos.registrar_gasto_ia("b", dia=_hoy(), tokens_in=20, tokens_out=15)
    repos.registrar_gasto_ia("viejo", dia="2000-01-01", tokens_in=999, tokens_out=999)
    gasto = repos.gasto_ia_del_dia(_hoy())
    assert gasto["tokens"] == 50 and gasto["generaciones"] == 2
    serie = repos.gasto_ia_por_dia(7)
    assert [d for d in serie if d["dia"] == _hoy()][0]["tokens"] == 50
    assert all(d["dia"] != "2000-01-01" for d in serie)  # fuera de la ventana


def test_hook_cierre_registra_gasto(entorno):
    gen_id = _gen()
    _cerrar(gen_id, tokens_in=1000, tokens_out=500, coste=0.5)
    gasto = repos.gasto_ia_del_dia(_hoy())
    assert gasto["tokens"] == 1500
    assert gasto["tokens_in"] == 1000 and gasto["tokens_out"] == 500
    assert gasto["generaciones"] == 1


def test_hook_error_tambien_registra(entorno):
    """Un job que MURIO en error gasto tokens igualmente (parciales): cuenta al presupuesto."""
    gen_id = _gen()
    _cerrar(gen_id, tokens_in=300, tokens_out=0, estado="error")
    assert repos.gasto_ia_del_dia(_hoy())["tokens"] == 300


# --------------------------------------------------------------------------- #
# gasto_ia.proceso: relleno en vivo (ADR 0011)                                  #
# --------------------------------------------------------------------------- #


def _proceso_de_gasto(gen_id: str) -> str | None:
    """Lee la columna `proceso` de la fila del ledger (sin reader publico)."""
    from keni_consola._db_comun import _conectar

    con = _conectar()
    try:
        fila = con.execute(
            "SELECT proceso FROM gasto_ia WHERE gen_id = ?", (gen_id,)
        ).fetchone()
    finally:
        con.close()
    return fila["proceso"] if fila else None


def test_ledger_proceso_default_produccion(entorno):
    # Sin pasar proceso, el ledger lo asume 'produccion' (la maquina de contenido).
    repos.registrar_gasto_ia("g1", dia=_hoy(), tokens_in=10, tokens_out=5)
    assert _proceso_de_gasto("g1") == "produccion"


def test_ledger_proceso_explicito(entorno):
    repos.registrar_gasto_ia(
        "g2", dia=_hoy(), tokens_in=10, tokens_out=5, proceso="investigacion"
    )
    assert _proceso_de_gasto("g2") == "investigacion"


def test_hook_cierre_sella_proceso_investigacion(entorno):
    # Una criba/verificacion de fuente (tipo pipeline + etiqueta "Verificar · …") -> investigacion.
    gen_id = generaciones.crear(
        {"tipo": "pipeline", "marca": _MARCA, "etiqueta": "Verificar · fuente"}
    )["id"]
    _cerrar(gen_id, tokens_in=100, tokens_out=50, coste=0.1)
    assert _proceso_de_gasto(gen_id) == "investigacion"


def test_hook_cierre_sella_proceso_produccion(entorno):
    gen_id = _gen(tipo="copy")
    _cerrar(gen_id, tokens_in=100, tokens_out=50, coste=0.1)
    assert _proceso_de_gasto(gen_id) == "produccion"


def test_hook_sin_consumo_no_deja_fila(entorno):
    """Un terminal sin metricas de tokens (imagen/proceso/fallo temprano) no ensucia el ledger."""
    gen_id = _gen(tipo="imagen")
    generaciones.actualizar(gen_id, {"estado": "completado", "fecha_fin": ahora_iso()})
    sin_metricas = _gen(tipo="render-video")
    _cerrar(sin_metricas, tokens_in=0, tokens_out=0, coste=0.0)
    assert repos.gasto_ia_del_dia(_hoy())["generaciones"] == 0


def test_hook_cierre_persiste_cache_de_prompt(entorno):
    """El cierre vuelca al ledger los tokens de PROMPT CACHING (cache_read/cache_creation).

    Sin esa señal no se puede medir si el caching ocurre ni el ahorro. La serie por dia los suma.
    """
    gen_id = _gen()
    generaciones.actualizar(gen_id, {
        "estado": "completado",
        "metricas": {
            "tokens_in": 100, "tokens_out": 50, "total_cost_usd": 0.1,
            "cache_read": 4000, "cache_creation": 200,
        },
        "fecha_fin": ahora_iso(),
    })
    serie = repos.gasto_ia_por_dia(7)
    hoy = [d for d in serie if d["dia"] == _hoy()][0]
    assert hoy["cache_read"] == 4000
    assert hoy["cache_creation"] == 200


def test_ledger_cache_default_cero_sin_caching(entorno):
    """Un run que NO cachea no rompe el ledger: las columnas de cache quedan en 0."""
    repos.registrar_gasto_ia("nc", dia=_hoy(), tokens_in=10, tokens_out=5)
    hoy = [d for d in repos.gasto_ia_por_dia(2) if d["dia"] == _hoy()][0]
    assert hoy["cache_read"] == 0 and hoy["cache_creation"] == 0


def test_hook_recierre_no_duplica(entorno):
    """Re-cerrar la misma generacion (reintento tras deploy) actualiza la fila, no la duplica."""
    gen_id = _gen()
    _cerrar(gen_id, tokens_in=100, tokens_out=100)
    _cerrar(gen_id, tokens_in=150, tokens_out=150)
    gasto = repos.gasto_ia_del_dia(_hoy())
    assert gasto["generaciones"] == 1 and gasto["tokens"] == 300


# --------------------------------------------------------------------------- #
# Niveles de corte                                                             #
# --------------------------------------------------------------------------- #


def test_nivel_normal_sin_presupuesto(entorno):
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL
    est = presupuesto_ia.estado()
    assert est["presupuesto_tokens_dia"] == 0
    assert est["restante_tokens"] is None and est["pct_usado"] is None


def test_nivel_escalones(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_DIA", "1000")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL

    repos.registrar_gasto_ia("g1", dia=_hoy(), tokens_in=600, tokens_out=400)  # = 1000
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_SOLO_MANUAL

    repos.registrar_gasto_ia("g2", dia=_hoy(), tokens_in=200, tokens_out=0)  # 1200 = +20%
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_AGOTADO

    est = presupuesto_ia.estado()
    assert est["gastado"]["tokens"] == 1200
    assert est["restante_tokens"] == 0
    assert est["pct_usado"] == pytest.approx(120.0)


def test_nivel_pausado_manda(entorno, monkeypatch):
    monkeypatch.setenv("KENI_GENERACION_PAUSADA", "1")
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_PAUSADO
    assert presupuesto_ia.estado()["pausada"] is True


# --------------------------------------------------------------------------- #
# Regla ÚNICA del presupuesto (bloqueo_admision): la comparten ambos gates      #
# --------------------------------------------------------------------------- #


def test_bloqueo_admision_es_la_fuente_unica_de_la_regla():
    """Matriz completa del helper que comparten `cola.encolar` y `worker._bucle`.

    PAUSADO corta todo; un PROCESO (no gasta tokens) solo lo frena el kill switch; AGOTADO
    corta todo lo que gasta tokens (manual incluido); SOLO_MANUAL corta solo el fondo.
    """
    B = presupuesto_ia.bloqueo_admision
    N, SM, AG, PA = (
        presupuesto_ia.NIVEL_NORMAL, presupuesto_ia.NIVEL_SOLO_MANUAL,
        presupuesto_ia.NIVEL_AGOTADO, presupuesto_ia.NIVEL_PAUSADO,
    )
    # NORMAL: nada se bloquea.
    for fondo in (True, False):
        assert B(N, gasta_tokens=True, es_fondo=fondo) is None
        assert B(N, gasta_tokens=False, es_fondo=fondo) is None
    # SOLO_MANUAL: solo el fondo que gasta tokens.
    assert B(SM, gasta_tokens=True, es_fondo=True) == SM
    assert B(SM, gasta_tokens=True, es_fondo=False) is None
    assert B(SM, gasta_tokens=False, es_fondo=True) is None  # proceso exento
    # AGOTADO: todo lo que gasta tokens (manual incluido); proceso exento.
    assert B(AG, gasta_tokens=True, es_fondo=True) == AG
    assert B(AG, gasta_tokens=True, es_fondo=False) == AG
    assert B(AG, gasta_tokens=False, es_fondo=True) is None
    # PAUSADO manda sobre todo, incluso procesos.
    for gasta in (True, False):
        for fondo in (True, False):
            assert B(PA, gasta_tokens=gasta, es_fondo=fondo) == PA


# --------------------------------------------------------------------------- #
# Gate de ADMISION (cola.encolar)                                              #
# --------------------------------------------------------------------------- #


def test_encolar_pausado_rechaza_todo(entorno, monkeypatch):
    monkeypatch.setenv("KENI_GENERACION_PAUSADA", "1")
    with pytest.raises(generaciones.GeneracionPausadaError):
        _encolar(jobspec.PRIORIDAD_MANUAL)
    with pytest.raises(generaciones.GeneracionPausadaError):
        _encolar(jobspec.PRIORIDAD_PIPELINE)


def test_encolar_solo_manual_corta_solo_fondo(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_DIA", "100")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=100, tokens_out=0)
    presupuesto_ia.invalidar_cache()
    with pytest.raises(generaciones.PresupuestoAgotadoError):
        _encolar(jobspec.PRIORIDAD_PIPELINE)
    assert _encolar(jobspec.PRIORIDAD_MANUAL)  # lo manual sigue


def test_encolar_agotado_corta_tambien_manual(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_DIA", "100")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=120, tokens_out=0)
    presupuesto_ia.invalidar_cache()
    with pytest.raises(generaciones.PresupuestoAgotadoError):
        _encolar(jobspec.PRIORIDAD_MANUAL)


def test_encolar_agotado_exime_jobs_de_proceso(entorno, monkeypatch):
    """Un job de PROCESO (render/ASR) no gasta tokens: el corte por presupuesto no lo frena."""
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_DIA", "100")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=999, tokens_out=0)
    presupuesto_ia.invalidar_cache()
    gen_id = _gen(tipo="render-video")
    spec = jobspec.construir_proceso(jobspec.PROC_RENDER_VIDEO, {"x": 1})
    assert cola.encolar(gen_id, spec)
    # ... pero el kill switch humano SI lo frena (freno de mano de toda la maquinaria).
    monkeypatch.setenv("KENI_GENERACION_PAUSADA", "1")
    otro = _gen(tipo="render-video")
    with pytest.raises(generaciones.GeneracionPausadaError):
        cola.encolar(otro, jobspec.construir_proceso(jobspec.PROC_RENDER_VIDEO, {"x": 1}))


def test_excepciones_son_cola_llena(entorno):
    """CONTRATO: las nuevas excepciones degradan al manejo existente (429 / backpressure)."""
    assert issubclass(generaciones.GeneracionPausadaError, generaciones.ColaLlenaError)
    assert issubclass(generaciones.PresupuestoAgotadoError, generaciones.ColaLlenaError)


# --------------------------------------------------------------------------- #
# Gate de RECLAMO (cola.reclamar con prioridad_minima)                         #
# --------------------------------------------------------------------------- #


def test_prioridad_breaking_adelanta_al_fondo_pero_no_al_equipo(entorno, monkeypatch):
    """CONTRATO de los 3 niveles: breaking adelanta al pipeline ordinario, nunca a una persona,
    y para la economia de tokens SIGUE siendo fondo (el corte solo_manual tambien lo frena)."""
    j_pipe = _encolar(jobspec.PRIORIDAD_PIPELINE)
    j_break = _encolar(jobspec.PRIORIDAD_BREAKING)
    j_manual = _encolar(jobspec.PRIORIDAD_MANUAL)
    assert cola.reclamar("w")["id"] == j_manual  # la persona primero
    assert cola.reclamar("w")["id"] == j_break   # breaking adelanta al lote ordinario
    assert cola.reclamar("w")["id"] == j_pipe
    # Con el presupuesto agotado (solo_manual), breaking NO se encola ni se reclama: es fondo.
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_DIA", "100")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=100, tokens_out=0)
    presupuesto_ia.invalidar_cache()
    with pytest.raises(generaciones.PresupuestoAgotadoError):
        _encolar(jobspec.PRIORIDAD_BREAKING)


def test_reclamar_prioridad_minima_corta_el_fondo_encolado(entorno):
    """La avalancha YA encolada deja de salir: con el corte, solo se reclama lo manual."""
    _encolar(jobspec.PRIORIDAD_PIPELINE)
    _encolar(jobspec.PRIORIDAD_PIPELINE)
    job_manual = _encolar(jobspec.PRIORIDAD_MANUAL)

    clavado = cola.reclamar("w1", prioridad_minima=jobspec.PRIORIDAD_MANUAL)
    assert clavado is not None and clavado["id"] == job_manual
    # Ya no queda nada manual: el fondo NO se reclama (queda pendiente, no se pierde).
    assert cola.reclamar("w1", prioridad_minima=jobspec.PRIORIDAD_MANUAL) is None
    # Sin corte, el fondo sigue ahi y sale con normalidad.
    assert cola.reclamar("w1") is not None


def test_reaper_respeta_generaciones_con_job_pendiente(entorno):
    """Una generacion cuyo job sigue PENDIENTE no es atascada: puede esperar mas que el TTL
    (retenida por el corte de presupuesto, el kill switch o una cola cargada) y el reaper
    NO debe segarla (la guardia anti-duplicado cerraria luego su job sin ejecutarlo)."""
    from datetime import datetime, timedelta

    viejo = (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds")

    encolada = _gen()
    cola.encolar(encolada, jobspec.construir(prompt="p", procesar=jobspec.construir_hashtags()))
    generaciones.actualizar(encolada, {"fecha_inicio": viejo})  # mas vieja que el TTL

    atascada = _gen()  # vieja y SIN job en cola: atascada de verdad
    generaciones.actualizar(atascada, {"fecha_inicio": viejo})

    assert generaciones.reclamar_atascadas(3600) == 1  # solo la atascada
    assert generaciones.obtener(encolada)["estado"] == "ejecutando"  # la encolada espera
    assert generaciones.obtener(atascada)["estado"] == generaciones.ESTADO_ERROR


# --------------------------------------------------------------------------- #
# Economia de CONTEXTO (tamano del prompt)                                      #
# --------------------------------------------------------------------------- #


def test_prompt_excesivo_se_rechaza(entorno, monkeypatch):
    """Un prompt por encima del tope DURO se rechaza al encolar (antes de gastar tokens)."""
    monkeypatch.setenv("KENI_PROMPT_MAX_CHARS", "100")
    gen_id = _gen()
    spec = jobspec.construir(prompt="x" * 101, procesar=jobspec.construir_hashtags())
    with pytest.raises(generaciones.PromptExcesivoError):
        cola.encolar(gen_id, spec)
    # Es subclase de ColaLlenaError: 429 claro sin handlers nuevos.
    assert issubclass(generaciones.PromptExcesivoError, generaciones.ColaLlenaError)
    # En el limite exacto (o con el tope a 0 = sin tope) SI encola.
    assert cola.encolar(gen_id, jobspec.construir(prompt="x" * 100, procesar=jobspec.construir_hashtags()))


def test_prompt_chars_se_sella_y_llega_al_ledger(entorno):
    """El encolado sella `prompt_chars` en el registro y el cierre lo vuelca al ledger."""
    gen_id = _gen()
    prompt = "hola " * 100  # 500 chars
    spec = jobspec.construir(prompt=prompt, procesar=jobspec.construir_hashtags())
    _ENCOLAR_REAL(
        gen_id, prompt=prompt, cwd=__import__("pathlib").Path("."),
        procesar=jobspec.reconstruir_procesar(spec), spec=spec,
    )
    assert generaciones.obtener(gen_id)["prompt_chars"] == len(prompt)
    _cerrar(gen_id, tokens_in=100, tokens_out=50)
    serie = repos.gasto_ia_por_dia(2)
    assert [d for d in serie if d["dia"] == _hoy()][0]["prompt_chars"] == len(prompt)


def test_worker_pausado_no_reclama(entorno, monkeypatch):
    """Con el kill switch puesto, el worker NO clava ni lo ya encolado (queda pendiente)."""
    import time

    from keni_consola import worker as worker_mod

    monkeypatch.setenv("KENI_WORKER_SONDEO_SEGUNDOS", "0.05")
    job_id = _encolar(jobspec.PRIORIDAD_MANUAL)  # encolado ANTES de pausar
    monkeypatch.setenv("KENI_GENERACION_PAUSADA", "1")
    presupuesto_ia.invalidar_cache()
    pool = worker_mod._Pool(1, "t-pausa")
    pool.arrancar()
    try:
        time.sleep(0.5)
        activos = {j["id"]: j for j in repos.jobs_activos()}
        assert activos[job_id]["estado"] == repos.JOB_PENDIENTE
    finally:
        pool.detener()


# --------------------------------------------------------------------------- #
# API: visibilidad en el monitor                                               #
# --------------------------------------------------------------------------- #


def _cli_token():
    from starlette.testclient import TestClient

    from keni_consola import app as app_modulo

    from .conftest import TOKEN_PRUEBA

    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    return c


def test_api_cola_expone_presupuesto(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_DIA", "1000")
    gen_id = _gen()
    _cerrar(gen_id, tokens_in=400, tokens_out=100)
    presupuesto_ia.invalidar_cache()
    data = _cli_token().get("/api/actividad/cola").json()
    p = data["presupuesto"]
    assert p["nivel"] == presupuesto_ia.NIVEL_NORMAL
    assert p["pausada"] is False
    assert p["presupuesto_tokens_dia"] == 1000
    assert p["gastado"]["tokens"] == 500
    assert p["restante_tokens"] == 500
    assert p["pct_usado"] == pytest.approx(50.0)


def test_api_series_expone_gasto(entorno):
    gen_id = _gen()
    _cerrar(gen_id, tokens_in=100, tokens_out=50)
    data = _cli_token().get("/api/actividad/cola/series?dias=7").json()
    assert any(d["dia"] == _hoy() and d["tokens"] == 150 for d in data["gasto"])
