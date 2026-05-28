"""Tests de la AMPLIACION del backend de la rota (auditoria post-piloto).

Cubre lo que se anadio al cerrar los gaps que dejo la auditoria:

  - CRUD `rota_turnos` completo: POST directo, DELETE individual, lote/borrar.
  - CRUD `rota_piezas` ampliado: duplicar + lote/borrar; columnas Excel (salida,
    comentarios, fecha_entrega_material, always_on).
  - CRUD `rota_eventos` ampliado: duplicar (sin turnos; `cambiado` reset).
  - Validacion cruzada `rota_turnos_trabajo` vs `rota_ausencias` (override exigido).

Reusa `cliente` (token de mantenimiento) y el aislamiento de `entorno`.
"""

from __future__ import annotations

from keni_consola import auth, repos

CLAVE = "clave-de-prueba"

# Fechas de referencia (sabados consecutivos y un lunes).
SAB1 = "2026-05-30"
LUNES1 = "2026-05-25"
LUNES2 = "2026-06-01"


def _crear_evento(cli, **extra) -> dict:
    base = {"titulo": "Partido", "fecha": SAB1, "hora": "16:00", "contenido": "Clip del gol"}
    base.update(extra)
    r = cli.post("/api/rota/eventos", json=base)
    assert r.status_code == 201, r.text
    return r.json()["evento"]


def _crear_pieza(cli, **extra) -> dict:
    base: dict = {"programa": "MUNDIAL", "contenido_sugerido": "post 1"}
    base.update(extra)
    r = cli.post("/api/rota/piezas", json=base)
    assert r.status_code == 201, r.text
    return r.json()["pieza"]


def _crear_equipo(n: int = 2) -> list[dict]:
    nombres = ["ana", "beto", "caro", "dani"]
    return [auth.crear_usuario(nombres[i], CLAVE, "editor") for i in range(n)]


# --------------------------------------------------------------------------- #
# rota_piezas: nuevos campos del Excel (salida/comentarios/fecha_entrega/always_on)
# --------------------------------------------------------------------------- #


def test_crear_pieza_con_salida_y_comentarios(cliente):
    p = _crear_pieza(
        cliente,
        salida="TV",
        comentarios="Coordinar con Ricardo antes de las 18h",
        fecha_entrega_material="2026-05-28",
    )
    assert p["salida"] == "TV"
    assert p["comentarios"] == "Coordinar con Ricardo antes de las 18h"
    assert p["fecha_entrega_material"] == "2026-05-28"


def test_crear_pieza_always_on(cliente):
    """Una pieza always_on puede ir SIN `dia` y se persiste como booleano."""
    p = _crear_pieza(cliente, programa="PATY CANTU", always_on=True, dia="")
    assert p["always_on"] is True
    assert p["dia"] == ""


def test_crear_pieza_fecha_entrega_invalida_400(cliente):
    r = cliente.post(
        "/api/rota/piezas",
        json={"programa": "X", "fecha_entrega_material": "no-fecha"},
    )
    assert r.status_code == 400


def test_actualizar_pieza_salida_y_always_on(cliente):
    p = _crear_pieza(cliente)
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}",
        json={"salida": "RADIO", "always_on": True, "comentarios": "Urgente"},
    )
    assert r.status_code == 200
    pieza = r.json()["pieza"]
    assert pieza["salida"] == "RADIO"
    assert pieza["always_on"] is True
    assert pieza["comentarios"] == "Urgente"


def test_actualizar_pieza_fecha_entrega_invalida_400(cliente):
    p = _crear_pieza(cliente)
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}",
        json={"fecha_entrega_material": "no-fecha"},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Duplicar pieza                                                                #
# --------------------------------------------------------------------------- #


def test_duplicar_pieza_resetea_workflow(cliente):
    """Duplicar una pieza reinicia material/contenido/publicado/enlace y estado."""
    original = _crear_pieza(
        cliente,
        programa="MUNDIAL",
        contenido_sugerido="post inicial",
        material_entregado=True,
        contenido_entregado=True,
        publicado=True,
        enlace="https://example.com/post/abc",
        estado="publicado",
        salida="TV",
        comentarios="ya publicado",
        notas="post-mortem",
        always_on=True,
    )
    r = cliente.post(f"/api/rota/piezas/{original['id']}/duplicar", json={})
    assert r.status_code == 201, r.text
    clon = r.json()["pieza"]
    assert clon["id"] != original["id"]
    # Campos editoriales que sí viajan.
    assert clon["programa"] == "MUNDIAL"
    assert clon["contenido_sugerido"] == "post inicial"
    assert clon["salida"] == "TV"
    assert clon["always_on"] is True
    # Workflow RESET.
    assert clon["estado"] == "pendiente"
    assert clon["material_entregado"] is False
    assert clon["contenido_entregado"] is False
    assert clon["publicado"] is False
    assert clon["enlace"] == ""
    # Comentarios y notas NO viajan al clon (contexto del original).
    assert clon["comentarios"] == ""
    assert clon["notas"] == ""


