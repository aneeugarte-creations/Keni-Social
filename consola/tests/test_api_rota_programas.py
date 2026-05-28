"""Tests de la API `/api/rota/programas` (#150 PARRILLA 2026.xlsx). Todo OFFLINE.

Cubre el CRUD del catalogo de programas evergreen ("Álvaro Fidalgo", "Real Oviedo",
"Anfitriones", "PATY CANTU", "MUNDIAL", "LA SELECCIÓN EN TUS MANOS", "IDEAS SIN DERECHOS"
del Excel) + la cascada de renombre sobre `rota_piezas.programa` y el cerrojo de borrado
cuando hay piezas que lo usan.

Reusa la fixture `cliente` (token de mantenimiento) y el aislamiento de `entorno`.
"""

from __future__ import annotations


def _crear_programa(cli, **extra) -> dict:
    base = {"nombre": "MUNDIAL", "color": "#FF3300", "descripcion": "Mundial 2026"}
    base.update(extra)
    r = cli.post("/api/rota/programas", json=base)
    assert r.status_code == 201, r.text
    return r.json()["programa"]


# --------------------------------------------------------------------------- #
# Crear / listar                                                                #
# --------------------------------------------------------------------------- #


def test_crear_programa_minimo(cliente):
    p = _crear_programa(cliente, nombre="Álvaro Fidalgo")
    assert p["id"]
    assert p["nombre"] == "Álvaro Fidalgo"
    assert p["activo"] is True
    assert p["creado"]
    assert p["actualizado"]


def test_crear_programa_con_color_y_fechas(cliente):
    p = _crear_programa(
        cliente,
        nombre="PATY CANTU",
        color="#8800FF",
        inicio="2026-05-01",
        fin="2026-08-31",
        descripcion="Campaña promocional 2026",
    )
    assert p["color"] == "#8800FF"
    assert p["inicio"] == "2026-05-01"
    assert p["fin"] == "2026-08-31"


def test_crear_programa_sin_nombre_400(cliente):
    r = cliente.post("/api/rota/programas", json={"color": "#ABC"})
    assert r.status_code == 400


def test_crear_programa_duplicado_409_case_insensitive(cliente):
    _crear_programa(cliente, nombre="MUNDIAL")
    r = cliente.post("/api/rota/programas", json={"nombre": "Mundial"})
    assert r.status_code == 409
    assert r.json()["programa_existente"] is True


def test_crear_programa_fechas_invertidas_400(cliente):
    r = cliente.post(
        "/api/rota/programas",
        json={"nombre": "X", "inicio": "2026-08-31", "fin": "2026-05-01"},
    )
    assert r.status_code == 400


def test_crear_programa_inicio_invalido_400(cliente):
    r = cliente.post(
        "/api/rota/programas",
        json={"nombre": "X", "inicio": "no-fecha"},
    )
    assert r.status_code == 400


def test_listar_programas_orden_y_filtro_activo(cliente):
    _crear_programa(cliente, nombre="anfitriones")  # lowercase
    _crear_programa(cliente, nombre="MUNDIAL")
    inactivo = _crear_programa(cliente, nombre="Old", activo=False)

    r = cliente.get("/api/rota/programas")
    nombres = [p["nombre"] for p in r.json()["programas"]]
    # Orden alfabetico case-insensitive (ASCII): "anfitriones" < "MUNDIAL" < "Old".
    assert nombres == ["anfitriones", "MUNDIAL", "Old"]

    r_act = cliente.get("/api/rota/programas?activo=true")
    nombres_act = [p["nombre"] for p in r_act.json()["programas"]]
    assert inactivo["nombre"] not in nombres_act
    assert "MUNDIAL" in nombres_act

    r_inact = cliente.get("/api/rota/programas?activo=false")
    nombres_inact = [p["nombre"] for p in r_inact.json()["programas"]]
    assert nombres_inact == ["Old"]


# --------------------------------------------------------------------------- #
# Actualizar (con cascada en rota_piezas)                                       #
# --------------------------------------------------------------------------- #


def test_actualizar_programa_color_y_descripcion(cliente):
    p = _crear_programa(cliente)
    r = cliente.patch(
        f"/api/rota/programas/{p['id']}",
        json={"color": "#000000", "descripcion": "Cobertura ampliada"},
    )
    assert r.status_code == 200
    actualizado = r.json()["programa"]
    assert actualizado["color"] == "#000000"
    assert actualizado["descripcion"] == "Cobertura ampliada"


