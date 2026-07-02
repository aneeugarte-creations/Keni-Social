"""Tests de la API Estado (/api/estado): el DOCTOR de la consola. Todo OFFLINE.

Los chequeos OPERATIVOS (consolidacion del banner del front) reusan las sondas
compartidas de `api/sistema`, `api/actividad` y `presupuesto_ia`; el de METRICAS
reusa el estado por marca de `api/conexiones` (la misma fuente que
`GET /api/conexiones/metricool`). Aqui se parchean por sonda para cubrir cada
escenario (cola llena, pausa, presupuesto, disco, backups, S3, daemons, Metricool)
sin depender del disco/config real de la maquina o del CI.
"""

from __future__ import annotations

import pytest

from keni_consola import presupuesto_ia
from keni_consola.api import actividad as api_actividad
from keni_consola.api import conexiones as api_conexiones
from keni_consola.api import estado as api_estado
from keni_consola.api import sistema as api_sistema

from .conftest import _cliente

# Claves del contrato de CADA chequeo (id estable + estado + mensaje + accion + rol).
_CLAVES_CHEQUEO = {"id", "estado", "nombre", "detalle", "icono", "admin", "siguiente_paso"}

# Ids de los chequeos por dominio.
_IDS_MAQUINA = {
    "maquina:cola",
    "maquina:presupuesto",
    "maquina:pausa",
    "maquina:daemons",
    "maquina:programadas",
}
_IDS_INFRA = {"infra:disco", "infra:backups", "infra:s3"}
_IDS_METRICAS = {"metricas:metricool"}

# Ids HEREDADOS del doctor CLI de keni_metricas que NO deben volver a aparecer.
_IDS_OBSOLETOS = {
    "metricas:python",
    "metricas:configuracion",
    "metricas:fuente",
    "metricas:cuentas",
    "metricas:credenciales",
}


def _snapshot_cola_sano() -> dict:
    # La cola NO tiene tope (R-NO-LIMIT): solo max_jobs (concurrencia) + conteo.
    return {
        "max_jobs": 4,
        "pendientes": 0, "reclamados": 0, "terminados": 0, "activos": 0,
    }


def _presupuesto_sano() -> dict:
    return {
        "nivel": presupuesto_ia.NIVEL_NORMAL, "pausada": False,
        "presupuesto_tokens_dia": 0, "presupuesto_usd_dia": 0.0, "margen_manual_pct": 20,
        "gastado": {"tokens": 0, "coste_usd": 0.0}, "restante_tokens": None,
        "pct_usado": None, "pct_usado_usd": None, "dia": "2026-01-01",
    }


def _discos_sanos() -> list[dict]:
    return [
        {"etiqueta": "Estado", "ruta": "/data", "usado": 10, "total": 100, "porcentaje": 10.0},
        {"etiqueta": "Sistema", "ruta": "/", "usado": 40, "total": 100, "porcentaje": 40.0},
    ]


def _metricool_todo_conectado() -> list[dict]:
    return [
        {"marca": "unotv", "etiqueta": "UnoTV", "conectado": True,
         "user_id_pista": "111", "blog_id": "222"},
        {"marca": "claro_sports", "etiqueta": "Claro Sports", "conectado": True,
         "user_id_pista": "333", "blog_id": "444"},
    ]


@pytest.fixture
def sondas_sanas(monkeypatch):
    """Sondas DETERMINISTAS y sanas: el disco/cola/BD/config real de la maquina o del
    runner de CI no debe colarse en los asserts (un runner con el disco al 90% no es
    un fallo del doctor). Cada test de escenario re-parchea la sonda que le toca."""
    monkeypatch.setattr(api_actividad, "snapshot_cola", _snapshot_cola_sano)
    monkeypatch.setattr(presupuesto_ia, "estado", _presupuesto_sano)
    monkeypatch.setattr(api_sistema, "_discos", _discos_sanos)
    monkeypatch.setattr(
        api_sistema, "sonda_daemons", lambda: {"daemons": [], "error": None}
    )
    monkeypatch.setattr(
        api_sistema,
        "sonda_backups",
        lambda: {"configurado": False, "estado": None, "dumps": 0,
                 "ultimo_dump": None, "atrasado": False, "error": None},
    )
    monkeypatch.setattr(
        api_sistema,
        "sonda_s3_salud",
        lambda: {"configurado": False, "salud": None, "error": None},
    )
    monkeypatch.setattr(
        api_conexiones, "estado_marcas_metricool", _metricool_todo_conectado
    )
    # Sin piezas programadas fuera de ventana (la sonda no toca la BD del runner).
    monkeypatch.setattr(api_estado, "_programadas_atrasadas", lambda: [])


