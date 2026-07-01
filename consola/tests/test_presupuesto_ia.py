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

from datetime import date

import pytest

from keni_consola import ajustes, cola, gate_diario, generaciones, presupuesto_ia, repos, ruteo_cuentas
from keni_consola.dominio import jobspec
from keni_consola.tiempo import ahora_iso

_MARCA = "unotv"

# Referencia GENUINA al encolado real: `crear_app` REASIGNA `generaciones.encolar_job_claude`
# por una fake (y persiste entre tests); la capturamos al importar (patron de test_worker_cola).
_ENCOLAR_REAL = generaciones.encolar_job_claude


def _hoy() -> str:
    # Bucket-dia del ledger en jornada CDMX, igual que lo escribe/lee el producto: garantiza que
    # `dia=` al insertar gasto case con el "hoy" que `presupuesto_ia` consulta.
    return presupuesto_ia._dia_cdmx()


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


def test_estado_incluye_ritmo(entorno, monkeypatch):
    """`estado()` expone el RITMO vigente (%) para que el panel de gasto lo lea de lo que ya recibe:
    el de la marca con `marca`, el global en ""; default 100 = sin freno."""
    monkeypatch.delenv("KENI_RITMO", raising=False)
    est = presupuesto_ia.estado()
    assert est["ritmo"] == 100 and est["ritmo_global"] == 100
    monkeypatch.setenv("KENI_RITMO", "40")
    ajustes.guardar("KENI_RITMO::unotv", "25")  # override por marca vive en el store
    est_unotv = presupuesto_ia.estado("unotv")
    assert est_unotv["ritmo"] == 25  # el propio de la marca
    assert est_unotv["ritmo_global"] == 40  # el global, aparte
    assert presupuesto_ia.estado()["ritmo"] == 40  # vista global


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


def test_bloqueo_inline_aplica_el_mismo_gate_que_la_cola(entorno, monkeypatch):
    """`bloqueo_inline` es el gate de los caminos que corren `claude -p` SIN encolar (pasos Haiku
    del pool). Mismo criterio que la admision de la cola: PAUSADO corta todo; AGOTADO corta todo
    lo que gasta tokens; SOLO_MANUAL solo el FONDO; NORMAL pasa."""
    # NORMAL: nada bloquea.
    assert presupuesto_ia.bloqueo_inline(presupuesto_ia.PROCESO_INVESTIGACION) is None

    # SOLO_MANUAL (gasto == cap USD): el FONDO cede, lo manual sigue.
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "10")
    monkeypatch.setenv("KENI_PRESUPUESTO_MARGEN_MANUAL", "20")
    repos.registrar_gasto_ia("g1", dia=_hoy(), tokens_in=1, tokens_out=1, coste_usd=10.0)
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.bloqueo_inline("", es_fondo=True) == presupuesto_ia.NIVEL_SOLO_MANUAL
    assert presupuesto_ia.bloqueo_inline("", es_fondo=False) is None

    # AGOTADO (supera el margen): corta tambien lo manual.
    repos.registrar_gasto_ia("g2", dia=_hoy(), tokens_in=1, tokens_out=1, coste_usd=2.0)
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.bloqueo_inline("", es_fondo=True) == presupuesto_ia.NIVEL_AGOTADO
    assert presupuesto_ia.bloqueo_inline("", es_fondo=False) == presupuesto_ia.NIVEL_AGOTADO

    # PAUSADO manda sobre todo.
    monkeypatch.setenv("KENI_GENERACION_PAUSADA", "1")
    presupuesto_ia.invalidar_cache()
    assert presupuesto_ia.bloqueo_inline("", es_fondo=False) == presupuesto_ia.NIVEL_PAUSADO


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


def test_fase_inline_del_pool_registra_gasto_con_etapa(entorno, monkeypatch):
    """Una fase INLINE del pool (Fusionar) vuelca su gasto al ledger con su ETAPA explícita; la
    economía la muestra como su propia fila de Investigación, no colapsada en «Verificar»."""
    from keni_consola import recolectar_daemon
    from keni_consola.dominio import traducir as _trad

    # El ejecutor síncrono no corre (no hay claude): simulamos las métricas acumuladas del paso.
    monkeypatch.setattr(
        _trad, "tomar_metricas_acumuladas",
        lambda: {"tokens_in": 100, "tokens_out": 30, "total_cost_usd": 0.02},
    )
    recolectar_daemon._registrar_actividad_ia(
        "unotv", "Fusionar historias — UnoTV: 2 absorbida(s)", "ok", etapa="Fusionar"
    )
    presupuesto_ia.invalidar_cache()
    inv = repos.gasto_ia_economia_por_proceso(2)["investigacion"]
    fus = next((e for e in inv["por_etapa"] if e["etapa"] == "Fusionar"), None)
    assert fus is not None, "la fase Fusionar debe aparecer como etapa propia"
    assert fus["tokens"] == 130 and fus["coste_usd"] == pytest.approx(0.02)


