"""Tests del backend POSTGRES de la capa operacional (`db.py` + `auth/` + `motor_db`).

Tras la ADR 0004, Postgres es el unico backend; estos tests cubren la paridad funcional
basica (CRUD de tareas, comercial + serie temporal con ON CONFLICT, rota, auth, cola de
jobs concurrente) sobre el Postgres de pruebas, y las migraciones de columnas idempotentes
para bases creadas por versiones anteriores. SKIP si no hay Postgres (ver `_postgres.py`).
"""

from __future__ import annotations

from keni_consola import auth, db, db_comercial, motor_db

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


def test_snapshot_metricas_granulares_se_guardan_y_leen(pg):
    """Un snapshot con el desglose granular por pieza (likes/comentarios/.../formato) se
    persiste y se relee con esos campos; ausentes -> 0 defensivo (sin ceros falsos: la UI
    distingue 'sin dato' por interacciones/encontrado)."""
    pub = db.crear_publicacion_comercial("https://x/g", formato="reel")
    assert pub["formato"] == "reel"
    granulares = {
        "likes": 50,
        "comentarios": 7,
        "compartidos": 3,
        "guardados": 4,
        "video_views": 900,
        "tiempo_medio_vis_s": 12,
        "clics_enlace": 5,
        # `seguidores_netos_atribuidos` ausente a proposito -> debe leerse como 0.
    }
    assert db.registrar_snapshot_comercial(
        pub["id"], "2026-02-01T00:00:00", 60, 1000, visualizaciones=900, granulares=granulares
    ) is True
    ultimo = db.ultimo_snapshot_comercial(pub["id"])
    assert ultimo["likes"] == 50
    assert ultimo["comentarios"] == 7
    assert ultimo["compartidos"] == 3
    assert ultimo["guardados"] == 4
    assert ultimo["video_views"] == 900
    assert ultimo["tiempo_medio_vis_s"] == 12
    assert ultimo["clics_enlace"] == 5
    assert ultimo["seguidores_netos_atribuidos"] == 0  # ausente -> 0
    # Y siguen las base.
    assert ultimo["interacciones"] == 60 and ultimo["visualizaciones"] == 900
    serie = db.listar_snapshots_comerciales(pub["id"])
    assert len(serie) == 1 and serie[0]["likes"] == 50


def test_snapshot_sin_granulares_defaultea_a_cero(pg):
    """Compat: registrar un snapshot SIN `granulares` (firma legada) deja el desglose en 0."""
    pub = db.crear_publicacion_comercial("https://x/g2")
    assert pub["formato"] == ""  # formato no provisto -> vacio
    assert db.registrar_snapshot_comercial(pub["id"], "2026-02-02T00:00:00", 10, 100) is True
    ultimo = db.ultimo_snapshot_comercial(pub["id"])
    for campo in db_comercial._METRICAS_GRANULARES_SNAPSHOT:
        assert ultimo[campo] == 0


def test_migracion_columnas_comercial_granulares_bd_vieja(pg):
    """Una BD hosted con `comercial_snapshots`/`comercial_publicaciones` creadas ANTES de la
    ola de metricas granulares (sin likes/.../formato) debe ALTERarse al crear el esquema,
    de forma idempotente, sin perder los datos previos."""
    con = motor_db.conectar_cruda()
    con.execute("DROP TABLE IF EXISTS comercial_snapshots")
    con.execute("DROP TABLE IF EXISTS comercial_publicaciones")
    # Esquema legado: publicaciones sin `formato`; snapshots con solo las 3 metricas base.
    con.execute(
        "CREATE TABLE comercial_publicaciones (id TEXT PRIMARY KEY, url TEXT NOT NULL DEFAULT '', "
        "id_post_metricool TEXT NOT NULL DEFAULT '', titulo TEXT NOT NULL DEFAULT '', "
        "marca TEXT NOT NULL DEFAULT '', cliente TEXT NOT NULL DEFAULT '', "
        "campania TEXT NOT NULL DEFAULT '', red TEXT NOT NULL DEFAULT '', "
        "metrica_objetivo TEXT NOT NULL DEFAULT 'interacciones', objetivo INTEGER NOT NULL DEFAULT 0, "
        "estado TEXT NOT NULL DEFAULT 'activa', publicado TEXT NOT NULL DEFAULT '', "
        "notas TEXT NOT NULL DEFAULT '', aviso_en TEXT NOT NULL DEFAULT '', "
        "fecha_creacion TEXT NOT NULL DEFAULT '', fecha_actualizacion TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "CREATE TABLE comercial_snapshots (id TEXT PRIMARY KEY, publicacion_id TEXT NOT NULL, "
        "ts TEXT NOT NULL, interacciones INTEGER NOT NULL DEFAULT 0, "
        "visualizaciones INTEGER NOT NULL DEFAULT 0, alcance INTEGER NOT NULL DEFAULT 0)"
    )
    con.execute(
        "INSERT INTO comercial_publicaciones (id, titulo) VALUES ('viejo', 'Pieza legada')"
    )
    con.execute(
        "INSERT INTO comercial_snapshots (id, publicacion_id, ts, interacciones) "
        "VALUES ('s1', 'viejo', '2026-01-01T00:00:00', 42)"
    )
    con.commit()
    con.close()

    # La primera operacion `db.*` crea/migra el esquema (ALTER ... ADD COLUMN IF NOT EXISTS).
    legada = db.obtener_publicacion_comercial("viejo")
    assert legada is not None
    assert legada["titulo"] == "Pieza legada"
    assert legada["formato"] == ""  # columna nueva: DEFAULT '' para la fila legada
    # El snapshot legado conserva su valor y gana las columnas granulares en 0.
    ultimo = db.ultimo_snapshot_comercial("viejo")
    assert ultimo["interacciones"] == 42
    for campo in db_comercial._METRICAS_GRANULARES_SNAPSHOT:
        assert ultimo[campo] == 0
    # Idempotente: re-crear el esquema no falla (las columnas ya existen).
    db._esquemas_asegurados.clear()
    assert db.obtener_publicacion_comercial("viejo") is not None


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
    db.encolar_job("gen-2", "{}")  # UNIQUE(gen_id): la fila VIVA no se duplica ni se toca
    assert db.reclamar_job() is not None
    assert db.reclamar_job() is None


def test_cola_encolar_resucita_fila_terminada_pg(pg):
    """Re-encolar un gen_id con fila `terminado` la REVIVE a `pendiente` (spec nuevo).

    Antes el `ON CONFLICT DO NOTHING` devolvia el job viejo y el trabajo nuevo no corria
    jamas. La resurreccion SOLO aplica a filas terminadas; una viva queda intacta.
    """
    j1 = db.encolar_job("gen-r", '{"v": 1}')
    assert db.reclamar_job("w") is not None
    db.terminar_job(j1)
    assert db.reclamar_job() is None  # nada pendiente

    j2 = db.encolar_job("gen-r", '{"v": 2}', 5)
    assert j2 == j1  # misma fila (UNIQUE gen_id), revivida
    fila = db.reclamar_job("w2")
    assert fila is not None and fila["gen_id"] == "gen-r"
    assert fila["spec"] == '{"v": 2}'  # corre el trabajo NUEVO


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
