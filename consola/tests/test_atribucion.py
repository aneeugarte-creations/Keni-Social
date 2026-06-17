"""Tests de ATRIBUCION por usuario del estado compartido (#130 Fase 1, ADR 0001).

El estado (borradores/piezas, historial de prompts, tareas/pendientes y el
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
# Piezas                                                               #
# --------------------------------------------------------------------------- #


def test_publicacion_creada_por_usuario_queda_atribuida(entorno):
    """Una pieza creada por la sesion de `ana` se atribuye a `ana` (id + nombre)."""
    c = _cli_con_usuario("ana")
    pub = c.post(
        "/api/piezas",
        json={"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C"},
        headers=_ORIGIN,
    ).json()["pieza"]
    assert pub["autor_nombre"] == "ana"
    assert pub["autor_id"]  # id estable presente
    # Y la atribucion sobrevive al listado (lectura compartida).
    listado = c.get("/api/piezas").json()["piezas"]
    assert listado[0]["autor_nombre"] == "ana"
    assert listado[0]["autor_id"] == pub["autor_id"]


def test_publicacion_por_token_no_tiene_autor(entorno):
    """Por el TOKEN (mantenimiento, sin usuario) la pieza nace sin autor (anonima)."""
    c = _cli_por_token()
    pub = c.post(
        "/api/piezas",
        json={"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C"},
        headers=_ORIGIN,
    ).json()["pieza"]
    assert pub["autor_id"] == ""
    assert pub["autor_nombre"] == ""


def test_publicacion_legada_sin_autor_se_lee_como_desconocido(entorno):
    """Una pieza creada SIN autor (legado en disco) se lee con autor vacio, sin romper."""
    # Creada directo por la capa de datos sin `autor` (simula un YAML legado).
    legada = repos.crear_pieza(_MARCA, "x", titulo="Vieja", contenido="C")
    assert legada["autor_id"] == "" and legada["autor_nombre"] == ""
    c = _cli_por_token()
    detalle = c.get(f"/api/piezas/{legada['id']}").json()["pieza"]
    assert detalle["autor_id"] == ""
    assert detalle["autor_nombre"] == ""


def test_lote_de_publicaciones_atribuido_al_usuario(entorno):
    """El alta por lote atribuye TODAS las piezas al usuario de la peticion."""
    c = _cli_con_usuario("ana")
    r = c.post(
        "/api/piezas/lote",
        json={"piezas": [
            {"marca": _MARCA, "red": "x", "titulo": "A"},
            {"marca": _MARCA, "red": "instagram", "titulo": "B"},
        ]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    for pub in r.json()["piezas"]:
        assert pub["autor_nombre"] == "ana"
        assert pub["autor_id"]


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

    El copy ya no se lanza por el motor de skills (retirado): se lanza desde la Texto
    con un prompt `salida=piezas` + redes. Devuelve el id para `POST /api/prompts/lanzar`.
    """
    from keni_consola import libprompts

    prompt = libprompts.crear("Copy desde nota", tipo="prompt", cuerpo="Convierte la nota.")
    ruta = libprompts._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    return prompt.id


def test_generacion_atribuye_registro_historial_y_publicaciones(entorno):
    """Generar copy como `ana` atribuye a `ana`: el registro de generacion, el historial
    y las piezas auto-creadas en el post-procesado (background)."""
    c = _cli_con_usuario("ana", lanzar_generacion=lanzador_generacion_completa(_SALIDA_COPY))
    prompt_id = _crear_prompt_piezas()
    gen = c.post(
        "/api/prompts/lanzar",
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
    # (El historial ya no se sirve por HTTP: se lee del registro via `repos`.)
    hid = gen["resultado"]["historial_id"]
    entrada = repos.obtener_historial_prompt(hid)
    assert entrada is not None
    assert entrada["autor_nombre"] == "ana"
    assert entrada["autor_id"]

    # 3) La pieza (borrador) auto-creada por pieza tambien.
    pubs = c.get("/api/piezas").json()["piezas"]
    assert len(pubs) == 1
    assert pubs[0]["autor_nombre"] == "ana"
    assert pubs[0]["autor_id"] == gen["autor_id"]


def test_generacion_por_token_sin_autor(entorno):
    """Una generacion lanzada por el TOKEN (mantenimiento) no atribuye autor (anonima)."""
    c = _cli_por_token(lanzar_generacion=lanzador_generacion_completa(_SALIDA_COPY))
    prompt_id = _crear_prompt_piezas()
    gen = c.post(
        "/api/prompts/lanzar",
        json={"prompt_id": prompt_id, "marca": _MARCA, "redes": ["x"],
              "target": {"tipo": "contenido", "valor": "una nota"}},
        headers=_ORIGIN,
    ).json()["generacion"]
    assert gen["autor_id"] == ""
    assert gen["autor_nombre"] == ""
    hid = gen["resultado"]["historial_id"]
    assert repos.obtener_historial_prompt(hid)["autor_nombre"] == ""
    assert c.get("/api/piezas").json()["piezas"][0]["autor_nombre"] == ""


def test_historial_legado_sin_autor_se_lee_como_desconocido(entorno):
    """Una entrada de historial registrada SIN autor se lee con autor vacio, sin romper."""
    hid = repos.registrar_historial_prompt("copy-desde-nota", _MARCA, "texto plano")
    entrada = repos.obtener_historial_prompt(hid)
    assert entrada["autor_id"] == ""
    assert entrada["autor_nombre"] == ""
