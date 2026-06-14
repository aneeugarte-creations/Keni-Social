"""Tests de los LATIDOS de daemons: db_latidos (upsert/contadores), la fachada
best-effort `latidos.py` (jamás propaga, throttle de ciclo, fichero de liveness),
la instrumentación de `bucle_gateado` y el endpoint `/api/sistema/daemons`.

Los tests de BD usan el Postgres de pruebas (fixture `entorno`); los de la fachada y el
bucle van con dobles (sin BD): el contrato clave es que un latido NUNCA rompe un barrido.
"""

from __future__ import annotations

import logging

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, daemon_util, db, latidos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
_LOG = logging.getLogger("test_latidos")


def _cli_admin() -> TestClient:
    auth.crear_usuario("u", CLAVE, "admin")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    )
    assert r.status_code == 200
    return c


# --------------------------------------------------------------------------- #
# db_latidos: upsert y contadores                                              #
# --------------------------------------------------------------------------- #


def test_latido_ciclo_upsert(entorno):
    db.latido_ciclo("demo", activo=True, intervalo_seg=300.0, tick_seg=60.0)
    db.latido_ciclo("demo", activo=False, intervalo_seg=600.0, tick_seg=60.0)
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "demo"]
    assert fila["activo"] is False
    assert fila["intervalo_seg"] == 600.0
    assert fila["visto"]
    # El ciclo NO toca los campos de barrido.
    assert fila["barridos"] == 0
    assert fila["ultimo_barrido"] == ""


def test_latido_barrido_ok_y_error_acumulan(entorno):
    db.latido_barrido("demo", ok=True, intervalo_seg=60.0, tick_seg=60.0, duracion_ms=12)
    db.latido_barrido(
        "demo", ok=False, intervalo_seg=60.0, tick_seg=60.0, duracion_ms=5,
        error_txt="ValueError('x')",
    )
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "demo"]
    assert fila["barridos"] == 2
    assert fila["errores"] == 1
    assert fila["ultimo_ok"] and fila["ultimo_error"]
    assert fila["error_txt"] == "ValueError('x')"
    assert fila["duracion_ms"] == 5
    # Un barrido marca el daemon como activo y visto.
    assert fila["activo"] is True
    assert fila["visto"]


def test_error_txt_truncado(entorno):
    db.latido_barrido(
        "demo", ok=False, intervalo_seg=1.0, tick_seg=1.0, error_txt="x" * 5000
    )
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "demo"]
    assert len(fila["error_txt"]) == 500


# --------------------------------------------------------------------------- #
# Fachada latidos: best-effort SIN BD + throttle + fichero                     #
# --------------------------------------------------------------------------- #


def test_fachada_no_propaga_sin_bd(monkeypatch):
    # Sin DATABASE_URL ni Postgres: registrar un latido debe ser un no-op silencioso.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST"):
        monkeypatch.delenv(var, raising=False)
    latidos.barrido("x", ok=True, intervalo_seg=1.0, tick_seg=1.0)
    latidos.ciclo("x", activo=True, intervalo_seg=1.0, tick_seg=1.0)


def test_ciclo_throttleado(monkeypatch):
    llamadas: list[str] = []

    def _falso_ciclo(daemon, **kwargs):
        llamadas.append(daemon)

    from keni_consola import db_latidos

    monkeypatch.setattr(db_latidos, "latido_ciclo", _falso_ciclo)
    monkeypatch.setattr(latidos, "_ultimo_ciclo", {})
    latidos.ciclo("t", activo=True, intervalo_seg=1.0, tick_seg=1.0)
    latidos.ciclo("t", activo=True, intervalo_seg=1.0, tick_seg=1.0)  # dentro del throttle
    assert llamadas == ["t"]


def test_fichero_latido(tmp_path, monkeypatch):
    ruta = tmp_path / "latido"
    monkeypatch.setenv(latidos.ENV_FICHERO_LATIDO, str(ruta))
    latidos.tocar_fichero()
    assert ruta.exists()
    assert ruta.read_text().strip().isdigit()


def test_nombre_de_sweep_alias():
    def sweep():  # __module__ = tests.test_latidos -> sin alias, nombre corto del modulo
        pass

    assert latidos.nombre_de_sweep(sweep) == "test_latidos"
    assert latidos._ALIAS["ingesta_daemon"] == "ingesta"
    # "pipeline" se partio en "investigacion"+"produccion": el nombre viejo esta
    # RETIRADO (la sonda ignora su fila huerfana) y ya no hay alias que lo resucite.
    assert "pipeline" in latidos.RETIRADOS
    assert "pipeline" not in latidos._ALIAS.values()


