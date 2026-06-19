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

from keni_consola import ajustes, cola, generaciones, presupuesto_ia, repos
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
        prompt="p", procesar=jobspec.construir_prompt_lib(), prioridad=prioridad
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
    # Una verificación/verificacion de fuente (tipo pipeline + etiqueta "Verificar · …") -> investigacion.
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
    assert est["presupuesto_tokens_dia"] == 0  # suma de los 4 topes por motor, todos en 0
    assert est["presupuesto_usd_dia"] == 0
    assert est["restante_tokens"] is None and est["pct_usado"] is None  # suma 0 = sin limite
    assert est["pct_usado_usd"] is None


def test_estado_presupuesto_tokens_es_suma_de_topes_motor(entorno, monkeypatch):
    """`presupuesto_tokens_dia` es INFORMATIVO: la SUMA de los 4 topes por motor (investigacion
    in+out + produccion in+out). restante/pct se miden contra esa suma; NO corta a nivel global."""
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA", "400")
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA", "100")
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA", "300")
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA", "200")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=300, tokens_out=200)  # 500 global
    presupuesto_ia.invalidar_cache()
    est = presupuesto_ia.estado()
    assert est["presupuesto_tokens_dia"] == 1000  # 400 + 100 + 300 + 200
    assert est["gastado"]["tokens"] == 500
    assert est["restante_tokens"] == 500
    assert est["pct_usado"] == pytest.approx(50.0)
    # Esa suma NO corta a nivel global: sin cap USD, el global es NORMAL.
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL


def test_nivel_escalones_por_usd(entorno, monkeypatch):
    """El presupuesto de COSTE (USD) corta igual que el de tokens: solo_manual al alcanzarlo,
    agotado al superar el margen. Es un proxy del gasto independiente del conteo de tokens."""
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "10")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL

    repos.registrar_gasto_ia("g1", dia=_hoy(), tokens_in=1, tokens_out=1, coste_usd=10.0)
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_SOLO_MANUAL

    repos.registrar_gasto_ia("g2", dia=_hoy(), tokens_in=1, tokens_out=1, coste_usd=2.0)  # 12 = +20%
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_AGOTADO

    est = presupuesto_ia.estado()
    assert est["presupuesto_usd_dia"] == pytest.approx(10.0)
    assert est["gastado"]["coste_usd"] == pytest.approx(12.0)
    assert est["pct_usado_usd"] == pytest.approx(120.0)


def test_nivel_global_solo_usd_no_corta_por_tokens(entorno, monkeypatch):
    """El corte GLOBAL es SOLO el cap de USD (+ parada): un gasto de tokens ENORME sin cap USD
    NO corta a nivel global. Al fijar el cap USD y superarlo, el global SI corta."""
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=10_000_000, tokens_out=10_000_000,
                             coste_usd=9999.0)
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL  # sin cap USD: no corta
    est = presupuesto_ia.estado()
    assert est["presupuesto_usd_dia"] == 0 and est["pct_usado_usd"] is None

    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "5")
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_AGOTADO  # 9999 >> 5*1.2


def test_nivel_pausado_manda(entorno, monkeypatch):
    monkeypatch.setenv("KENI_GENERACION_PAUSADA", "1")
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_PAUSADO
    assert presupuesto_ia.estado()["pausada"] is True


# --------------------------------------------------------------------------- #
# Presupuesto + parada de emergencia POR MARCA (enforced)                       #
# --------------------------------------------------------------------------- #


def test_nivel_por_marca_su_cap_no_afecta_a_otras(entorno):
    """El cap USD propio de una marca corta SOLO su trabajo; el global y las otras marcas siguen."""
    ajustes.guardar("KENI_PRESUPUESTO_USD_DIA::unotv", "5")
    repos.registrar_gasto_ia("u1", dia=_hoy(), proceso="produccion", tipo="copy",
                             marca="unotv", tokens_in=1, tokens_out=1, coste_usd=5.0)
    presupuesto_ia.invalidar_cache()
    # Sin cap global: el global sigue NORMAL; la marca unotv alcanza su cap -> solo_manual.
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL
    assert presupuesto_ia.nivel("unotv") == presupuesto_ia.NIVEL_SOLO_MANUAL
    assert presupuesto_ia.nivel("claro-sports") == presupuesto_ia.NIVEL_NORMAL


