"""Integridad del esquema endurecido (ADR 0012): FKs, CHECK, version optimista, tipos jsonb.

Backend Postgres real (fixture `pg`, ver `tests/_postgres.py`; SKIP si no hay Postgres de
pruebas). El journal de migraciones se trunca entre tests, asi que cada test parte de un
esquema recien (re)migrado: ejercita TAMBIEN la idempotencia de las migraciones de integridad.
"""
from __future__ import annotations

import pytest

from keni_consola import db, motor_db
from keni_consola._db_core.migraciones_integridad import _FKS, _migrar_fks_hub

# La fixture `pg` se autodescubre via `pytest_plugins` en conftest (`tests._postgres`).


def _cruda():
    return motor_db.conectar_cruda()


# --------------------------------------------------------------------------- #
# Bloque 1: FOREIGN KEYS (cascada + rechazo de sueltos + limpieza previa)     #
# --------------------------------------------------------------------------- #


def test_fks_creadas(pg):
    db.listar_swaps_turno()  # asegura el esquema
    con = _cruda()
    try:
        nombres = {
            f["conname"]
            for f in con.execute(
                "SELECT conname FROM pg_constraint WHERE contype = 'f'"
            ).fetchall()
        }
    finally:
        con.close()
    for tabla, columna, *_ in _FKS:
        assert f"fk_{tabla}_{columna}" in nombres


def test_fk_cascade_borra_hijas(pg):
    """Borrar un `contenido` arrastra sus filas por plataforma (y, transitivamente, sus hijas)."""
    c = db.crear_publicacion(titulo="t")
    p = db.crear_pieza_fila(publicacion_id=c["id"], red="x")
    db.crear_comentario(publicacion_id=c["id"], texto="hola", autor={"id": "u", "usuario": "u"})
    db.registrar_copy_version(
        pieza_id=p["id"], publicacion_id=c["id"], copy="v1",
        autor={"id": "u", "usuario": "u"},
    )
    assert db.borrar_publicacion(c["id"]) is True
    assert db.obtener_pieza_fila(p["id"]) is None
    assert db.listar_comentarios(c["id"]) == []
    assert db.listar_copy_versiones(p["id"]) == []


def test_fk_rechaza_plataforma_suelta(pg):
    db.listar_swaps_turno()  # esquema
    con = _cruda()
    try:
        with pytest.raises(motor_db.IntegrityError):
            con.execute(
                "INSERT INTO pieza (id, publicacion_id, creado, actualizado) "
                "VALUES (?, ?, ?, ?)",
                ("phuerf", "no-existe", "x", "x"),
            )
            con.commit()
    finally:
        con.close()


def test_fks_idempotentes_y_limpian_sueltos(pg):
    """Re-aplicar la migracion de FKs sobre una BD con SUELTOS los borra y recrea la FK."""
    c = db.crear_publicacion(titulo="t")
    con = _cruda()
    try:
        # Suelta la FK y mete sueltos (id inexistente + sentinel '').
        con.execute("ALTER TABLE pieza DROP CONSTRAINT fk_pieza_publicacion_id")
        con.execute(
            "INSERT INTO pieza (id, publicacion_id, creado, actualizado) "
            "VALUES ('o1', 'ghost', 'x', 'x')"
        )
        con.execute(
            "INSERT INTO pieza (id, publicacion_id, creado, actualizado) "
            "VALUES ('o2', '', 'x', 'x')"
        )
        con.commit()
        # Re-aplica la migracion: limpia sueltos y recrea la FK.
        _migrar_fks_hub(con)
        con.commit()
        n = con.execute(
            "SELECT count(*) AS n FROM pieza WHERE id IN ('o1', 'o2')"
        ).fetchone()["n"]
        assert n == 0
        # La fila legitima sobrevive; la FK vuelve a existir.
        existe = con.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = 'fk_pieza_publicacion_id'"
        ).fetchone()
        assert existe is not None
    finally:
        con.close()
    assert db.obtener_publicacion(c["id"]) is not None


# --------------------------------------------------------------------------- #
# Bloque 2: CHECK de allowlist en campos de estado                              #
# --------------------------------------------------------------------------- #


