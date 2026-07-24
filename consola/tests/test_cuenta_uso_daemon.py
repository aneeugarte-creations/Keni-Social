"""Tests del muestreo de fondo del uso de la cuenta de Claude.

Dos capas:
  - PURAS (offline): el mapeo de medidores (`_extraer_medidores`) y la línea base del consumo
    de hoy (`db_cuenta_uso._baseline_dia`).
  - CON Postgres (`entorno`): persistencia singleton (`guardar`/`leer`), el rodado de la base
    del día y el barrido del daemon (muestrea `claude -p /usage` parcheado y persiste).
"""

from __future__ import annotations

from keni_consola import cuenta_uso_daemon as dae
from keni_consola import repos
from keni_consola.db import cuenta_uso as db_cuenta_uso

# Salida típica de `cuenta_claude.uso()` con medidor completo (tras parsear `/usage`).
_USO_COMPLETO = {
    "disponible": True,
    "mensaje": "You are currently using your subscription",
    "medidores": [
        {"etiqueta": "Current session", "pct": 26, "reset": "Jun 15 at 7:39pm (UTC)",
         "reset_iso": "2026-06-15T19:39:00Z"},
        {"etiqueta": "Current week (all models)", "pct": 67, "reset": "Jul 1, 7am (UTC)",
         "reset_iso": "2026-07-01T07:00:00Z"},
    ],
    "actualizado": 1750000000.0,
    "cacheado": False,
}

# Lectura sin medidor (cuenta desconectada / solo frase).
_USO_SIN_MEDIDOR = {"disponible": False, "mensaje": "", "medidores": [], "crudo": ""}


# --- PURO: mapeo de medidores --------------------------------------------- #


def test_extraer_medidores_mapea_los_dos():
    campos = dae._extraer_medidores(_USO_COMPLETO)
    assert campos["conectada"] is True
    assert campos["sesion_5h_pct"] == 26
    assert campos["semana_pct"] == 67
    assert campos["reset_semana_iso"] == "2026-07-01T07:00:00Z"
    assert campos["reset_semana_txt"] == "Jul 1, 7am (UTC)"
    assert campos["reset_sesion_iso"] == "2026-06-15T19:39:00Z"  # reset de la 5h, para el burn rate
    assert campos["actualizado_ts"] == 1750000000.0


def test_extraer_medidores_sin_medidor_es_desconectada():
    campos = dae._extraer_medidores(_USO_SIN_MEDIDOR)
    assert campos["conectada"] is False
    assert campos["semana_pct"] is None
    assert campos["sesion_5h_pct"] is None
    assert campos["reset_sesion_iso"] == ""
    # Sin `actualizado` en la lectura, se sella el instante actual (float epoch).
    assert isinstance(campos["actualizado_ts"], float)


# --- PURO: línea base del consumo de hoy ---------------------------------- #


def test_baseline_dia_sin_previa_usa_lectura_actual():
    base, dia = db_cuenta_uso._baseline_dia(None, "2026-06-14", 67)
    assert base == 67 and dia == "2026-06-14"


def test_baseline_dia_mismo_dia_conserva_base():
    previa = {"dia_utc": "2026-06-14", "semana_pct_inicio_dia": 60, "semana_pct": 67}
    base, dia = db_cuenta_uso._baseline_dia(previa, "2026-06-14", 70)
    assert base == 60 and dia == "2026-06-14"


def test_baseline_dia_nuevo_dia_hereda_cierre_anterior():
    # Al cambiar de día, la base es el último `semana_pct` del día anterior (≈ valor de medianoche).
    previa = {"dia_utc": "2026-06-14", "semana_pct_inicio_dia": 60, "semana_pct": 67}
    base, dia = db_cuenta_uso._baseline_dia(previa, "2026-06-15", 68)
    assert base == 67 and dia == "2026-06-15"


def test_baseline_dia_reset_semanal_baja_la_base():
    # La ventana semanal reseteó a mitad del día (el % cayó): la base baja para que el consumo
    # de hoy no sea negativo.
    previa = {"dia_utc": "2026-06-14", "semana_pct_inicio_dia": 60, "semana_pct": 67}
    base, dia = db_cuenta_uso._baseline_dia(previa, "2026-06-14", 3)
    assert base == 3 and dia == "2026-06-14"


