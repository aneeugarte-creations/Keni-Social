"""Tests de la API Rota (HTTP, vía TestClient). Todo OFFLINE (F4 · #144).

Cubre el CONTRATO de `/api/rota/*`: equipo, eventos CRUD, proponer (con la rotación de
sábados), edición con override, aprobación (solo admin), "mi próxima semana" y export
.xlsx/CSV. Reusa el aislamiento de `entorno`; los miembros del equipo son usuarios
creados a mano (auth) — el `cliente` por defecto entra por el token de mantenimiento.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"

# Sábados consecutivos reales.
SAB1 = "2026-05-30"
SAB2 = "2026-06-06"
LUNES1 = "2026-05-25"
LUNES2 = "2026-06-01"


def _crear_equipo(n: int = 2) -> list[dict]:
    """Crea n usuarios (miembros del equipo) directos en la BD; devuelve su forma pública."""
    nombres = ["ana", "beto", "caro", "dani"]
    return [auth.crear_usuario(nombres[i], CLAVE, "editor") for i in range(n)]


def _crear_evento(cli: TestClient, **campos) -> dict:
    base = {"titulo": "Partido", "fecha": SAB1, "hora": "16:00", "contenido": "Clip del gol"}
    base.update(campos)
    r = cli.post("/api/rota/eventos", json=base)
    assert r.status_code == 201, r.text
    return r.json()["evento"]


# --------------------------------------------------------------------------- #
# Equipo                                                                       #
# --------------------------------------------------------------------------- #


def test_equipo_lista_usuarios(cliente):
    _crear_equipo(2)
    r = cliente.get("/api/rota/equipo")
    assert r.status_code == 200
    nombres = {m["nombre"] for m in r.json()["equipo"]}
    assert {"ana", "beto"} <= nombres


# --------------------------------------------------------------------------- #
# Eventos / transmisiones                                                      #
# --------------------------------------------------------------------------- #


def test_crear_evento_y_listar(cliente):
    ev = _crear_evento(cliente, titulo="Final", contenido="Resumen 1 min")
    assert ev["es_sabado"] is True
    assert ev["contenido"] == "Resumen 1 min"
    r = cliente.get("/api/rota/eventos")
    assert any(e["id"] == ev["id"] for e in r.json()["eventos"])


def test_crear_evento_sin_titulo_400(cliente):
    r = cliente.post("/api/rota/eventos", json={"fecha": SAB1})
    assert r.status_code == 400


def test_crear_evento_fecha_invalida_400(cliente):
    r = cliente.post("/api/rota/eventos", json={"titulo": "X", "fecha": "no-fecha"})
    assert r.status_code == 400


def test_editar_y_borrar_evento(cliente):
    ev = _crear_evento(cliente)
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"contenido": "Nuevo plan"})
    assert r.status_code == 200
    assert r.json()["evento"]["contenido"] == "Nuevo plan"
    d = cliente.delete(f"/api/rota/eventos/{ev['id']}")
    assert d.status_code == 200
    assert cliente.delete(f"/api/rota/eventos/{ev['id']}").status_code == 404


def test_borrar_evento_borra_sus_turnos(cliente):
    _crear_equipo(2)
    ev = _crear_evento(cliente)
    cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    assert cliente.get(f"/api/rota/semana?lunes={LUNES1}").json()["total"] == 1
    cliente.delete(f"/api/rota/eventos/{ev['id']}")
    assert cliente.get(f"/api/rota/semana?lunes={LUNES1}").json()["total"] == 0


# --------------------------------------------------------------------------- #
# Proponer + rotación de sábados (criterio de aceptación)                      #
# --------------------------------------------------------------------------- #


def test_proponer_vincula_turno_a_evento_y_contenido(cliente):
    _crear_equipo(2)
    _crear_evento(cliente, contenido="Clip del penal")
    r = cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    assert r.status_code == 200
    turnos = r.json()["turnos"]
    assert len(turnos) == 1
    t = turnos[0]
    assert t["evento_id"]
    assert t["contenido"] == "Clip del penal"  # vinculado a "qué sacar"
    assert t["miembro_id"]  # asignado a alguien
    assert t["estado"] == "propuesto"  # NO publicado aún


def test_proponer_no_repite_sabado_consecutivo(cliente):
    _crear_equipo(2)
    # Semana 1: sábado SAB1.
    _crear_evento(cliente, fecha=SAB1)
    r1 = cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    sab1 = next(t for t in r1.json()["turnos"] if t["es_sabado"])
    # Semana 2: sábado SAB2 (consecutivo).
    _crear_evento(cliente, fecha=SAB2)
    r2 = cliente.post("/api/rota/proponer", json={"lunes": LUNES2})
    sab2 = next(t for t in r2.json()["turnos"] if t["es_sabado"])
    assert sab1["miembro_id"] != sab2["miembro_id"]  # NO repite la misma persona


def test_proponer_es_idempotente_reemplaza(cliente):
    _crear_equipo(2)
    _crear_evento(cliente)
    cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    # Re-proponer no duplica turnos: sigue habiendo 1.
    assert cliente.get(f"/api/rota/semana?lunes={LUNES1}").json()["total"] == 1


def test_proponer_sin_lunes_400(cliente):
    r = cliente.post("/api/rota/proponer", json={})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Edición de turno + override (regla de aceptación)                            #
# --------------------------------------------------------------------------- #


def test_editar_turno_que_repite_sabado_exige_override(cliente):
    equipo = _crear_equipo(2)
    # Semana 1: propone y aprobamos un sábado para 'ana' (o quien toque).
    _crear_evento(cliente, fecha=SAB1)
    r1 = cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    sab1 = next(t for t in r1.json()["turnos"] if t["es_sabado"])
    persona_previa = sab1["miembro_id"]

    # Semana 2: propone (rotará a otra persona).
    _crear_evento(cliente, fecha=SAB2)
    r2 = cliente.post("/api/rota/proponer", json={"lunes": LUNES2})
    turno2 = next(t for t in r2.json()["turnos"] if t["es_sabado"])

    # Intentar reasignar el sábado 2 a la persona del sábado 1 SIN override -> 409.
    r = cliente.patch(
        f"/api/rota/turnos/{turno2['id']}", json={"miembro_id": persona_previa}
    )
    assert r.status_code == 409
    assert r.json()["requiere_override"] is True

    # Con override explícito SÍ se permite (cobertura estratégica de Elías).
    r_ok = cliente.patch(
        f"/api/rota/turnos/{turno2['id']}",
        json={"miembro_id": persona_previa, "override": True, "motivo": "Cobertura clave"},
    )
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["turno"]["override"] is True
    assert r_ok.json()["turno"]["miembro_id"] == persona_previa
    # 'equipo' usado para que el lint no marque la variable sin uso.
    assert len(equipo) == 2


def test_editar_turno_miembro_inexistente_400(cliente):
    _crear_equipo(2)
    _crear_evento(cliente)
    r = cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    turno = r.json()["turnos"][0]
    bad = cliente.patch(f"/api/rota/turnos/{turno['id']}", json={"miembro_id": "no-existe"})
    assert bad.status_code == 400


# --------------------------------------------------------------------------- #
# Aprobación (solo admin) + publicación                                        #
# --------------------------------------------------------------------------- #
#
# Aprobar es SOLO ADMIN (#153, ESTRICTO por #150): exige una SESION de un admin REAL.
# El token de mantenimiento NO es admin (#150), asi que aprobar vía token -> 403; por eso
# estos tests aprueban con una sesión admin (el setup no-gated sí puede ir por el token).


def _cli_admin_sesion(app) -> TestClient:
    """TestClient autenticado por SESION con un admin real (no el token de mantenimiento)."""
    auth.crear_usuario("jefa", CLAVE, "admin")
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"usuario": "jefa", "password": CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return c


def test_aprobar_marca_semana_publicada(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    # Setup vía token de mantenimiento (equipo/evento/propuesta NO son solo-admin).
    token_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    _crear_equipo(2)
    _crear_evento(token_cli)
    token_cli.post("/api/rota/proponer", json={"lunes": LUNES1})
    assert token_cli.get(f"/api/rota/semana?lunes={LUNES1}").json()["aprobada"] is False
    # Aprobar es solo-admin (#150/#153): lo hace una SESION admin real, no el token.
    admin = _cli_admin_sesion(app)
    r = admin.post("/api/rota/semana/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["aprobada"] is True
    assert all(t["estado"] == "aprobado" for t in r.json()["turnos"])


def test_aprobar_sin_turnos_400(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    # Aprobar es solo-admin (#150/#153): sin una sesión admin sería 403. Con admin y sin
    # turnos propuestos, el handler responde 400 (la validación de negocio que prueba el test).
    admin = _cli_admin_sesion(app)
    r = admin.post("/api/rota/semana/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 400


def test_editor_no_puede_aprobar_403(entorno):
    """Un editor (no admin) con sesión no puede aprobar/publicar la rota."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    # Equipo + un evento (vía token de mantenimiento) y propuesta.
    _crear_equipo(2)
    admin_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    _crear_evento(admin_cli)
    admin_cli.post("/api/rota/proponer", json={"lunes": LUNES1})

    # Sesión de un editor real (sin el token de bootstrap).
    auth.crear_usuario("editora", CLAVE, "editor")
    editor_cli = TestClient(app)
    editor_cli.post("/api/auth/login", json={"usuario": "editora", "password": CLAVE}, headers=_ORIGIN)
    r = editor_cli.post("/api/rota/semana/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# "Mi próxima semana"                                                          #
# --------------------------------------------------------------------------- #


def test_mi_semana_filtra_por_usuario(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(2)
    admin_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    _crear_evento(admin_cli)
    admin_cli.post("/api/rota/proponer", json={"lunes": LUNES1})
    turnos = admin_cli.get(f"/api/rota/semana?lunes={LUNES1}").json()["turnos"]
    asignado = turnos[0]["miembro_id"]
    nombre_asignado = next(u["usuario"] for u in equipo if u["id"] == asignado)

    # La persona asignada ve su turno; la otra no.
    cli = TestClient(app)
    cli.post("/api/auth/login", json={"usuario": nombre_asignado, "password": CLAVE}, headers=_ORIGIN)
    r = cli.get(f"/api/rota/mi-semana?lunes={LUNES1}")
    assert r.status_code == 200
    datos = r.json()
    assert datos["miembro_id"] == asignado
    assert len(datos["mis_turnos"]) == 1

    otro = next(u for u in equipo if u["id"] != asignado)
    cli2 = TestClient(app)
    cli2.post("/api/auth/login", json={"usuario": otro["usuario"], "password": CLAVE}, headers=_ORIGIN)
    r2 = cli2.get(f"/api/rota/mi-semana?lunes={LUNES1}")
    assert r2.json()["mis_turnos"] == []


def test_mi_semana_sin_sesion_avisa(cliente):
    # El cliente por defecto entra por el token (sin usuario de sesión).
    r = cliente.get(f"/api/rota/mi-semana?lunes={LUNES1}")
    assert r.status_code == 200
    assert r.json()["mis_turnos"] == []
    assert r.json()["aviso"]


# --------------------------------------------------------------------------- #
# Export .xlsx / CSV                                                           #
# --------------------------------------------------------------------------- #


def test_export_csv(cliente):
    _crear_equipo(2)
    _crear_evento(cliente, titulo="Final", contenido="Resumen")
    cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    r = cliente.get(f"/api/rota/export.csv?lunes={LUNES1}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "rota-" in r.headers.get("content-disposition", "")
    texto = r.text
    assert "Qué sacar" in texto  # cabecera de columna
    assert "Final" in texto and "Resumen" in texto  # datos del turno


def test_export_xlsx(cliente):
    _crear_equipo(2)
    _crear_evento(cliente, titulo="Final")
    cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    r = cliente.get(f"/api/rota/export.xlsx?lunes={LUNES1}")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    # Un .xlsx es un ZIP (Open XML): empieza por "PK".
    assert r.content[:2] == b"PK"
    assert len(r.content) > 0


def test_export_csv_semana_vacia_no_rompe(cliente):
    r = cliente.get("/api/rota/export.csv")
    assert r.status_code == 200
    assert "Fecha" in r.text  # al menos la cabecera