def test_checks_creados(pg):
    db.listar_swaps_turno()
    con = _cruda()
    try:
        nombres = {
            f["conname"]
            for f in con.execute(
                "SELECT conname FROM pg_constraint WHERE contype = 'c'"
            ).fetchall()
        }
    finally:
        con.close()
    for ck in (
        "ck_publicacion_estado",
        "ck_pieza_estado",
        "ck_pieza_aprobaciones_decision",
        "ck_usuarios_rol",
        "ck_publicacion_verificacion_fuente",
    ):
        assert ck in nombres


def test_check_rechaza_estado_invalido(pg):
    c = db.crear_publicacion(titulo="t")
    con = _cruda()
    try:
        with pytest.raises(motor_db.IntegrityError):
            con.execute("UPDATE publicacion SET estado = 'bogus' WHERE id = ?", (c["id"],))
            con.commit()
    finally:
        con.close()


def test_check_verificacion_fuente_acepta_vacio_y_canonicos(pg):
    c = db.crear_publicacion(titulo="t")
    con = _cruda()
    try:
        for v in ("", "en_curso", "verificado", "requiere_humano", "rechazado", "caducada", "saltada"):
            con.execute("UPDATE publicacion SET verificacion_fuente = ? WHERE id = ?", (v, c["id"]))
            con.commit()
        with pytest.raises(motor_db.IntegrityError):
            con.execute("UPDATE publicacion SET verificacion_fuente = 'inventado' WHERE id = ?", (c["id"],))
            con.commit()
    finally:
        con.close()


def test_migracion_renombra_verificacion_fuente_legada(pg):
    """La migración 0029 RENOMBRA los valores legados de `verificacion_fuente` a la nomenclatura de
    3 niveles (`no_verificado`->`verificado`, `problema`->`requiere_humano`), NO los normaliza a ""."""
    from keni_consola._db_core.migraciones_integridad import _migrar_checks_dominio

    verificada = db.crear_publicacion(titulo="legado-nv")
    a_mesa = db.crear_publicacion(titulo="legado-prob")
    con = _cruda()
    try:
        # Escribe valores LEGADOS saltando el CHECK actual (que ya no los admite).
        con.execute("ALTER TABLE publicacion DROP CONSTRAINT IF EXISTS ck_publicacion_verificacion_fuente")
        con.execute("UPDATE publicacion SET verificacion_fuente = 'no_verificado' WHERE id = ?", (verificada["id"],))
        con.execute("UPDATE publicacion SET verificacion_fuente = 'problema' WHERE id = ?", (a_mesa["id"],))
        con.commit()
        _migrar_checks_dominio(con)
        con.commit()
        a = con.execute("SELECT verificacion_fuente FROM publicacion WHERE id = ?", (verificada["id"],)).fetchone()
        b = con.execute("SELECT verificacion_fuente FROM publicacion WHERE id = ?", (a_mesa["id"],)).fetchone()
        assert a["verificacion_fuente"] == "verificado"
        assert b["verificacion_fuente"] == "requiere_humano"
    finally:
        con.close()


def test_check_dropa_el_fosil_ck_contenido_de_la_tabla_renombrada(pg):
    """Regresion (deploy hosted): `publicacion` se llamo `contenido`; al renombrar la tabla,
    Postgres conserva el NOMBRE viejo de sus CHECK (`ck_contenido_verificacion_fuente`). La
    migracion calculaba el nombre como `ck_{tabla}_{columna}` (`ck_publicacion_*`), asi que su
    DROP no tocaba el fosil: este, con la allowlist VIEJA, rechazaba el valor renombrado
    `requiere_humano` y tumbaba el deploy con CheckViolation. La migracion debe DROPear tambien
    el fosil `ck_contenido_<col>` antes de renombrar los valores legados."""
    from keni_consola._db_core.migraciones_integridad import _migrar_checks_dominio

    c = db.crear_publicacion(titulo="fosil")
    con = _cruda()
    try:
        # Reproduce hosted: NINGUN constraint con el nombre nuevo y SI el fosil `ck_contenido_*`
        # con la allowlist VIEJA (sin `requiere_humano`), con una fila en un valor legado que el
        # renombre mandara a `requiere_humano`.
        con.execute("ALTER TABLE publicacion DROP CONSTRAINT IF EXISTS ck_publicacion_verificacion_fuente")
        con.execute("UPDATE publicacion SET verificacion_fuente = 'problema' WHERE id = ?", (c["id"],))
        con.execute(
            "ALTER TABLE publicacion ADD CONSTRAINT ck_contenido_verificacion_fuente "
            "CHECK (verificacion_fuente IN ('', 'no_verificado', 'problema', 'verificado'))"
        )
        con.commit()
        # NO debe lanzar: DROP del fosil -> renombra 'problema'->'requiere_humano' -> ADD del nuevo.
        _migrar_checks_dominio(con)
        con.commit()
        v = con.execute(
            "SELECT verificacion_fuente FROM publicacion WHERE id = ?", (c["id"],)
        ).fetchone()["verificacion_fuente"]
        assert v == "requiere_humano"
    finally:
        con.close()


