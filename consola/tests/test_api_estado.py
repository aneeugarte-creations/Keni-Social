"""Tests de la API Estado (/api/estado): el DOCTOR de la consola. Todo OFFLINE.

El doctor real escanea el PATH/rutas; para no depender de la maquina, inyectamos
`ejecutar_chequeos` con un set determinista (OK + AVISO + ERROR). Los chequeos
OPERATIVOS (consolidacion del banner del front) reusan las sondas compartidas de
`api/sistema`, `api/actividad` y `presupuesto_ia`: aqui se parchean por sonda para
cubrir cada escenario (cola llena, pausa, presupuesto, disco, backups, S3, daemons)
sin depender del disco real de la maquina/CI.
"""

from __future__ import annotations

import pytest
from keni_metricas import doctor

from keni_consola import presupuesto_ia
from keni_consola.api import actividad as api_actividad
from keni_consola.api import estado as api_estado
from keni_consola.api import sistema as api_sistema

from .conftest import _cliente

# Claves del contrato de CADA chequeo (id estable + estado + mensaje + accion + rol).
_CLAVES_CHEQUEO = {"id", "estado", "nombre", "detalle", "icono", "admin", "siguiente_paso"}

# Ids de los chequeos operativos nuevos (los del banner consolidado en el doctor).
_IDS_MAQUINA = {"maquina:cola", "maquina:presupuesto", "maquina:pausa", "maquina:daemons"}
_IDS_INFRA = {"infra:disco", "infra:backups", "infra:s3"}


def _resultados_demo() -> list[doctor.Resultado]:
    """Set determinista que cubre los tres estados DENTRO del dominio consola.

    El error vive en un chequeo del dominio (`Fuente`), no en whisper/ffmpeg: la
    consola filtra esos chequeos clip-a-copy fuera de su indicador de salud.
    """
    return [
        doctor.Resultado("Python", doctor.Estado.OK, "Python 3.12.1"),
        doctor.Resultado("Fuente", doctor.Estado.ERROR, "No se pudo construir la fuente"),
        doctor.Resultado("Configuracion", doctor.Estado.AVISO, "No hay config (se usa muestra)"),
        doctor.Resultado("Credenciales", doctor.Estado.AVISO, "0/5 plataformas conectadas"),
    ]


def _resultados_con_clip_a_copy() -> list[doctor.Resultado]:
    """El set del doctor incluye los chequeos clip-a-copy que la consola filtra."""
    return [
        *_resultados_demo(),
        doctor.Resultado("binario whisper-cli", doctor.Estado.ERROR, "whisper-cli no esta en el PATH."),
        doctor.Resultado("binario ffmpeg", doctor.Estado.ERROR, "ffmpeg no esta en el PATH."),
        doctor.Resultado("modelo whisper", doctor.Estado.ERROR, "no se encontro modelo de whisper."),
    ]


def _snapshot_cola_sano() -> dict:
    return {
        "max_jobs": 4, "max_cola": 16, "tope": 20,
        "pendientes": 0, "reclamados": 0, "terminados": 0, "activos": 0,
        "cola_llena": False,
    }


def _presupuesto_sano() -> dict:
    return {
        "nivel": presupuesto_ia.NIVEL_NORMAL, "pausada": False,
        "presupuesto_tokens_dia": 0, "margen_manual_pct": 20,
        "gastado": {"tokens": 0}, "restante_tokens": None, "pct_usado": None,
        "dia": "2026-01-01",
    }


def _discos_sanos() -> list[dict]:
    return [
        {"etiqueta": "Estado", "ruta": "/data", "usado": 10, "total": 100, "porcentaje": 10.0},
        {"etiqueta": "Sistema", "ruta": "/", "usado": 40, "total": 100, "porcentaje": 40.0},
    ]


@pytest.fixture
def doctor_mockeado(monkeypatch):
    monkeypatch.setattr(api_estado, "ejecutar_chequeos", lambda *a, **k: _resultados_demo())


@pytest.fixture
def sondas_sanas(monkeypatch):
    """Sondas operativas DETERMINISTAS y sanas: el disco/cola/BD real de la maquina o del
    runner de CI no debe colarse en los asserts (un runner con el disco al 90% no es un
    fallo del doctor). Cada test de escenario re-parchea la sonda que le toca."""
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


def _chequeos(datos: dict) -> dict[str, dict]:
    """Indexa los chequeos de la respuesta por su id estable."""
    return {c["id"]: c for c in datos["resultados"]}


# --------------------------------------------------------------------------- #
# Contrato general                                                             #
# --------------------------------------------------------------------------- #


def test_estado_devuelve_json_con_contrato(entorno, doctor_mockeado, sondas_sanas):
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
    # Ids estables y UNICOS (el front ancla logica a ellos).
    ids = [f["id"] for f in datos["resultados"]]
    assert len(ids) == len(set(ids))