def _chequeos(datos: dict) -> dict[str, dict]:
    """Indexa los chequeos de la respuesta por su id estable."""
    return {c["id"]: c for c in datos["resultados"]}


# --------------------------------------------------------------------------- #
# Contrato general                                                             #
# --------------------------------------------------------------------------- #


def test_estado_devuelve_json_con_contrato(entorno, sondas_sanas):
    c = _cliente()
    r = c.get("/api/estado")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    datos = r.json()
    assert set(datos) >= {"resultados", "resumen", "siguiente_paso"}
    assert isinstance(datos["resultados"], list)
    for fila in datos["resultados"]:
        assert set(fila) == _CLAVES_CHEQUEO
        assert isinstance(fila["admin"], bool)
        assert fila["estado"] in {"ok", "aviso", "error"}
    # Ids estables y UNICOS (el front ancla logica a ellos).
    ids = [f["id"] for f in datos["resultados"]]
    assert len(ids) == len(set(ids))


def test_estado_incluye_todos_los_dominios_con_rol(entorno, sondas_sanas):
    """Maquina (equipo) + infra (admin) + metricas (admin), cada uno con su flag."""
    ch = _chequeos(_cliente().get("/api/estado").json())
    assert _IDS_MAQUINA | _IDS_INFRA | _IDS_METRICAS <= set(ch)
    for id_ in _IDS_MAQUINA:
        assert ch[id_]["admin"] is False, f"{id_} es de la maquina (no admin)"
    for id_ in _IDS_INFRA | _IDS_METRICAS:
        assert ch[id_]["admin"] is True, f"{id_} es de operador (admin)"
    # Con las sondas sanas, todo esta ok y sin siguiente paso.
    for id_ in _IDS_MAQUINA | _IDS_INFRA | _IDS_METRICAS:
        assert ch[id_]["estado"] == "ok"
        assert ch[id_]["siguiente_paso"] is None


def test_estado_no_incluye_chequeos_heredados_del_doctor_cli(entorno, sondas_sanas):
    """Los chequeos del doctor CLI de keni_metricas (Python, cuentas demo, credenciales
    por plataforma, fuente de muestra) describian un modelo obsoleto: fuera."""
    datos = _cliente().get("/api/estado").json()
    ids = {f["id"] for f in datos["resultados"]}
    assert ids & _IDS_OBSOLETOS == set()
    textos = " ".join(f"{f['nombre']} {f['detalle']}" for f in datos["resultados"])
    assert "fuente de muestra" not in textos
    assert "plataformas conectadas" not in textos
    # El siguiente_paso generico de la era CLI tampoco vuelve.
    pasos = [f["siguiente_paso"] for f in datos["resultados"] if f["siguiente_paso"]]
    assert all("comando exacto" not in p for p in pasos)


def test_estado_resumen_todo_ok(entorno, sondas_sanas):
    datos = _cliente().get("/api/estado").json()
    assert "orden" in datos["resumen"]
    assert datos["siguiente_paso"]


def test_estado_resumen_con_error(entorno, sondas_sanas, monkeypatch):
    sonda = {"daemons": [{"daemon": "programador", "estado": "atrasado"}], "error": None}
    monkeypatch.setattr(api_sistema, "sonda_daemons", lambda: sonda)
    datos = _cliente().get("/api/estado").json()
    assert "problema" in datos["resumen"]
    assert "siguiente paso" in datos["siguiente_paso"]


def test_estado_si_los_chequeos_lanzan_da_500_en_espanol(entorno, sondas_sanas, monkeypatch):
    def boom():
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(api_estado, "_chequeos_maquina", boom)
    r = _cliente().get("/api/estado")
    assert r.status_code == 500
    assert "autodiagnóstico" in r.json()["error"]
    assert "Traceback" not in r.json()["error"]