def test_checks_normalizan_valores_invalidos_preexistentes(pg):
    """Re-aplicar la migracion sobre datos sucios normaliza al default antes del CHECK."""
    from keni_consola._db_core.migraciones_integridad import _migrar_checks_dominio

    c = db.crear_publicacion(titulo="t")
    con = _cruda()
    try:
        con.execute("ALTER TABLE publicacion DROP CONSTRAINT ck_publicacion_estado")
        con.execute("UPDATE publicacion SET estado = 'zzz' WHERE id = ?", (c["id"],))
        con.commit()
        _migrar_checks_dominio(con)
        con.commit()
        v = con.execute("SELECT estado FROM publicacion WHERE id = ?", (c["id"],)).fetchone()["estado"]
        assert v == "pendiente"
    finally:
        con.close()


def test_check_normaliza_aunque_el_check_viejo_prohiba_el_default(pg):
    """Regresion (colapso 2026-06): el CHECK heredado prohibia 'borrador' (el valor NUEVO de
    normalizacion de plataforma). La migracion debe DROPear el CHECK viejo ANTES de normalizar;
    si no, el UPDATE que escribe 'borrador' falla con CheckViolation sobre el constraint viejo
    (lo que tumbaba el deploy en hosted)."""
    from keni_consola._db_core.migraciones_integridad import _migrar_checks_dominio

    c = db.crear_publicacion(titulo="t")
    p = db.crear_pieza_fila(publicacion_id=c["id"], red="x")  # nace 'borrador' (valido hoy)
    con = _cruda()
    try:
        # Reproduce el estado HEREDADO en hosted: el CHECK con la allowlist VIEJA (sin 'borrador',
        # con el retirado 'aprobado') y una fila en ese estado retirado que la allowlist permitia.
        # Orden: quita el CHECK actual, pon la fila en 'aprobado', y SOLO entonces aplica el CHECK
        # viejo (que prohibe el 'borrador' con el que nacio la fila).
        con.execute("ALTER TABLE pieza DROP CONSTRAINT ck_pieza_estado")
        con.execute("UPDATE pieza SET estado = 'aprobado' WHERE id = ?", (p["id"],))
        con.execute(
            "ALTER TABLE pieza ADD CONSTRAINT ck_pieza_estado "
            "CHECK (estado IN ('aprobado', 'en_revision', 'programado', 'publicado'))"
        )
        con.commit()
        # NO debe lanzar: DROP del viejo -> normaliza 'aprobado'->'borrador' -> ADD del nuevo.
        _migrar_checks_dominio(con)
        con.commit()
        v = con.execute(
            "SELECT estado FROM pieza WHERE id = ?", (p["id"],)
        ).fetchone()["estado"]
        assert v == "borrador"
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Bloque 3: CONCURRENCIA OPTIMISTA (`version`)                                   #
# --------------------------------------------------------------------------- #


def test_version_nace_en_cero_y_sube_en_cada_edicion(pg):
    c = db.crear_publicacion(titulo="t")
    assert c["version"] == 0
    u1 = db.actualizar_publicacion(c["id"], {"titulo": "a"})
    assert u1["version"] == 1
    u2 = db.actualizar_publicacion(c["id"], {"titulo": "b"})
    assert u2["version"] == 2
    p = db.crear_pieza_fila(publicacion_id=c["id"], red="x")
    assert p["version"] == 0
    pu = db.actualizar_pieza_fila(p["id"], {"copy": "hi"})
    assert pu["version"] == 1


