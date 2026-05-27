"""Tests del backend POSTGRES de la capa operacional (`db.py` + `auth/` + `motor_db`).

SKIP si no hay Postgres (ver `_postgres.py`): un CI sin Postgres queda verde; donde lo haya
(service `postgres` + `KENI_TEST_DATABASE_URL`), corren de verdad. Cubren que las MISMAS
funciones publicas (las que en `test_db.py`/`test_auth.py` se prueban en SQLite) funcionan
identicas sobre Postgres: CRUD de tareas, comercial + serie temporal (INSERT OR IGNORE ->
ON CONFLICT), rota, y auth (crear usuario, duplicado UNIQUE neutro, login, sesiones).
"""

from __future__ import annotations

from keni_consola import auth, db, motor_db

# La fixture `pg` (activa Postgres o salta) se autodescubre via `pytest_plugins` en
# conftest (`tests._postgres`); no se importa aqui (evita falsos F811).


# --------------------------------------------------------------------------- #
# Esquema + seleccion de backend                                              #
# --------------------------------------------------------------------------- #


def test_backend_es_postgres(pg):
    assert motor_db.es_postgres() is True


def test_esquema_se_crea_on_demand(pg):
    # La primera operacion crea el esquema en Postgres y devuelve vacio.
    assert db.listar_tareas() == []


# --------------------------------------------------------------------------- #
# Tareas: CRUD (paridad con test_db.py sobre Postgres)                        #
# --------------------------------------------------------------------------- #


def test_crear_listar_obtener_tarea(pg):
    t = db.crear_tarea("proj1", "Una tarea", "detalle")
    assert t["id"] and t["estado"] == "pendiente"
    assert db.obtener_tarea(t["id"])["titulo"] == "Una tarea"
    assert len(db.listar_tareas()) == 1
    assert len(db.listar_tareas("proj1")) == 1
    assert db.listar_tareas("otro") == []


def test_actualizar_y_borrar_tarea(pg):
    t = db.crear_tarea("p", "Cambia")
    assert db.actualizar_estado_tarea(t["id"], "hecha")["estado"] == "hecha"
    assert db.actualizar_tarea(
        t["id"], {"responsable_id": "u1", "responsable_nombre": "ana", "enlace": "/x"}
    )["responsable_nombre"] == "ana"
    assert db.borrar_tarea(t["id"]) is True
    assert db.borrar_tarea(t["id"]) is False
    assert db.obtener_tarea(t["id"]) is None


def test_sql_parametrizado_no_inyectable(pg):
    malicioso = "'; DROP TABLE tareas; --"
    t = db.crear_tarea("p", malicioso)
    assert db.obtener_tarea(t["id"])["titulo"] == malicioso
    assert len(db.listar_tareas()) == 1


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
    ev = db.crear_evento_rota("Transmision", fecha="2026-03-01", hora="20:00")
    assert db.obtener_evento_rota(ev["id"])["titulo"] == "Transmision"
    turno = db.crear_turno_rota("2026-W09", ev["id"], miembro_nombre="luis", override=True)
    assert turno["override"] is True
    assert len(db.listar_turnos_rota("2026-W09")) == 1
    assert db.aprobar_semana_rota("2026-W09") == 1
    assert db.listar_turnos_rota("2026-W09")[0]["estado"] == db.ESTADO_ROTA_APROBADO
    # Borrar el evento arrastra sus turnos.
    assert db.borrar_evento_rota(ev["id"]) is True
    assert db.listar_turnos_rota("2026-W09") == []


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