def test_parada_de_emergencia_por_marca(entorno):
    """La parada de una marca la pausa SOLO a ella; el global y las otras marcas no se tocan."""
    ajustes.guardar("KENI_GENERACION_PAUSADA::unotv", "1")
    assert presupuesto_ia.nivel("unotv") == presupuesto_ia.NIVEL_PAUSADO
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL
    assert presupuesto_ia.nivel("claro-sports") == presupuesto_ia.NIVEL_NORMAL
    # estado(marca) refleja la parada PROPIA de la marca; el global, no.
    assert presupuesto_ia.estado("unotv")["pausada"] is True
    assert presupuesto_ia.estado()["pausada"] is False


def test_parada_global_manda_sobre_la_marca(entorno, monkeypatch):
    """La parada GLOBAL corta TODAS las marcas (el más restrictivo entre global y marca)."""
    monkeypatch.setenv("KENI_GENERACION_PAUSADA", "1")
    assert presupuesto_ia.nivel("unotv") == presupuesto_ia.NIVEL_PAUSADO


def test_estado_por_marca_acota_gasto_y_controles(entorno):
    """estado(marca) trae el gasto y los controles PROPIOS de la marca; estado() agrega todo."""
    ajustes.guardar("KENI_PRESUPUESTO_USD_DIA::unotv", "8")
    repos.registrar_gasto_ia("u1", dia=_hoy(), proceso="produccion", tipo="copy",
                             marca="unotv", tokens_in=100, tokens_out=40, coste_usd=4.0)
    repos.registrar_gasto_ia("c1", dia=_hoy(), proceso="produccion", tipo="copy",
                             marca="claro-sports", tokens_in=10, tokens_out=5, coste_usd=1.0)
    presupuesto_ia.invalidar_cache()

    est_unotv = presupuesto_ia.estado("unotv")
    assert est_unotv["marca"] == "unotv"
    assert est_unotv["gastado"]["coste_usd"] == pytest.approx(4.0)  # solo unotv
    assert est_unotv["presupuesto_usd_dia"] == pytest.approx(8.0)  # cap propio de la marca
    assert est_unotv["pct_usado_usd"] == pytest.approx(50.0)
    # En vista de marca los topes por motor son los PROPIOS de la marca; aquí ninguno fijado -> 0.
    assert est_unotv["por_proceso"]["produccion"]["presupuesto_tokens_in_dia"] == 0

    est_global = presupuesto_ia.estado()
    assert est_global["marca"] == ""
    assert est_global["gastado"]["coste_usd"] == pytest.approx(5.0)  # unotv + claro-sports


def test_tope_tokens_por_marca_corta_su_motor(entorno):
    """Un tope de tokens por motor PROPIO de la marca corta SOLO ese motor de esa marca."""
    ajustes.guardar("KENI_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA::unotv", "100")
    repos.registrar_gasto_ia("u1", dia=_hoy(), proceso="produccion", tipo="copy", marca="unotv",
                             tokens_in=10, tokens_out=100, coste_usd=0.0)
    presupuesto_ia.invalidar_cache()
    # El tope OUT de la marca (100) se alcanza con su gasto OUT (100): corta producción de unotv.
    assert presupuesto_ia.nivel_proceso("produccion", "unotv") == presupuesto_ia.NIVEL_SOLO_MANUAL
    # Otra marca y el global, intactos (es un tope PROPIO de unotv).
    assert presupuesto_ia.nivel_proceso("produccion", "claro-sports") == presupuesto_ia.NIVEL_NORMAL
    assert presupuesto_ia.nivel_proceso("produccion") == presupuesto_ia.NIVEL_NORMAL
    # estado(marca) muestra el tope propio del motor y su % consumido.
    bloque = presupuesto_ia.estado("unotv")["por_proceso"]["produccion"]
    assert bloque["presupuesto_tokens_out_dia"] == 100 and bloque["pct_out"] == pytest.approx(100.0)


def test_encolar_parada_marca_corta_su_trabajo_no_otras(entorno):
    """La parada de una marca rechaza el encolado de SU trabajo (fondo y manual); otras pasan."""
    ajustes.guardar("KENI_GENERACION_PAUSADA::unotv", "1")

    def _encolar_marca(marca: str, prioridad: int) -> str:
        gen_id = generaciones.crear({"tipo": "copy", "marca": marca, "etiqueta": "X"})["id"]
        spec = jobspec.construir(
            prompt="p", procesar=jobspec.construir_prompt_lib(), prioridad=prioridad
        )
        return cola.encolar(gen_id, spec, proceso="produccion", marca=marca)

    with pytest.raises(generaciones.GeneracionPausadaError):
        _encolar_marca("unotv", jobspec.PRIORIDAD_MANUAL)
    with pytest.raises(generaciones.GeneracionPausadaError):
        _encolar_marca("unotv", jobspec.PRIORIDAD_PIPELINE)
    # Otra marca no se ve afectada por la parada de unotv.
    assert _encolar_marca("claro-sports", jobspec.PRIORIDAD_PIPELINE)


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
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "5")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=10, tokens_out=10, coste_usd=5.0)
    presupuesto_ia.invalidar_cache()
    with pytest.raises(generaciones.PresupuestoAgotadoError):
        _encolar(jobspec.PRIORIDAD_PIPELINE)
    assert _encolar(jobspec.PRIORIDAD_MANUAL)  # lo manual sigue


