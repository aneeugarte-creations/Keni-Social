"""Tests de la API Rota (HTTP, vía TestClient). Todo OFFLINE (F4 · #144).

Cubre el CONTRATO de `/api/rota/*`: equipo, eventos CRUD, edición de turnos con la
regla de override del sábado consecutivo, aprobación (solo admin), "mi próxima semana"
y export .xlsx/CSV. Reusa el aislamiento de `entorno`; los miembros del equipo son
usuarios creados a mano (auth) — el `cliente` por defecto entra por el token de
mantenimiento. Los turnos se siembran directo en la BD (`repos.*`) porque la consola
ya no propone reparto automático: Elías asigna a mano y el backend solo persiste.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

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


def _crear_turno(
    semana: str,
    evento_id: str,
    miembro: dict,
    *,
    override: bool = False,
    motivo: str = "",
) -> dict:
    """Siembra un turno de cobertura en la BD (Elías asigna a mano; el backend persiste)."""
    return repos.crear_turno_rota(
        semana,
        evento_id,
        miembro_id=miembro["id"],
        miembro_nombre=miembro["usuario"],
        override=override,
        motivo=motivo,
    )


def _crear_turno_trabajo(
    semana: str,
    fecha: str,
    miembro: dict,
    *,
    franja: str = "matutino",
    override: bool = False,
    motivo: str = "",
) -> dict:
    """Siembra un turno de TRABAJO en la BD (Elías asigna a mano)."""
    return repos.crear_turno_trabajo_rota(
        semana,
        fecha,
        miembro_id=miembro["id"],
        miembro_nombre=miembro["usuario"],
        franja=franja,
        override=override,
        motivo=motivo,
    )


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
    equipo = _crear_equipo(2)
    ev = _crear_evento(cliente)
    _crear_turno(LUNES1, ev["id"], equipo[0])
    assert cliente.get(f"/api/rota/semana?lunes={LUNES1}").json()["total"] == 1
    cliente.delete(f"/api/rota/eventos/{ev['id']}")
    assert cliente.get(f"/api/rota/semana?lunes={LUNES1}").json()["total"] == 0


# --------------------------------------------------------------------------- #
# Cobertura + prioridad + reprogramaciones (ola B, #144)                       #
# --------------------------------------------------------------------------- #


def test_evento_nace_con_cobertura_y_prioridad_por_defecto(cliente):
    ev = _crear_evento(cliente)
    assert ev["tipo_cobertura"] == "transmision"  # default
    assert ev["prioridad"] == "media"  # default
    assert ev["cambiado"] is False  # recién creado: nada que avisar
    assert ev["actualizado"]  # se sella la marca temporal al crear


def test_crear_evento_cobertura_y_prioridad_explicitas(cliente):
    ev = _crear_evento(cliente, tipo_cobertura="imagenes", prioridad="alta")
    assert ev["tipo_cobertura"] == "imagenes"
    assert ev["prioridad"] == "alta"


def test_crear_evento_cobertura_invalida_400(cliente):
    r = cliente.post(
        "/api/rota/eventos", json={"titulo": "X", "fecha": SAB1, "tipo_cobertura": "humo"}
    )
    assert r.status_code == 400


def test_crear_evento_prioridad_invalida_400(cliente):
    r = cliente.post(
        "/api/rota/eventos", json={"titulo": "X", "fecha": SAB1, "prioridad": "urgentisima"}
    )
    assert r.status_code == 400


def test_editar_hora_marca_cambiado(cliente):
    ev = _crear_evento(cliente, hora="16:00")
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"hora": "18:00"})
    assert r.status_code == 200
    assert r.json()["evento"]["cambiado"] is True  # se reprogramó -> hay que avisar


def test_editar_fecha_marca_cambiado(cliente):
    ev = _crear_evento(cliente, fecha=SAB1)
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"fecha": SAB2})
    assert r.json()["evento"]["cambiado"] is True


def test_editar_tipo_cobertura_marca_cambiado(cliente):
    ev = _crear_evento(cliente)
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"tipo_cobertura": "imagenes"})
    assert r.json()["evento"]["cambiado"] is True


def test_editar_solo_contenido_no_marca_cambiado(cliente):
    ev = _crear_evento(cliente)
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"contenido": "Otro plan"})
    assert r.json()["evento"]["cambiado"] is False  # editar "qué sacar" NO reprograma


def test_actualizado_se_refresca_en_cada_edicion(cliente):
    ev = _crear_evento(cliente)
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"contenido": "v2"})
    assert r.json()["evento"]["actualizado"]  # sigue presente tras editar


def test_marcar_avisado_limpia_cambiado(cliente):
    ev = _crear_evento(cliente, hora="16:00")
    cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"hora": "18:00"})  # cambiado=1
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"cambiado": False})
    assert r.status_code == 200
    assert r.json()["evento"]["cambiado"] is False  # "ya avisé / visto"


def test_marcar_avisado_gana_aunque_se_reprograme_en_el_mismo_patch(cliente):
    ev = _crear_evento(cliente, hora="16:00")
    # Mismo request: reprograma la hora PERO pide limpiar el aviso -> limpiar gana.
    r = cliente.patch(
        f"/api/rota/eventos/{ev['id']}", json={"hora": "20:00", "cambiado": False}
    )
    assert r.json()["evento"]["cambiado"] is False
    assert r.json()["evento"]["hora"] == "20:00"


def test_filtro_cambiados_solo_reprogramados(cliente):
    ev1 = _crear_evento(cliente, titulo="Sin tocar", fecha=SAB1)
    ev2 = _crear_evento(cliente, titulo="Reprogramado", fecha=SAB1, hora="16:00")
    cliente.patch(f"/api/rota/eventos/{ev2['id']}", json={"hora": "18:00"})  # cambiado=1
    r = cliente.get("/api/rota/eventos?cambiados=true")
    ids = {e["id"] for e in r.json()["eventos"]}
    assert ev2["id"] in ids
    assert ev1["id"] not in ids


def test_filtro_tipo_cobertura(cliente):
    ev_tx = _crear_evento(cliente, titulo="TX", tipo_cobertura="transmision")
    ev_img = _crear_evento(cliente, titulo="IMG", tipo_cobertura="imagenes")
    r = cliente.get("/api/rota/eventos?tipo_cobertura=imagenes")
    ids = {e["id"] for e in r.json()["eventos"]}
    assert ev_img["id"] in ids
    assert ev_tx["id"] not in ids


def test_filtro_tipo_cobertura_invalido_400(cliente):
    r = cliente.get("/api/rota/eventos?tipo_cobertura=humo")
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Edición de turno + override (regla de aceptación)                            #
# --------------------------------------------------------------------------- #


def test_editar_turno_que_repite_sabado_exige_override(cliente):
    equipo = _crear_equipo(2)
    # Semana 1: alguien (ana) cubre el sábado SAB1.
    ev1 = _crear_evento(cliente, fecha=SAB1)
    _crear_turno(LUNES1, ev1["id"], equipo[0])  # ana cubre el sábado previo
    # Semana 2: alguien (beto) cubre el sábado SAB2 (rotación a mano).
    ev2 = _crear_evento(cliente, fecha=SAB2)
    turno2 = _crear_turno(LUNES2, ev2["id"], equipo[1])

    # Intentar reasignar el sábado 2 a la persona del sábado 1 SIN override -> 409.
    r = cliente.patch(
        f"/api/rota/turnos/{turno2['id']}", json={"miembro_id": equipo[0]["id"]}
    )
    assert r.status_code == 409
    assert r.json()["requiere_override"] is True

    # Con override explícito SÍ se permite (cobertura estratégica de Elías).
    r_ok = cliente.patch(
        f"/api/rota/turnos/{turno2['id']}",
        json={"miembro_id": equipo[0]["id"], "override": True, "motivo": "Cobertura clave"},
    )
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["turno"]["override"] is True
    assert r_ok.json()["turno"]["miembro_id"] == equipo[0]["id"]


def test_editar_turno_miembro_inexistente_400(cliente):
    equipo = _crear_equipo(2)
    ev = _crear_evento(cliente)
    turno = _crear_turno(LUNES1, ev["id"], equipo[0])
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
    # Setup vía token de mantenimiento (equipo/evento NO son solo-admin).
    token_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    equipo = _crear_equipo(2)
    ev = _crear_evento(token_cli)
    _crear_turno(LUNES1, ev["id"], equipo[0])
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
    # turnos asignados, el handler responde 400 (la validación de negocio que prueba el test).
    admin = _cli_admin_sesion(app)
    r = admin.post("/api/rota/semana/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 400


def test_editor_no_puede_aprobar_403(entorno):
    """Un editor (no admin) con sesión no puede aprobar/publicar la rota."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    # Equipo + un evento + un turno asignado (vía token de mantenimiento).
    equipo = _crear_equipo(2)
    admin_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    ev = _crear_evento(admin_cli)
    _crear_turno(LUNES1, ev["id"], equipo[0])

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
    ev = _crear_evento(admin_cli)
    _crear_turno(LUNES1, ev["id"], equipo[0])
    asignado = equipo[0]["id"]
    nombre_asignado = equipo[0]["usuario"]

    # La persona asignada ve su turno; la otra no.
    cli = TestClient(app)
    cli.post("/api/auth/login", json={"usuario": nombre_asignado, "password": CLAVE}, headers=_ORIGIN)
    r = cli.get(f"/api/rota/mi-semana?lunes={LUNES1}")
    assert r.status_code == 200
    datos = r.json()
    assert datos["miembro_id"] == asignado
    assert len(datos["mis_turnos"]) == 1

    otro = equipo[1]
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
    equipo = _crear_equipo(2)
    ev = _crear_evento(cliente, titulo="Final", contenido="Resumen")
    _crear_turno(LUNES1, ev["id"], equipo[0])
    r = cliente.get(f"/api/rota/export.csv?lunes={LUNES1}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "rota-" in r.headers.get("content-disposition", "")
    texto = r.text
    assert "Qué sacar" in texto  # cabecera de columna
    assert "Final" in texto and "Resumen" in texto  # datos del turno


def test_export_xlsx(cliente):
    equipo = _crear_equipo(2)
    ev = _crear_evento(cliente, titulo="Final")
    _crear_turno(LUNES1, ev["id"], equipo[0])
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


# --------------------------------------------------------------------------- #
# Gestión de turnos: ausencias / vacaciones (CRUD)                             #
# --------------------------------------------------------------------------- #


def _crear_ausencia(cli: TestClient, miembro_id: str, **campos) -> dict:
    base = {
        "miembro_id": miembro_id,
        "desde": "2026-05-25",
        "hasta": "2026-05-31",
        "tipo": "vacaciones",
    }
    base.update(campos)
    r = cli.post("/api/rota/ausencias", json=base)
    assert r.status_code == 201, r.text
    return r.json()["ausencia"]


def test_ausencias_crud(cliente):
    equipo = _crear_equipo(2)
    a = _crear_ausencia(cliente, equipo[0]["id"], motivo="Playa")
    assert a["tipo"] == "vacaciones"
    assert a["miembro_nombre"] == equipo[0]["usuario"]
    # Listar.
    lista = cliente.get("/api/rota/ausencias").json()["ausencias"]
    assert any(x["id"] == a["id"] for x in lista)
    # Editar.
    p = cliente.patch(f"/api/rota/ausencias/{a['id']}", json={"tipo": "baja"})
    assert p.status_code == 200
    assert p.json()["ausencia"]["tipo"] == "baja"
    # Borrar.
    d = cliente.delete(f"/api/rota/ausencias/{a['id']}")
    assert d.status_code == 200
    assert cliente.delete(f"/api/rota/ausencias/{a['id']}").status_code == 404


def test_ausencia_miembro_invalido_400(cliente):
    _crear_equipo(1)
    r = cliente.post(
        "/api/rota/ausencias",
        json={"miembro_id": "no-existe", "desde": "2026-05-25", "hasta": "2026-05-26"},
    )
    assert r.status_code == 400


def test_ausencia_rango_invertido_400(cliente):
    equipo = _crear_equipo(1)
    r = cliente.post(
        "/api/rota/ausencias",
        json={"miembro_id": equipo[0]["id"], "desde": "2026-05-31", "hasta": "2026-05-25"},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Gestión de turnos: edición + override del sábado de trabajo                   #
# --------------------------------------------------------------------------- #


def test_editar_turno_trabajo_franja(cliente):
    equipo = _crear_equipo(2)
    turno = _crear_turno_trabajo(LUNES1, LUNES1, equipo[0], franja="matutino")
    r = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}",
        json={"franja": "descanso", "nota_relevo": "Dejo pendiente el clip del 2T"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["turno"]["franja"] == "descanso"
    assert r.json()["turno"]["nota_relevo"] == "Dejo pendiente el clip del 2T"


def test_editar_turno_trabajo_repite_sabado_exige_override(cliente):
    equipo = _crear_equipo(3)
    # Semana 1: ana TRABAJA el sábado SAB1 (asignación manual).
    _crear_turno_trabajo(LUNES1, SAB1, equipo[0], franja="matutino")
    # Semana 2: beto TRABAJA el sábado SAB2 (asignación manual, rota a mano).
    turno_sab2 = _crear_turno_trabajo(LUNES2, SAB2, equipo[1], franja="matutino")

    # Reasignar el sábado 2 a la persona del sábado 1 SIN override -> 409.
    r = cliente.patch(
        f"/api/rota/horario/turnos/{turno_sab2['id']}",
        json={"miembro_id": equipo[0]["id"], "franja": "matutino"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["requiere_override"] is True

    # Con override explícito SÍ se permite.
    r_ok = cliente.patch(
        f"/api/rota/horario/turnos/{turno_sab2['id']}",
        json={
            "miembro_id": equipo[0]["id"],
            "franja": "matutino",
            "override": True,
            "motivo": "Cobertura clave",
        },
    )
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["turno"]["override"] is True


def test_editar_turno_trabajo_miembro_inexistente_400(cliente):
    equipo = _crear_equipo(2)
    turno = _crear_turno_trabajo(LUNES1, LUNES1, equipo[0])
    bad = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}", json={"miembro_id": "no-existe"}
    )
    assert bad.status_code == 400


def test_editar_turno_trabajo_franja_invalida_400(cliente):
    equipo = _crear_equipo(2)
    turno = _crear_turno_trabajo(LUNES1, LUNES1, equipo[0])
    bad = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}", json={"franja": "nocturno"}
    )
    assert bad.status_code == 400