def test_renombrar_programa_hace_cascada_en_piezas(cliente):
    """Cuando renombro el programa, las piezas que lo referencian se actualizan."""
    p = _crear_programa(cliente, nombre="OLD NAME")
    # Crea piezas con el nombre antiguo.
    cliente.post(
        "/api/rota/piezas",
        json={"programa": "OLD NAME", "contenido_sugerido": "post 1"},
    )
    cliente.post(
        "/api/rota/piezas",
        json={"programa": "OLD NAME", "contenido_sugerido": "post 2"},
    )
    # Una pieza con OTRO nombre no debe cambiar.
    cliente.post(
        "/api/rota/piezas",
        json={"programa": "Real Oviedo", "contenido_sugerido": "post 3"},
    )

    # Renombrar el programa.
    r = cliente.patch(f"/api/rota/programas/{p['id']}", json={"nombre": "NEW NAME"})
    assert r.status_code == 200
    assert r.json()["programa"]["nombre"] == "NEW NAME"

    # Las piezas con el nombre antiguo cambiaron; las del otro programa no.
    todas = cliente.get("/api/rota/piezas").json()["piezas"]
    nombres = [p["programa"] for p in todas]
    assert nombres.count("NEW NAME") == 2
    assert "OLD NAME" not in nombres
    assert "Real Oviedo" in nombres


def test_renombrar_a_un_nombre_ya_existente_409(cliente):
    _crear_programa(cliente, nombre="A")
    b = _crear_programa(cliente, nombre="B")
    r = cliente.patch(f"/api/rota/programas/{b['id']}", json={"nombre": "a"})  # CI
    assert r.status_code == 409
    assert r.json()["programa_existente"] is True


def test_renombrar_al_mismo_nombre_es_no_op(cliente):
    """Renombrar al mismo nombre (case-insensitive) NO choca con su propia unicidad."""
    p = _crear_programa(cliente, nombre="MUNDIAL")
    r = cliente.patch(f"/api/rota/programas/{p['id']}", json={"nombre": "MUNDIAL"})
    assert r.status_code == 200
    assert r.json()["programa"]["nombre"] == "MUNDIAL"


def test_actualizar_programa_fechas_invertidas_400(cliente):
    p = _crear_programa(cliente, inicio="2026-05-01", fin="2026-08-31")
    r = cliente.patch(
        f"/api/rota/programas/{p['id']}", json={"fin": "2026-04-01"}
    )
    assert r.status_code == 400


def test_actualizar_programa_inactivar(cliente):
    p = _crear_programa(cliente)
    r = cliente.patch(f"/api/rota/programas/{p['id']}", json={"activo": False})
    assert r.json()["programa"]["activo"] is False


def test_actualizar_programa_inexistente_404(cliente):
    r = cliente.patch("/api/rota/programas/no-existe", json={"color": "#fff"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Borrar (con cerrojo si esta en uso)                                           #
# --------------------------------------------------------------------------- #


def test_borrar_programa_sin_piezas(cliente):
    p = _crear_programa(cliente)
    r = cliente.delete(f"/api/rota/programas/{p['id']}")
    assert r.status_code == 200
    assert "mensaje" in r.json()
    # Idempotencia: re-borrar -> 404.
    assert cliente.delete(f"/api/rota/programas/{p['id']}").status_code == 404


def test_borrar_programa_en_uso_409(cliente):
    p = _crear_programa(cliente, nombre="MUNDIAL")
    cliente.post(
        "/api/rota/piezas",
        json={"programa": "MUNDIAL", "contenido_sugerido": "post 1"},
    )
    r = cliente.delete(f"/api/rota/programas/{p['id']}")
    assert r.status_code == 409
    cuerpo = r.json()
    assert cuerpo["en_uso"] is True
    assert cuerpo["piezas_afectadas"] == 1


def test_borrar_programa_forzar_true(cliente):
    """Con ?forzar=true se borra aunque haya piezas; estas siguen mostrando el nombre."""
    p = _crear_programa(cliente, nombre="MUNDIAL")
    pieza_r = cliente.post(
        "/api/rota/piezas",
        json={"programa": "MUNDIAL", "contenido_sugerido": "post 1"},
    )
    pieza_id = pieza_r.json()["pieza"]["id"]
    r = cliente.delete(f"/api/rota/programas/{p['id']}?forzar=true")
    assert r.status_code == 200
    assert r.json()["piezas_afectadas"] == 1
    # La pieza huerfana sigue accesible y conserva el texto del programa.
    piezas = cliente.get("/api/rota/piezas").json()["piezas"]
    huerfana = next(p for p in piezas if p["id"] == pieza_id)
    assert huerfana["programa"] == "MUNDIAL"