def test_version_obsoleta_levanta_conflicto(pg):
    c = db.crear_publicacion(titulo="t")
    db.actualizar_publicacion(c["id"], {"titulo": "a"})  # version -> 1
    # Un editor con la version vieja (0) choca: NO pisa el cambio.
    with pytest.raises(db.ConflictoVersion):
        db.actualizar_publicacion(c["id"], {"titulo": "z"}, version_esperada=0)
    # La version correcta SI aplica.
    u = db.actualizar_publicacion(c["id"], {"titulo": "z"}, version_esperada=1)
    assert u["titulo"] == "z"
    assert u["version"] == 2


def test_version_esperada_en_inexistente_da_none_no_conflicto(pg):
    assert db.actualizar_publicacion("no-existe", {"titulo": "x"}, version_esperada=0) is None


def test_version_plataforma_obsoleta_levanta_conflicto(pg):
    c = db.crear_publicacion(titulo="t")
    p = db.crear_pieza_fila(publicacion_id=c["id"], red="x")
    db.actualizar_pieza_fila(p["id"], {"copy": "uno"})  # version -> 1
    with pytest.raises(db.ConflictoVersion):
        db.actualizar_pieza_fila(p["id"], {"copy": "dos"}, version_esperada=0)


def test_transicion_estado_sube_version(pg):
    """El AVANCE de estado (pipeline) tambien sube la version (carrera pipeline↔humano)."""
    c = db.crear_publicacion(titulo="t")
    p = db.crear_pieza_fila(publicacion_id=c["id"], red="x", estado="en_revision")
    v0 = db.obtener_pieza_fila(p["id"])["version"]
    db.transicionar_estado_pieza(p["id"], "en_revision", "programado")
    v1 = db.obtener_pieza_fila(p["id"])["version"]
    assert v1 == v0 + 1


# --------------------------------------------------------------------------- #
# Bloque 4: TIPOS — jsonb en jobs.spec y metricas_cache.payload                  #
# --------------------------------------------------------------------------- #


def test_jsonb_tipos_aplicados(pg):
    db.listar_swaps_turno()
    con = _cruda()
    try:
        def dtype(t, c):
            return con.execute(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = ? AND column_name = ?",
                (t, c),
            ).fetchone()["data_type"]
        assert dtype("jobs", "spec") == "jsonb"
        assert dtype("metricas_cache", "payload") == "jsonb"
    finally:
        con.close()


def test_jobs_spec_roundtrip_jsonb(pg):
    """encolar (str JSON) -> reclamar -> deserializar (dict via jsonb)."""
    from keni_consola.dominio import jobspec

    db.encolar_job("genJ", jobspec.serializar({"prompt": "hola", "kind": "texto"}), 5)
    claimed = db.reclamar_job("w1")
    assert claimed is not None
    spec = jobspec.deserializar(claimed["spec"])  # acepta dict (jsonb) o str
    assert spec["prompt"] == "hola"


def test_metricas_cache_payload_roundtrip_jsonb(pg):
    db.guardar_metricas_cache(
        "k1", "reporte", "7d", "", {"fuente": "muestra", "a": [1, 2, 3]}, "muestra", "2026-01-01"
    )
    ent = db.leer_metricas_cache("k1")
    assert ent is not None
    assert ent["payload"] == {"fuente": "muestra", "a": [1, 2, 3]}


def test_jsonb_migracion_idempotente_y_limpia_valor_sucio(pg):
    from keni_consola._db_core.migraciones_integridad import _migrar_tipos_jsonb

    db.listar_swaps_turno()
    con = _cruda()
    try:
        # Vuelve a TEXT, mete un valor JSON valido y otro sucio, re-migra.
        con.execute("TRUNCATE jobs")
        con.execute("ALTER TABLE jobs ALTER COLUMN spec TYPE text USING spec::text")
        con.execute("INSERT INTO jobs (id, gen_id, spec, estado, creado) VALUES ('a','ga','{\"p\":1}','pendiente','2026-01-01T00:00:00')")
        con.execute("INSERT INTO jobs (id, gen_id, spec, estado, creado) VALUES ('b','gb','basura','pendiente','2026-01-01T00:00:00')")
        con.commit()
        _migrar_tipos_jsonb(con)
        con.commit()
        filas = {r["id"]: r["spec"] for r in con.execute("SELECT id, spec FROM jobs").fetchall()}
        assert filas["a"] == {"p": 1}
        assert filas["b"] == {}  # valor sucio degradado a '{}'
        # Idempotente: re-correr no falla.
        _migrar_tipos_jsonb(con)
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Bloque 6: TIPOS — fechas TEXT -> nativas (timestamptz/date), migracion 0033    #
# --------------------------------------------------------------------------- #


