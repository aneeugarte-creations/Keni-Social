"""Tests del backend POSTGRES de la capa operacional (`db.py` + `auth/` + `motor_db`).

Tras la ADR 0004, Postgres es el unico backend; estos tests cubren la paridad funcional
basica (CRUD de tareas, comercial + serie temporal con ON CONFLICT, rota, auth, cola de
jobs concurrente) sobre el Postgres de pruebas, y las migraciones de columnas idempotentes
para bases creadas por versiones anteriores. SKIP si no hay Postgres (ver `_postgres.py`).
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
# Comercial + snapshots (INSERT OR IGNORE -> ON CONFLICT DO NOTHING)          #
# --------------------------------------------------------------------------- #


def test_comercial_crud_y_filtros(pg):
    pub = db.crear_publicacion_comercial(
        "https://x/1", titulo="P1", cliente="amx", campania="c1", objetivo=100
    )
    assert pub["objetivo"] == 100
    assert len(db.listar_publicaciones_comerciales(cliente="amx")) == 1
    assert db.listar_publicaciones_comerciales(cliente="otro") == []
    act = db.actualizar_publicacion_comercial(pub["id"], {"objetivo": 200, "estado": "pausada"})
    assert act["objetivo"] == 200 and act["estado"] == "pausada"
    assert db.borrar_publicacion_comercial(pub["id"]) is True


def test_snapshots_idempotentes_on_conflict(pg):
    pub = db.crear_publicacion_comercial("https://x/2")
    assert db.registrar_snapshot_comercial(pub["id"], "2026-01-01T00:00:00", 10, 100) is True
    # Mismo ts: el indice UNIQUE -> ON CONFLICT DO NOTHING -> no inserta (False).
    assert db.registrar_snapshot_comercial(pub["id"], "2026-01-01T00:00:00", 99, 999) is False
    serie = db.listar_snapshots_comerciales(pub["id"])
    assert len(serie) == 1 and serie[0]["interacciones"] == 10
    ultimo = db.ultimo_snapshot_comercial(pub["id"])
    assert ultimo["alcance"] == 100


def test_marcar_aviso_solo_primera_vez(pg):
    pub = db.crear_publicacion_comercial("https://x/3")
    db.marcar_aviso_comercial(pub["id"], "2026-01-02T10:00:00")
    db.marcar_aviso_comercial(pub["id"], "2026-09-09T10:00:00")  # idempotente: no re-marca
    assert db.obtener_publicacion_comercial(pub["id"])["aviso_en"] == "2026-01-02T10:00:00"


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
    # Usamos el shim retrocompat `franja="vespertino"` que siembra la franja Tarde de la
    # semana y traduce a `franja_id`. La aserción es por la franja Tarde resuelta en BD.
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
    """Regresion del 500 del calendario en hosted: un `rota_eventos` Postgres creado ANTES
    de la ola B (sin tipo_cobertura/prioridad/cambiado/actualizado) debe ALTERarse al crear
    el esquema, TAMBIEN en Postgres.

    Reproduce el estado real del hosted: la tabla PERSISTE entre despliegues, asi que
    `CREATE TABLE IF NOT EXISTS` no anade columnas. Antes la migracion estaba gateada a SQLite
    -> leer el calendario sobre Postgres daba `UndefinedColumn` -> 500. Ahora corre en ambos.
    """
    # Simula la tabla legada (esquema pre-ola-B) sobre Postgres.
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
    # El evento legado queda con los DEFAULT de la ola B (sigue cubierto, prioridad media).
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
    db.encolar_job("gen-2", "{}")  # UNIQUE(gen_id) -> ON CONFLICT DO NOTHING
    assert db.reclamar_job() is not None
    assert db.reclamar_job() is None


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