def test_subllamadas_del_pool_dejan_etapa_propia_cotejar_subtema(entorno, monkeypatch):
    """Cada sub-llamada del job de Fusionar (Cotejar/Subtema) sella su gasto bajo su ETAPA propia, así
    la economía las muestra como filas SEPARADAS de «Fusionar» (antes su coste quedaba invisible)."""
    from keni_consola.dominio import actividad_pool
    from keni_consola.dominio import traducir as _trad

    # Métricas distintas por sub-llamada (el ejecutor síncrono no corre: las simulamos).
    metricas = iter([
        {"tokens_in": 40, "tokens_out": 10, "total_cost_usd": 0.01},
        {"tokens_in": 20, "tokens_out": 5, "total_cost_usd": 0.005},
    ])
    monkeypatch.setattr(_trad, "tomar_metricas_acumuladas", lambda: next(metricas))
    actividad_pool.registrar_actividad_pool("unotv", "Cotejar grupos — UnoTV", etapa="Cotejar")
    actividad_pool.registrar_actividad_pool("unotv", "Subtema — UnoTV", etapa="Subtema")
    presupuesto_ia.invalidar_cache()
    inv = repos.gasto_ia_economia_por_proceso(2)["investigacion"]
    etapas = {e["etapa"]: e for e in inv["por_etapa"]}
    assert "Cotejar" in etapas and "Subtema" in etapas, "Cotejar y Subtema deben ser etapas propias"
    assert etapas["Cotejar"]["tokens"] == 50 and etapas["Cotejar"]["coste_usd"] == pytest.approx(0.01)
    assert etapas["Subtema"]["tokens"] == 25 and etapas["Subtema"]["coste_usd"] == pytest.approx(0.005)


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
        _encolar_marca("unotv", jobspec.PRIORIDAD_AUTOMATICO)
    # Otra marca no se ve afectada por la parada de unotv.
    assert _encolar_marca("claro-sports", jobspec.PRIORIDAD_AUTOMATICO)


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
        _encolar(jobspec.PRIORIDAD_AUTOMATICO)


def test_encolar_solo_manual_corta_solo_fondo(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "5")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=10, tokens_out=10, coste_usd=5.0)
    presupuesto_ia.invalidar_cache()
    with pytest.raises(generaciones.PresupuestoAgotadoError):
        _encolar(jobspec.PRIORIDAD_AUTOMATICO)
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


def test_manual_adelanta_al_automatico_que_es_fondo(entorno, monkeypatch):
    """Gestor de prioridad (dos niveles): lo MANUAL se reclama antes que lo AUTOMATICO, y lo
    automatico es fondo (el corte solo_manual tambien lo frena). Nada mas: sin niveles intermedios."""
    j_auto = _encolar(jobspec.PRIORIDAD_AUTOMATICO)
    j_manual = _encolar(jobspec.PRIORIDAD_MANUAL)
    assert cola.reclamar("w")["id"] == j_manual  # la persona primero
    assert cola.reclamar("w")["id"] == j_auto    # lo automatico despues
    # Con el presupuesto agotado (solo_manual), lo automatico NO se encola ni se reclama: es fondo.
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "5")
    repos.registrar_gasto_ia("g", dia=_hoy(), tokens_in=10, tokens_out=10, coste_usd=5.0)
    presupuesto_ia.invalidar_cache()
    with pytest.raises(generaciones.PresupuestoAgotadoError):
        _encolar(jobspec.PRIORIDAD_AUTOMATICO)


def test_reclamar_prioridad_minima_corta_el_fondo_encolado(entorno):
    """La avalancha YA encolada deja de salir: con el corte, solo se reclama lo manual."""
    _encolar(jobspec.PRIORIDAD_AUTOMATICO)
    _encolar(jobspec.PRIORIDAD_AUTOMATICO)
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