def _dtype(con, tabla, columna):
    return con.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        (tabla, columna),
    ).fetchone()["data_type"]


def test_fecha_nativa_tipos_aplicados(pg):
    """El DDL/migracion 0033 deja las columnas de fecha de alto uso en su tipo NATIVO."""
    db.listar_swaps_turno()  # asegura esquema+migraciones
    con = _cruda()
    try:
        assert _dtype(con, "publicacion", "creado") == "timestamp with time zone"
        assert _dtype(con, "publicacion", "actualizado") == "timestamp with time zone"
        assert _dtype(con, "jobs", "creado") == "timestamp with time zone"
        assert _dtype(con, "jobs", "claimed_at") == "timestamp with time zone"
        assert _dtype(con, "metricas_pieza_snapshots", "ts") == "timestamp with time zone"
        assert _dtype(con, "eventos_internos", "creado") == "timestamp with time zone"
        assert _dtype(con, "gasto_ia", "dia") == "date"
    finally:
        con.close()


def test_fecha_nativa_migracion_desde_text_sentinel_a_null_e_idempotente(pg):
    """Convierte TEXT->timestamptz/date: canon ISO se conserva, '' pasa a NULL, idempotente."""
    from keni_consola._db_core.migraciones_integridad import _migrar_tipos_fecha

    db.listar_swaps_turno()
    con = _cruda()
    try:
        # Siembra datos: un job con `claimed_at` real y otro con valor vacio.
        con.execute("TRUNCATE jobs")
        con.execute("ALTER TABLE jobs ALTER COLUMN creado TYPE text USING creado::text")
        con.execute(
            "ALTER TABLE jobs ALTER COLUMN claimed_at TYPE text "
            "USING COALESCE(claimed_at::text, '')"
        )
        con.execute("ALTER TABLE jobs ALTER COLUMN claimed_at SET DEFAULT ''")
        con.execute(
            "INSERT INTO jobs (id, gen_id, spec, estado, creado, claimed_at) "
            "VALUES ('a','ga','{}','reclamado','2026-06-13T10:00:00','2026-06-13T10:00:05')"
        )
        con.execute(
            "INSERT INTO jobs (id, gen_id, spec, estado, creado, claimed_at) "
            "VALUES ('b','gb','{}','pendiente','2026-06-13T11:00:00','')"
        )
        con.commit()
        assert _dtype(con, "jobs", "creado") == "text"

        _migrar_tipos_fecha(con)
        con.commit()
        assert _dtype(con, "jobs", "creado") == "timestamp with time zone"
        assert _dtype(con, "jobs", "claimed_at") == "timestamp with time zone"
        filas = {
            r["id"]: r for r in con.execute(
                "SELECT id, to_char(creado AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') AS c, "
                "claimed_at FROM jobs"
            ).fetchall()
        }
        # El instante canonico se conserva exacto (UTC).
        assert filas["a"]["c"] == "2026-06-13T10:00:00"
        assert filas["a"]["claimed_at"] is not None
        # El sentinel '' pasa a NULL en la columna nativa.
        assert filas["b"]["claimed_at"] is None
        # Idempotente: re-correr (ya no es text) no toca nada ni falla.
        _migrar_tipos_fecha(con)
        con.commit()
    finally:
        con.close()


def test_claimed_at_null_y_serializacion_iso(pg):
    """Un job recien encolado tiene claimed_at NULL; `jobs_activos` lo re-emite como '' (canon)."""
    from keni_consola.dominio import jobspec

    db.encolar_job("genX", jobspec.serializar({"prompt": "h", "kind": "texto"}), 5)
    activos = {j["gen_id"]: j for j in db.jobs_activos()}
    assert activos["genX"]["claimed_at"] == ""  # NULL -> '' (contrato TEXT historico)
    # `creado` vuelve como string ISO canonico (segundos, sin offset), no un datetime.
    creado = activos["genX"]["creado"]
    assert isinstance(creado, str) and creado[10] == "T" and len(creado) == 19