# --- CON Postgres: persistencia + barrido --------------------------------- #


def test_guardar_y_leer_singleton(entorno):
    assert repos.leer_uso_cuenta() is None  # cold start
    repos.guardar_uso_cuenta(
        conectada=True, semana_pct=67, sesion_5h_pct=26,
        reset_semana_iso="2026-07-01T07:00:00Z", reset_semana_txt="Jul 1, 7am (UTC)",
        actualizado_ts=1750000000.0, dia_utc="2026-06-14",
    )
    fila = repos.leer_uso_cuenta()
    assert fila is not None
    assert fila["semana_pct"] == 67 and fila["sesion_5h_pct"] == 26
    assert fila["semana_pct_inicio_dia"] == 67  # cold start: base = lectura actual
    # Singleton: una segunda escritura ACTUALIZA la misma fila (no inserta otra).
    repos.guardar_uso_cuenta(
        conectada=True, semana_pct=70, sesion_5h_pct=30,
        actualizado_ts=1750001000.0, dia_utc="2026-06-14",
    )
    fila = repos.leer_uso_cuenta()
    assert fila["semana_pct"] == 70
    assert fila["semana_pct_inicio_dia"] == 67  # mismo día: base intacta


def test_consumo_de_hoy_rueda_la_base_al_cambiar_de_dia(entorno):
    repos.guardar_uso_cuenta(conectada=True, semana_pct=67, sesion_5h_pct=26, dia_utc="2026-06-14")
    # Día nuevo: la base hereda el cierre de ayer (67); el consumo de hoy = 71 - 67 = 4.
    repos.guardar_uso_cuenta(conectada=True, semana_pct=71, sesion_5h_pct=10, dia_utc="2026-06-15")
    fila = repos.leer_uso_cuenta()
    assert fila["dia_utc"] == "2026-06-15"
    assert fila["semana_pct_inicio_dia"] == 67
    assert fila["semana_pct"] - fila["semana_pct_inicio_dia"] == 4


def test_guardar_y_leer_por_cuenta(entorno):
    # Una fila POR CUENTA: A y B no se pisan; `leer_uso_cuentas` las devuelve juntas.
    repos.guardar_uso_cuenta(cuenta="a", conectada=True, semana_pct=10, sesion_5h_pct=1,
                             dia_utc="2026-06-14")
    repos.guardar_uso_cuenta(cuenta="b", conectada=True, semana_pct=80, sesion_5h_pct=5,
                             dia_utc="2026-06-14")
    a = repos.leer_uso_cuenta("a")
    b = repos.leer_uso_cuenta("b")
    assert a["semana_pct"] == 10 and a["cuenta"] == "a"
    assert b["semana_pct"] == 80 and b["cuenta"] == "b"
    ambas = repos.leer_uso_cuentas()
    assert ambas["a"]["semana_pct"] == 10 and ambas["b"]["semana_pct"] == 80


def test_leer_uso_cuentas_cold_start(entorno):
    # Sin muestreo aún: ambas cuentas vienen como None (claves siempre presentes).
    assert repos.leer_uso_cuentas() == {"a": None, "b": None}


def test_barrido_muestrea_ambas_cuentas(entorno, monkeypatch):
    # El barrido lee `cuenta_claude.uso(cuenta)` por cada cuenta y persiste cada snapshot.
    # Best-effort: la cuenta B no está logueada (lectura sin medidor) -> fila desconectada, no rompe.
    lecturas = {"a": _USO_COMPLETO, "b": _USO_SIN_MEDIDOR}
    monkeypatch.setattr(dae.cuenta_claude, "uso", lambda cuenta="a": lecturas[cuenta])
    filas = dae.ejecutar_barrido()
    assert set(filas) == {"a", "b"}
    assert filas["a"]["conectada"] == 1 and filas["a"]["semana_pct"] == 67
    assert filas["b"]["conectada"] == 0  # B sin medidor -> desconectada (best-effort)
    a = repos.leer_uso_cuenta("a")
    b = repos.leer_uso_cuenta("b")
    assert a["semana_pct"] == 67
    assert a["reset_semana_iso"] == "2026-07-01T07:00:00Z"
    assert b is not None and b["conectada"] == 0 and b["semana_pct"] is None