# --------------------------------------------------------------------------- #
# Proyeccion de gasto a fin de dia (burn-rate). PURO: sin Postgres ni red.    #
# --------------------------------------------------------------------------- #


def _patch_gasto(monkeypatch, coste_usd: float) -> None:
    """Fija el gasto del dia (sin tocar Postgres) para las pruebas de proyeccion."""
    gasto = {"tokens": 0, "tokens_in": 0, "tokens_out": 0,
             "coste_usd": coste_usd, "generaciones": 1}
    monkeypatch.setattr(presupuesto_ia, "_gasto_hoy", lambda marca="": gasto)
    monkeypatch.setattr(presupuesto_ia, "_gasto_por_proceso_hoy",
                        lambda marca="": presupuesto_ia._gasto_vacio_por_proceso())
    monkeypatch.setattr(presupuesto_ia, "nivel", lambda marca="": presupuesto_ia.NIVEL_NORMAL)


def test_proyeccion_extrapola_coste_segun_fraccion_del_dia(monkeypatch):
    # A un cuarto del dia con $2.5 gastados, la proyeccion a fin de dia es $10.
    monkeypatch.setattr(presupuesto_ia, "_fraccion_dia_cdmx", lambda: 0.25)
    _patch_gasto(monkeypatch, 2.5)
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "8")
    est = presupuesto_ia.estado()
    assert est["proyeccion_usd_dia"] == pytest.approx(10.0)
    # 10 / 8 = 125% del tope (la proyeccion lo supera).
    assert est["pct_proyectado_usd"] == pytest.approx(125.0)


def test_proyeccion_arranque_del_dia_es_none(monkeypatch):
    # Fraccion ~0: no se proyecta (dividir por casi-cero dispararia la cifra).
    monkeypatch.setattr(presupuesto_ia, "_fraccion_dia_cdmx", lambda: 0.001)
    _patch_gasto(monkeypatch, 1.0)
    monkeypatch.setenv("KENI_PRESUPUESTO_USD_DIA", "8")
    est = presupuesto_ia.estado()
    assert est["proyeccion_usd_dia"] is None
    assert est["pct_proyectado_usd"] is None


def test_proyeccion_sin_presupuesto_usd_pct_proyectado_none(monkeypatch):
    monkeypatch.setattr(presupuesto_ia, "_fraccion_dia_cdmx", lambda: 0.5)
    _patch_gasto(monkeypatch, 3.0)
    monkeypatch.delenv("KENI_PRESUPUESTO_USD_DIA", raising=False)
    est = presupuesto_ia.estado()
    assert est["proyeccion_usd_dia"] == pytest.approx(6.0)  # 3.0 / 0.5
    assert est["pct_proyectado_usd"] is None  # sin cap USD


def test_fraccion_dia_cdmx_deriva_del_reloj_canonico(monkeypatch):
    # El reloj canonico es UTC; la fraccion es de la JORNADA CDMX (UTC-6).
    # Mediodia UTC = 06:00 CDMX -> 0.25 del dia.
    monkeypatch.setattr(presupuesto_ia, "ahora_iso", lambda: "2026-06-21T12:00:00")
    assert presupuesto_ia._fraccion_dia_cdmx() == pytest.approx(0.25)
    # Medianoche UTC = 18:00 CDMX (del dia anterior) -> 0.75 del dia.
    monkeypatch.setattr(presupuesto_ia, "ahora_iso", lambda: "2026-06-21T00:00:00")
    assert presupuesto_ia._fraccion_dia_cdmx() == pytest.approx(0.75)


# --------------------------------------------------------------------------- #
# Gate DIARIO por % del limite SEMANAL POR CUENTA de Claude (gate_diario)        #
# --------------------------------------------------------------------------- #
#
# Hay DOS cuentas (A=claro-sports/fundacion, B=unotv/nacion-gamer/unotv-us). Cada cuenta reparte el
# cupo semanal que le QUEDA entre los dias hasta su reset (cupo del dia; ~14,3 pp/dia plano de
# respaldo cuando falta el reset). Al alcanzar el umbral del dia de una cuenta,
# pausa SOLO las marcas de esa cuenta; aceptar +10% sube el umbral del dia de ESA cuenta y reanuda.
# La fuente del % vive tras UN accesor por cuenta (`consumo_semanal_hoy_pct(cuenta)`); None => NO
# cortar (fallback seguro). El estado del dia (umbral/aceptados) es independiente por cuenta.

