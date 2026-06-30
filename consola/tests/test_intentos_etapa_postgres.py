"""Tests del CONTADOR de intentos por etapa (`intentos_etapa`) — la tabla que SOBREVIVE a la purga.

El contador vive en su propia tabla Postgres (no en `copy_pendiente`), así que estos tests usan
la fixture `pg` (Postgres de pruebas; se SALTAN si no hay). Cubren el UPSERT incremental, el tope,
el reset, el backoff (con `actualizado` controlado vía conexión directa para fijar la edad sin
depender del reloj) y el aislamiento entre sujetos/etapas. Un test final comprueba que la
migración crea la tabla.

La fixture `pg` se autodescubre vía `pytest_plugins` en conftest (`tests._postgres`).
"""

from __future__ import annotations

from keni_consola import db, db_intentos
from keni_consola.pipeline_contenido import _intentos
from keni_consola.tiempo import ahora_iso

VIEJO = "2020-01-01T00:00:00+00:00"


def _fijar_ts(sujeto: str, etapa: str, ts: str) -> None:
    """Fija `actualizado` de una fila existente (controla su edad para el backoff)."""
    con = db_intentos._conectar()
    try:
        con.execute(
            "UPDATE intentos_etapa SET actualizado = ? WHERE sujeto = ? AND etapa = ?",
            (ts, sujeto, etapa),
        )
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Capa db: UPSERT incremental + reset                                          #
# --------------------------------------------------------------------------- #


def test_anotar_intento_etapa_es_upsert_incremental(pg):
    """Anotar tres veces devuelve 1, 2, 3 y deja el contador en 3 (UPSERT atómico)."""
    assert db.intentos_etapa("pub-1", "redactar") == 0  # sin fila => 0
    assert db.anotar_intento_etapa("pub-1", "redactar") == 1
    assert db.anotar_intento_etapa("pub-1", "redactar") == 2
    assert db.anotar_intento_etapa("pub-1", "redactar") == 3
    assert db.intentos_etapa("pub-1", "redactar") == 3


def test_reset_intentos_etapa_borra_la_fila(pg):
    """`reset` borra el contador: vuelve a 0 y el timestamp desaparece. Idempotente."""
    db.anotar_intento_etapa("pub-1", "verificar")
    assert db.intentos_etapa("pub-1", "verificar") == 1
    assert db.intento_ts("pub-1", "verificar") is not None

    db.reset_intentos_etapa("pub-1", "verificar")
    assert db.intentos_etapa("pub-1", "verificar") == 0
    assert db.intento_ts("pub-1", "verificar") is None
    db.reset_intentos_etapa("pub-1", "verificar")  # idempotente: no casca


def test_intento_ts_none_sin_fila(pg):
    """`intento_ts` es None cuando no hay intentos anotados (base del backoff: sin espera)."""
    assert db.intento_ts("pub-x", "redactar") is None


def test_sujetos_y_etapas_distintos_no_se_pisan(pg):
    """La clave es `(sujeto, etapa)`: anotar uno no toca los demás."""
    db.anotar_intento_etapa("pub-1", "redactar")
    db.anotar_intento_etapa("pub-1", "redactar")
    db.anotar_intento_etapa("pub-1", "verificar")
    db.anotar_intento_etapa("pub-2", "redactar")

    assert db.intentos_etapa("pub-1", "redactar") == 2
    assert db.intentos_etapa("pub-1", "verificar") == 1
    assert db.intentos_etapa("pub-2", "redactar") == 1
    assert db.intentos_etapa("pub-2", "verificar") == 0


# --------------------------------------------------------------------------- #
# Helper `_intentos`: tope + backoff                                           #
# --------------------------------------------------------------------------- #


def test_tope_alcanzado_a_los_tres_intentos(pg):
    """`tope_alcanzado` es False hasta el 3.er intento (el `_MAX_INTENTOS_ETAPA` por defecto)."""
    sujeto, etapa = "cl-1", _intentos.ETAPA_VERIFICAR
    assert _intentos.tope_alcanzado(sujeto, etapa) is False
    _intentos.anotar(sujeto, etapa)
    _intentos.anotar(sujeto, etapa)
    assert _intentos.tope_alcanzado(sujeto, etapa) is False  # 2 < 3
    _intentos.anotar(sujeto, etapa)
    assert _intentos.tope_alcanzado(sujeto, etapa) is True  # 3 >= 3


def test_en_backoff_respeta_el_timestamp(pg):
    """Tras anotar, el intento reciente => en_backoff; con un TS viejo, la espera ya pasó."""
    sujeto, etapa = "pub-bo", _intentos.ETAPA_REDACTAR
    assert _intentos.en_backoff(sujeto, etapa) is False  # sin intentos: no espera

    _intentos.anotar(sujeto, etapa)
    _fijar_ts(sujeto, etapa, ahora_iso())
    assert _intentos.en_backoff(sujeto, etapa) is True  # último intento recién hecho: espera

    _fijar_ts(sujeto, etapa, VIEJO)
    assert _intentos.en_backoff(sujeto, etapa) is False  # intento muy viejo: la espera ya pasó


def test_reset_helper_limpia_tope_y_backoff(pg):
    """El `reset` del helper (éxito de la etapa) deja el contador a cero."""
    sujeto, etapa = "pub-r", _intentos.ETAPA_ILUSTRAR
    _intentos.anotar(sujeto, etapa)
    _intentos.anotar(sujeto, etapa)
    _intentos.anotar(sujeto, etapa)
    assert _intentos.tope_alcanzado(sujeto, etapa) is True

    _intentos.reset(sujeto, etapa)
    assert _intentos.intentos(sujeto, etapa) == 0
    assert _intentos.tope_alcanzado(sujeto, etapa) is False
    assert _intentos.en_backoff(sujeto, etapa) is False


# --------------------------------------------------------------------------- #
# Migración: la tabla existe en el esquema                                     #
# --------------------------------------------------------------------------- #


def test_migracion_crea_tabla_intentos_etapa(pg):
    """El arranque del esquema (on-demand) crea la tabla `intentos_etapa`."""
    db.intentos_etapa("seed", "verificar")  # primera conexión: crea/migra el esquema
    con = db_intentos._conectar()
    try:
        fila = con.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'intentos_etapa'"
        ).fetchone()
    finally:
        con.close()
    assert fila is not None