def test_estado_mapea_enum_a_strings(entorno, doctor_mockeado, sondas_sanas):
    c = _cliente()
    datos = c.get("/api/estado").json()
    estados = [r["estado"] for r in datos["resultados"]]
    assert set(estados) <= {"ok", "aviso", "error"}
    assert "ok" in estados
    assert "aviso" in estados
    assert "error" in estados


def test_estado_ids_estables_de_metricas(entorno, doctor_mockeado, sondas_sanas):
    ch = _chequeos(_cliente().get("/api/estado").json())
    assert {"metricas:python", "metricas:fuente", "metricas:configuracion",
            "metricas:credenciales"} <= set(ch)
    # Los chequeos del doctor de metricas son de operador (admin) y, si no estan ok,
    # remiten a su detalle como siguiente paso.
    assert ch["metricas:python"]["admin"] is True
    assert ch["metricas:python"]["siguiente_paso"] is None
    assert ch["metricas:fuente"]["estado"] == "error"
    assert ch["metricas:fuente"]["siguiente_paso"]


def test_estado_incluye_chequeos_operativos_con_rol(entorno, doctor_mockeado, sondas_sanas):
    """Los chequeos del banner viven ahora en el doctor: maquina (equipo) + infra (admin)."""
    ch = _chequeos(_cliente().get("/api/estado").json())
    assert _IDS_MAQUINA | _IDS_INFRA <= set(ch)
    for id_ in _IDS_MAQUINA:
        assert ch[id_]["admin"] is False, f"{id_} es de la maquina (no admin)"
    for id_ in _IDS_INFRA:
        assert ch[id_]["admin"] is True, f"{id_} es de infraestructura (admin)"
    # Con las sondas sanas, todo lo operativo esta ok y sin siguiente paso.
    for id_ in _IDS_MAQUINA | _IDS_INFRA:
        assert ch[id_]["estado"] == "ok"
        assert ch[id_]["siguiente_paso"] is None


def test_estado_incluye_resumen_y_siguiente_paso(entorno, doctor_mockeado, sondas_sanas):
    datos = _cliente().get("/api/estado").json()
    # El resumen global refleja el ERROR del set demo (Fuente) con las frases del doctor.
    assert "problema" in datos["resumen"]
    assert datos["siguiente_paso"]


def test_estado_no_expone_secretos(entorno, monkeypatch, sondas_sanas):
    con_token = [doctor.Resultado("Credenciales", doctor.Estado.OK, "5/5 plataformas conectadas")]
    monkeypatch.setattr(api_estado, "ejecutar_chequeos", lambda *a, **k: con_token)
    datos = _cliente().get("/api/estado").json()
    ch = _chequeos(datos)
    assert ch["metricas:credenciales"]["detalle"] == "5/5 plataformas conectadas"


def test_estado_si_el_doctor_lanza_da_500_en_espanol(entorno, monkeypatch, sondas_sanas):
    def boom(*a, **k):
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(api_estado, "ejecutar_chequeos", boom)
    r = _cliente().get("/api/estado")
    assert r.status_code == 500
    assert "autodiagnóstico" in r.json()["error"]
    assert "Traceback" not in r.json()["error"]


def test_estado_filtra_chequeos_clip_a_copy(entorno, monkeypatch, sondas_sanas):
    """whisper-cli / ffmpeg / modelo whisper NO aparecen en el indicador consola."""
    monkeypatch.setattr(
        api_estado, "ejecutar_chequeos", lambda *a, **k: _resultados_con_clip_a_copy()
    )
    datos = _cliente().get("/api/estado").json()
    nombres = {r["nombre"] for r in datos["resultados"]}
    assert "binario whisper-cli" not in nombres
    assert "binario ffmpeg" not in nombres
    assert "modelo whisper" not in nombres
    # Los chequeos del dominio de la consola SI se conservan.
    assert {"Python", "Fuente", "Configuracion", "Credenciales"} <= nombres


def test_estado_filtrado_no_arrastra_error_ajeno(entorno, monkeypatch, sondas_sanas):
    """Un error clip-a-copy filtrado no contamina ni los chequeos ni el resumen global."""
    solo_clip = [
        doctor.Resultado("Python", doctor.Estado.OK, "Python 3.12.1"),
        doctor.Resultado("binario whisper-cli", doctor.Estado.ERROR, "no esta"),
        doctor.Resultado("binario ffmpeg", doctor.Estado.ERROR, "no esta"),
    ]
    monkeypatch.setattr(api_estado, "ejecutar_chequeos", lambda *a, **k: solo_clip)
    datos = _cliente().get("/api/estado").json()
    estados = {r["estado"] for r in datos["resultados"]}
    # Todo ok: el unico chequeo de metricas que queda (Python) + operativos sanos.
    assert estados == {"ok"}
    assert "problema" not in datos["resumen"]


def test_estado_real_offline_no_crashea(entorno, sondas_sanas):
    """Sin mock del doctor: el doctor real (escaneo de PATH, sin red) responde 200."""
    r = _cliente().get("/api/estado")
    assert r.status_code == 200
    assert "resultados" in r.json()


