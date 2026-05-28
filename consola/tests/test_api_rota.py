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


def test_proponer_excluye_eventos_no_cubrir(cliente):
    _crear_equipo(2)
    _crear_evento(cliente, titulo="Se cubre", tipo_cobertura="transmision")
    _crear_evento(cliente, titulo="Se cubre con fotos", tipo_cobertura="imagenes")
    _crear_evento(cliente, titulo="No se cubre", tipo_cobertura="no_cubrir")
    r = cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    titulos = {t["evento_titulo"] for t in r.json()["turnos"]}
    assert "Se cubre" in titulos
    assert "Se cubre con fotos" in titulos
    assert "No se cubre" not in titulos  # trackeado pero NO asignado


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


def test_aprobar_marca_semana_publicada(cliente):
    _crear_equipo(2)
    _crear_evento(cliente)
    cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    assert cliente.get(f"/api/rota/semana?lunes={LUNES1}").json()["aprobada"] is False
    r = cliente.post("/api/rota/semana/aprobar", json={"lunes": LUNES1})
    assert r.status_code == 200, r.text
    assert r.json()["aprobada"] is True
    assert all(t["estado"] == "aprobado" for t in r.json()["turnos"])


def test_aprobar_sin_turnos_400(cliente):
    r = cliente.post("/api/rota/semana/aprobar", json={"lunes": LUNES1})
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
# Gestión de turnos: proponer horario + ausencias respetadas                   #
# --------------------------------------------------------------------------- #


def test_proponer_horario_cubre_y_respeta_ausencias(cliente):
    equipo = _crear_equipo(3)
    # equipo[0] de vacaciones toda la semana 1.
    _crear_ausencia(cliente, equipo[0]["id"])
    r = cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    assert r.status_code == 200, r.text
    turnos = r.json()["turnos"]
    assert len(turnos) > 0
    asignados = {t["miembro_id"] for t in turnos}
    assert equipo[0]["id"] not in asignados  # el ausente nunca entra
    # Cada día tiene mañana y tarde (con 2 disponibles).
    franjas_por_dia: dict[str, list[str]] = {}
    for t in turnos:
        franjas_por_dia.setdefault(t["fecha"], []).append(t["franja"])
    for franjas in franjas_por_dia.values():
        assert "matutino" in franjas
        assert "vespertino" in franjas
    assert all(t["estado"] == "propuesto" for t in turnos)  # no publicado


def test_proponer_horario_idempotente_reemplaza(cliente):
    _crear_equipo(2)
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    total1 = cliente.get(f"/api/rota/horario?lunes={LUNES1}").json()["total"]
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    total2 = cliente.get(f"/api/rota/horario?lunes={LUNES1}").json()["total"]
    assert total1 == total2  # re-proponer no duplica


def test_proponer_horario_sin_lunes_400(cliente):
    r = cliente.post("/api/rota/horario/proponer", json={})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Gestión de turnos: edición + override del sábado de trabajo                   #
# --------------------------------------------------------------------------- #


def _turno_sabado(cli: TestClient, lunes: str, sabado: str) -> dict | None:
    turnos = cli.get(f"/api/rota/horario?lunes={lunes}").json()["turnos"]
    for t in turnos:
        if t["fecha"] == sabado and t["franja"] in ("matutino", "vespertino"):
            return t
    return None


def test_editar_turno_trabajo_franja(cliente):
    _crear_equipo(2)
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    turno = cliente.get(f"/api/rota/horario?lunes={LUNES1}").json()["turnos"][0]
    r = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}",
        json={"franja": "descanso", "nota_relevo": "Dejo pendiente el clip del 2T"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["turno"]["franja"] == "descanso"
    assert r.json()["turno"]["nota_relevo"] == "Dejo pendiente el clip del 2T"


def test_editar_turno_trabajo_repite_sabado_exige_override(cliente):
    equipo = _crear_equipo(3)
    # Semana 1: propone (alguien trabaja el sábado SAB1).
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    sab1 = _turno_sabado(cliente, LUNES1, SAB1)
    assert sab1 is not None
    persona_previa = sab1["miembro_id"]

    # Semana 2: propone (rota: persona_previa descansa el sábado SAB2).
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES2})
    # Buscar un turno de trabajo de sábado en la semana 2 que NO sea de persona_previa,
    # para reasignarlo a persona_previa (repetiría el sábado).
    turnos2 = cliente.get(f"/api/rota/horario?lunes={LUNES2}").json()["turnos"]
    objetivo = next(
        t for t in turnos2 if t["fecha"] == SAB2 and t["franja"] in ("matutino", "vespertino")
    )

    # Reasignar a la persona del sábado 1 SIN override -> 409.
    r = cliente.patch(
        f"/api/rota/horario/turnos/{objetivo['id']}",
        json={"miembro_id": persona_previa, "franja": "matutino"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["requiere_override"] is True

    # Con override explícito SÍ se permite.
    r_ok = cliente.patch(
        f"/api/rota/horario/turnos/{objetivo['id']}",
        json={
            "miembro_id": persona_previa,
            "franja": "matutino",
            "override": True,
            "motivo": "Cobertura clave",
        },
    )
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["turno"]["override"] is True
    assert len(equipo) == 3


def test_editar_turno_trabajo_miembro_inexistente_400(cliente):
    _crear_equipo(2)
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    turno = cliente.get(f"/api/rota/horario?lunes={LUNES1}").json()["turnos"][0]
    bad = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}", json={"miembro_id": "no-existe"}
    )
    assert bad.status_code == 400


def test_editar_turno_trabajo_franja_invalida_400(cliente):
    _crear_equipo(2)
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    turno = cliente.get(f"/api/rota/horario?lunes={LUNES1}").json()["turnos"][0]
    bad = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}", json={"franja": "nocturno"}
    )
    assert bad.status_code == 400


# --------------------------------------------------------------------------- #
# Gestión de turnos: aprobación (solo admin) + "mi horario"                     #
# --------------------------------------------------------------------------- #


def test_aprobar_horario_marca_publicado(cliente):
    _crear_equipo(2)
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    assert cliente.get(f"/api/rota/horario?lunes={LUNES1}").json()["aprobada"] is False
    r = cliente.post("/api/rota/horario/aprobar", json={"lunes": LUNES1})
    assert r.status_code == 200, r.text
    assert r.json()["aprobada"] is True
    assert all(t["estado"] == "aprobado" for t in r.json()["turnos"])


def test_aprobar_horario_sin_turnos_400(cliente):
    r = cliente.post("/api/rota/horario/aprobar", json={"lunes": LUNES1})
    assert r.status_code == 400


def test_editor_no_puede_aprobar_horario_403(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    _crear_equipo(2)
    admin_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    admin_cli.post("/api/rota/horario/proponer", json={"lunes": LUNES1})

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
    admin_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    admin_cli.post("/api/rota/horario/proponer", json={"lunes": LUNES1})

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

    _crear_equipo(2)
    _crear_evento(cliente, titulo="Final")
    cliente.post("/api/rota/proponer", json={"lunes": LUNES1})
    cliente.post("/api/rota/horario/proponer", json={"lunes": LUNES1})
    r = cliente.get(f"/api/rota/export.xlsx?lunes={LUNES1}")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    # Un .xlsx es un ZIP: workbook.xml lista las hojas por nombre.
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        workbook = z.read("xl/workbook.xml").decode("utf-8")
    assert "Rota" in workbook
    assert "Horario equipo" in workbook