_BASE = 100.0 / 7.0  # umbral base del dia (~14,3 pp del semanal)
_CUENTA_A = jobspec.CUENTA_A
_CUENTA_B = jobspec.CUENTA_B


def _patch_consumo(monkeypatch, por_cuenta: dict[str, float | None]) -> None:
    """Fija la fuente del % POR CUENTA (sin tocar repos): consumo de hoy de cada cuenta."""
    monkeypatch.setattr(
        gate_diario, "consumo_semanal_hoy_pct", lambda cuenta: por_cuenta.get(cuenta)
    )


# --- Cupo del dia adaptativo: lo que queda / dias hasta el reset (PURO, sin BD) --------------- #


def test_umbral_base_reparte_lo_que_queda_entre_dias_restantes():
    hoy = date(2026, 6, 29)
    # Reset 1-jul 07:00 UTC = 1-jul 01:00 CDMX -> dia del reset 1-jul; dias desde hoy (incl.) = 2.
    # Con 40% ya consumido al inicio del dia quedan 60 pp -> 60/2 = 30 pp de cupo HOY.
    assert gate_diario._umbral_base_pct(40, "2026-07-01T07:00:00Z", hoy) == pytest.approx(30.0)
    # Mismo restante pero a 6 dias del reset -> 60/6 = 10 pp/dia (semana sobrada => menos cupo/dia).
    assert gate_diario._umbral_base_pct(40, "2026-07-05T07:00:00Z", hoy) == pytest.approx(10.0)


def test_umbral_base_ultimo_dia_da_todo_lo_que_queda():
    # Reset manana (30-jun) -> queda 1 dia -> hoy puedes gastar TODO lo que reste del cupo.
    assert gate_diario._umbral_base_pct(70, "2026-06-30T07:00:00Z", date(2026, 6, 29)) == pytest.approx(30.0)


def test_umbral_base_sin_reset_cae_a_reparto_plano():
    # Sin fecha de reset fiable: reparto plano de la semana (1/7), el comportamiento de respaldo.
    assert gate_diario._umbral_base_pct(0, "", date(2026, 6, 29)) == pytest.approx(_BASE)
    assert gate_diario._umbral_base_pct(None, "2026-07-01T07:00:00Z", date(2026, 6, 29)) == pytest.approx(_BASE)


def test_dias_hasta_reset_minimo_uno():
    # En el dia del reset (o pasado) nunca divide por cero: minimo 1 dia.
    assert gate_diario._dias_hasta_reset("2026-06-29T07:00:00Z", date(2026, 6, 29)) == 1
    assert gate_diario._dias_hasta_reset("2026-06-28T07:00:00Z", date(2026, 6, 29)) == 1


def _encolar_marca(marca: str, prioridad: int) -> str:
    """Encola un job de COPY de `marca` (con marca, que es donde aplica el gate por cuenta)."""
    gen_id = generaciones.crear({"tipo": "copy", "marca": marca, "etiqueta": "X"})["id"]
    spec = jobspec.construir(
        prompt="p", procesar=jobspec.construir_prompt_lib(), prioridad=prioridad
    )
    return cola.encolar(gen_id, spec, proceso="produccion", marca=marca)


def test_gate_accesor_por_cuenta_sin_snapshot_es_none(entorno):
    """Sin snapshot de uso persistido para una cuenta, su accesor devuelve None: gate inerte
    (no corta). Fallback seguro."""
    assert gate_diario.consumo_semanal_hoy_pct(_CUENTA_A) is None
    assert gate_diario.consumo_semanal_hoy_pct(_CUENTA_B) is None