def test_estado_sondas_reales_no_crashean(entorno, doctor_mockeado):
    """Sin mock de sondas: cola/presupuesto contra el Postgres de pruebas, disco real,
    backups/S3 sin configurar. El doctor responde 200 con todos los ids operativos."""
    datos = _cliente().get("/api/estado").json()
    assert _IDS_MAQUINA | _IDS_INFRA <= set(_chequeos(datos))


# --------------------------------------------------------------------------- #
# Escenarios de la MAQUINA (cola, presupuesto, pausa, daemons)                  #
# --------------------------------------------------------------------------- #


def test_chequeo_cola_llena_avisa(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    lleno = {**_snapshot_cola_sano(), "activos": 20, "cola_llena": True}
    monkeypatch.setattr(api_actividad, "snapshot_cola", lambda: lleno)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:cola"]
    assert ch["estado"] == "aviso"
    assert "LLENA" in ch["detalle"]
    assert "20/20" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_cola_degrada_si_bd_cae(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    def boom():
        raise RuntimeError("bd caida")

    monkeypatch.setattr(api_actividad, "snapshot_cola", boom)
    r = _cliente().get("/api/estado")
    assert r.status_code == 200  # la sonda degrada, nunca 500
    ch = _chequeos(r.json())["maquina:cola"]
    assert ch["estado"] == "aviso"
    assert ch["siguiente_paso"]


def test_chequeo_presupuesto_agotado_es_error(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    est = {**_presupuesto_sano(), "nivel": presupuesto_ia.NIVEL_AGOTADO}
    monkeypatch.setattr(presupuesto_ia, "estado", lambda: est)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:presupuesto"]
    assert ch["estado"] == "error"
    assert "AGOTADO" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_presupuesto_solo_manual_avisa(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    est = {**_presupuesto_sano(), "nivel": presupuesto_ia.NIVEL_SOLO_MANUAL}
    monkeypatch.setattr(presupuesto_ia, "estado", lambda: est)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:presupuesto"]
    assert ch["estado"] == "aviso"
    assert "manual" in ch["detalle"].lower()


def test_chequeo_pausa_por_kill_switch(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    est = {**_presupuesto_sano(), "nivel": presupuesto_ia.NIVEL_PAUSADO, "pausada": True}
    monkeypatch.setattr(presupuesto_ia, "estado", lambda: est)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:pausa"]
    assert ch["estado"] == "aviso"
    assert "PAUSADA" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_daemons_atrasado_es_error(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
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


def test_chequeo_daemons_barrido_en_error_avisa(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    sonda = {"daemons": [{"daemon": "alertas", "estado": "error"}], "error": None}
    monkeypatch.setattr(api_sistema, "sonda_daemons", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["maquina:daemons"]
    assert ch["estado"] == "aviso"
    assert "alertas" in ch["detalle"]


# --------------------------------------------------------------------------- #
# Escenarios de INFRA (disco, backups, S3)                                      #
# --------------------------------------------------------------------------- #


def test_chequeo_disco_sobre_umbral_avisa(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    discos = [{"etiqueta": "Estado", "ruta": "/data", "usado": 91, "total": 100,
               "porcentaje": 91.0}]
    monkeypatch.setattr(api_sistema, "_discos", lambda: discos)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:disco"]
    assert ch["estado"] == "aviso"
    assert "Estado" in ch["detalle"] and "91" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_disco_critico_es_error(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    discos = [{"etiqueta": "Sistema", "ruta": "/", "usado": 97, "total": 100,
               "porcentaje": 97.0}]
    monkeypatch.setattr(api_sistema, "_discos", lambda: discos)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:disco"]
    assert ch["estado"] == "error"


def test_chequeo_backups_fallido_es_error(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    sonda = {"configurado": True, "estado": {"ok": False, "paso": "pg_dump"},
             "dumps": 3, "ultimo_dump": None, "atrasado": False, "error": None}
    monkeypatch.setattr(api_sistema, "sonda_backups", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:backups"]
    assert ch["estado"] == "error"
    assert "pg_dump" in ch["detalle"]
    assert ch["siguiente_paso"]


def test_chequeo_backups_atrasado_avisa(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    sonda = {"configurado": True, "estado": {"ok": True, "paso": ""},
             "dumps": 3, "ultimo_dump": None, "atrasado": True, "error": None}
    monkeypatch.setattr(api_sistema, "sonda_backups", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:backups"]
    assert ch["estado"] == "aviso"
    assert "26 h" in ch["detalle"]


def test_chequeo_s3_con_error_de_salud(entorno, doctor_mockeado, sondas_sanas, monkeypatch):
    sonda = {"configurado": True, "salud": "err",
             "error": "No se pudo conectar con el almacenamiento."}
    monkeypatch.setattr(api_sistema, "sonda_s3_salud", lambda: sonda)
    ch = _chequeos(_cliente().get("/api/estado").json())["infra:s3"]
    assert ch["estado"] == "error"
    assert ch["siguiente_paso"]