# --------------------------------------------------------------------------- #
# Gestión de turnos: aprobación (solo admin) + "mi horario"                     #
# --------------------------------------------------------------------------- #


def test_aprobar_horario_marca_publicado(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    # Setup vía token de mantenimiento (sembrar turno NO es solo-admin).
    token_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    equipo = _crear_equipo(2)
    _crear_turno_trabajo(LUNES1, LUNES1, equipo[0], franja="matutino")
    assert token_cli.get(f"/api/rota/horario?lunes={LUNES1}").json()["aprobada"] is False
    # Aprobar el horario es solo-admin (#150/#153): lo hace una SESION admin real, no el token.
    admin = _cli_admin_sesion(app)
    r = admin.post("/api/rota/horario/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["aprobada"] is True
    assert all(t["estado"] == "aprobado" for t in r.json()["turnos"])


def test_aprobar_horario_sin_turnos_400(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    # Aprobar el horario es solo-admin (#150/#153): con admin y sin turnos asignados, el
    # handler responde 400 (la validación de negocio que prueba el test).
    admin = _cli_admin_sesion(app)
    r = admin.post("/api/rota/horario/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 400


def test_editor_no_puede_aprobar_horario_403(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(2)
    _crear_turno_trabajo(LUNES1, LUNES1, equipo[0], franja="matutino")

    auth.crear_usuario("editora2", CLAVE, "editor")
    editor_cli = TestClient(app)
    editor_cli.post(
        "/api/auth/login", json={"usuario": "editora2", "password": CLAVE}, headers=_ORIGIN
    )
    r = editor_cli.post("/api/rota/horario/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 403


def test_mi_horario_filtra_por_usuario(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(2)
    _crear_turno_trabajo(LUNES1, LUNES1, equipo[0], franja="matutino")
    _crear_turno_trabajo(LUNES1, LUNES1, equipo[1], franja="vespertino")

    # Cada miembro ve solo sus propios turnos de trabajo.
    cli = TestClient(app)
    cli.post(
        "/api/auth/login",
        json={"usuario": equipo[0]["usuario"], "password": CLAVE},
        headers=_ORIGIN,
    )
    r = cli.get(f"/api/rota/mi-horario?lunes={LUNES1}")
    assert r.status_code == 200
    datos = r.json()
    assert datos["miembro_id"] == equipo[0]["id"]
    assert all(t["miembro_id"] == equipo[0]["id"] for t in datos["mis_turnos"])


def test_mi_horario_sin_sesion_avisa(cliente):
    r = cliente.get(f"/api/rota/mi-horario?lunes={LUNES1}")
    assert r.status_code == 200
    assert r.json()["mis_turnos"] == []
    assert r.json()["aviso"]


# --------------------------------------------------------------------------- #
# Gestión de turnos: el .xlsx incluye la hoja "Horario equipo"                  #
# --------------------------------------------------------------------------- #


def test_export_xlsx_incluye_hoja_horario(cliente):
    import io
    import zipfile

    equipo = _crear_equipo(2)
    ev = _crear_evento(cliente, titulo="Final")
    _crear_turno(LUNES1, ev["id"], equipo[0])
    _crear_turno_trabajo(LUNES1, LUNES1, equipo[0], franja="matutino")
    r = cliente.get(f"/api/rota/export.xlsx?lunes={LUNES1}")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    # Un .xlsx es un ZIP: workbook.xml lista las hojas por nombre.
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        workbook = z.read("xl/workbook.xml").decode("utf-8")
    assert "Rota" in workbook
    assert "Horario equipo" in workbook