def test_gasto_ia_dia_date_roundtrip_y_serie(pg):
    """`gasto_ia.dia` es `date`: agrupacion por dia y serie re-emiten el string YYYY-MM-DD."""
    from keni_consola import repos

    repos.registrar_gasto_ia("g1", dia="2026-06-13", tokens_in=100, tokens_out=50)
    serie = repos.gasto_ia_por_dia(30)
    fila = [d for d in serie if d["dia"] == "2026-06-13"]
    assert fila and fila[0]["tokens"] == 150
    assert isinstance(fila[0]["dia"], str)  # date -> string ISO, no objeto date
    assert db.gasto_ia_del_dia("2026-06-13")["tokens"] == 150


def test_gasto_ia_economia_garantiza_las_4_pestanas_y_zero_fill(pg):
    """Sin filas: las 4 pestañas de Contexto presentes, a cero y por_dia de longitud `dias`."""
    eco = db.gasto_ia_economia_por_proceso(5)
    assert set(eco) == {"investigacion", "produccion", "herramientas", "desarrollo"}
    for pestana in eco:
        bloque = eco[pestana]
        assert bloque["total"] == {"items": 0, "tokens": 0, "coste_usd": 0.0}
        assert bloque["por_etapa"] == []
        assert len(bloque["por_dia"]) == 5
        assert all(d["items"] == 0 and d["tokens"] == 0 and d["coste_usd"] == 0.0
                   and d["por_etapa"] == [] for d in bloque["por_dia"])
        # por_dia ordenado antiguo -> reciente, sin huecos.
        fechas = [d["dia"] for d in bloque["por_dia"]]
        assert fechas == sorted(fechas)


def test_gasto_ia_economia_agrega_por_pestana_dia_y_etapa(pg):
    """Agrega GLOBAL (sin marca) por pestaña; zero-fill del eje; por_etapa por coste desc + cruces."""
    from datetime import timedelta

    from keni_consola import repos
    from keni_consola.tiempo import hoy_utc

    hoy = hoy_utc()
    ayer = (hoy - timedelta(days=1)).isoformat()
    hoy_iso = hoy.isoformat()
    # Produccion: dos tipos en dias distintos y dos marcas (deben sumarse, GLOBAL).
    repos.registrar_gasto_ia("p1", dia=hoy_iso, proceso="produccion", tipo="copy",
                             marca="unotv", tokens_in=100, tokens_out=40, coste_usd=0.01)
    repos.registrar_gasto_ia("p2", dia=hoy_iso, proceso="produccion", tipo="copy",
                             marca="claro-sports", tokens_in=10, tokens_out=5, coste_usd=0.002)
    repos.registrar_gasto_ia("p3", dia=ayer, proceso="produccion", tipo="imagen",
                             marca="unotv", tokens_in=0, tokens_out=0, coste_usd=0.05)
    # Investigacion: una fila hoy.
    repos.registrar_gasto_ia("i1", dia=hoy_iso, proceso="investigacion", tipo="verificacion",
                             marca="unotv", tokens_in=200, tokens_out=20, coste_usd=0.004)

    eco = db.gasto_ia_economia_por_proceso(3)

    prod = eco["produccion"]
    assert prod["total"] == {"items": 3, "tokens": 155, "coste_usd": pytest.approx(0.062)}
    # por_etapa = fases del pipeline: imagen->Ilustrar (0.05) antes que copy->Redactar (0.012).
    assert [t["etapa"] for t in prod["por_etapa"]] == ["Ilustrar", "Redactar"]
    etapa_redactar = next(t for t in prod["por_etapa"] if t["etapa"] == "Redactar")
    assert etapa_redactar["items"] == 2 and etapa_redactar["tokens"] == 155
    assert etapa_redactar["coste_usd"] == pytest.approx(0.012)
    # Cruce por_etapa[].por_dia: la etapa Redactar tiene su serie de 3 dias (zero-filled), con sus
    # 2 items en HOY.
    redactar_por_dia = {d["dia"]: d for d in etapa_redactar["por_dia"]}
    assert len(etapa_redactar["por_dia"]) == 3 and redactar_por_dia[hoy_iso]["items"] == 2
    assert redactar_por_dia[ayer]["items"] == 0
    # por_dia: longitud 3, el dia mas reciente suma las dos filas de hoy.
    assert len(prod["por_dia"]) == 3
    por_dia = {d["dia"]: d for d in prod["por_dia"]}
    assert por_dia[hoy_iso]["items"] == 2 and por_dia[hoy_iso]["tokens"] == 155
    assert por_dia[ayer]["coste_usd"] == pytest.approx(0.05)
    # Cruce por_dia[].por_etapa: el desglose por etapa de HOY trae Redactar (2 items); AYER, Ilustrar.
    assert [e["etapa"] for e in por_dia[hoy_iso]["por_etapa"]] == ["Redactar"]
    assert por_dia[hoy_iso]["por_etapa"][0]["items"] == 2
    assert [e["etapa"] for e in por_dia[ayer]["por_etapa"]] == ["Ilustrar"]

    inv = eco["investigacion"]
    assert inv["total"]["items"] == 1 and inv["total"]["tokens"] == 220


