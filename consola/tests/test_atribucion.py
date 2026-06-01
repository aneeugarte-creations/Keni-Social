"""Tests de ATRIBUCION por usuario del estado compartido (#130 Fase 1, ADR 0001).

El estado (borradores/publicaciones, historial de skills, tareas/pendientes y el
registro de generaciones) es COMPARTIDO en el servidor; estos tests prueban que cada
registro creado por la API queda ATRIBUIDO al usuario autenticado y que la atribucion
se EXPONE en las respuestas y se RENDERIZA. RETROCOMPATIBILIDAD: un registro legado /
anonimo (creado sin sesion, o antes de la atribucion) se lee como autor vacio ("") =
"desconocido", sin romper la lectura.

Convive con lo ya cerrado (#134/#130): la auth/CSRF/sesion no se toca. Para atribuir a
un usuario concreto se hace login real (cookie de sesion); el acceso por TOKEN de
bootstrap NO tiene usuario asociado, asi que su atribucion es vacia (mantenimiento).

Todo OFFLINE; reusa el aislamiento de `entorno` y los fakes de `conftest`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, db, repos

from .conftest import TOKEN_PRUEBA, lanzador_generacion_completa

# Origin del propio host del TestClient (pasa el chequeo CSRF en mutaciones).
_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba"
_MARCA = "unotv"


def _app(bootstrap=False, lanzar_generacion=None):
    """App con token de prueba (sin lanzadores reales salvo el que se pase)."""
    kw = {"token": TOKEN_PRUEBA, "bootstrap": bootstrap}
    if lanzar_generacion is not None:
        kw["lanzar_generacion"] = lanzar_generacion
    return app_modulo.crear_app(**kw)


def _cli_con_usuario(usuario: str, lanzar_generacion=None) -> TestClient:
    """TestClient con SESION de `usuario` (login real): atribuye al crear/generar."""
    auth.crear_usuario(usuario, _CLAVE, "editor")
    c = TestClient(_app(lanzar_generacion=lanzar_generacion))
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _cli_por_token(lanzar_generacion=None) -> TestClient:
    """TestClient autenticado por el TOKEN de bootstrap (sin usuario => atribucion vacia)."""
    cab = {"Authorization": f"Bearer {TOKEN_PRUEBA}"}
    return TestClient(_app(lanzar_generacion=lanzar_generacion), headers=cab)


# --------------------------------------------------------------------------- #
# Publicaciones                                                               #
# --------------------------------------------------------------------------- #


def test_publicacion_creada_por_usuario_queda_atribuida(entorno):
    """Una publicacion creada por la sesion de `ana` se atribuye a `ana` (id + nombre)."""
    c = _cli_con_usuario("ana")
    pub = c.post(
        "/api/publicaciones",
        json={"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C"},
        headers=_ORIGIN,
    ).json()["publicacion"]
    assert pub["autor_nombre"] == "ana"
    assert pub["autor_id"]  # id estable presente
    # Y la atribucion sobrevive al listado (lectura compartida).
    listado = c.get("/api/publicaciones").json()["publicaciones"]
    assert listado[0]["autor_nombre"] == "ana"
    assert listado[0]["autor_id"] == pub["autor_id"]


def test_publicacion_por_token_no_tiene_autor(entorno):
    """Por el TOKEN (mantenimiento, sin usuario) la publicacion nace sin autor (anonima)."""
    c = _cli_por_token()
    pub = c.post(
        "/api/publicaciones",
        json={"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C"},
        headers=_ORIGIN,
    ).json()["publicacion"]
    assert pub["autor_id"] == ""
    assert pub["autor_nombre"] == ""


def test_publicacion_legada_sin_autor_se_lee_como_desconocido(entorno):
    """Una publicacion creada SIN autor (legado en disco) se lee con autor vacio, sin romper."""
    # Creada directo por la capa de datos sin `autor` (simula un YAML legado).
    legada = repos.crear_publicacion(_MARCA, "x", titulo="Vieja", contenido="C")
    assert legada["autor_id"] == "" and legada["autor_nombre"] == ""
    c = _cli_por_token()
    detalle = c.get(f"/api/publicaciones/{legada['id']}").json()["publicacion"]
    assert detalle["autor_id"] == ""
    assert detalle["autor_nombre"] == ""


def test_lote_de_publicaciones_atribuido_al_usuario(entorno):
    """El alta por lote atribuye TODAS las piezas al usuario de la peticion."""
    c = _cli_con_usuario("ana")
    r = c.post(
        "/api/publicaciones/lote",
        json={"publicaciones": [
            {"marca": _MARCA, "red": "x", "titulo": "A"},
            {"marca": _MARCA, "red": "instagram", "titulo": "B"},
        ]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    for pub in r.json()["publicaciones"]:
        assert pub["autor_nombre"] == "ana"
        assert pub["autor_id"]


def test_duplicar_atribuye_al_usuario_que_duplica(entorno):
    """La copia (duplicar) se atribuye a QUIEN duplica, no al autor del original."""
    # Original creado por token (anonimo); lo duplica `ana`.
    original = repos.crear_publicacion(_MARCA, "x", titulo="Orig", contenido="C")
    c = _cli_con_usuario("ana")
    copia = c.post(f"/api/publicaciones/{original['id']}/duplicar", json={}, headers=_ORIGIN)
    assert copia.status_code == 200
    assert copia.json()["publicacion"]["autor_nombre"] == "ana"


# --------------------------------------------------------------------------- #
# Tareas / pendientes                                                         #
# --------------------------------------------------------------------------- #


def test_tarea_legada_sin_columnas_de_autor_se_migra_y_lee(entorno):
    """Una BD vieja sin columnas de autor se ALTERa (idempotente) y la tarea se lee vacia.

    Recrea el escenario real (Postgres hosted PERSISTE entre despliegues): una fila de
    `tareas` que existia ANTES de la atribucion no tiene `autor_id`/`autor_nombre`. Tras la
    migracion on-demand, debe leerse con autor "" (desconocido) sin romper, y la columna
    queda disponible para nuevas filas.
    """
    # 1) Tabla `tareas` con el esquema VIEJO (sin las columnas de atribucion) sobre Postgres.
    from keni_consola import motor_db

    con = motor_db.conectar_cruda()
    con.execute("DROP TABLE IF EXISTS tareas")
    con.execute(
        "CREATE TABLE tareas (id TEXT PRIMARY KEY, proyecto TEXT NOT NULL, titulo TEXT NOT NULL, "
        "detalle TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'pendiente', "
        "fecha TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "INSERT INTO tareas (id, proyecto, titulo) VALUES ('vieja', 'proy', 'Tarea vieja')"
    )
    con.commit()
    con.close()

    # 2) Cualquier operacion via la capa de datos dispara la migracion idempotente.
    tarea = db.obtener_tarea("vieja")
    assert tarea is not None
    assert tarea["titulo"] == "Tarea vieja"
    assert tarea["autor_id"] == ""
    assert tarea["autor_nombre"] == ""
    # 3) La columna existe ahora: una tarea nueva con autor persiste el autor.
    nueva = db.crear_tarea("proy", "Nueva", autor={"id": "u1", "usuario": "ana"})
    assert nueva["autor_nombre"] == "ana"
    assert db.obtener_tarea(nueva["id"])["autor_nombre"] == "ana"


# --------------------------------------------------------------------------- #
# Historial de skills + registro de generacion (via el flujo de generacion)    #
# --------------------------------------------------------------------------- #


_SALIDA_COPY = """✅ Copy listo.

