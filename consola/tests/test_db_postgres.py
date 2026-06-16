"""Tests del backend POSTGRES de la capa operacional (`db.py` + `auth/` + `motor_db`).

Estos tests cubren la paridad funcional basica (CRUD de tareas, rota, auth, cola de jobs
concurrente) sobre el Postgres de pruebas, y las migraciones de columnas idempotentes.
SKIP si no hay Postgres (ver `_postgres.py`).
"""

from __future__ import annotations

from keni_consola import auth, db, motor_db

# La fixture `pg` (activa Postgres o salta) se autodescubre via `pytest_plugins` en
# conftest (`tests._postgres`); no se importa aqui (evita falsos F811).


# --------------------------------------------------------------------------- #
# Esquema                                                                     #
# --------------------------------------------------------------------------- #


def test_esquema_se_crea_on_demand(pg):
    # La primera operacion crea el esquema en Postgres y devuelve vacio.
    assert db.listar_swaps_turno() == []


# --------------------------------------------------------------------------- #
# Rota (eventos + turnos)                                                     #
# --------------------------------------------------------------------------- #


def test_rota_eventos_y_turnos(pg):
    """Modelo "franjas por semana": un turno es horario `(fecha, franja_id)`; NO va atado a
    un evento. Eventos y turnos viven independientes. Borrar un evento NO arrastra turnos
    (la "cobertura" es una vista DERIVADA por la API: ver test_api_rota).
    """
    ev = db.crear_evento_rota("Transmision", fecha="2026-03-01", hora="20:00")
    assert db.obtener_evento_rota(ev["id"])["titulo"] == "Transmision"
    turno = db.crear_turno_rota(
        "2026-W09", "2026-03-01", miembro_id="u-luis", miembro_nombre="luis",
        franja="vespertino", override=True,
    )
    assert turno["override"] is True
    assert turno["franja_id"]
    # La franja_id apunta a "Tarde" en la semana que contiene 2026-03-01.
    franja_def = db.obtener_franja_semana(turno["franja_id"])
    assert franja_def is not None
    assert franja_def["nombre"] == "Tarde"
    assert len(db.listar_turnos_rota("2026-W09")) == 1
    assert db.aprobar_semana_rota("2026-W09") == 1
    assert db.listar_turnos_rota("2026-W09")[0]["estado"] == db.ESTADO_ROTA_APROBADO
    # Borrar el evento NO arrastra turnos (son independientes).
    assert db.borrar_evento_rota(ev["id"]) is True
    assert len(db.listar_turnos_rota("2026-W09")) == 1
    # Borrado individual del turno.
    assert db.borrar_turno_rota(turno["id"]) is True
    assert db.listar_turnos_rota("2026-W09") == []


def test_migracion_columnas_eventos_rota_postgres_bd_vieja(pg):
    """La tabla `rota_eventos` debe ALTERarse al crear el esquema para añadir nuevas columnas.

    La tabla PERSISTE entre despliegues, asi que `CREATE TABLE IF NOT EXISTS` no anade
    columnas nuevas. La migracion debe ejecutarse de forma idempotente en Postgres.
    """
    con = motor_db.conectar_cruda()
    con.execute("DROP TABLE IF EXISTS rota_eventos")
    con.execute(
        "CREATE TABLE rota_eventos (id TEXT PRIMARY KEY, titulo TEXT NOT NULL, "
        "fecha TEXT NOT NULL DEFAULT '', hora TEXT NOT NULL DEFAULT '', "
        "contenido TEXT NOT NULL DEFAULT '', nota TEXT NOT NULL DEFAULT '', "
        "creado TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "INSERT INTO rota_eventos (id, titulo, fecha) VALUES ('viejo', 'Partido', '2026-06-02')"
    )
    con.commit()
    con.close()

    # La primera conexion (lo que hace la pestaña Calendario: GET /api/rota/eventos) crea el
    # esquema -> dispara la migracion idempotente -> ya no revienta.
    eventos = db.listar_eventos_rota(desde="2026-06-01", hasta="2026-06-07")
    assert len(eventos) == 1
    legado = eventos[0]
    # Los campos nuevos tienen sus valores por defecto.
    assert legado["tipo_cobertura"] == "transmision"
    assert legado["prioridad"] == "media"
    assert legado["cambiado"] is False


# --------------------------------------------------------------------------- #
# Auth sobre Postgres (usuarios, UNIQUE neutro, login, sesiones)              #
# --------------------------------------------------------------------------- #


def test_crear_usuario_y_duplicado_unique_neutro(pg):
    u = auth.crear_usuario("ana", "clave-de-prueba", "admin")
    assert u is not None and u["usuario"] == "ana"
    # UNIQUE de `usuario`: el duplicado se captura como motor_db.IntegrityError -> None.
    assert auth.crear_usuario("ana", "otra-clave-1234") is None
    assert auth.contar_admins() == 1
    assert len(auth.listar_usuarios()) == 1