def test_gate_accesor_lee_delta_por_cuenta(entorno):
    """Cableado a `cuenta_uso` POR CUENTA: consumo de hoy = semana_pct - semana_pct_inicio_dia,
    independiente por cuenta."""
    # Cuenta A: primer muestreo ancla base=30 -> 0; mismo dia sube a 45 -> 15 pp.
    repos.guardar_uso_cuenta(cuenta=_CUENTA_A, conectada=True, semana_pct=30,
                             sesion_5h_pct=5, sonnet_pct=20, dia_utc="2026-06-28")
    repos.guardar_uso_cuenta(cuenta=_CUENTA_A, conectada=True, semana_pct=45,
                             sesion_5h_pct=8, sonnet_pct=30, dia_utc="2026-06-28")
    # Cuenta B: base=10 -> 12 -> 2 pp; independiente de A.
    repos.guardar_uso_cuenta(cuenta=_CUENTA_B, conectada=True, semana_pct=10,
                             sesion_5h_pct=2, sonnet_pct=5, dia_utc="2026-06-28")
    repos.guardar_uso_cuenta(cuenta=_CUENTA_B, conectada=True, semana_pct=12,
                             sesion_5h_pct=3, sonnet_pct=6, dia_utc="2026-06-28")
    assert gate_diario.consumo_semanal_hoy_pct(_CUENTA_A) == pytest.approx(15.0)
    assert gate_diario.consumo_semanal_hoy_pct(_CUENTA_B) == pytest.approx(2.0)
    # Cuenta B desconectada -> None (no corta sus marcas).
    repos.guardar_uso_cuenta(cuenta=_CUENTA_B, conectada=False, semana_pct=None,
                             sesion_5h_pct=None, sonnet_pct=None, dia_utc="2026-06-28")
    assert gate_diario.consumo_semanal_hoy_pct(_CUENTA_B) is None


def test_gate_umbral_y_aceptar_son_independientes_por_cuenta(entorno):
    """El estado del dia (umbral/aceptados) es POR CUENTA: aceptar en una no toca a la otra."""
    assert gate_diario.aceptados_hoy(_CUENTA_A) == 0
    assert gate_diario.umbral_vigente(_CUENTA_A) == pytest.approx(_BASE)
    gate_diario.aceptar_mas(_CUENTA_A)
    assert gate_diario.aceptados_hoy(_CUENTA_A) == 1
    assert gate_diario.umbral_vigente(_CUENTA_A) == pytest.approx(_BASE + 10.0)
    # La cuenta B conserva su umbral base: el aceptar de A no la tocó.
    assert gate_diario.aceptados_hoy(_CUENTA_B) == 0
    assert gate_diario.umbral_vigente(_CUENTA_B) == pytest.approx(_BASE)
    gate_diario.aceptar_mas(_CUENTA_A)
    assert gate_diario.umbral_vigente(_CUENTA_A) == pytest.approx(_BASE + 20.0)


def test_gate_reset_al_cambiar_de_dia_cdmx_por_cuenta(entorno, monkeypatch):
    monkeypatch.setattr(gate_diario, "dia_cdmx", lambda: "2026-06-28")
    gate_diario.aceptar_mas(_CUENTA_B)
    assert gate_diario.aceptados_hoy(_CUENTA_B) == 1
    # Dia CDMX nuevo: el contador de ayer no cuenta -> umbral vuelve a la base.
    monkeypatch.setattr(gate_diario, "dia_cdmx", lambda: "2026-06-29")
    assert gate_diario.aceptados_hoy(_CUENTA_B) == 0
    assert gate_diario.umbral_vigente(_CUENTA_B) == pytest.approx(_BASE)


def test_gate_escalon_pausa_y_reanuda_con_aceptar_por_cuenta(entorno, monkeypatch):
    """El escalon completo de UNA cuenta: alcanzar el umbral pausa; aceptar +10% reanuda hasta el
    nuevo umbral. Aceptar en B no afecta a A."""
    # 13% < base ~14,3 -> no pausa.
    _patch_consumo(monkeypatch, {_CUENTA_B: 13.0})
    assert gate_diario.pausado_por_pct(_CUENTA_B) is False
    # 15% >= 14,3 -> pausa.
    _patch_consumo(monkeypatch, {_CUENTA_B: 15.0})
    assert gate_diario.pausado_por_pct(_CUENTA_B) is True
    # Aceptar +10% en B sube su umbral a ~24,3: 15% ya no pausa B.
    gate_diario.aceptar_mas(_CUENTA_B)
    assert gate_diario.pausado_por_pct(_CUENTA_B) is False
    # ...hasta cruzar el NUEVO umbral de B.
    _patch_consumo(monkeypatch, {_CUENTA_B: 25.0})
    assert gate_diario.pausado_por_pct(_CUENTA_B) is True


def test_gate_fuente_none_no_corta(entorno, monkeypatch):
    _patch_consumo(monkeypatch, {_CUENTA_A: None, _CUENTA_B: None})
    assert gate_diario.pausado_por_pct(_CUENTA_A) is False
    est = gate_diario.estado(_CUENTA_A)
    assert est["consumo_hoy_pct"] is None and est["pausado_por_pct"] is False