```json
{"piezas": [{"red": "x", "texto": "Tweet."}]}
```
"""


def test_generacion_atribuye_registro_historial_y_publicaciones(entorno):
    """Generar copy como `ana` atribuye a `ana`: el registro de generacion, el historial
    y las publicaciones auto-creadas en el post-procesado (background)."""
    c = _cli_con_usuario("ana", lanzar_generacion=lanzador_generacion_completa(_SALIDA_COPY))
    gen = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": _MARCA, "valores": {"fuente": "una nota"},
              "redes": ["x"]},
        headers=_ORIGIN,
    ).json()["generacion"]

    # 1) El registro de generacion lleva el autor.
    assert gen["autor_nombre"] == "ana"
    assert gen["autor_id"]
    # Y el sondeo (GET) lo reexpone igual.
    sondeo = c.get(f"/api/generaciones/{gen['id']}").json()["generacion"]
    assert sondeo["autor_nombre"] == "ana"

    # 2) La entrada de historial creada en el post-procesado se atribuye a `ana`.
    hid = gen["resultado"]["historial_id"]
    detalle = c.get(f"/api/skills/historial/{hid}").json()
    assert detalle["autor_nombre"] == "ana"
    assert detalle["autor_id"]
    lista = c.get("/api/skills/historial").json()["historial"]
    assert lista[0]["autor_nombre"] == "ana"

    # 3) La publicacion (borrador) auto-creada por pieza tambien.
    pubs = c.get("/api/publicaciones").json()["publicaciones"]
    assert len(pubs) == 1
    assert pubs[0]["autor_nombre"] == "ana"
    assert pubs[0]["autor_id"] == gen["autor_id"]


def test_generacion_por_token_sin_autor(entorno):
    """Una generacion lanzada por el TOKEN (mantenimiento) no atribuye autor (anonima)."""
    c = _cli_por_token(lanzar_generacion=lanzador_generacion_completa(_SALIDA_COPY))
    gen = c.post(
        "/api/skills/ejecutar",
        json={"skill": "copy-desde-nota", "marca": _MARCA, "valores": {"fuente": "una nota"},
              "redes": ["x"]},
        headers=_ORIGIN,
    ).json()["generacion"]
    assert gen["autor_id"] == ""
    assert gen["autor_nombre"] == ""
    hid = gen["resultado"]["historial_id"]
    assert c.get(f"/api/skills/historial/{hid}").json()["autor_nombre"] == ""
    assert c.get("/api/publicaciones").json()["publicaciones"][0]["autor_nombre"] == ""


def test_historial_legado_sin_autor_se_lee_como_desconocido(entorno):
    """Una entrada de historial registrada SIN autor se lee con autor vacio, sin romper."""
    hid = repos.registrar_historial_skill("copy-desde-nota", _MARCA, "texto plano")
    c = _cli_por_token()
    detalle = c.get(f"/api/skills/historial/{hid}").json()
    assert detalle["autor_id"] == ""
    assert detalle["autor_nombre"] == ""