def test_encolar_agotado_corta_tambien_manual(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "5")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=10, tokens_out=10, coste_usd=6.0)
    presupuesto_ia.invalidar_cache()
    with pytest.raises(generaciones.PresupuestoAgotadoError):
        _encolar(jobspec.PRIORIDAD_MANUAL)


def test_encolar_agotado_exime_jobs_de_proceso(entorno, monkeypatch):
    """Un job de PROCESO (render/ASR) no gasta tokens: el corte por presupuesto no lo frena."""
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "5")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=10, tokens_out=10, coste_usd=999.0)
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
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "5")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=10, tokens_out=10, coste_usd=5.0)
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


def test_limpiador_respeta_generaciones_con_job_pendiente(entorno):
    """Una generacion cuyo job sigue PENDIENTE no es atascada: puede esperar mas que el TTL
    (retenida por el corte de presupuesto, el kill switch o una cola cargada) y el limpiador
    NO debe segarla (la guardia anti-duplicado cerraria luego su job sin ejecutarlo)."""
    from datetime import datetime, timedelta

    viejo = (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds")

    encolada = _gen()
    cola.encolar(encolada, jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib()))
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
    spec = jobspec.construir(prompt="x" * 101, procesar=jobspec.construir_prompt_lib())
    with pytest.raises(generaciones.PromptExcesivoError):
        cola.encolar(gen_id, spec)
    # Es subclase de ColaLlenaError: 429 claro sin handlers nuevos.
    assert issubclass(generaciones.PromptExcesivoError, generaciones.ColaLlenaError)
    # En el limite exacto (o con el tope a 0 = sin tope) SI encola.
    assert cola.encolar(gen_id, jobspec.construir(prompt="x" * 100, procesar=jobspec.construir_prompt_lib()))


def test_prompt_chars_se_sella_y_llega_al_ledger(entorno):
    """El encolado sella `prompt_chars` en el registro y el cierre lo vuelca al ledger."""
    gen_id = _gen()
    prompt = "hola " * 100  # 500 chars
    spec = jobspec.construir(prompt=prompt, procesar=jobspec.construir_prompt_lib())
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
    # `presupuesto_tokens_dia` expuesto = suma de los 4 topes por motor (aqui 600 + 400 = 1000).
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA", "600")
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA", "400")
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


# --------------------------------------------------------------------------- #
# Topes POR MOTOR (ADR 0011): corte por motor (IN/OUT) + desglose `por_proceso` #
# --------------------------------------------------------------------------- #
#
# Cada motor tiene DOS topes propios de tokens: ENTRADA y SALIDA. El corte efectivo de un motor
# es el MAS restrictivo entre su tope IN (vs sus tokens_in), su tope OUT (vs sus tokens_out) y el
# cap global de USD. La parada de emergencia y el resumen de gasto siguen GLOBALES; los topes por
# motor son ADITIVOS (en 0 no cambian el comportamiento global).

_GASTO_CERO = {"tokens": 0, "tokens_in": 0, "tokens_out": 0, "coste_usd": 0.0, "generaciones": 0}


def test_nivel_proceso_tope_in_corta_solo_por_input(monkeypatch):
    """El tope IN del motor corta por su gasto de ENTRADA; sin tope OUT, la salida no influye."""
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA", "1000")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    monkeypatch.setattr(presupuesto_ia, "_gasto_hoy", lambda: dict(_GASTO_CERO))
    monkeypatch.setattr(presupuesto_ia, "_gasto_por_proceso_hoy", lambda: {
        "investigacion": {"tokens_in": 1100, "tokens_out": 9999, "tokens": 11099,
                          "coste_usd": 0.0, "generaciones": 2},
        "produccion": {"tokens_in": 10, "tokens_out": 5, "tokens": 15,
                       "coste_usd": 0.0, "generaciones": 1},
    })
    # in 1100 >= 1000 (< 1200) -> solo_manual; el out enorme NO corta (no hay tope OUT).
    assert presupuesto_ia.nivel_proceso("investigacion") == presupuesto_ia.NIVEL_SOLO_MANUAL
    assert presupuesto_ia.nivel_proceso("produccion") == presupuesto_ia.NIVEL_NORMAL
    # El GLOBAL no cambia (caps globales apagados): la parada/el resumen siguen globales.
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL


def test_nivel_proceso_tope_out_corta_solo_por_output(monkeypatch):
    """El tope OUT del motor corta por su gasto de SALIDA; sin tope IN, la entrada no influye."""
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA", "1000")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    monkeypatch.setattr(presupuesto_ia, "_gasto_hoy", lambda: dict(_GASTO_CERO))
    monkeypatch.setattr(presupuesto_ia, "_gasto_por_proceso_hoy", lambda: {
        "investigacion": {"tokens_in": 0, "tokens_out": 0, "tokens": 0,
                          "coste_usd": 0.0, "generaciones": 0},
        "produccion": {"tokens_in": 9999, "tokens_out": 1200, "tokens": 11199,
                       "coste_usd": 0.0, "generaciones": 3},
    })
    # out 1200 >= 1000*1.2 -> agotado; el in enorme NO corta (no hay tope IN).
    assert presupuesto_ia.nivel_proceso("produccion") == presupuesto_ia.NIVEL_AGOTADO
    assert presupuesto_ia.nivel_proceso("investigacion") == presupuesto_ia.NIVEL_NORMAL
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL


def test_nivel_proceso_mas_restrictivo_entre_in_out_y_global(monkeypatch):
    """El nivel del motor es el MAS restrictivo de su tope IN, su tope OUT y el cap global de USD."""
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA", "1000")
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA", "1000")
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "10")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    # global USD: 5 < 10 -> normal; IN 1000 == tope -> solo_manual; OUT 1200 >= 1200 -> agotado.
    monkeypatch.setattr(presupuesto_ia, "_gasto_hoy", lambda: {**_GASTO_CERO, "coste_usd": 5.0})
    monkeypatch.setattr(presupuesto_ia, "_gasto_por_proceso_hoy", lambda: {
        "investigacion": {"tokens_in": 1000, "tokens_out": 1200, "tokens": 2200,
                          "coste_usd": 5.0, "generaciones": 2},
        "produccion": {"tokens_in": 0, "tokens_out": 0, "tokens": 0,
                       "coste_usd": 0.0, "generaciones": 0},
    })
    # OUT (agotado) manda sobre IN (solo_manual) y sobre el global (normal).
    assert presupuesto_ia.nivel_proceso("investigacion") == presupuesto_ia.NIVEL_AGOTADO


def test_nivel_proceso_sin_topes_motor_es_el_global(monkeypatch):
    """Sin topes IN/OUT por motor (0), nivel_proceso de cada motor == nivel GLOBAL (reusa USD)."""
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "10")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    monkeypatch.setattr(presupuesto_ia, "_gasto_hoy", lambda: {**_GASTO_CERO, "coste_usd": 11.0})
    monkeypatch.setattr(presupuesto_ia, "_gasto_por_proceso_hoy",
                        presupuesto_ia._gasto_vacio_por_proceso)
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_SOLO_MANUAL  # 11 >= 10 (< 12)
    assert presupuesto_ia.nivel_proceso("investigacion") == presupuesto_ia.NIVEL_SOLO_MANUAL
    assert presupuesto_ia.nivel_proceso("produccion") == presupuesto_ia.NIVEL_SOLO_MANUAL


def test_nivel_proceso_pausa_global_manda(monkeypatch):
    monkeypatch.setenv("KENI_GENERACION_PAUSADA", "1")
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA", "1000")
    assert presupuesto_ia.nivel_proceso("produccion") == presupuesto_ia.NIVEL_PAUSADO


def test_bloqueo_admision_con_proceso_aplica_tope_motor(monkeypatch):
    """Con `proceso`, el corte del job es el más restrictivo entre global y motor.

    Sin `proceso` (o con job exento de tokens) cae al comportamiento GLOBAL de siempre.
    """
    B = presupuesto_ia.bloqueo_admision
    N, AG = presupuesto_ia.NIVEL_NORMAL, presupuesto_ia.NIVEL_AGOTADO
    monkeypatch.setattr(
        presupuesto_ia, "nivel_proceso",
        lambda p, marca="": AG if p == "investigacion" else N,
    )
    # Global NORMAL pero el motor 'investigacion' AGOTADO por su tope propio: corta manual y fondo.
    assert B(N, gasta_tokens=True, es_fondo=True, proceso="investigacion") == AG
    assert B(N, gasta_tokens=True, es_fondo=False, proceso="investigacion") == AG
    # 'produccion' (su motor normal) pasa; sin proceso pasa; proceso exento (no gasta) pasa.
    assert B(N, gasta_tokens=True, es_fondo=True, proceso="produccion") is None
    assert B(N, gasta_tokens=True, es_fondo=True) is None
    assert B(N, gasta_tokens=False, es_fondo=True, proceso="investigacion") is None