def test_resumen_barrido():
    filas = {"a": {"conectada": 1, "semana_pct": 67}, "b": {"conectada": 0}}
    assert dae._resumen_barrido(filas) == "a: semana 67% · b: sin medidor"
    assert dae._resumen_barrido({}) == "sin cuentas"


# --------------------------------------------------------------------------- #
# Aviso de CADUCIDAD de la credencial (el otro estado que decide si genera)    #
# --------------------------------------------------------------------------- #


def _caducidad(*, caducada: bool, horas: float, refresh: bool = True) -> dict:
    return {
        "conocida": True, "caducada": caducada, "expira_en_iso": "2026-07-24T17:16:22+00:00",
        "segundos_restantes": horas * 3600.0, "tiene_refresh": refresh,
    }


def _capturar_emisiones(monkeypatch) -> list[tuple[str, dict, str]]:
    """Sustituye el bus de eventos y el aviso in-app; devuelve la lista de emisiones."""
    emitidos: list[tuple[str, dict, str]] = []

    def falso_emitir(tipo, datos, *, clave_idempotencia="", **_resto):
        emitidos.append((tipo, datos, clave_idempotencia))
        return True

    monkeypatch.setattr(dae.eventos, "emitir", falso_emitir)
    monkeypatch.setattr(
        dae.notificaciones, "tras_credencial_por_caducar",
        lambda *a, **k: None,
    )
    return emitidos


def test_avisa_cuando_la_credencial_ya_caduco(entorno, monkeypatch):
    """Credencial muerta: avisa SIEMPRE, sea cual sea la antelación configurada."""
    monkeypatch.setenv("KENI_CUENTA_AVISO_CADUCIDAD_H", "0")  # sin aviso previo
    monkeypatch.setattr(dae.cuenta_claude, "caducidad", lambda c: _caducidad(caducada=True, horas=-2, refresh=False))
    emitidos = _capturar_emisiones(monkeypatch)

    assert dae._avisar_credencial("a", "2026-07-24") is True
    tipo, datos, clave = emitidos[0]
    assert tipo == "cuenta.credencial_expira"
    assert datos["caducada"] is True and datos["tiene_refresh"] is False
    assert clave == "cuenta.credencial_expira:a:caducada:2026-07-24"


def test_avisa_antes_de_caducar_dentro_de_la_antelacion(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CUENTA_AVISO_CADUCIDAD_H", "2")
    monkeypatch.setattr(dae.cuenta_claude, "caducidad", lambda c: _caducidad(caducada=False, horas=1.5))
    emitidos = _capturar_emisiones(monkeypatch)

    assert dae._avisar_credencial("a", "2026-07-24") is True
    _tipo, datos, clave = emitidos[0]
    assert datos["caducada"] is False and datos["horas_restantes"] == 1.5
    # Clave distinta a la de «caducada»: el paso de aviso previo a muerta vuelve a avisar.
    assert clave == "cuenta.credencial_expira:a:aviso:2026-07-24"


def test_no_avisa_con_la_credencial_holgada_ni_sin_lectura(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CUENTA_AVISO_CADUCIDAD_H", "2")
    emitidos = _capturar_emisiones(monkeypatch)

    monkeypatch.setattr(dae.cuenta_claude, "caducidad", lambda c: _caducidad(caducada=False, horas=7))
    assert dae._avisar_credencial("a", "2026-07-24") is False

    # Sin lectura de la credencial no se afirma nada (no se avisa en falso).
    monkeypatch.setattr(dae.cuenta_claude, "caducidad", lambda c: {"conocida": False})
    assert dae._avisar_credencial("a", "2026-07-24") is False
    assert emitidos == []