def test_estado_sondas_reales_no_crashean(entorno):
    """Sin mock de sondas: cola/presupuesto contra el Postgres de pruebas, disco real,
    backups/S3/config de metricas sin configurar. El doctor responde 200 con todos
    los ids."""
    r = _cliente().get("/api/estado")
    assert r.status_code == 200
    assert _IDS_MAQUINA | _IDS_INFRA | _IDS_METRICAS <= set(_chequeos(r.json()))


# --------------------------------------------------------------------------- #
# Escenarios de la MAQUINA (cola, presupuesto, pausa, daemons)                  #
# --------------------------------------------------------------------------- #


def test_chequeo_cola_ok_sin_concepto_de_llena(entorno, sondas_sanas, monkeypatch):
    """La cola NO tiene tope (R-NO-LIMIT): aunque haya mucho en proceso, el chequeo es OK (no avisa
    de "llena", que ya no existe); el exceso simplemente espera por concurrencia."""
    cargada = {**_snapshot_cola_sano(), "reclamados": 4, "pendientes": 50, "activos": 54}
    monkeypatch.setattr(api_actividad, "snapshot_cola", lambda: cargada)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:cola"]
    assert ch["estado"] == "ok"
    assert "LLENA" not in ch["detalle"]
    assert "50 esperando" in ch["detalle"]


def test_chequeo_cola_degrada_si_bd_cae(entorno, sondas_sanas, monkeypatch):
    def boom():
        raise RuntimeError("bd caida")

    monkeypatch.setattr(api_actividad, "snapshot_cola", boom)
    r = _cliente().get("/api/estado")
    assert r.status_code == 200  # la sonda degrada, nunca 500
    ch = _chequeos(r.json())["maquina:cola"]
    assert ch["estado"] == "aviso"
    assert ch["siguiente_paso"]


def test_chequeo_presupuesto_agotado_es_error(entorno, sondas_sanas, monkeypatch):
    est = {**_presupuesto_sano(), "nivel": presupuesto_ia.NIVEL_AGOTADO}
    monkeypatch.setattr(presupuesto_ia, "estado", lambda: est)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:presupuesto"]
    assert ch["estado"] == "error"
    assert "AGOTADO" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_presupuesto_solo_manual_avisa(entorno, sondas_sanas, monkeypatch):
    est = {**_presupuesto_sano(), "nivel": presupuesto_ia.NIVEL_SOLO_MANUAL}
    monkeypatch.setattr(presupuesto_ia, "estado", lambda: est)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:presupuesto"]
    assert ch["estado"] == "aviso"
    assert "manual" in ch["detalle"].lower()


def test_chequeo_pausa_por_kill_switch(entorno, sondas_sanas, monkeypatch):
    est = {**_presupuesto_sano(), "nivel": presupuesto_ia.NIVEL_PAUSADO, "pausada": True}
    monkeypatch.setattr(presupuesto_ia, "estado", lambda: est)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:pausa"]
    assert ch["estado"] == "aviso"
    assert "PAUSADA" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_pausa_por_gate_diario(entorno, sondas_sanas, monkeypatch):
    """Freno del FONDO por % del consumo del día de UNA cuenta (no kill switch): el chequeo
    `maquina:pausa` lo distingue y nombra la cuenta afectada."""
    est = {
        **_presupuesto_sano(),
        "nivel": presupuesto_ia.NIVEL_SOLO_MANUAL,
        "pausada": False,
        "gate_diario_cuentas": {
            "a": {"cuenta": "a", "consumo_hoy_pct": 5.0, "umbral_pct": 14.3, "pausado_por_pct": False},
            "b": {"cuenta": "b", "consumo_hoy_pct": 16.0, "umbral_pct": 14.3, "pausado_por_pct": True},
        },
    }
    monkeypatch.setattr(presupuesto_ia, "estado", lambda: est)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:pausa"]
    assert ch["estado"] == "aviso"
    assert "consumo del día" in ch["detalle"]
    assert "cuenta B" in ch["detalle"]  # nombra la cuenta gateada, no la sana
    assert "+10%" in ch["siguiente_paso"]