# --------------------------------------------------------------------------- #
# bucle_gateado instrumentado (dobles, sin BD)                                 #
# --------------------------------------------------------------------------- #


def test_bucle_gateado_registra_barrido_ok_y_error(monkeypatch):
    registros: list[tuple[str, bool, str]] = []

    def _falso_barrido(daemon, *, ok, intervalo_seg, tick_seg, duracion_ms=0, error="", resumen=""):
        registros.append((daemon, ok, error))

    monkeypatch.setattr(latidos, "barrido", _falso_barrido)
    monkeypatch.setattr(latidos, "ciclo", lambda *a, **k: None)

    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 0.0,
        sweep_fn=lambda: None,
        tick_seg=0.001,
        log=_LOG,
        nombre="mi-daemon",
        _max_vueltas=1,
    )

    def explota():
        raise ValueError("boom")

    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 0.0,
        sweep_fn=explota,
        tick_seg=0.001,
        log=_LOG,
        nombre="mi-daemon",
        _max_vueltas=1,
    )
    assert registros[0] == ("mi-daemon", True, "")
    assert registros[1][0:2] == ("mi-daemon", False)
    assert "boom" in registros[1][2]


def test_bucle_gateado_apagado_late_como_ciclo(monkeypatch):
    ciclos: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        latidos, "ciclo", lambda d, *, activo, **k: ciclos.append((d, activo))
    )
    monkeypatch.setattr(latidos, "barrido", lambda *a, **k: None)
    daemon_util.bucle_gateado(
        activo_fn=lambda: False,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=lambda: None,
        tick_seg=0.001,
        log=_LOG,
        nombre="apagado",
        _max_vueltas=2,
    )
    assert ciclos == [("apagado", False), ("apagado", False)]


# --------------------------------------------------------------------------- #
# Endpoint /api/sistema/daemons                                                #
# --------------------------------------------------------------------------- #


def test_endpoint_daemons_contrato_y_estados(entorno):
    db.latido_barrido("sano", ok=True, intervalo_seg=60.0, tick_seg=60.0, duracion_ms=10)
    db.latido_barrido(
        "roto", ok=False, intervalo_seg=60.0, tick_seg=60.0, error_txt="RuntimeError('x')"
    )
    db.latido_ciclo("dormido", activo=False, intervalo_seg=3600.0, tick_seg=60.0)
    c = _cli_admin()
    r = c.get("/api/sistema/daemons")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["error"] is None
    por_nombre = {d["daemon"]: d for d in cuerpo["daemons"]}
    assert por_nombre["sano"]["estado"] == "ok"
    assert por_nombre["sano"]["edad_seg"] is not None
    assert por_nombre["roto"]["estado"] == "error"
    assert por_nombre["roto"]["error_txt"] == "RuntimeError('x')"
    assert por_nombre["dormido"]["estado"] == "inactivo"


def _envejecer_latido(daemon: str) -> None:
    """Deja el `visto` del daemon muy atras en el tiempo (mas alla de todo umbral)."""
    from keni_consola._db_comun import _conectar

    con = _conectar()
    try:
        con.execute(
            "UPDATE daemon_latidos SET visto = ? WHERE daemon = ?",
            ("2020-01-01T00:00:00", daemon),
        )
        con.commit()
    finally:
        con.close()