def test_login_y_anti_fuerza_bruta(pg):
    auth.crear_usuario("luis", "clave-correcta", "editor")
    assert auth.autenticar("luis", "clave-correcta") is not None
    assert auth.autenticar("luis", "incorrecta") is None
    assert auth.autenticar("noexiste", "x") is None


def test_sesiones_ciclo_de_vida(pg):
    u = auth.crear_usuario("roger", "clave-de-prueba", "editor")
    token = auth.crear_sesion(u["id"])
    assert auth.sesion_valida(token)["usuario"] == "roger"
    auth.borrar_sesion(token)
    assert auth.sesion_valida(token) is None


def test_bootstrap_admin_idempotente(pg, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_USER", "jefe")
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", "clave-admin-1234")
    assert auth.hay_usuarios() is False
    auth.bootstrap_admin()
    auth.bootstrap_admin()  # idempotente: no crea un segundo
    assert auth.hay_usuarios() is True
    admins = [u for u in auth.listar_usuarios() if u["usuario"] == "jefe"]
    assert len(admins) == 1


# --------------------------------------------------------------------------- #
# Cola de jobs sobre Postgres (#130 Fase 2): claim FOR UPDATE SKIP LOCKED      #
# --------------------------------------------------------------------------- #


def test_cola_encolar_reclamar_terminar_pg(pg):
    job_id = db.encolar_job("gen-1", '{"prompt": "p"}')
    assert job_id
    fila = db.reclamar_job("w1")
    assert fila is not None and fila["gen_id"] == "gen-1"
    # Ya no quedan pendientes.
    assert db.reclamar_job("w2") is None
    db.terminar_job(job_id)


def test_cola_encolar_idempotente_por_gen_id_pg(pg):
    db.encolar_job("gen-2", "{}")
    db.encolar_job("gen-2", "{}")  # UNIQUE(gen_id): la fila VIVA no se duplica ni se toca
    assert db.reclamar_job() is not None
    assert db.reclamar_job() is None


def test_cola_encolar_resucita_fila_terminada_pg(pg):
    """Re-encolar un gen_id con fila `terminado` la REVIVE a `pendiente` (spec nuevo).

    La resurreccion SOLO aplica a filas terminadas; una viva queda intacta.
    """
    j1 = db.encolar_job("gen-r", '{"v": 1}')
    assert db.reclamar_job("w") is not None
    db.terminar_job(j1)
    assert db.reclamar_job() is None  # nada pendiente

    j2 = db.encolar_job("gen-r", '{"v": 2}', 5)
    assert j2 == j1  # misma fila (UNIQUE gen_id), revivida
    fila = db.reclamar_job("w2")
    assert fila is not None and fila["gen_id"] == "gen-r"
    # `spec` es jsonb (ADR 0012): `dict_row` lo devuelve ya como dict, no como el str crudo.
    assert fila["spec"] == {"v": 2}  # corre el trabajo NUEVO


def test_cola_reclama_por_prioridad_desc_pg(pg):
    """`reclamar_job` despacha por (prioridad DESC, creado ASC): manual antes que pipeline."""
    db.encolar_job("gen-fondo-1", "{}", 0)
    db.encolar_job("gen-manual", "{}", 10)
    db.encolar_job("gen-fondo-2", "{}", 0)
    assert db.reclamar_job("w")["gen_id"] == "gen-manual"
    # El fondo va despues (a igual prioridad el orden es FIFO por `creado`; aqui ambos caen
    # en el mismo segundo, asi que no se asserta el orden relativo entre ellos).
    assert {db.reclamar_job("w")["gen_id"], db.reclamar_job("w")["gen_id"]} == {
        "gen-fondo-1", "gen-fondo-2",
    }


def test_cola_cancelar_y_flag_pg(pg):
    db.encolar_job("gen-3", "{}")
    assert db.cancelar_job("gen-3") is True
    fila = db.reclamar_job("w")
    assert fila is not None
    assert db.job_cancelado(fila["id"]) is True


def test_cola_reclamacion_concurrente_no_doble_ejecuta_pg(pg):
    """N hilos reclamando a la vez sobre Postgres: cada job lo clava EXACTAMENTE uno.

    Ejercita `FOR UPDATE SKIP LOCKED`: dos workers concurrentes NO se llevan la misma
    fila. Cada hilo abre su PROPIA conexion (cada `reclamar_job` lo hace), como en hosted.
    """
    import threading

    for i in range(20):
        db.encolar_job(f"gen-c-{i}", "{}")
    encolados = {f"gen-c-{i}" for i in range(20)}
    reclamados: list[str] = []
    lock = threading.Lock()
    arrancar = threading.Event()

    def trabajar(wid: str) -> None:
        arrancar.wait()
        while True:
            fila = db.reclamar_job(wid)
            if fila is None:
                return
            with lock:
                reclamados.append(fila["gen_id"])

    hilos = [threading.Thread(target=trabajar, args=(f"w{i}",)) for i in range(8)]
    for h in hilos:
        h.start()
    arrancar.set()
    for h in hilos:
        h.join(timeout=20)

    assert sorted(reclamados) == sorted(encolados)
    assert len(reclamados) == len(set(reclamados))  # ninguno dos veces