def test_chequeo_daemons_atrasado_es_error(entorno, sondas_sanas, monkeypatch):
    sonda = {
        "daemons": [
            {"daemon": "ingesta", "estado": "atrasado"},
            {"daemon": "trends", "estado": "ok"},
        ],
        "error": None,
    }
    monkeypatch.setattr(api_sistema, "sonda_daemons", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:daemons"]
    assert ch["estado"] == "error"
    assert "ingesta" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_daemons_inactivo_no_es_problema(entorno, sondas_sanas, monkeypatch):
    """Un daemon apagado por su toggle/ajuste NO late de barrido y eso es lo esperado:
    el chequeo queda ok y lo menciona como informacion, no como aviso/error."""
    sonda = {
        "daemons": [
            {"daemon": "investigacion", "estado": "inactivo"},
            {"daemon": "produccion", "estado": "inactivo"},
            {"daemon": "programador", "estado": "ok"},
        ],
        "error": None,
    }
    monkeypatch.setattr(api_sistema, "sonda_daemons", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:daemons"]
    assert ch["estado"] == "ok"
    assert "apagado" in ch["detalle"]
    assert "2" in ch["detalle"]
    assert ch["siguiente_paso"] is None


def test_chequeo_daemons_en_espera_no_es_problema(entorno, sondas_sanas, monkeypatch):
    """Un daemon «en espera» (su interruptor ON pero la máquina apagada) NO es un fallo: el
    chequeo queda ok y lo menciona como información, igual que «inactivo»."""
    sonda = {
        "daemons": [
            {"daemon": "investigacion", "estado": "en_espera"},
            {"daemon": "programador", "estado": "ok"},
        ],
        "error": None,
    }
    monkeypatch.setattr(api_sistema, "sonda_daemons", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:daemons"]
    assert ch["estado"] == "ok"
    assert "en espera" in ch["detalle"]
    assert ch["siguiente_paso"] is None


def test_chequeo_daemons_barrido_en_error_avisa(entorno, sondas_sanas, monkeypatch):
    sonda = {"daemons": [{"daemon": "alertas", "estado": "error"}], "error": None}
    monkeypatch.setattr(api_sistema, "sonda_daemons", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:daemons"]
    assert ch["estado"] == "aviso"
    assert "alertas" in ch["detalle"]


def test_chequeo_programadas_fuera_de_ventana_avisa(entorno, sondas_sanas, monkeypatch):
    """Piezas programadas que vencieron >2 h sin publicarse: aviso con conteo y paso claro.

    El barrido del programador las salta en silencio (ventana de frescura); el doctor
    es el sitio donde ese silencio se vuelve visible."""
    atrasadas = [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]
    monkeypatch.setattr(api_estado, "_programadas_atrasadas", lambda: atrasadas)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:programadas"]
    assert ch["estado"] == "aviso"
    assert ch["admin"] is False
    assert "3" in ch["detalle"] and "fuera de ventana" in ch["detalle"]
    assert "Reprográmalas" in ch["siguiente_paso"]


def test_chequeo_programadas_degrada_si_bd_cae(entorno, sondas_sanas, monkeypatch):
    def _explota():
        raise RuntimeError("bd caída")

    monkeypatch.setattr(api_estado, "_programadas_atrasadas", _explota)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:programadas"]
    assert ch["estado"] == "aviso"
    assert ch["siguiente_paso"]


# --------------------------------------------------------------------------- #
# Escenarios de INFRA (disco, backups, S3)                                      #
# --------------------------------------------------------------------------- #


def test_chequeo_disco_sobre_umbral_avisa(entorno, sondas_sanas, monkeypatch):
    discos = [{"etiqueta": "Estado", "ruta": "/data", "usado": 91, "total": 100,
               "porcentaje": 91.0}]
    monkeypatch.setattr(api_sistema, "_discos", lambda: discos)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:disco"]
    assert ch["estado"] == "aviso"
    assert "Estado" in ch["detalle"] and "91" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_disco_critico_es_error(entorno, sondas_sanas, monkeypatch):
    discos = [{"etiqueta": "Sistema", "ruta": "/", "usado": 97, "total": 100,
               "porcentaje": 97.0}]
    monkeypatch.setattr(api_sistema, "_discos", lambda: discos)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:disco"]
    assert ch["estado"] == "error"


def test_chequeo_backups_fallido_es_error(entorno, sondas_sanas, monkeypatch):
    sonda = {"configurado": True, "estado": {"ok": False, "paso": "pg_dump"},
             "dumps": 3, "ultimo_dump": None, "atrasado": False, "error": None}
    monkeypatch.setattr(api_sistema, "sonda_backups", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:backups"]
    assert ch["estado"] == "error"
    assert "pg_dump" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_backups_atrasado_avisa(entorno, sondas_sanas, monkeypatch):
    sonda = {"configurado": True, "estado": {"ok": True, "paso": ""},
             "dumps": 3, "ultimo_dump": None, "atrasado": True, "error": None}
    monkeypatch.setattr(api_sistema, "sonda_backups", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:backups"]
    assert ch["estado"] == "aviso"
    assert "26 h" in ch["detalle"]


def test_chequeo_s3_con_error_de_salud(entorno, sondas_sanas, monkeypatch):
    sonda = {"configurado": True, "salud": "err",
             "error": "No se pudo conectar con el almacenamiento."}
    monkeypatch.setattr(api_sistema, "sonda_s3_salud", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:s3"]
    assert ch["estado"] == "error"
    assert ch["siguiente_paso"]


# --------------------------------------------------------------------------- #
# Escenarios de METRICAS (Metricool por marca)                                  #
# --------------------------------------------------------------------------- #


def test_chequeo_metricool_todo_conectado_ok(entorno, sondas_sanas):
    ch = _chequeos(_cliente().get("/api/estado").json())["metricas:metricool"]
    assert ch["estado"] == "ok"
    assert "2 de 2" in ch["detalle"]
    assert ch["siguiente_paso"] is None
    # Nunca se filtran credenciales al detalle.
    assert "111" not in ch["detalle"] and "222" not in ch["detalle"]


def test_chequeo_metricool_marca_suelta_avisa(entorno, sondas_sanas, monkeypatch):
    marcas = [
        {"marca": "unotv", "etiqueta": "UnoTV", "conectado": True},
        {"marca": "fundacion", "etiqueta": "Fundación", "conectado": False},
    ]
    monkeypatch.setattr(api_conexiones, "estado_marcas_metricool", lambda: marcas)
    ch = _chequeos(_cliente().get("/api/estado").json())["metricas:metricool"]
    assert ch["estado"] == "aviso"
    assert "1 de 2" in ch["detalle"]
    assert "Fundación" in ch["detalle"]
    assert "Conexiones" in ch["siguiente_paso"]


def test_chequeo_metricool_sin_conexiones_avisa(entorno, sondas_sanas, monkeypatch):
    marcas = [
        {"marca": "unotv", "etiqueta": "UnoTV", "conectado": False},
        {"marca": "claro_sports", "etiqueta": "Claro Sports", "conectado": False},
    ]
    monkeypatch.setattr(api_conexiones, "estado_marcas_metricool", lambda: marcas)
    ch = _chequeos(_cliente().get("/api/estado").json())["metricas:metricool"]
    assert ch["estado"] == "aviso"
    assert "Ninguna" in ch["detalle"]
    assert "Conexiones" in ch["siguiente_paso"]


def test_chequeo_metricool_config_ilegible_es_error(entorno, sondas_sanas, monkeypatch):
    def boom():
        raise ValueError("toml corrupto")

    monkeypatch.setattr(api_conexiones, "estado_marcas_metricool", boom)
    r = _cliente().get("/api/estado")
    assert r.status_code == 200  # degrada a chequeo en error, nunca 500
    ch = _chequeos(r.json())["metricas:metricool"]
    assert ch["estado"] == "error"
    assert "config" in ch["detalle"].lower()
    assert ch["siguiente_paso"]
    assert "toml corrupto" not in ch["detalle"]  # sin tracebacks ni detalles crudos