def test_endpoint_daemons_atrasado(entorno):
    # Un latido ACTIVO con `visto` viejo (mas alla del umbral) debe salir "atrasado".
    db.latido_barrido("zombi", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    _envejecer_latido("zombi")
    c = _cli_admin()
    r = c.get("/api/sistema/daemons")
    por_nombre = {d["daemon"]: d for d in r.json()["daemons"]}
    assert por_nombre["zombi"]["estado"] == "atrasado"


def test_endpoint_daemons_inactivo_viejo_no_es_atrasado(entorno):
    # Un daemon APAGADO por su toggle (activo=0) que no late es lo ESPERADO: sale
    # "inactivo" aunque su `visto` sea viejisimo (jamas un falso "atrasado").
    db.latido_ciclo("apagado", activo=False, intervalo_seg=15.0, tick_seg=60.0)
    _envejecer_latido("apagado")
    c = _cli_admin()
    por_nombre = {d["daemon"]: d for d in c.get("/api/sistema/daemons").json()["daemons"]}
    assert por_nombre["apagado"]["estado"] == "inactivo"


def test_endpoint_daemons_ignora_retirados(entorno):
    # La fila huerfana de un daemon RETIRADO/renombrado (p. ej. "pipeline", que se
    # partio en investigacion+produccion) no se pinta nunca: nadie la actualizara.
    db.latido_barrido("pipeline", ok=True, intervalo_seg=15.0, tick_seg=60.0)
    _envejecer_latido("pipeline")
    db.latido_barrido("programador", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    nombres = {d["daemon"] for d in c.get("/api/sistema/daemons").json()["daemons"]}
    assert "pipeline" not in nombres
    assert "programador" in nombres


def test_endpoint_daemons_expone_barrible(entorno):
    # `barrible` = su bucle corre sobre `bucle_gateado` y CONSUME el flag de barrido forzado
    # (latidos.BARRIBLES); los bucles legados (programador/metricas/...) no lo miran, asi que
    # el front solo les ofrece "Barrer ahora" a los primeros.
    db.latido_barrido("ingesta", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    db.latido_barrido("programador", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    por_nombre = {d["daemon"]: d for d in c.get("/api/sistema/daemons").json()["daemons"]}
    assert por_nombre["ingesta"]["barrible"] is True
    assert por_nombre["programador"]["barrible"] is False


# --------------------------------------------------------------------------- #
# Clasificacion: grupo (motor/papel) + gasta_tokens (constantes y endpoint)     #
# --------------------------------------------------------------------------- #


def test_grupo_de_clasifica_cada_motor():
    # Mapeo explícito por grupo (fuente única en latidos): un daemon de cada motor.
    assert latidos.grupo_de("ingesta") == "investigacion"
    assert latidos.grupo_de("investigacion") == "investigacion"
    assert latidos.grupo_de("produccion") == "produccion"
    assert latidos.grupo_de("sugerencias") == "produccion"
    assert latidos.grupo_de("comercial") == "flujo"
    assert latidos.grupo_de("programador") == "flujo"
    assert latidos.grupo_de("vencimientos") == "flujo"
    assert latidos.grupo_de("metricas") == "infra"
    assert latidos.grupo_de("reaper") == "infra"


def test_grupo_de_default_infra():
    # Un daemon registrado fuera del mapeo cae a "infra" (nunca rompe el panel).
    assert latidos.grupo_de("daemon_nuevo_sin_clasificar") == "infra"


def test_gasta_tokens_solo_los_que_encolan_claude():
    # Solo investigacion/produccion/sugerencias corren `claude -p`; el resto no gasta.
    # patrones deriva de Metricool SIN claude => False.
    assert latidos.gasta_tokens("investigacion") is True
    assert latidos.gasta_tokens("produccion") is True
    assert latidos.gasta_tokens("sugerencias") is True
    for d in ("ingesta", "trends", "algoritmos", "comercial", "programador",
              "vencimientos", "metricas", "metricas_piezas", "alertas_rendimiento",
              "media_gc", "patrones", "noticias_gc", "reaper"):
        assert latidos.gasta_tokens(d) is False


def test_endpoint_daemons_expone_grupo_y_gasta_tokens(entorno):
    # El endpoint añade `grupo` y `gasta_tokens` a cada daemon (contrato del dashboard
    # de Workers): el front agrupa por aquí sin hardcodear nombres.
    db.latido_barrido("investigacion", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    db.latido_barrido("metricas", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    por_nombre = {d["daemon"]: d for d in c.get("/api/sistema/daemons").json()["daemons"]}
    assert por_nombre["investigacion"]["grupo"] == "investigacion"
    assert por_nombre["investigacion"]["gasta_tokens"] is True
    assert por_nombre["metricas"]["grupo"] == "infra"
    assert por_nombre["metricas"]["gasta_tokens"] is False


# --------------------------------------------------------------------------- #
# clase + motor: clasificacion afinada (ia/maquina/sistema + motor del loop)    #
# --------------------------------------------------------------------------- #


def test_clase_de_clasifica_ia_maquina_sistema():
    # IA: gasta tokens + tiene prompt.
    for d in ("investigacion", "produccion", "sugerencias"):
        assert latidos.clase_de(d) == "ia"
    # MAQUINA: parte de la maquina de contenido NO-IA.
    for d in ("ingesta", "trends", "algoritmos", "noticias_gc", "programador", "vencimientos"):
        assert latidos.clase_de(d) == "maquina"
    # SISTEMA: infraestructura (incl. patrones, comercial, media_gc).
    for d in ("reaper", "media_gc", "metricas", "metricas_piezas", "alertas_rendimiento",
              "patrones", "comercial"):
        assert latidos.clase_de(d) == "sistema"


def test_motor_de_mapea_el_loop_o_none():
    assert latidos.motor_de("investigacion") == "investigacion"
    assert latidos.motor_de("produccion") == "produccion"
    assert latidos.motor_de("sugerencias") == "produccion"
    # La maquina sirve a un motor concreto.
    assert latidos.motor_de("ingesta") == "investigacion"
    assert latidos.motor_de("noticias_gc") == "investigacion"
    assert latidos.motor_de("programador") == "produccion"
    assert latidos.motor_de("vencimientos") == "produccion"
    # Sistema no pertenece a ningun motor.
    for d in ("reaper", "metricas", "patrones", "comercial"):
        assert latidos.motor_de(d) is None


def test_clase_motor_default_sistema_none():
    # Un daemon no mapeado cae a sistema/None (nunca rompe el panel).
    assert latidos.clase_de("daemon_nuevo_sin_clasificar") == "sistema"
    assert latidos.motor_de("daemon_nuevo_sin_clasificar") is None


def test_endpoint_daemons_expone_clase_y_motor(entorno):
    # El endpoint añade `clase` y `motor` a cada daemon (contrato ADITIVO del dashboard).
    db.latido_barrido("investigacion", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    db.latido_barrido("ingesta", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    db.latido_barrido("metricas", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    por_nombre = {d["daemon"]: d for d in c.get("/api/sistema/daemons").json()["daemons"]}
    assert por_nombre["investigacion"]["clase"] == "ia"
    assert por_nombre["investigacion"]["motor"] == "investigacion"
    assert por_nombre["ingesta"]["clase"] == "maquina"
    assert por_nombre["ingesta"]["motor"] == "investigacion"
    assert por_nombre["metricas"]["clase"] == "sistema"
    assert por_nombre["metricas"]["motor"] is None


# --------------------------------------------------------------------------- #
# clave_gate: qué clave de ajuste enciende/apaga cada daemon (toggle de fila)   #
# --------------------------------------------------------------------------- #


def test_clave_gate_de_mapea_cada_daemon_gateado():
    # Mapeo explícito daemon -> clave KENI_* que gobierna su on/off (fuente única en latidos).
    assert latidos.clave_gate_de("ingesta") == "KENI_PIPELINE_SELECCION"
    assert latidos.clave_gate_de("trends") == "KENI_TRENDS"
    assert latidos.clave_gate_de("algoritmos") == "KENI_ALGORITMOS_AUTO"
    assert latidos.clave_gate_de("sugerencias") == "KENI_SUGERENCIAS_EDITORIALES"
    assert latidos.clave_gate_de("media_gc") == "KENI_MEDIA_GC"
    assert latidos.clave_gate_de("noticias_gc") == "KENI_NOTICIAS_GC"
    assert latidos.clave_gate_de("patrones") == "KENI_PATRONES_AUTO"
    assert latidos.clave_gate_de("alertas_rendimiento") == "KENI_ALERTAS_RENDIMIENTO"
    assert latidos.clave_gate_de("vencimientos") == "KENI_EVENTOS_VENCIMIENTOS"
    # Los loops del pipeline no tienen clave propia (varias etapas): toggle de fila = maestro.
    assert latidos.clave_gate_de("investigacion") == "KENI_MAQUINA"
    assert latidos.clave_gate_de("produccion") == "KENI_MAQUINA"


def test_clave_gate_de_null_en_siempre_on():
    # Daemons SIEMPRE-ON sin toggle de ajuste -> None (el front no pinta switch on/off).
    for d in ("reaper", "programador", "comercial", "metricas", "metricas_piezas"):
        assert latidos.clave_gate_de(d) is None
    # Un daemon desconocido tampoco tiene gate.
    assert latidos.clave_gate_de("daemon_nuevo_sin_clasificar") is None


def test_clave_gate_son_claves_reales_del_catalogo():
    # Cada clave_gate debe ser una clave EDITABLE real del catálogo de ajustes: así el front
    # puede pasarla tal cual a POST /api/ajustes. Si alguien renombra la env, este test cae.
    from keni_consola import ajustes_catalogo

    for daemon, clave in latidos.CLAVE_GATE.items():
        assert ajustes_catalogo.por_clave(clave) is not None, (
            f"clave_gate de {daemon!r} ({clave!r}) no existe en el catálogo de ajustes"
        )


def test_endpoint_daemons_expone_clave_gate(entorno):
    # El endpoint añade `clave_gate` a cada daemon (contrato del toggle de fila): el front
    # lee aquí qué clave conmutar, o null si el daemon es siempre-on.
    db.latido_barrido("ingesta", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    db.latido_barrido("reaper", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    por_nombre = {d["daemon"]: d for d in c.get("/api/sistema/daemons").json()["daemons"]}
    assert por_nombre["ingesta"]["clave_gate"] == "KENI_PIPELINE_SELECCION"
    assert por_nombre["reaper"]["clave_gate"] is None


# --------------------------------------------------------------------------- #
# Barrido FORZADO: flag en BD + consumo en bucle_gateado + endpoint             #
# --------------------------------------------------------------------------- #


def test_solicitar_y_consumir_barrido(entorno):
    db.latido_barrido("demo", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    # Sin fila registrada no hay a quien pedirselo.
    assert db.solicitar_barrido("inexistente") is False
    assert db.solicitar_barrido("demo") is True
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "demo"]
    assert fila["barrido_solicitado"] != ""
    # El consumo es ATOMICO y de un solo uso: el primero la ve, el segundo ya no.
    assert db.consumir_solicitud_barrido("demo") is True
    assert db.consumir_solicitud_barrido("demo") is False
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "demo"]
    assert fila["barrido_solicitado"] == ""


def test_consumir_solicitud_sin_bd_devuelve_false(monkeypatch):
    # Best-effort: un fallo de BD degrada a False (el bucle sigue, sin barrido extra).
    from keni_consola import db_latidos

    def _explota(daemon):
        raise RuntimeError("BD caida")

    monkeypatch.setattr(db_latidos, "consumir_solicitud_barrido", _explota)
    assert latidos.consumir_solicitud("x") is False


def test_bucle_gateado_barrido_forzado_corre_ya(monkeypatch):
    """Con el gate ON y una solicitud pendiente, el sweep corre en ese MISMO tick aunque por
    intervalo no tocara (y la solicitud se consume: una solicitud = un barrido extra)."""
    monkeypatch.setattr(latidos, "ciclo", lambda *a, **k: None)
    monkeypatch.setattr(latidos, "barrido", lambda *a, **k: None)
    solicitudes = ["pendiente"]  # doble del flag persistido: una solicitud en cola
    monkeypatch.setattr(
        latidos, "consumir_solicitud", lambda d: bool(solicitudes and solicitudes.pop())
    )
    llamadas: list[int] = []
    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 3600.0,  # por intervalo solo tocaria el primer barrido
        sweep_fn=lambda: llamadas.append(1),
        tick_seg=0.0,
        log=_LOG,
        nombre="forzado",
        _max_vueltas=3,
    )
    # Vuelta 1: barrido normal de arranque + consume la solicitud (el mismo sweep la
    # satisface). Sin solicitud restante, las vueltas 2-3 no barren (intervalo enorme).
    assert llamadas == [1]


def test_bucle_gateado_barrido_forzado_tras_arranque(monkeypatch):
    """La solicitud que llega DESPUES del barrido de arranque dispara un sweep extra en el
    siguiente tick, sin esperar al intervalo."""
    monkeypatch.setattr(latidos, "ciclo", lambda *a, **k: None)
    monkeypatch.setattr(latidos, "barrido", lambda *a, **k: None)
    vueltas = {"n": 0}

    def _consumir(daemon):  # la solicitud "se escribe" tras la primera vuelta
        vueltas["n"] += 1
        return vueltas["n"] == 2

    monkeypatch.setattr(latidos, "consumir_solicitud", _consumir)
    llamadas: list[int] = []
    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=lambda: llamadas.append(1),
        tick_seg=0.0,
        log=_LOG,
        nombre="forzado",
        _max_vueltas=3,
    )
    assert llamadas == [1, 1]  # arranque + forzado; la vuelta 3 ya no barre


def test_bucle_gateado_apagado_no_consume_solicitud(monkeypatch):
    """Con el gate OFF la solicitud NI se consume NI se barre: espera a la reactivacion."""
    monkeypatch.setattr(latidos, "ciclo", lambda *a, **k: None)
    monkeypatch.setattr(latidos, "barrido", lambda *a, **k: None)
    consultas: list[str] = []

    def _consumir(daemon):
        consultas.append(daemon)
        return True

    monkeypatch.setattr(latidos, "consumir_solicitud", _consumir)
    llamadas: list[int] = []
    daemon_util.bucle_gateado(
        activo_fn=lambda: False,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=lambda: llamadas.append(1),
        tick_seg=0.0,
        log=_LOG,
        nombre="apagado",
        _max_vueltas=3,
    )
    assert llamadas == []
    assert consultas == []


def test_endpoint_barrer_solicita_y_devuelve_contrato(entorno):
    # "ingesta" esta en latidos.BARRIBLES: su bucle consume el flag, asi que se acepta.
    db.latido_barrido("ingesta", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    r = c.post("/api/sistema/daemons/ingesta/barrer", headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json() == {"solicitado": True, "daemon": "ingesta"}
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "ingesta"]
    assert fila["barrido_solicitado"] != ""


def test_endpoint_barrer_desconocido_404(entorno):
    c = _cli_admin()
    r = c.post("/api/sistema/daemons/no-existe/barrer", headers=_ORIGIN)
    assert r.status_code == 404
    assert "no-existe" in r.json()["error"]


def test_endpoint_barrer_retirado_404(entorno):
    # La fila huerfana de un daemon RETIRADO no acepta solicitudes: nadie las consumiria.
    db.latido_barrido("pipeline", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    assert c.post("/api/sistema/daemons/pipeline/barrer", headers=_ORIGIN).status_code == 404


def test_endpoint_barrer_apagado_409(entorno):
    # Con el gate OFF el bucle ignoraria la solicitud: 409 con mensaje claro, sin encolarla.
    # ("trends" es barrible: lo que se prueba aqui es SOLO el gate apagado.)
    db.latido_ciclo("trends", activo=False, intervalo_seg=3600.0, tick_seg=60.0)
    c = _cli_admin()
    r = c.post("/api/sistema/daemons/trends/barrer", headers=_ORIGIN)
    assert r.status_code == 409
    assert "apagado" in r.json()["error"]
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "trends"]
    assert fila["barrido_solicitado"] == ""


def test_endpoint_barrer_no_barrible_409(entorno):
    # Un daemon LEGADO (fuera de latidos.BARRIBLES) late pero su bucle NO consume el
    # flag: aceptar la solicitud la dejaria huerfana para siempre. 409 sin encolarla.
    db.latido_barrido("programador", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    r = c.post("/api/sistema/daemons/programador/barrer", headers=_ORIGIN)
    assert r.status_code == 409
    assert "no admite barrido forzado" in r.json()["error"]
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "programador"]
    assert fila["barrido_solicitado"] == ""


def test_endpoint_barrer_solo_admin(entorno):
    db.latido_barrido("sano", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    auth.crear_usuario("e", CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = c.post(
        "/api/auth/login", json={"usuario": "e", "password": CLAVE}, headers=_ORIGIN
    )
    assert r.status_code == 200
    assert c.post("/api/sistema/daemons/sano/barrer", headers=_ORIGIN).status_code == 403


# --------------------------------------------------------------------------- #
# Historial por barrido: daemon_barridos (insercion + poda + listado + endpoint) #
# --------------------------------------------------------------------------- #


def test_registrar_barrido_inserta_y_lista_nuevo_primero(entorno):
    db.registrar_barrido(
        "demo", ok=True, ts_inicio="2026-06-01T00:00:01", duracion_ms=10, resumen="3 items"
    )
    db.registrar_barrido(
        "demo", ok=False, ts_inicio="2026-06-01T00:00:02", error_txt="boom"
    )
    barridos = db.listar_barridos("demo")
    assert len(barridos) == 2
    # Nuevo primero (orden por ts desc).
    assert barridos[0]["ok"] is False
    assert barridos[0]["error_txt"] == "boom"
    assert barridos[1]["ok"] is True
    assert barridos[1]["resumen"] == "3 items"
    assert barridos[1]["duracion_ms"] == 10


def test_registrar_barrido_poda_cota_dura(entorno, monkeypatch):
    from keni_consola import db_latidos

    monkeypatch.setattr(db_latidos, "_MAX_BARRIDOS_POR_DAEMON", 3)
    for i in range(6):
        db.registrar_barrido("demo", ok=True, ts_inicio=f"2026-06-01T00:00:0{i}")
    barridos = db.listar_barridos("demo", limite=50)
    # Solo quedan los 3 mas recientes (poda en cada insercion).
    assert [b["ts_inicio"] for b in barridos] == [
        "2026-06-01T00:00:05", "2026-06-01T00:00:04", "2026-06-01T00:00:03",
    ]


def test_registrar_barrido_trunca_resumen_y_error(entorno):
    db.registrar_barrido("demo", ok=False, resumen="r" * 1000, error_txt="e" * 1000)
    (b,) = db.listar_barridos("demo")
    assert len(b["resumen"]) == 300
    assert len(b["error_txt"]) == 500


def test_bucle_gateado_escribe_historial_con_resumen(entorno):
    # El hook comun `latidos.barrido` (via bucle_gateado) deja una fila de historial; el str
    # que devuelve el sweep viaja como `resumen`.
    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 0.0,
        sweep_fn=lambda: "ok 5 items",
        tick_seg=0.001,
        log=_LOG,
        nombre="histdemo",
        _max_vueltas=1,
    )
    barridos = db.listar_barridos("histdemo")
    assert len(barridos) == 1
    assert barridos[0]["ok"] is True
    assert barridos[0]["resumen"] == "ok 5 items"


def test_resumen_fn_formatea_dict_de_conteos():
    # Los formateadores de resumen son PUROS: derivan un str humano de los conteos del sweep
    # (dict que consumen tests/disparo a demanda) sin tocar ese contrato. Vacio => "sin novedad".
    from keni_consola.ingesta_daemon import _bucle as ingesta_bucle
    from keni_consola.pipeline_contenido import _barrido as pc_barrido

    assert ingesta_bucle._resumen_barrido(
        {"feeds": 3, "items_nuevos": 7, "clustering": {"clusters_nuevos": 2}}
    ) == "3 feed(s) sondeado(s) · 7 item(s) nuevo(s) · 2 historia(s)"
    assert ingesta_bucle._resumen_barrido(
        {"feeds": 0, "items_nuevos": 0, "clustering": {"clusters_nuevos": 0}}
    ) == "sin novedad"
    assert pc_barrido._resumen_produccion(
        {"lanzados": [1, 2], "artes": [1], "avances": []}
    ) == "2 copy · 1 arte(s) · 0 avance(s) a revisión"
    assert pc_barrido._resumen_produccion(
        {"lanzados": [], "artes": [], "avances": []}
    ) == "sin novedad"


def test_bucle_gateado_resumen_fn_escribe_historial(entorno):
    # Daemon GATEADO con dict de conteos: el `resumen_fn` deriva el str del resultado del sweep
    # y ese texto aterriza NO VACIO en `daemon_barridos` (lo que pinta la pagina de detalle).
    from keni_consola.ingesta_daemon import _bucle as ingesta_bucle

    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 0.0,
        sweep_fn=lambda: {"feeds": 4, "items_nuevos": 9, "clustering": {"clusters_nuevos": 1}},
        tick_seg=0.001,
        log=_LOG,
        nombre="ingesta-hist",
        resumen_fn=ingesta_bucle._resumen_barrido,
        _max_vueltas=1,
    )
    barridos = db.listar_barridos("ingesta-hist")
    assert len(barridos) == 1
    assert barridos[0]["ok"] is True
    assert barridos[0]["resumen"] == "4 feed(s) sondeado(s) · 9 item(s) nuevo(s) · 1 historia(s)"


def test_bucle_gateado_resumen_fn_falla_degrada_sin_romper(monkeypatch):
    # Formatear el resumen es BEST-EFFORT: si `resumen_fn` revienta, el barrido sigue OK con
    # resumen vacio (el `ok`/`error` los manda solo el sweep, jamas el formateo).
    registros: list[tuple[bool, str]] = []

    def _falso_barrido(daemon, *, ok, intervalo_seg, tick_seg, duracion_ms=0, error="", resumen=""):
        registros.append((ok, resumen))

    monkeypatch.setattr(latidos, "barrido", _falso_barrido)
    monkeypatch.setattr(latidos, "ciclo", lambda *a, **k: None)

    def _resumen_que_explota(_res):
        raise ValueError("boom")

    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 0.0,
        sweep_fn=lambda: {"x": 1},
        tick_seg=0.001,
        log=_LOG,
        nombre="resumen-roto",
        resumen_fn=_resumen_que_explota,
        _max_vueltas=1,
    )
    assert registros == [(True, "")]


def test_latido_barrido_resumen_llega_a_daemon_barridos(entorno):
    # Camino LEGADO (programador/metricas/comercial): su bucle llama `latidos.barrido` directo
    # con `resumen=`; ese texto debe aterrizar en `daemon_barridos`.
    latidos.barrido(
        "comercial", ok=True, intervalo_seg=60.0, tick_seg=60.0,
        duracion_ms=5, resumen="3 snapshot(s) capturado(s)",
    )
    (b,) = db.listar_barridos("comercial")
    assert b["ok"] is True
    assert b["resumen"] == "3 snapshot(s) capturado(s)"


def test_endpoint_barridos_contrato(entorno):
    db.latido_barrido("ingesta", ok=True, intervalo_seg=60.0, tick_seg=60.0)  # registra el daemon
    db.registrar_barrido("ingesta", ok=True, ts_inicio="2026-06-01T00:00:01", resumen="3 items")
    c = _cli_admin()
    r = c.get("/api/sistema/daemons/ingesta/barridos")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["daemon"] == "ingesta"
    assert len(cuerpo["barridos"]) == 1
    assert cuerpo["barridos"][0]["resumen"] == "3 items"
    assert cuerpo["barridos"][0]["ok"] is True


def test_endpoint_barridos_desconocido_404(entorno):
    c = _cli_admin()
    assert c.get("/api/sistema/daemons/no-existe/barridos").status_code == 404


def test_endpoint_barridos_retirado_404(entorno):
    # La fila huerfana de un daemon RETIRADO no tiene historial consultable.
    db.latido_barrido("pipeline", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    c = _cli_admin()
    assert c.get("/api/sistema/daemons/pipeline/barridos").status_code == 404


def test_endpoint_barridos_solo_admin(entorno):
    db.latido_barrido("ingesta", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    auth.crear_usuario("e", CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    assert (
        c.post(
            "/api/auth/login", json={"usuario": "e", "password": CLAVE}, headers=_ORIGIN
        ).status_code
        == 200
    )
    assert c.get("/api/sistema/daemons/ingesta/barridos").status_code == 403


# --------------------------------------------------------------------------- #
# Endpoint /api/sistema/backups                                                #
# --------------------------------------------------------------------------- #


def test_endpoint_backups_sin_configurar(entorno, monkeypatch):
    monkeypatch.delenv("KENI_BACKUPS_DIR", raising=False)
    c = _cli_admin()
    r = c.get("/api/sistema/backups")
    assert r.status_code == 200
    assert r.json()["configurado"] is False


def test_endpoint_backups_contrato(entorno, monkeypatch, tmp_path):
    raiz = tmp_path / "backups"
    (raiz / "postgres").mkdir(parents=True)
    (raiz / "postgres" / "keni-20260610-033500.dump").write_bytes(b"x" * 128)
    (raiz / "estado.json").write_text(
        '{"stamp":"20260610-033500","ok":true,"paso":"fin","error":"",'
        '"duracion_seg":42,"dump_bytes":128,"verificado":true,'
        '"volumenes":[{"volumen":"keni-data","bytes":1024}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("KENI_BACKUPS_DIR", str(raiz))
    c = _cli_admin()
    cuerpo = c.get("/api/sistema/backups").json()
    assert cuerpo["configurado"] is True
    assert cuerpo["estado"]["ok"] is True
    assert cuerpo["estado"]["verificado"] is True
    assert cuerpo["dumps"] == 1
    assert cuerpo["ultimo_dump"]["bytes"] == 128
    assert cuerpo["atrasado"] is False  # mtime recien creado
    assert cuerpo["error"] is None


def test_endpoint_backups_sin_dumps_atrasado(entorno, monkeypatch, tmp_path):
    raiz = tmp_path / "backups"
    (raiz / "postgres").mkdir(parents=True)
    monkeypatch.setenv("KENI_BACKUPS_DIR", str(raiz))
    c = _cli_admin()
    cuerpo = c.get("/api/sistema/backups").json()
    assert cuerpo["configurado"] is True
    assert cuerpo["dumps"] == 0
    assert cuerpo["atrasado"] is True
    assert cuerpo["estado"] is None  # sin estado.json: degradado, no error


def test_endpoint_backups_estado_roto_degrada(entorno, monkeypatch, tmp_path):
    raiz = tmp_path / "backups"
    (raiz / "postgres").mkdir(parents=True)
    (raiz / "estado.json").write_text("{no es json", encoding="utf-8")
    monkeypatch.setenv("KENI_BACKUPS_DIR", str(raiz))
    c = _cli_admin()
    cuerpo = c.get("/api/sistema/backups").json()
    assert cuerpo["configurado"] is True
    assert cuerpo["estado"] is None
    assert "estado.json" in (cuerpo["error"] or "")


def test_endpoint_backups_editor_403(entorno, monkeypatch):
    monkeypatch.delenv("KENI_BACKUPS_DIR", raising=False)
    auth.crear_usuario("e2", CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    assert (
        c.post(
            "/api/auth/login", json={"usuario": "e2", "password": CLAVE}, headers=_ORIGIN
        ).status_code
        == 200
    )
    assert c.get("/api/sistema/backups").status_code == 403


def test_endpoint_daemons_editor_403(entorno):
    auth.crear_usuario("e", CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    assert (
        c.post(
            "/api/auth/login", json={"usuario": "e", "password": CLAVE}, headers=_ORIGIN
        ).status_code
        == 200
    )
    assert c.get("/api/sistema/daemons").status_code == 403
