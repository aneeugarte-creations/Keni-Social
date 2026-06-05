"""Tests de ATRIBUCION por usuario del estado compartido (#130 Fase 1, ADR 0001).

El estado (borradores/publicaciones, historial de prompts, tareas/pendientes y el
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
from keni_consola import auth, repos

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
# Historial de prompts + registro de generacion (via el flujo de generacion)   #
# --------------------------------------------------------------------------- #


_SALIDA_COPY = """✅ Copy listo.

```json
{"piezas": [{"red": "x", "texto": "Tweet."}]}
```
"""


def _crear_prompt_piezas() -> str:
    """Crea en el store un prompt de copy con `salida=piezas` y devuelve su id.

    El copy ya no se lanza por el motor de skills (retirado): se lanza desde la Biblioteca
    con un prompt `salida=piezas` + redes. Devuelve el id para `POST /api/biblioteca/lanzar`.
    """
    from keni_consola import biblioteca

    prompt = biblioteca.crear("Copy desde nota", tipo="prompt", cuerpo="Convierte la nota.")
    ruta = biblioteca._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    return prompt.id


def test_generacion_atribuye_registro_historial_y_publicaciones(entorno):
    """Generar copy como `ana` atribuye a `ana`: el registro de generacion, el historial
    y las publicaciones auto-creadas en el post-procesado (background)."""
    c = _cli_con_usuario("ana", lanzar_generacion=lanzador_generacion_completa(_SALIDA_COPY))
    prompt_id = _crear_prompt_piezas()
    gen = c.post(
        "/api/biblioteca/lanzar",
        json={"prompt_id": prompt_id, "marca": _MARCA, "redes": ["x"],
              "target": {"tipo": "contenido", "valor": "una nota"}},
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
    detalle = c.get(f"/api/prompts/historial/{hid}").json()
    assert detalle["autor_nombre"] == "ana"
    assert detalle["autor_id"]
    lista = c.get("/api/prompts/historial").json()["historial"]
    assert lista[0]["autor_nombre"] == "ana"

    # 3) La publicacion (borrador) auto-creada por pieza tambien.
    pubs = c.get("/api/publicaciones").json()["publicaciones"]
    assert len(pubs) == 1
    assert pubs[0]["autor_nombre"] == "ana"
    assert pubs[0]["autor_id"] == gen["autor_id"]


def test_generacion_por_token_sin_autor(entorno):
    """Una generacion lanzada por el TOKEN (mantenimiento) no atribuye autor (anonima)."""
    c = _cli_por_token(lanzar_generacion=lanzador_generacion_completa(_SALIDA_COPY))
    prompt_id = _crear_prompt_piezas()
    gen = c.post(
        "/api/biblioteca/lanzar",
        json={"prompt_id": prompt_id, "marca": _MARCA, "redes": ["x"],
              "target": {"tipo": "contenido", "valor": "una nota"}},
        headers=_ORIGIN,
    ).json()["generacion"]
    assert gen["autor_id"] == ""
    assert gen["autor_nombre"] == ""
    hid = gen["resultado"]["historial_id"]
    assert c.get(f"/api/prompts/historial/{hid}").json()["autor_nombre"] == ""
    assert c.get("/api/publicaciones").json()["publicaciones"][0]["autor_nombre"] == ""


def test_historial_legado_sin_autor_se_lee_como_desconocido(entorno):
    """Una entrada de historial registrada SIN autor se lee con autor vacio, sin romper."""
    hid = repos.registrar_historial_prompt("copy-desde-nota", _MARCA, "texto plano")
    c = _cli_por_token()
    detalle = c.get(f"/api/prompts/historial/{hid}").json()
    assert detalle["autor_id"] == ""
    assert detalle["autor_nombre"] == ""


def test_historial_listado_pagina_y_reporta_total(entorno):
    """`GET /api/prompts/historial` pagina (`?limite=&desplazamiento=`) y reporta el `total`.

    Cada entrada lleva el resultado completo, asi que el listado se acota: con `?limite=`
    se devuelve solo esa pagina, el envelope `paginacion.total` cuenta TODAS, y la clave
    `historial` sigue presente (retrocompatible).
    """
    c = _cli_por_token()
    for i in range(5):
        repos.registrar_historial_prompt("copy-desde-nota", _MARCA, f"texto {i}")

    cuerpo = c.get("/api/prompts/historial?limite=2&desplazamiento=1").json()
    assert len(cuerpo["historial"]) == 2
    assert cuerpo["paginacion"]["total"] == 5
    assert cuerpo["paginacion"]["limite"] == 2
    assert cuerpo["paginacion"]["desplazamiento"] == 1

    # Sin params hay defaults sensatos (no peta) y la clave `historial` sigue ahi.
    por_defecto = c.get("/api/prompts/historial").json()
    assert por_defecto["paginacion"]["total"] == 5
    assert len(por_defecto["historial"]) == 5