def test_gate_estado_forma(entorno, monkeypatch):
    _patch_consumo(monkeypatch, {_CUENTA_A: 9.5})
    est = gate_diario.estado(_CUENTA_A)
    assert set(est) == {
        "cuenta", "consumo_hoy_pct", "umbral_pct", "aceptados_hoy", "pausado_por_pct",
        "base_umbral_pct", "paso_pct", "limite", "dia",
    }
    assert est["cuenta"] == _CUENTA_A
    assert est["consumo_hoy_pct"] == pytest.approx(9.5)
    assert est["umbral_pct"] == pytest.approx(round(_BASE, 1))
    assert est["paso_pct"] == 10.0
    assert est["limite"] == "semanal"  # sin fila de Sonnet, el unico con dato es el semanal


def test_gate_corta_por_sonnet_cuando_es_el_que_primero_se_agota(entorno):
    """Con Sonnet mas atado que el semanal, el corte (y el limite que reporta `estado`) es Sonnet."""
    # Base del dia 10/10 (semana/sonnet); luego semana sube a 20 (consume 10 pp) y Sonnet a 40
    # (consume 30 pp). Sin reset explicito el cupo de cada uno es ~12,9 pp/dia: Sonnet lo cruza.
    repos.guardar_uso_cuenta(cuenta=_CUENTA_A, conectada=True, semana_pct=10, sesion_5h_pct=0,
                             sonnet_pct=10, dia_utc="2026-06-28")
    repos.guardar_uso_cuenta(cuenta=_CUENTA_A, conectada=True, semana_pct=20, sesion_5h_pct=0,
                             sonnet_pct=40, dia_utc="2026-06-28")
    assert gate_diario.consumo_semanal_hoy_pct(_CUENTA_A) == pytest.approx(10.0)  # semanal no corta
    assert gate_diario.pausado_por_pct(_CUENTA_A) is True  # Sonnet si
    est = gate_diario.estado(_CUENTA_A)
    assert est["limite"] == "sonnet"
    assert est["consumo_hoy_pct"] == pytest.approx(30.0)


def test_gate_estado_todas_trae_las_dos_cuentas(entorno, monkeypatch):
    _patch_consumo(monkeypatch, {_CUENTA_A: 5.0, _CUENTA_B: 20.0})
    todas = gate_diario.estado_todas()
    assert set(todas) == set(jobspec.CUENTAS)
    assert todas[_CUENTA_A]["pausado_por_pct"] is False  # 5 < ~14,3
    assert todas[_CUENTA_B]["pausado_por_pct"] is True  # 20 >= ~14,3
    assert todas[_CUENTA_B]["cuenta"] == _CUENTA_B


def test_nivel_pausado_por_gate_de_la_cuenta_de_la_marca(entorno, monkeypatch):
    """Con la cuenta de la marca en umbral, `nivel(marca)` es PAUSADO; `estado(marca)` lo distingue
    del kill switch. Aceptar +10% en ESA cuenta reanuda."""
    cuenta_unotv = ruteo_cuentas.cuenta_de_marca("unotv")
    _patch_consumo(monkeypatch, {cuenta_unotv: 20.0})  # > base ~14,3
    assert presupuesto_ia.nivel("unotv") == presupuesto_ia.NIVEL_PAUSADO
    est = presupuesto_ia.estado("unotv")
    assert est["pausada"] is False  # NO es el kill switch manual
    assert est["gate_diario"]["pausado_por_pct"] is True
    assert est["gate_diario"]["cuenta"] == cuenta_unotv
    # Aceptar +10% en la cuenta de unotv (umbral ~24,3) reanuda: 20% ya no pausa.
    gate_diario.aceptar_mas(cuenta_unotv)
    assert presupuesto_ia.nivel("unotv") == presupuesto_ia.NIVEL_NORMAL


