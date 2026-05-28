"""Tests de la API Rota (HTTP, vía TestClient). Todo OFFLINE (F4 · #144).

Modelo NUEVO (ola back3, feedback usuario): un TURNO es el horario de un miembro en
`(fecha, franja)`. NO va atado a un evento. La "cobertura" es DERIVADA: para un evento,
sus cubridores son los miembros con un turno en su franja+fecha. Pueden existir turnos
sin eventos y eventos sin turnos.

Cubre el CONTRATO de `/api/rota/*`:
  - eventos (CRUD + duplicar + filtros)
  - turnos (CRUD completo: GET semana, POST individual, PATCH, DELETE, lote, duplicar,
    aprobar) con la regla de override del sábado de trabajo y la cruzada de ausencias.
  - cobertura DERIVADA (`/api/rota/cobertura`, `/api/rota/cobertura/evento/{id}`).
  - copia-semana de turnos, carga del equipo, export csv/xlsx.

Reusa el aislamiento de `entorno`; el equipo son usuarios creados a mano (auth); el
`cliente` por defecto entra por el token de mantenimiento. Los turnos se siembran a
mano (Elias asigna). Las pruebas de aprobacion (solo-admin) usan una sesion admin real.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"

# Sábados consecutivos reales (para la regla de rotacion).
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
    fecha: str,
    miembro: dict,
    *,
    franja: str = "matutino",
    override: bool = False,
    motivo: str = "",
    nota_relevo: str = "",
) -> dict:
    """Siembra un TURNO en la BD (Elias asigna a mano; el backend solo persiste).

    El turno es el horario del miembro en `(fecha, franja)`. NO va atado a un evento.
    """
    return repos.crear_turno_rota(
        semana,
        fecha,
        miembro_id=miembro["id"],
        miembro_nombre=miembro["usuario"],
        franja=franja,
        override=override,
        motivo=motivo,
        nota_relevo=nota_relevo,
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
# Eventos / transmisiones (CRUD)                                              #
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


def test_borrar_evento_no_arrastra_turnos(cliente):
    """Modelo nuevo: turnos y eventos son independientes. Borrar un evento NO toca turnos."""
    equipo = _crear_equipo(1)
    ev = _crear_evento(cliente)
    _crear_turno(LUNES1, SAB1, equipo[0], franja="vespertino")
    assert cliente.get(f"/api/rota/turnos?lunes={LUNES1}").json()["total"] == 1
    cliente.delete(f"/api/rota/eventos/{ev['id']}")
    # El turno sigue ahi (es un horario, no una asignacion a un evento concreto).
    assert cliente.get(f"/api/rota/turnos?lunes={LUNES1}").json()["total"] == 1


# --------------------------------------------------------------------------- #
# Cobertura + prioridad + reprogramaciones (ola B, #144)                       #
# --------------------------------------------------------------------------- #


def test_evento_nace_con_cobertura_y_prioridad_por_defecto(cliente):
    ev = _crear_evento(cliente)
    assert ev["tipo_cobertura"] == "transmision"
    assert ev["prioridad"] == "media"
    assert ev["cambiado"] is False
    assert ev["actualizado"]


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
    assert r.json()["evento"]["cambiado"] is True


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
    assert r.json()["evento"]["cambiado"] is False


def test_marcar_avisado_limpia_cambiado(cliente):
    ev = _crear_evento(cliente, hora="16:00")
    cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"hora": "18:00"})
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"cambiado": False})
    assert r.status_code == 200
    assert r.json()["evento"]["cambiado"] is False


def test_filtro_cambiados_solo_reprogramados(cliente):
    ev1 = _crear_evento(cliente, titulo="Sin tocar", fecha=SAB1)
    ev2 = _crear_evento(cliente, titulo="Reprogramado", fecha=SAB1, hora="16:00")
    cliente.patch(f"/api/rota/eventos/{ev2['id']}", json={"hora": "18:00"})
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


# --------------------------------------------------------------------------- #
# Turnos: GET semana                                                           #
# --------------------------------------------------------------------------- #


def test_turnos_semana_devuelve_los_de_la_semana(cliente):
    equipo = _crear_equipo(2)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino")
    _crear_turno(LUNES1, LUNES1, equipo[1], franja="vespertino")
    r = cliente.get(f"/api/rota/turnos?lunes={LUNES1}")
    assert r.status_code == 200
    datos = r.json()
    assert datos["total"] == 2
    assert datos["lunes"] == LUNES1
    assert datos["aprobada"] is False  # nada aprobado todavia
    fechas_franjas = {(t["fecha"], t["miembro_id"], t["franja"]) for t in datos["turnos"]}
    assert (LUNES1, equipo[0]["id"], "matutino") in fechas_franjas
    assert (LUNES1, equipo[1]["id"], "vespertino") in fechas_franjas


# --------------------------------------------------------------------------- #
# Turnos: POST (crear)                                                         #
# --------------------------------------------------------------------------- #


def test_crear_turno_basico(cliente):
    equipo = _crear_equipo(1)
    r = cliente.post(
        "/api/rota/turnos",
        json={
            "fecha": LUNES1,
            "miembro_id": equipo[0]["id"],
            "franja": "matutino",
            "nota_relevo": "Pendiente clip del 2T",
        },
    )
    assert r.status_code == 201, r.text
    turno = r.json()["turno"]
    assert turno["fecha"] == LUNES1
    assert turno["franja"] == "matutino"
    assert turno["miembro_id"] == equipo[0]["id"]
    assert turno["nota_relevo"] == "Pendiente clip del 2T"
    # Semana derivada del lunes que contiene LUNES1.
    assert turno["semana"] == LUNES1


def test_crear_turno_con_lunes_explicito(cliente):
    """Si el cliente pasa `lunes`, lo respetamos (caso comun: viene del calendario)."""
    equipo = _crear_equipo(1)
    # La fecha cae en la semana de LUNES1, y pasamos lunes=LUNES1 explicito.
    r = cliente.post(
        "/api/rota/turnos",
        json={
            "lunes": LUNES1,
            "fecha": "2026-05-27",
            "miembro_id": equipo[0]["id"],
            "franja": "matutino",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["turno"]["semana"] == LUNES1


def test_crear_turno_fecha_invalida_400(cliente):
    equipo = _crear_equipo(1)
    r = cliente.post(
        "/api/rota/turnos",
        json={"fecha": "no-fecha", "miembro_id": equipo[0]["id"], "franja": "matutino"},
    )
    assert r.status_code == 400


def test_crear_turno_miembro_inexistente_400(cliente):
    r = cliente.post(
        "/api/rota/turnos",
        json={"fecha": LUNES1, "miembro_id": "no-existe", "franja": "matutino"},
    )
    assert r.status_code == 400


def test_crear_turno_franja_invalida_400(cliente):
    equipo = _crear_equipo(1)
    r = cliente.post(
        "/api/rota/turnos",
        json={"fecha": LUNES1, "miembro_id": equipo[0]["id"], "franja": "nocturno"},
    )
    assert r.status_code == 400


def test_crear_turno_duplicado_409(cliente):
    """Ya existe un turno para `(miembro, fecha, franja)` -> 409 con el id existente."""
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino")
    r = cliente.post(
        "/api/rota/turnos",
        json={"fecha": LUNES1, "miembro_id": equipo[0]["id"], "franja": "matutino"},
    )
    assert r.status_code == 409
    assert "turno_existente" in r.json()


def test_crear_turno_sabado_exige_override(cliente):
    """Sabado consecutivo de trabajo sin override -> 409 (regla de aceptacion)."""
    equipo = _crear_equipo(1)
    ana = equipo[0]
    _crear_turno(LUNES1, SAB1, ana, franja="matutino")
    r = cliente.post(
        "/api/rota/turnos",
        json={"fecha": SAB2, "miembro_id": ana["id"], "franja": "matutino"},
    )
    assert r.status_code == 409
    assert r.json()["requiere_override"] is True
    # Con override SI se permite.
    r_ok = cliente.post(
        "/api/rota/turnos",
        json={"fecha": SAB2, "miembro_id": ana["id"], "franja": "matutino", "override": True},
    )
    assert r_ok.status_code == 201


def test_crear_turno_descanso_no_choca_con_sabado_previo(cliente):
    """Asignar `descanso` en sabado a quien trabajo el sabado previo NO viola la rotacion."""
    equipo = _crear_equipo(1)
    ana = equipo[0]
    _crear_turno(LUNES1, SAB1, ana, franja="matutino")
    r = cliente.post(
        "/api/rota/turnos",
        json={"fecha": SAB2, "miembro_id": ana["id"], "franja": "descanso"},
    )
    assert r.status_code == 201


# --------------------------------------------------------------------------- #
# Turnos: PATCH                                                                #
# --------------------------------------------------------------------------- #


def test_editar_turno_franja_y_nota(cliente):
    equipo = _crear_equipo(1)
    turno = _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino")
    r = cliente.patch(
        f"/api/rota/turnos/{turno['id']}",
        json={"franja": "descanso", "nota_relevo": "Dejo pendiente el clip del 2T"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["turno"]["franja"] == "descanso"
    assert r.json()["turno"]["nota_relevo"] == "Dejo pendiente el clip del 2T"


def test_editar_turno_sabado_consecutivo_exige_override(cliente):
    """PATCH con sabado consecutivo de trabajo sin override -> 409."""
    equipo = _crear_equipo(2)
    _crear_turno(LUNES1, SAB1, equipo[0], franja="matutino")
    turno_sab2 = _crear_turno(LUNES2, SAB2, equipo[1], franja="matutino")
    r = cliente.patch(
        f"/api/rota/turnos/{turno_sab2['id']}",
        json={"miembro_id": equipo[0]["id"]},
    )
    assert r.status_code == 409
    assert r.json()["requiere_override"] is True
    # Con override SI se permite.
    r_ok = cliente.patch(
        f"/api/rota/turnos/{turno_sab2['id']}",
        json={"miembro_id": equipo[0]["id"], "override": True, "motivo": "Cobertura clave"},
    )
    assert r_ok.status_code == 200


def test_editar_turno_miembro_inexistente_400(cliente):
    equipo = _crear_equipo(1)
    turno = _crear_turno(LUNES1, LUNES1, equipo[0])
    r = cliente.patch(f"/api/rota/turnos/{turno['id']}", json={"miembro_id": "no-existe"})
    assert r.status_code == 400


def test_editar_turno_franja_invalida_400(cliente):
    equipo = _crear_equipo(1)
    turno = _crear_turno(LUNES1, LUNES1, equipo[0])
    r = cliente.patch(f"/api/rota/turnos/{turno['id']}", json={"franja": "nocturno"})
    assert r.status_code == 400


def test_editar_turno_persona_ausente_exige_override(cliente):
    """Asignar a alguien AUSENTE en su rango -> 409 con la ausencia."""
    equipo = _crear_equipo(2)
    ana, beto = equipo[0], equipo[1]
    repos.crear_ausencia_rota(
        ana["id"], "2026-05-25", "2026-05-31",
        miembro_nombre=ana["usuario"], tipo="vacaciones",
    )
    turno = _crear_turno(LUNES1, "2026-05-27", beto, franja="matutino")
    r = cliente.patch(
        f"/api/rota/turnos/{turno['id']}",
        json={"miembro_id": ana["id"]},
    )
    assert r.status_code == 409
    assert r.json()["requiere_override"] is True
    assert r.json()["ausencia"]["tipo"] == "vacaciones"


# --------------------------------------------------------------------------- #
# Turnos: DELETE                                                               #
# --------------------------------------------------------------------------- #


def test_borrar_turno_individual(cliente):
    equipo = _crear_equipo(1)
    turno = _crear_turno(LUNES1, LUNES1, equipo[0])
    r = cliente.delete(f"/api/rota/turnos/{turno['id']}")
    assert r.status_code == 200
    assert cliente.delete(f"/api/rota/turnos/{turno['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# Turnos: lote (POST/PATCH/DELETE)                                             #
# --------------------------------------------------------------------------- #


def test_crear_turnos_lote(cliente):
    """POST /api/rota/turnos/lote crea varios turnos en una sola petición."""
    equipo = _crear_equipo(1)
    luis = equipo[0]
    r = cliente.post(
        "/api/rota/turnos/lote",
        json={
            "turnos": [
                {"fecha": "2026-05-25", "miembro_id": luis["id"], "franja": "matutino"},
                {"fecha": "2026-05-26", "miembro_id": luis["id"], "franja": "matutino"},
                {"fecha": "2026-05-27", "miembro_id": luis["id"], "franja": "matutino"},
            ]
        },
    )
    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["creados"] == 3
    assert all(t["miembro_id"] == luis["id"] for t in datos["turnos"])


def test_crear_turnos_lote_choque_409(cliente):
    """Si alguna entrada choca con un turno existente o duplicado en el propio lote -> 409."""
    equipo = _crear_equipo(1)
    luis = equipo[0]
    _crear_turno(LUNES1, "2026-05-25", luis, franja="matutino")
    r = cliente.post(
        "/api/rota/turnos/lote",
        json={
            "turnos": [
                {"fecha": "2026-05-25", "miembro_id": luis["id"], "franja": "matutino"},
                {"fecha": "2026-05-26", "miembro_id": luis["id"], "franja": "matutino"},
            ]
        },
    )
    assert r.status_code == 409
    assert r.json()["errores"][0]["indice"] == 0


def test_actualizar_turnos_lote(cliente):
    equipo = _crear_equipo(2)
    luis, tescu = equipo[0], equipo[1]
    turnos = [
        _crear_turno(LUNES1, f"2026-05-2{5 + i}", tescu, franja="vespertino")
        for i in range(3)
    ]
    ids = [t["id"] for t in turnos]
    r = cliente.patch(
        "/api/rota/turnos/lote",
        json={"ids": ids, "miembro_id": luis["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["actualizados"] == 3
    assert all(t["miembro_id"] == luis["id"] for t in r.json()["turnos"])


def test_actualizar_turnos_lote_sabado_exige_override_atomico(cliente):
    """Lote con un sabado problematico -> 409 sin tocar nada (atomico)."""
    equipo = _crear_equipo(2)
    ana, beto = equipo[0], equipo[1]
    # Semana 1: ana TRABAJA el sabado.
    _crear_turno(LUNES1, SAB1, ana, franja="matutino")
    # Semana 2: beto tiene turno el sabado y otro entre semana.
    t_sab2 = _crear_turno(LUNES2, SAB2, beto, franja="matutino")
    t_mar = _crear_turno(LUNES2, "2026-06-02", beto, franja="matutino")
    # Intentar pasar ambos a ana: el sabado choca. ATOMICO -> 409.
    r = cliente.patch(
        "/api/rota/turnos/lote",
        json={"ids": [t_sab2["id"], t_mar["id"]], "miembro_id": ana["id"]},
    )
    assert r.status_code == 409
    assert r.json()["ids_que_requieren_override"] == [t_sab2["id"]]
    # Con override SI se aplica.
    r_ok = cliente.patch(
        "/api/rota/turnos/lote",
        json={
            "ids": [t_sab2["id"], t_mar["id"]],
            "miembro_id": ana["id"],
            "override": True,
        },
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["actualizados"] == 2


def test_actualizar_turnos_lote_miembro_vacio_quita_asignacion(cliente):
    equipo = _crear_equipo(1)
    luis = equipo[0]
    t1 = _crear_turno(LUNES1, "2026-05-25", luis)
    t2 = _crear_turno(LUNES1, "2026-05-26", luis)
    r = cliente.patch(
        "/api/rota/turnos/lote",
        json={"ids": [t1["id"], t2["id"]], "miembro_id": ""},
    )
    assert r.status_code == 200, r.text
    assert r.json()["actualizados"] == 2
    assert all(t["miembro_id"] == "" for t in r.json()["turnos"])


def test_borrar_turnos_lote(cliente):
    equipo = _crear_equipo(1)
    turnos = [
        _crear_turno(LUNES1, f"2026-05-2{5 + i}", equipo[0])
        for i in range(3)
    ]
    r = cliente.post(
        "/api/rota/turnos/lote/borrar",
        json={"ids": [turnos[0]["id"], turnos[1]["id"]]},
    )
    assert r.status_code == 200
    assert r.json()["borrados"] == 2
    semana = cliente.get(f"/api/rota/turnos?lunes={LUNES1}").json()
    ids = {t["id"] for t in semana["turnos"]}
    assert turnos[2]["id"] in ids
    assert turnos[0]["id"] not in ids


def test_borrar_turnos_lote_tolerante_a_no_encontrados(cliente):
    equipo = _crear_equipo(1)
    t = _crear_turno(LUNES1, LUNES1, equipo[0])
    r = cliente.post(
        "/api/rota/turnos/lote/borrar",
        json={"ids": [t["id"], "no-existe-1"]},
    )
    assert r.status_code == 200
    assert r.json()["borrados"] == 1
    assert r.json()["no_encontrados"] == ["no-existe-1"]


def test_borrar_turnos_lote_sin_ids_400(cliente):
    r = cliente.post("/api/rota/turnos/lote/borrar", json={"ids": []})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Turnos: duplicar                                                             #
# --------------------------------------------------------------------------- #


def test_duplicar_turno_simple(cliente):
    equipo = _crear_equipo(1)
    original = _crear_turno(LUNES1, "2026-05-25", equipo[0], franja="matutino")
    r = cliente.post(
        f"/api/rota/turnos/{original['id']}/duplicar",
        json={"fecha": "2026-05-26"},
    )
    assert r.status_code == 201, r.text
    clon = r.json()["turno"]
    assert clon["id"] != original["id"]
    assert clon["fecha"] == "2026-05-26"
    assert clon["miembro_id"] == equipo[0]["id"]
    assert clon["franja"] == "matutino"


def test_duplicar_turno_choque_409(cliente):
    equipo = _crear_equipo(1)
    original = _crear_turno(LUNES1, "2026-05-25", equipo[0], franja="matutino")
    # Ya existe otro turno con la misma clave -> 409.
    _crear_turno(LUNES1, "2026-05-26", equipo[0], franja="matutino")
    r = cliente.post(
        f"/api/rota/turnos/{original['id']}/duplicar",
        json={"fecha": "2026-05-26"},
    )
    assert r.status_code == 409


def test_duplicar_turno_inexistente_404(cliente):
    r = cliente.post("/api/rota/turnos/no-existe/duplicar", json={})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Turnos: aprobar (solo admin) + mis-turnos                                    #
# --------------------------------------------------------------------------- #


def _cli_admin_sesion(app) -> TestClient:
    auth.crear_usuario("jefa", CLAVE, "admin")
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"usuario": "jefa", "password": CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return c


def test_aprobar_turnos_marca_semana_publicada(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    token_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino")
    assert token_cli.get(f"/api/rota/turnos?lunes={LUNES1}").json()["aprobada"] is False
    admin = _cli_admin_sesion(app)
    r = admin.post("/api/rota/turnos/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["aprobada"] is True
    assert all(t["estado"] == "aprobado" for t in r.json()["turnos"])


def test_aprobar_turnos_sin_turnos_400(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    admin = _cli_admin_sesion(app)
    r = admin.post("/api/rota/turnos/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 400


def test_editor_no_puede_aprobar_403(entorno):
    """Un editor (no admin) con sesion no puede aprobar/publicar los turnos."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino")
    auth.crear_usuario("editora", CLAVE, "editor")
    editor_cli = TestClient(app)
    editor_cli.post(
        "/api/auth/login", json={"usuario": "editora", "password": CLAVE}, headers=_ORIGIN
    )
    r = editor_cli.post("/api/rota/turnos/aprobar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 403


def test_mis_turnos_filtra_por_usuario(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(2)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino")
    _crear_turno(LUNES1, LUNES1, equipo[1], franja="vespertino")
    cli = TestClient(app)
    cli.post(
        "/api/auth/login",
        json={"usuario": equipo[0]["usuario"], "password": CLAVE},
        headers=_ORIGIN,
    )
    r = cli.get(f"/api/rota/mis-turnos?lunes={LUNES1}")
    assert r.status_code == 200
    datos = r.json()
    assert datos["miembro_id"] == equipo[0]["id"]
    assert all(t["miembro_id"] == equipo[0]["id"] for t in datos["mis_turnos"])


def test_mis_turnos_sin_sesion_avisa(cliente):
    r = cliente.get(f"/api/rota/mis-turnos?lunes={LUNES1}")
    assert r.status_code == 200
    assert r.json()["mis_turnos"] == []
    assert r.json()["aviso"]


# --------------------------------------------------------------------------- #
# Cobertura DERIVADA                                                           #
# --------------------------------------------------------------------------- #


def test_cobertura_semana_derivada(cliente):
    """Para cada evento de la semana, devuelve los miembros con turno en su franja+fecha."""
    equipo = _crear_equipo(2)
    luis, tescu = equipo[0], equipo[1]
    ev_tarde = _crear_evento(cliente, titulo="Final", fecha=SAB1, hora="18:00")
    ev_madru = _crear_evento(cliente, titulo="Madrugada", fecha=SAB1, hora="03:00")
    # Sembramos: tescu vespertino SAB1 (cubre el de 18:00), luis vespertino SAB1 tambien.
    _crear_turno(LUNES1, SAB1, tescu, franja="vespertino")
    _crear_turno(LUNES1, SAB1, luis, franja="vespertino")
    # luis tambien tiene matutino otro dia (no cubre nada el sabado).
    _crear_turno(LUNES1, "2026-05-25", luis, franja="matutino")

    r = cliente.get(f"/api/rota/cobertura?lunes={LUNES1}")
    assert r.status_code == 200, r.text
    eventos = r.json()["eventos"]
    cubrir_tarde = next(e for e in eventos if e["id"] == ev_tarde["id"])
    cubrir_madru = next(e for e in eventos if e["id"] == ev_madru["id"])
    ids_tarde = {c["miembro_id"] for c in cubrir_tarde["cobertura"]}
    assert ids_tarde == {luis["id"], tescu["id"]}
    # El evento de madrugada cae en franja descanso -> sin cobertura.
    assert cubrir_madru["cobertura"] == []


def test_cobertura_evento_uno_solo(cliente):
    equipo = _crear_equipo(1)
    ev = _crear_evento(cliente, fecha=SAB1, hora="16:00")
    _crear_turno(LUNES1, SAB1, equipo[0], franja="vespertino")
    r = cliente.get(f"/api/rota/cobertura/evento/{ev['id']}")
    assert r.status_code == 200, r.text
    cobertura = r.json()["evento"]["cobertura"]
    assert len(cobertura) == 1
    assert cobertura[0]["miembro_id"] == equipo[0]["id"]


def test_cobertura_evento_inexistente_404(cliente):
    r = cliente.get("/api/rota/cobertura/evento/no-existe")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Ausencias / vacaciones                                                       #
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
    lista = cliente.get("/api/rota/ausencias").json()["ausencias"]
    assert any(x["id"] == a["id"] for x in lista)
    p = cliente.patch(f"/api/rota/ausencias/{a['id']}", json={"tipo": "baja"})
    assert p.status_code == 200
    assert p.json()["ausencia"]["tipo"] == "baja"
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
# Export .xlsx / CSV                                                           #
# --------------------------------------------------------------------------- #


def test_export_csv(cliente):
    equipo = _crear_equipo(1)
    _crear_evento(cliente, titulo="Final", fecha=SAB1, hora="16:00", contenido="Resumen")
    _crear_turno(LUNES1, SAB1, equipo[0], franja="vespertino")
    r = cliente.get(f"/api/rota/export.csv?lunes={LUNES1}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    texto = r.text
    assert "Qué sacar" in texto
    assert "Final" in texto and "Resumen" in texto


def test_export_xlsx(cliente):
    equipo = _crear_equipo(1)
    _crear_evento(cliente, titulo="Final", fecha=SAB1, hora="16:00")
    _crear_turno(LUNES1, SAB1, equipo[0], franja="vespertino")
    r = cliente.get(f"/api/rota/export.xlsx?lunes={LUNES1}")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"


def test_export_csv_semana_vacia_no_rompe(cliente):
    r = cliente.get("/api/rota/export.csv")
    assert r.status_code == 200
    assert "Fecha" in r.text


def test_export_xlsx_incluye_hoja_horario(cliente):
    import io
    import zipfile

    equipo = _crear_equipo(1)
    _crear_evento(cliente, titulo="Final", fecha=SAB1, hora="16:00")
    _crear_turno(LUNES1, SAB1, equipo[0], franja="vespertino")
    r = cliente.get(f"/api/rota/export.xlsx?lunes={LUNES1}")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        workbook = z.read("xl/workbook.xml").decode("utf-8")
    assert "Rota" in workbook
    assert "Horario equipo" in workbook


# --------------------------------------------------------------------------- #
# Copia de semana + carga                                                      #
# --------------------------------------------------------------------------- #


def test_copiar_semana_replica_turnos_con_offset(cliente):
    equipo = _crear_equipo(2)
    luis, tescu = equipo[0], equipo[1]
    _crear_turno(LUNES1, "2026-05-25", luis, franja="matutino")
    _crear_turno(LUNES1, "2026-05-25", tescu, franja="vespertino")
    _crear_turno(LUNES1, SAB1, luis, franja="descanso")
    _crear_turno(LUNES1, SAB1, tescu, franja="matutino")
    r = cliente.post(
        "/api/rota/copiar-semana",
        json={"de_lunes": LUNES1, "a_lunes": LUNES2},
    )
    assert r.status_code == 200, r.text
    assert r.json()["copiados"] == 4
    semana2 = cliente.get(f"/api/rota/turnos?lunes={LUNES2}").json()
    fechas_franjas = {(t["fecha"], t["miembro_id"], t["franja"]) for t in semana2["turnos"]}
    assert (LUNES2, luis["id"], "matutino") in fechas_franjas
    assert (LUNES2, tescu["id"], "vespertino") in fechas_franjas
    assert (SAB2, luis["id"], "descanso") in fechas_franjas
    assert (SAB2, tescu["id"], "matutino") in fechas_franjas
    assert all(t["estado"] == "propuesto" for t in semana2["turnos"])


def test_copiar_semana_misma_origen_destino_400(cliente):
    r = cliente.post(
        "/api/rota/copiar-semana",
        json={"de_lunes": LUNES1, "a_lunes": LUNES1},
    )
    assert r.status_code == 400


def test_copiar_semana_reemplazar(cliente):
    equipo = _crear_equipo(1)
    luis = equipo[0]
    _crear_turno(LUNES1, "2026-05-25", luis, franja="matutino")
    _crear_turno(LUNES2, LUNES2, luis, franja="descanso")
    r = cliente.post(
        "/api/rota/copiar-semana",
        json={"de_lunes": LUNES1, "a_lunes": LUNES2, "reemplazar": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["copiados"] == 1
    semana2 = cliente.get(f"/api/rota/turnos?lunes={LUNES2}").json()
    assert semana2["total"] == 1
    assert semana2["turnos"][0]["franja"] == "matutino"


def test_carga_resumen_por_persona(cliente):
    """Cobertura DERIVADA: los turnos que cubren franja+fecha de eventos cuentan.

    Defaults franjas (#185): matutino 08-16, vespertino 16-24.
    """
    equipo = _crear_equipo(2)
    tescu, luis = equipo[0], equipo[1]
    # 5 eventos vespertinos lunes-viernes + 1 evento sabado vespertino.
    eventos_fechas = ["2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", SAB1]
    for i, f in enumerate(eventos_fechas):
        _crear_evento(cliente, titulo=f"E{i}", fecha=f, hora="18:00")
    # Tescu vespertino lun-vie + sabado vespertino + 1 descanso (jueves).
    for f in ["2026-05-25", "2026-05-26", "2026-05-27", "2026-05-29", SAB1]:
        _crear_turno(LUNES1, f, tescu, franja="vespertino")
    _crear_turno(LUNES1, "2026-05-28", tescu, franja="descanso")
    # Luis sin cobertura (matutino los dias entre semana solamente).
    _crear_turno(LUNES1, "2026-05-25", luis, franja="matutino")
    _crear_turno(LUNES1, "2026-05-26", luis, franja="matutino")

    r = cliente.get(f"/api/rota/carga?lunes={LUNES1}")
    assert r.status_code == 200, r.text
    miembros = r.json()["miembros"]
    # Ordenado por eventos desc: Tescu primero.
    tescu_carga = next(m for m in miembros if m["nombre"] == tescu["usuario"])
    luis_carga = next(m for m in miembros if m["nombre"] == luis["usuario"])
    # Tescu cubre los 5 vespertinos lun-vie (jueves se salta, es descanso) + el sabado.
    # Concretamente: lun, mar, mie (no jueves), vie, sab -> 5 eventos.
    assert tescu_carga["eventos"] == 5
    assert tescu_carga["sabado"] is True
    assert tescu_carga["descansos"] == 1
    assert luis_carga["eventos"] == 0
    assert luis_carga["sabado"] is False


def test_carga_sin_lunes_400(cliente):
    r = cliente.get("/api/rota/carga")
    assert r.status_code == 400