def test_gasto_ia_economia_reclasifica_herramientas_y_desarrollo(pg):
    """dev-fase/dev-discovery -> Desarrollo; transcribir/idear/import -> Herramientas; el resto cae
    a su motor sellado (la ambiguedad de `pipeline` la resuelve la columna `proceso`)."""
    from keni_consola import repos
    from keni_consola.tiempo import hoy_utc

    hoy_iso = hoy_utc().isoformat()
    # Aunque se sellen como 'produccion' en el ledger, la economia los reclasifica por su tipo.
    repos.registrar_gasto_ia("d1", dia=hoy_iso, proceso="produccion", tipo="dev-fase",
                             marca="", tokens_in=100, tokens_out=50, coste_usd=0.02)
    repos.registrar_gasto_ia("h1", dia=hoy_iso, proceso="produccion", tipo="transcribir",
                             marca="unotv", tokens_in=10, tokens_out=5, coste_usd=0.001)
    repos.registrar_gasto_ia("h2", dia=hoy_iso, proceso="produccion", tipo="evergreen-ideas",
                             marca="unotv", tokens_in=20, tokens_out=10, coste_usd=0.003)
    repos.registrar_gasto_ia("c1", dia=hoy_iso, proceso="produccion", tipo="copy",
                             marca="unotv", tokens_in=30, tokens_out=10, coste_usd=0.004)
    # `pipeline` ambiguo: el sello de proceso decide (investigacion = verificar).
    repos.registrar_gasto_ia("v1", dia=hoy_iso, proceso="investigacion", tipo="pipeline",
                             marca="unotv", tokens_in=200, tokens_out=20, coste_usd=0.005)

    eco = db.gasto_ia_economia_por_proceso(2)
    assert eco["desarrollo"]["total"]["items"] == 1 and eco["desarrollo"]["total"]["tokens"] == 150
    assert eco["herramientas"]["total"]["items"] == 2  # transcribir + evergreen-ideas
    assert eco["produccion"]["total"]["items"] == 1  # solo copy
    assert eco["investigacion"]["total"]["items"] == 1  # el pipeline sellado investigacion


def test_gasto_ia_economia_filtra_por_marca(pg):
    """`marca` acota el desglose a sus filas; "" devuelve el AGREGADO de todas."""
    from keni_consola import repos
    from keni_consola.tiempo import hoy_utc

    hoy_iso = hoy_utc().isoformat()
    repos.registrar_gasto_ia("m1", dia=hoy_iso, proceso="produccion", tipo="copy",
                             marca="unotv", tokens_in=100, tokens_out=40, coste_usd=0.01)
    repos.registrar_gasto_ia("m2", dia=hoy_iso, proceso="produccion", tipo="copy",
                             marca="claro-sports", tokens_in=10, tokens_out=5, coste_usd=0.002)

    solo_unotv = db.gasto_ia_economia_por_proceso(3, marca="unotv")
    assert solo_unotv["produccion"]["total"] == {
        "items": 1, "tokens": 140, "coste_usd": pytest.approx(0.01)}

    todas = db.gasto_ia_economia_por_proceso(3)
    assert todas["produccion"]["total"]["items"] == 2
    assert todas["produccion"]["total"]["tokens"] == 155