def test_estado_por_proceso_forma_y_gasto(entorno, monkeypatch):
    """`estado().por_proceso` desglosa cada motor con la forma del contrato (in/out); `gastado` sigue global."""
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA", "1000")
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA", "500")
    repos.registrar_gasto_ia("i1", dia=_hoy(), tokens_in=300, tokens_out=200,
                             coste_usd=0.5, proceso="investigacion")
    repos.registrar_gasto_ia("p1", dia=_hoy(), tokens_in=10, tokens_out=5,
                             coste_usd=0.01, proceso="produccion")
    presupuesto_ia.invalidar_cache()
    est = presupuesto_ia.estado()
    pp = est["por_proceso"]
    assert set(pp) >= {"investigacion", "produccion"}
    campos = {"tokens_in", "tokens_out", "tokens", "coste_usd", "generaciones",
              "presupuesto_tokens_in_dia", "presupuesto_tokens_out_dia",
              "restante_in", "pct_in", "restante_out", "pct_out", "nivel"}
    inv = pp["investigacion"]
    assert set(inv) == campos
    assert (inv["tokens_in"], inv["tokens_out"], inv["tokens"]) == (300, 200, 500)
    assert inv["generaciones"] == 1
    assert inv["presupuesto_tokens_in_dia"] == 1000
    assert inv["presupuesto_tokens_out_dia"] == 500
    assert inv["restante_in"] == 700 and inv["pct_in"] == pytest.approx(30.0)
    assert inv["restante_out"] == 300 and inv["pct_out"] == pytest.approx(40.0)
    prod = pp["produccion"]
    assert prod["tokens"] == 15
    assert prod["presupuesto_tokens_in_dia"] == 0 and prod["presupuesto_tokens_out_dia"] == 0
    assert prod["restante_in"] is None and prod["pct_in"] is None
    assert prod["restante_out"] is None and prod["pct_out"] is None
    # El resumen GLOBAL no cambia: suma de ambos motores.
    assert est["gastado"]["tokens"] == 515


def test_tope_por_motor_corta_solo_ese_motor(entorno, monkeypatch):
    """El tope propio de un motor lo corta sin tocar al otro ni al global."""
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA", "100")
    repos.registrar_gasto_ia("i", dia=_hoy(), tokens_in=120, tokens_out=20,
                             proceso="investigacion")  # in 120 >= 100*1.2 -> agotado
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.nivel_proceso("investigacion") == presupuesto_ia.NIVEL_AGOTADO
    assert presupuesto_ia.nivel_proceso("produccion") == presupuesto_ia.NIVEL_NORMAL
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL  # global intacto


def test_sin_topes_por_motor_comportamiento_global_identico(entorno, monkeypatch):
    """Con los topes por motor en 0, el corte de cada motor es EXACTAMENTE el global (cap USD)."""
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "5")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=10, tokens_out=10, coste_usd=5.0,
                             proceso="produccion")
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_SOLO_MANUAL
    assert presupuesto_ia.nivel_proceso("produccion") == presupuesto_ia.NIVEL_SOLO_MANUAL
    assert presupuesto_ia.nivel_proceso("investigacion") == presupuesto_ia.NIVEL_SOLO_MANUAL


def test_encolar_tope_motor_corta_solo_ese_motor(entorno, monkeypatch):
    """El gate de admisión, con `proceso`, corta el motor agotado y deja pasar el otro."""
    monkeypatch.setenv("KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA", "100")
    repos.registrar_gasto_ia("i", dia=_hoy(), tokens_in=150, tokens_out=50,
                             proceso="investigacion")  # in 150 >= 120 -> agotado
    presupuesto_ia.invalidar_cache()
    spec = jobspec.construir(
        prompt="p", procesar=jobspec.construir_prompt_lib(), prioridad=jobspec.PRIORIDAD_MANUAL
    )
    with pytest.raises(generaciones.PresupuestoAgotadoError):
        cola.encolar(_gen(), spec, proceso="investigacion")
    # Un job de producción (su motor sin tope, global apagado) sigue entrando.
    spec2 = jobspec.construir(
        prompt="p", procesar=jobspec.construir_prompt_lib(), prioridad=jobspec.PRIORIDAD_MANUAL
    )
    assert cola.encolar(_gen(), spec2, proceso="produccion")