def test_duplicar_pieza_con_nuevo_dia(cliente):
    """Caso comun: duplicar para una nueva jornada -> nuevo `dia`."""
    original = _crear_pieza(cliente, dia="2026-06-01")
    r = cliente.post(
        f"/api/rota/piezas/{original['id']}/duplicar", json={"dia": "2026-06-08"}
    )
    assert r.status_code == 201
    assert r.json()["pieza"]["dia"] == "2026-06-08"


def test_duplicar_pieza_inexistente_404(cliente):
    r = cliente.post("/api/rota/piezas/no-existe/duplicar", json={})
    assert r.status_code == 404


def test_duplicar_pieza_evento_inexistente_400(cliente):
    original = _crear_pieza(cliente)
    r = cliente.post(
        f"/api/rota/piezas/{original['id']}/duplicar",
        json={"evento_id": "no-existe"},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Lote: borrar piezas                                                           #
# --------------------------------------------------------------------------- #


def test_borrar_piezas_lote(cliente):
    p1 = _crear_pieza(cliente, contenido_sugerido="a")
    p2 = _crear_pieza(cliente, contenido_sugerido="b")
    p3 = _crear_pieza(cliente, contenido_sugerido="c")
    r = cliente.post(
        "/api/rota/piezas/lote/borrar", json={"ids": [p1["id"], p2["id"]]}
    )
    assert r.status_code == 200
    assert r.json()["borrados"] == 2
    assert r.json()["no_encontrados"] == []
    # p3 sobrevive.
    restantes = cliente.get("/api/rota/piezas").json()["piezas"]
    ids = {p["id"] for p in restantes}
    assert p3["id"] in ids
    assert p1["id"] not in ids


def test_borrar_piezas_lote_tolerante_a_no_encontrados(cliente):
    p1 = _crear_pieza(cliente)
    r = cliente.post(
        "/api/rota/piezas/lote/borrar",
        json={"ids": [p1["id"], "no-existe-1", "no-existe-2"]},
    )
    assert r.status_code == 200
    assert r.json()["borrados"] == 1
    assert sorted(r.json()["no_encontrados"]) == ["no-existe-1", "no-existe-2"]


def test_borrar_piezas_lote_sin_ids_400(cliente):
    r = cliente.post("/api/rota/piezas/lote/borrar", json={"ids": []})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Duplicar evento                                                               #
# --------------------------------------------------------------------------- #


def test_duplicar_evento_sin_turnos_y_cambiado_reset(cliente):
    """Duplicar un evento NO arrastra sus turnos y reinicia `cambiado`."""
    equipo = _crear_equipo(1)
    original = _crear_evento(cliente, titulo="Pumas vs America J17", hora="16:00")
    # Lo marcamos como reprogramado (cambiado=1) y le ponemos un turno.
    cliente.patch(f"/api/rota/eventos/{original['id']}", json={"hora": "18:00"})
    repos.crear_turno_rota(
        LUNES1, original["id"],
        miembro_id=equipo[0]["id"], miembro_nombre=equipo[0]["usuario"],
    )
    # Verifica que se marco cambiado.
    actualizado = cliente.get(
        f"/api/rota/eventos?desde={SAB1}&hasta={SAB1}"
    ).json()["eventos"]
    assert any(e["id"] == original["id"] and e["cambiado"] for e in actualizado)

    # Duplicar para Jornada 18 (nueva fecha y titulo).
    r = cliente.post(
        f"/api/rota/eventos/{original['id']}/duplicar",
        json={"fecha": "2026-06-06", "titulo": "Pumas vs America J18"},
    )
    assert r.status_code == 201, r.text
    clon = r.json()["evento"]
    assert clon["id"] != original["id"]
    assert clon["fecha"] == "2026-06-06"
    assert clon["titulo"] == "Pumas vs America J18"
    # cambiado reset: es un evento nuevo, no reprogramado.
    assert clon["cambiado"] is False
    # NO se clonan turnos (la cobertura es de la semana).
    semana2 = cliente.get(f"/api/rota/semana?lunes={LUNES2}").json()
    assert all(t["evento_id"] != clon["id"] for t in semana2["turnos"])


def test_duplicar_evento_inexistente_404(cliente):
    r = cliente.post("/api/rota/eventos/no-existe/duplicar", json={})
    assert r.status_code == 404


def test_duplicar_evento_titulo_vacio_400(cliente):
    original = _crear_evento(cliente)
    r = cliente.post(
        f"/api/rota/eventos/{original['id']}/duplicar", json={"titulo": "   "}
    )
    assert r.status_code == 400


def test_duplicar_evento_fecha_invalida_400(cliente):
    original = _crear_evento(cliente)
    r = cliente.post(
        f"/api/rota/eventos/{original['id']}/duplicar", json={"fecha": "no-fecha"}
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Turnos cobertura: POST directo, DELETE individual, lote/borrar                #
# --------------------------------------------------------------------------- #


def test_crear_turno_directo(cliente):
    equipo = _crear_equipo(1)
    ev = _crear_evento(cliente)
    r = cliente.post(
        "/api/rota/turnos",
        json={"evento_id": ev["id"], "miembro_id": equipo[0]["id"]},
    )
    assert r.status_code == 201, r.text
    turno = r.json()["turno"]
    assert turno["evento_id"] == ev["id"]
    assert turno["miembro_id"] == equipo[0]["id"]
    # Aparece en la semana del evento.
    semana = cliente.get(f"/api/rota/semana?lunes={LUNES1}").json()
    assert any(t["id"] == turno["id"] for t in semana["turnos"])


def test_crear_turno_vacio_sin_miembro(cliente):
    """Se puede crear un turno SIN asignar (Elías deja huecos a propósito)."""
    ev = _crear_evento(cliente)
    r = cliente.post("/api/rota/turnos", json={"evento_id": ev["id"]})
    assert r.status_code == 201
    assert r.json()["turno"]["miembro_id"] == ""


def test_crear_turno_evento_inexistente_400(cliente):
    r = cliente.post("/api/rota/turnos", json={"evento_id": "no-existe"})
    assert r.status_code == 400


def test_crear_turno_miembro_inexistente_400(cliente):
    ev = _crear_evento(cliente)
    r = cliente.post(
        "/api/rota/turnos",
        json={"evento_id": ev["id"], "miembro_id": "no-existe"},
    )
    assert r.status_code == 400


def test_crear_turno_repite_sabado_sin_override_409(cliente):
    """Mismas reglas que el PATCH: sabado consecutivo sin override -> 409."""
    equipo = _crear_equipo(1)
    ana = equipo[0]
    # Semana 1: ana cubre el sabado.
    ev1 = _crear_evento(cliente, fecha=SAB1)
    repos.crear_turno_rota(
        LUNES1, ev1["id"], miembro_id=ana["id"], miembro_nombre=ana["usuario"]
    )
    # Semana 2: intentamos crear un turno para ana en el sabado siguiente.
    ev2 = _crear_evento(cliente, fecha="2026-06-06")
    r = cliente.post(
        "/api/rota/turnos",
        json={"evento_id": ev2["id"], "miembro_id": ana["id"]},
    )
    assert r.status_code == 409
    assert r.json()["requiere_override"] is True


def test_crear_turno_evento_sin_fecha_400(cliente):
    """Sin fecha en el evento no podemos derivar la semana -> 400 con mensaje claro."""
    ev = _crear_evento(cliente)
    # Limpiamos la fecha del evento. Usamos repos para saltarnos la validacion del PATCH.
    from keni_consola import db
    con = db.conectar()
    try:
        con.execute("UPDATE rota_eventos SET fecha = ? WHERE id = ?", ("", ev["id"]))
        con.commit()
    finally:
        con.close()
    r = cliente.post("/api/rota/turnos", json={"evento_id": ev["id"]})
    assert r.status_code == 400


def test_borrar_turno_individual(cliente):
    equipo = _crear_equipo(1)
    ev = _crear_evento(cliente)
    turno = repos.crear_turno_rota(
        LUNES1, ev["id"], miembro_id=equipo[0]["id"], miembro_nombre=equipo[0]["usuario"]
    )
    # Borrar.
    r = cliente.delete(f"/api/rota/turnos/{turno['id']}")
    assert r.status_code == 200
    # Idempotencia: re-borrar -> 404.
    assert cliente.delete(f"/api/rota/turnos/{turno['id']}").status_code == 404


def test_borrar_turno_aprobado_se_permite(cliente):
    """DECISION: borrar un turno APROBADO se permite (Elías rectifica tras publicar)."""
    equipo = _crear_equipo(1)
    ev = _crear_evento(cliente)
    turno = repos.crear_turno_rota(
        LUNES1, ev["id"], miembro_id=equipo[0]["id"], miembro_nombre=equipo[0]["usuario"]
    )
    repos.aprobar_semana_rota(LUNES1)
    r = cliente.delete(f"/api/rota/turnos/{turno['id']}")
    assert r.status_code == 200


def test_borrar_turnos_lote(cliente):
    equipo = _crear_equipo(1)
    evs = [
        _crear_evento(cliente, titulo=f"E{i}", fecha="2026-05-26", hora=f"{14 + i}:00")
        for i in range(3)
    ]
    turnos = [
        repos.crear_turno_rota(
            LUNES1, ev["id"],
            miembro_id=equipo[0]["id"], miembro_nombre=equipo[0]["usuario"],
        )
        for ev in evs
    ]
    r = cliente.post(
        "/api/rota/turnos/lote/borrar",
        json={"ids": [turnos[0]["id"], turnos[1]["id"]]},
    )
    assert r.status_code == 200
    assert r.json()["borrados"] == 2
    # turnos[2] sobrevive.
    semana = cliente.get(f"/api/rota/semana?lunes={LUNES1}").json()
    ids = {t["id"] for t in semana["turnos"]}
    assert turnos[2]["id"] in ids
    assert turnos[0]["id"] not in ids


def test_borrar_turnos_lote_no_encontrados(cliente):
    equipo = _crear_equipo(1)
    ev = _crear_evento(cliente)
    t = repos.crear_turno_rota(
        LUNES1, ev["id"], miembro_id=equipo[0]["id"], miembro_nombre=equipo[0]["usuario"]
    )
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
# Horario: validacion cruzada con ausencias                                     #
# --------------------------------------------------------------------------- #


def test_editar_horario_turnos_persona_ausente_exige_override(cliente):
    """Asignar a una persona AUSENTE en su rango devuelve 409 con la ausencia."""
    equipo = _crear_equipo(2)
    ana, beto = equipo[0], equipo[1]
    # Ana esta de vacaciones esa semana.
    repos.crear_ausencia_rota(
        ana["id"], "2026-05-25", "2026-05-31",
        miembro_nombre=ana["usuario"], tipo="vacaciones",
    )
    # Hay un turno de trabajo en esa fecha asignado a beto.
    turno = repos.crear_turno_trabajo_rota(
        LUNES1, "2026-05-27",
        miembro_id=beto["id"], miembro_nombre=beto["usuario"], franja="matutino",
    )
    # Intentar pasarlo a ana SIN override -> 409 con la ausencia.
    r = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}",
        json={"miembro_id": ana["id"], "franja": "matutino"},
    )
    assert r.status_code == 409, r.text
    cuerpo = r.json()
    assert cuerpo["requiere_override"] is True
    assert cuerpo["ausencia"]["tipo"] == "vacaciones"
    assert cuerpo["ausencia"]["desde"] == "2026-05-25"

    # Con override SI se permite (cobertura excepcional).
    r_ok = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}",
        json={
            "miembro_id": ana["id"], "franja": "matutino",
            "override": True, "motivo": "Acepto cubrir aunque estoy de vacaciones",
        },
    )
    assert r_ok.status_code == 200, r_ok.text


def test_editar_horario_descanso_no_choca_con_ausencia(cliente):
    """`descanso` ES legal incluso si la persona esta ausente (no es jornada laboral)."""
    equipo = _crear_equipo(1)
    ana = equipo[0]
    repos.crear_ausencia_rota(
        ana["id"], "2026-05-25", "2026-05-31",
        miembro_nombre=ana["usuario"], tipo="vacaciones",
    )
    turno = repos.crear_turno_trabajo_rota(
        LUNES1, "2026-05-27",
        miembro_id=ana["id"], miembro_nombre=ana["usuario"], franja="descanso",
    )
    # Editar la franja sin cambiar el miembro a otra de TRABAJO siendo ausente -> 409.
    r_bad = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}", json={"franja": "matutino"}
    )
    assert r_bad.status_code == 409
    # Mantener `descanso` -> 200 (sin choque).
    r_ok = cliente.patch(
        f"/api/rota/horario/turnos/{turno['id']}", json={"franja": "descanso"}
    )
    assert r_ok.status_code == 200
