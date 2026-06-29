"""Tests de RETENCIÓN/purga de las tablas que crecían sin límite: `jobs` y `generaciones_indice`.

Ambas tablas viven en Postgres, así que estos tests usan el fixture `entorno` (Postgres de
pruebas; se SALTAN si no hay). Las filas se insertan con `creado`/`actualizado` controlados (vía
conexión directa) para fijar su edad sin depender del reloj. La poda del índice es INDEPENDIENTE
del fichero YAML: aquí no se crea ningún YAML y aun así borra las filas huérfanas viejas.
"""

from __future__ import annotations

from keni_consola import db_jobs, generaciones, limpiador_generaciones
from keni_consola.tiempo import ahora_iso

# Edades de control: "viejo" (muy anterior a cualquier retención) y "reciente" (ahora mismo).
VIEJO = "2020-01-01T00:00:00"
RECIENTE = ahora_iso()


def _insertar_job(*, id: str, gen_id: str, estado: str, creado: str) -> None:
    con = db_jobs._conectar()
    try:
        con.execute(
            "INSERT INTO jobs (id, gen_id, spec, estado, creado) VALUES (?, ?, ?, ?, ?)",
            (id, gen_id, "{}", estado, creado),
        )
        con.commit()
    finally:
        con.close()


def _insertar_indice(*, gen_id: str, actualizado: str) -> None:
    con = db_jobs._conectar()
    try:
        con.execute(
            "INSERT INTO generaciones_indice (gen_id, actualizado) VALUES (?, ?)",
            (gen_id, actualizado),
        )
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Retención de jobs terminados                                                 #
# --------------------------------------------------------------------------- #


def test_purga_jobs_terminados_viejos_conserva_vivos_y_recientes(entorno):
    """Borra solo `terminado` antiguos; un `terminado` reciente o un job VIVO nunca se tocan."""
    _insertar_job(id="t-viejo", gen_id="g1", estado=db_jobs.JOB_TERMINADO, creado=VIEJO)
    _insertar_job(id="t-nuevo", gen_id="g2", estado=db_jobs.JOB_TERMINADO, creado=RECIENTE)
    _insertar_job(id="pend-viejo", gen_id="g3", estado=db_jobs.JOB_PENDIENTE, creado=VIEJO)
    _insertar_job(id="recl-viejo", gen_id="g4", estado=db_jobs.JOB_RECLAMADO, creado=VIEJO)

    borrados = db_jobs.purgar_jobs_terminados()  # default 7 días

    assert borrados == 1
    por_estado = db_jobs.contar_jobs_por_estado()
    assert por_estado.get(db_jobs.JOB_TERMINADO) == 1  # solo sobrevive el terminado reciente
    assert por_estado.get(db_jobs.JOB_PENDIENTE) == 1
    assert por_estado.get(db_jobs.JOB_RECLAMADO) == 1


def test_purga_jobs_respeta_la_ventana_dias(entorno):
    """`dias` muy grande NO borra nada (todo cae dentro de la ventana de retención)."""
    _insertar_job(id="t-viejo", gen_id="g1", estado=db_jobs.JOB_TERMINADO, creado=VIEJO)
    assert db_jobs.purgar_jobs_terminados(dias=100000) == 0
    assert db_jobs.contar_jobs_por_estado().get(db_jobs.JOB_TERMINADO) == 1


def test_purga_jobs_vacia_no_rompe(entorno):
    assert db_jobs.purgar_jobs_terminados() == 0


# --------------------------------------------------------------------------- #
# Poda por edad del índice de generaciones (huérfanas, sin tocar el fichero)   #
# --------------------------------------------------------------------------- #


def test_poda_indice_borra_viejas_fuera_del_piso(entorno):
    """Filas viejas y fuera del piso de las N más recientes se borran (huérfanas), aunque NO haya YAML."""
    _insertar_indice(gen_id="r-a", actualizado="2026-06-29T04:00:00")
    _insertar_indice(gen_id="r-b", actualizado="2026-06-29T03:00:00")
    _insertar_indice(gen_id="v-a", actualizado="2020-01-03T00:00:00")
    _insertar_indice(gen_id="v-b", actualizado="2020-01-02T00:00:00")
    _insertar_indice(gen_id="v-c", actualizado="2020-01-01T00:00:00")

    borradas = db_jobs.purgar_indice_generaciones("2026-01-01T00:00:00", 2)

    assert borradas == 3  # las tres viejas; el piso protege las 2 recientes
    assert db_jobs.contar_indice_generaciones() == 2


def test_poda_indice_el_piso_protege_lo_viejo(entorno):
    """El piso (`maximo`) conserva SIEMPRE las N más recientes aunque sean viejas."""
    _insertar_indice(gen_id="v-a", actualizado="2020-01-03T00:00:00")
    _insertar_indice(gen_id="v-b", actualizado="2020-01-02T00:00:00")
    _insertar_indice(gen_id="v-c", actualizado="2020-01-01T00:00:00")

    # corte futuro: las tres son "viejas", pero el piso de 2 deja solo v-c como candidata.
    borradas = db_jobs.purgar_indice_generaciones("2030-01-01T00:00:00", 2)

    assert borradas == 1
    assert db_jobs.contar_indice_generaciones() == 2


def test_poda_indice_respeta_filas_sin_fecha(entorno):
    """Una fila con `actualizado` vacío no tiene evidencia de edad: nunca se borra."""
    _insertar_indice(gen_id="sin-fecha", actualizado="")
    assert db_jobs.purgar_indice_generaciones("2030-01-01T00:00:00", 0) == 0
    assert db_jobs.contar_indice_generaciones() == 1


def test_poda_indice_wrapper_resuelve_politica_del_entorno(entorno, monkeypatch):
    """El wrapper de `generaciones` resuelve dias/maximo del entorno y delega en la capa DB."""
    monkeypatch.setenv("KENI_GENERACIONES_RETENCION_DIAS", "30")
    monkeypatch.setenv("KENI_GENERACIONES_RETENCION_MAX", "1")
    _insertar_indice(gen_id="reciente", actualizado=RECIENTE)
    _insertar_indice(gen_id="vieja", actualizado=VIEJO)

    borradas = generaciones.purgar_indice_generaciones()

    assert borradas == 1  # la vieja (fuera de 30 d y del piso de 1); la reciente se conserva
    assert db_jobs.contar_indice_generaciones() == 1


# --------------------------------------------------------------------------- #
# Cableado en el barrido del limpiador                                         #
# --------------------------------------------------------------------------- #


def test_barrido_purga_jobs_y_indice(entorno, monkeypatch):
    """`ejecutar_barrido` purga jobs terminados antiguos Y filas huérfanas del índice viejas."""
    monkeypatch.setenv("KENI_GENERACIONES_RETENCION_DIAS", "30")
    monkeypatch.setenv("KENI_GENERACIONES_RETENCION_MAX", "0")  # sin piso: solo manda la edad
    _insertar_job(id="t-viejo", gen_id="g1", estado=db_jobs.JOB_TERMINADO, creado=VIEJO)
    _insertar_indice(gen_id="huerfana-vieja", actualizado=VIEJO)
    _insertar_indice(gen_id="reciente", actualizado=RECIENTE)

    limpiador_generaciones.ejecutar_barrido()

    assert db_jobs.contar_jobs_por_estado().get(db_jobs.JOB_TERMINADO, 0) == 0
    assert db_jobs.contar_indice_generaciones() == 1  # solo sobrevive la reciente