def test_gate_diario_pausa_solo_las_marcas_de_la_cuenta_gateada(entorno, monkeypatch):
    """CUENTA B en umbral pausa SOLO las marcas de B: un job de unotv (B) se bloquea; uno de
    claro-sports (A) NO. El gate por cuenta corta en la ADMISION (donde se conoce la marca)."""
    # Solo la cuenta B alcanza su umbral; la A sigue muy por debajo.
    _patch_consumo(monkeypatch, {_CUENTA_A: 0.0, _CUENTA_B: 50.0})
    assert ruteo_cuentas.cuenta_de_marca("unotv") == _CUENTA_B
    assert ruteo_cuentas.cuenta_de_marca("claro-sports") == _CUENTA_A

    # nivel/bloqueo por marca: unotv (B) PAUSADO; claro-sports (A) NORMAL.
    assert presupuesto_ia.nivel("unotv") == presupuesto_ia.NIVEL_PAUSADO
    assert presupuesto_ia.nivel("claro-sports") == presupuesto_ia.NIVEL_NORMAL
    assert presupuesto_ia.bloqueo_inline("", "unotv", es_fondo=True) == presupuesto_ia.NIVEL_PAUSADO
    assert presupuesto_ia.bloqueo_inline("", "unotv", es_fondo=False) == presupuesto_ia.NIVEL_PAUSADO
    assert presupuesto_ia.bloqueo_inline("", "claro-sports", es_fondo=True) is None

    # ADMISION (cola.encolar con marca): rechaza unotv (fondo y manual); deja pasar claro-sports.
    with pytest.raises(generaciones.GeneracionPausadaError):
        _encolar_marca("unotv", jobspec.PRIORIDAD_MANUAL)
    with pytest.raises(generaciones.GeneracionPausadaError):
        _encolar_marca("unotv", jobspec.PRIORIDAD_AUTOMATICO)
    assert _encolar_marca("claro-sports", jobspec.PRIORIDAD_AUTOMATICO)


def test_gate_diario_sin_marca_usa_la_cuenta_por_defecto(entorno, monkeypatch):
    """Sin marca (cross-marca), el job rutea a la cuenta POR DEFECTO: su gate lo frena igual que a
    las marcas de esa cuenta. Con la por defecto en umbral, el global sin marca es PAUSADO y el
    encolado sin marca (fondo Y manual) se rechaza; la OTRA cuenta gateada no afecta al sin-marca."""
    defecto = ruteo_cuentas.cuenta_por_defecto()
    otra = _CUENTA_B if defecto == _CUENTA_A else _CUENTA_A
    # Solo la cuenta por defecto alcanza su umbral; la otra sigue muy por debajo.
    _patch_consumo(monkeypatch, {defecto: 50.0, otra: 0.0})
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_PAUSADO  # sin marca: gate de la por defecto
    assert presupuesto_ia.bloqueo_inline("", es_fondo=True) == presupuesto_ia.NIVEL_PAUSADO
    assert presupuesto_ia.bloqueo_inline("", es_fondo=False) == presupuesto_ia.NIVEL_PAUSADO  # manual
    # ADMISION sin marca: rechaza el fondo Y el manual (mismo freno duro que las marcas).
    with pytest.raises(generaciones.GeneracionPausadaError):
        _encolar(jobspec.PRIORIDAD_AUTOMATICO)
    with pytest.raises(generaciones.GeneracionPausadaError):
        _encolar(jobspec.PRIORIDAD_MANUAL)


def test_gate_diario_sin_marca_pasa_con_la_por_defecto_bajo_umbral(entorno, monkeypatch):
    """Con la cuenta por defecto por debajo de su umbral, el trabajo sin marca sigue pasando aunque
    OTRA cuenta este gateada (el sin-marca rutea solo a la por defecto)."""
    defecto = ruteo_cuentas.cuenta_por_defecto()
    otra = _CUENTA_B if defecto == _CUENTA_A else _CUENTA_A
    _patch_consumo(monkeypatch, {defecto: 0.0, otra: 50.0})
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL
    assert presupuesto_ia.bloqueo_inline("", es_fondo=True) is None
    assert _encolar(jobspec.PRIORIDAD_AUTOMATICO)  # encolado SIN marca: pasa


def test_gate_diario_fuente_none_no_afecta_a_nivel(entorno):
    """Sin cablear la fuente (None por defecto), el gate diario no cambia el nivel de ninguna marca
    (NORMAL) y ninguna cuenta figura pausada en estado_todas."""
    assert presupuesto_ia.nivel() == presupuesto_ia.NIVEL_NORMAL
    assert presupuesto_ia.nivel("unotv") == presupuesto_ia.NIVEL_NORMAL
    cuentas = presupuesto_ia.estado()["gate_diario_cuentas"]
    assert all(g["pausado_por_pct"] is False for g in cuentas.values())
