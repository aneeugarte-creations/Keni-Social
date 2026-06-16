"""Tests de la API de franjas POR SEMANA (`#XYZ Mundial`).

Cobertura del CRUD `/api/rota/semana/{lunes}/franjas` + `/api/rota/franjas/{id}`:
  - GET siembra por defecto (3 franjas: Mañana, Tarde, Descanso).
  - POST crear extra; con nombre duplicado -> 409.
  - PATCH renombrar/ajustar rangos.
  - DELETE: con turnos -> 409; con `?forzar=true` -> cascada.
  - POST `/api/rota/turnos` con `franja_id` de Descanso: OK, pero NO aparece en cobertura.
  - Cobertura con SOLAPE: 3 franjas + evento en franja solapada -> UNION.

Reutiliza la fixture `cliente` (token de mantenimiento) y un admin opcional para los
endpoints que exigen rol admin.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
LUNES = "2026-06-08"  # semana del Mundial (caso real)
# GRID POR MARCA: la rejilla solo se siembra para una marca concreta; usamos el piloto.
MARCA = "claro-sports"


def _cli_admin(app) -> TestClient:
    """TestClient autenticado como admin (sesion)."""
    cli = TestClient(app)
    auth.crear_usuario("elias", CLAVE, "admin")
    r = cli.post(
        "/api/auth/login",
        json={"usuario": "elias", "password": CLAVE},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    return cli


# --------------------------------------------------------------------------- #
# GET /api/rota/semana/{lunes}/franjas: siembra por defecto                    #
# --------------------------------------------------------------------------- #


def test_listar_franjas_siembra_por_defecto(cliente):
    """Si la semana no tiene franjas, GET con `?marca=` siembra: Mañana, Tarde, Descanso."""
    r = cliente.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    assert r.status_code == 200, r.text
    franjas = r.json()["franjas"]
    nombres = [f["nombre"] for f in franjas]
    assert nombres == ["Mañana", "Tarde", "Descanso"]
    # La de descanso tiene el flag y rangos triviales.
    descanso = next(f for f in franjas if f["es_descanso"])
    assert descanso["inicio"] == "00:00" and descanso["fin"] == "00:00"
    assert descanso["orden"] == 999
    # Las dos primeras no son descanso.
    manana = next(f for f in franjas if f["nombre"] == "Mañana")
    assert manana["es_descanso"] is False
    assert manana["orden"] == 0


def test_listar_franjas_lunes_invalido_400(cliente):
    r = cliente.get("/api/rota/semana/no-fecha/franjas")
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# POST /api/rota/semana/{lunes}/franjas: crear extra                            #
# --------------------------------------------------------------------------- #


def test_crear_franja_extra(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    # Siembra defaults primero.
    cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    r = cli.post(
        f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}",
        json={
            "nombre": "Cobertura nocturna",
            "inicio": "17:00",
            "fin": "01:00",
            "orden": 2,
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 201, r.text
    creada = r.json()
    assert creada["nombre"] == "Cobertura nocturna"
    assert creada["inicio"] == "17:00" and creada["fin"] == "01:00"
    assert creada["es_descanso"] is False
    # Ahora la lista tiene 4 franjas.
    franjas = cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}").json()["franjas"]
    nombres = {f["nombre"] for f in franjas}
    assert {"Mañana", "Tarde", "Descanso", "Cobertura nocturna"} <= nombres


def test_crear_franja_nombre_duplicado_409(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")  # siembra Mañana/Tarde/Descanso
    r = cli.post(
        f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}",
        json={"nombre": "Mañana", "inicio": "07:00", "fin": "10:00"},
        headers=_ORIGIN,
    )
    assert r.status_code == 409, r.text


def test_crear_franja_no_admin_403(cliente):
    """El cliente por defecto (token de mantenimiento) NO es admin con sesion."""
    cliente.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    r = cliente.post(
        f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}",
        json={"nombre": "Cobertura", "inicio": "17:00", "fin": "01:00"},
    )
    assert r.status_code == 403


def test_crear_franja_hora_invalida_400(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    r = cli.post(
        f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}",
        json={"nombre": "Mala", "inicio": "25:00", "fin": "26:00"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# PATCH /api/rota/franjas/{franja_id}                                          #
# --------------------------------------------------------------------------- #


def test_actualizar_franja(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    franjas = cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}").json()["franjas"]
    manana = next(f for f in franjas if f["nombre"] == "Mañana")
    r = cli.patch(
        f"/api/rota/franjas/{manana['id']}",
        json={"inicio": "09:00", "fin": "17:00"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["inicio"] == "09:00"
    assert r.json()["fin"] == "17:00"


def test_actualizar_franja_inexistente_404(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        "/api/rota/franjas/no-existe", json={"nombre": "X"}, headers=_ORIGIN
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# DELETE /api/rota/franjas/{franja_id}                                         #
# --------------------------------------------------------------------------- #


def test_borrar_franja_sin_turnos(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    # Anade una extra para borrarla (no la Mañana/Tarde/Descanso por costumbre).
    cli.post(
        f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}",
        json={"nombre": "Extra", "inicio": "12:00", "fin": "14:00"},
        headers=_ORIGIN,
    )
    extra = next(
        f for f in cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}").json()["franjas"]
        if f["nombre"] == "Extra"
    )
    r = cli.delete(f"/api/rota/franjas/{extra['id']}", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    nombres = {
        f["nombre"]
        for f in cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}").json()["franjas"]
    }
    assert "Extra" not in nombres


def test_borrar_franja_con_turnos_409(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    ana = auth.crear_usuario("ana", CLAVE, "editor", cobertura=True)
    # Siembra defaults y consigue id de Mañana.
    cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    franjas = cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}").json()["franjas"]
    manana = next(f for f in franjas if f["nombre"] == "Mañana")
    # Crea un turno asignado a la franja Mañana.
    repos.crear_turno_rota(
        LUNES, LUNES,
        miembro_id=ana["id"], miembro_nombre="ana", franja_id=manana["id"],
    )
    # Borrar sin `forzar` falla con 409.
    r = cli.delete(f"/api/rota/franjas/{manana['id']}", headers=_ORIGIN)
    assert r.status_code == 409
    assert r.json()["turnos_asociados"] == 1
    # Con `?forzar=true`, cascada.
    r2 = cli.delete(
        f"/api/rota/franjas/{manana['id']}?forzar=true", headers=_ORIGIN
    )
    assert r2.status_code == 200
    assert r2.json()["turnos_borrados"] == 1


def test_borrar_franja_inexistente_404(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.delete("/api/rota/franjas/no-existe", headers=_ORIGIN)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/rota/turnos con franja descanso: turno valido, NO cubre eventos    #
# --------------------------------------------------------------------------- #


def test_crear_turno_descanso_explicito_y_no_cubre(cliente):
    """Una persona con turno en la franja Descanso de un dia NO aparece como cobertura de
    ningun evento de ese dia."""
    ana = auth.crear_usuario("ana", CLAVE, "editor", cobertura=True)
    # Asegura defaults inicializados (Mañana, Tarde, Descanso).
    cliente.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    franjas = cliente.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}").json()["franjas"]
    descanso = next(f for f in franjas if f["es_descanso"])
    # Crea un evento al mediodia.
    ev = cliente.post(
        "/api/rota/eventos",
        json={"titulo": "Partido", "fecha": LUNES, "hora": "10:00"},
    ).json()["evento"]
    # Crea el turno de ana en la franja Descanso del lunes.
    r = cliente.post(
        "/api/rota/turnos",
        json={"fecha": LUNES, "miembro_id": ana["id"], "franja_id": descanso["id"]},
    )
    assert r.status_code == 201, r.text
    # La cobertura del evento NO incluye a ana (descanso no cubre).
    cob = cliente.get(f"/api/rota/cobertura/evento/{ev['id']}").json()["evento"][
        "cobertura"
    ]
    assert ana["id"] not in {c["miembro_id"] for c in cob}


# --------------------------------------------------------------------------- #
# Cobertura con SOLAPE: 3 franjas + evento en franja solapada -> UNION         #
# --------------------------------------------------------------------------- #


def test_cobertura_evento_con_solape_es_union(entorno):
    """Mundial mié 10 jun: 3 franjas con solape (Mañana 09-17, Tarde 13-21, Noche 17-01).
    Un evento a las 14:00 cae en 2 franjas activas (Mañana y Tarde); la cobertura es la
    UNION de las personas con turno en alguna de esas franjas."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    # Crear personas (cobertura=True para entrar en el equipo de rota).
    a = auth.crear_usuario("a", CLAVE, "editor", cobertura=True)
    b = auth.crear_usuario("b", CLAVE, "editor", cobertura=True)
    c = auth.crear_usuario("c", CLAVE, "editor", cobertura=True)

    # Inicializar las 3 franjas en la semana del Mundial (Mañana, Tarde, Descanso).
    cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}")
    franjas = cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}").json()["franjas"]
    manana = next(f for f in franjas if f["nombre"] == "Mañana")
    tarde = next(f for f in franjas if f["nombre"] == "Tarde")
    # Ajusta Mañana a 09-17, Tarde a 13-21 (el solape).
    assert cli.patch(
        f"/api/rota/franjas/{manana['id']}",
        json={"inicio": "09:00", "fin": "17:00"},
        headers=_ORIGIN,
    ).status_code == 200
    assert cli.patch(
        f"/api/rota/franjas/{tarde['id']}",
        json={"inicio": "13:00", "fin": "21:00"},
        headers=_ORIGIN,
    ).status_code == 200
    # Anade una Noche 17:00-01:00 que cruza medianoche.
    r_noche = cli.post(
        f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}",
        json={"nombre": "Noche", "inicio": "17:00", "fin": "01:00", "orden": 2},
        headers=_ORIGIN,
    )
    assert r_noche.status_code == 201, r_noche.text
    noche = r_noche.json()

    # Un evento al miercoles 14:00 (cae en Mañana y Tarde, no en Noche).
    miercoles = "2026-06-10"
    ev = cli.post(
        "/api/rota/eventos",
        json={"titulo": "Final", "fecha": miercoles, "hora": "14:00"},
        headers=_ORIGIN,
    ).json()["evento"]

    # Inicializamos: a en Mañana, b en Tarde, c en Noche (Noche no aplica a las 14:00).
    repos.crear_turno_rota(
        LUNES, miercoles, miembro_id=a["id"], miembro_nombre="a",
        franja_id=manana["id"],
    )
    repos.crear_turno_rota(
        LUNES, miercoles, miembro_id=b["id"], miembro_nombre="b",
        franja_id=tarde["id"],
    )
    repos.crear_turno_rota(
        LUNES, miercoles, miembro_id=c["id"], miembro_nombre="c",
        franja_id=noche["id"],
    )

    # Cobertura = UNION de Mañana y Tarde = {a, b}. c NO cubre (su franja no esta activa).
    cob = cli.get(
        f"/api/rota/cobertura/evento/{ev['id']}", headers=_ORIGIN
    ).json()["evento"]["cobertura"]
    ids = {c_["miembro_id"] for c_ in cob}
    assert ids == {a["id"], b["id"]}


# --------------------------------------------------------------------------- #
# PLANTILLA de franjas (lista flexible): GET/PATCH /api/rota/config/franjas    #
# y su efecto al sembrar una semana nueva.                                     #
# --------------------------------------------------------------------------- #


def test_config_franjas_get_default_es_lista(cliente):
    """Sin fila guardada, GET devuelve la plantilla por defecto como LISTA (Mañana, Tarde).

    "Descanso" NO va en la plantilla (la añade aparte la siembra de la semana)."""
    r = cliente.get(f"/api/rota/config/franjas?marca={MARCA}")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    franjas = cuerpo["franjas"]
    assert isinstance(franjas, list)
    assert [f["nombre"] for f in franjas] == ["Mañana", "Tarde"]
    manana = franjas[0]
    assert manana["inicio"] == "08:00" and manana["fin"] == "16:00"
    assert franjas[1]["inicio"] == "16:00" and franjas[1]["fin"] == "24:00"


def test_plantilla_franjas_guardar_y_releer(entorno):
    """Admin PATCH una plantilla de 3 franjas (con Nocturna); GET la devuelve igual."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        f"/api/rota/config/franjas?marca={MARCA}",
        json={
            "franjas": [
                {"nombre": "Mañana", "inicio": "08:00", "fin": "16:00"},
                {"nombre": "Tarde", "inicio": "16:00", "fin": "24:00"},
                {"nombre": "Nocturna", "inicio": "00:00", "fin": "08:00"},
            ]
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    guardadas = r.json()["franjas"]
    assert [f["nombre"] for f in guardadas] == ["Mañana", "Tarde", "Nocturna"]
    # Releer por GET devuelve lo mismo (persistio en la columna JSON).
    releidas = cli.get(f"/api/rota/config/franjas?marca={MARCA}").json()["franjas"]
    noct = next(f for f in releidas if f["nombre"] == "Nocturna")
    assert noct["inicio"] == "00:00" and noct["fin"] == "08:00"


def test_plantilla_franjas_siembra_nocturna_en_semana_nueva(entorno):
    """Tras guardar una plantilla con «Nocturna», una semana NUEVA se siembra con ella.

    Es el objetivo del cambio: la plantilla flexible mete una 3a franja en cada semana nueva
    (antes la plantilla eran 2 columnas fijas mañana/tarde y no cabia)."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    cli.patch(
        f"/api/rota/config/franjas?marca={MARCA}",
        json={
            "franjas": [
                {"nombre": "Mañana", "inicio": "08:00", "fin": "16:00"},
                {"nombre": "Tarde", "inicio": "16:00", "fin": "24:00"},
                {"nombre": "Nocturna", "inicio": "00:00", "fin": "08:00"},
            ]
        },
        headers=_ORIGIN,
    )
    # Primer GET de la semana => siembra desde la plantilla recien guardada.
    franjas = cli.get(f"/api/rota/semana/{LUNES}/franjas?marca={MARCA}").json()["franjas"]
    nombres = [f["nombre"] for f in franjas]
    assert {"Mañana", "Tarde", "Nocturna", "Descanso"} == set(nombres)
    noct = next(f for f in franjas if f["nombre"] == "Nocturna")
    assert noct["inicio"] == "00:00" and noct["fin"] == "08:00"
    assert noct["es_descanso"] is False
    # "Descanso" sigue siendo la ultima (orden alto) y con su flag.
    descanso = next(f for f in franjas if f["nombre"] == "Descanso")
    assert descanso["es_descanso"] is True and descanso["orden"] == 999


def test_plantilla_franjas_rechaza_descanso(entorno):
    """«Descanso» es reservado (lo añade la siembra): no se admite en la plantilla -> 400."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        f"/api/rota/config/franjas?marca={MARCA}",
        json={
            "franjas": [
                {"nombre": "Mañana", "inicio": "08:00", "fin": "16:00"},
                {"nombre": "Descanso", "inicio": "00:00", "fin": "00:00"},
            ]
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 400, r.text


def test_plantilla_franjas_rechaza_duplicados(entorno):
    """Dos franjas con el mismo nombre (la siembra usa el nombre como clave) -> 400."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        f"/api/rota/config/franjas?marca={MARCA}",
        json={
            "franjas": [
                {"nombre": "Mañana", "inicio": "08:00", "fin": "16:00"},
                {"nombre": "mañana", "inicio": "16:00", "fin": "20:00"},
            ]
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 400, r.text


def test_plantilla_franjas_rechaza_lista_vacia(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        f"/api/rota/config/franjas?marca={MARCA}",
        json={"franjas": []},
        headers=_ORIGIN,
    )
    assert r.status_code == 400, r.text


def test_plantilla_franjas_rechaza_hora_invalida(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        f"/api/rota/config/franjas?marca={MARCA}",
        json={"franjas": [{"nombre": "Mala", "inicio": "25:00", "fin": "26:00"}]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400, r.text


def test_plantilla_franjas_rechaza_inicio_despues_de_fin(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        f"/api/rota/config/franjas?marca={MARCA}",
        json={"franjas": [{"nombre": "Rara", "inicio": "16:00", "fin": "08:00"}]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400, r.text


def test_plantilla_franjas_patch_no_admin_403(cliente):
    """El cliente por defecto (token de mantenimiento) NO es admin con sesion -> 403."""
    r = cliente.patch(
        f"/api/rota/config/franjas?marca={MARCA}",
        json={"franjas": [{"nombre": "Mañana", "inicio": "08:00", "fin": "16:00"}]},
    )
    assert r.status_code == 403


def test_plantilla_franjas_patch_sin_marca_400(entorno):
    """Editar la plantilla exige una marca concreta (no "Todas") -> 400."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        "/api/rota/config/franjas",
        json={"franjas": [{"nombre": "Mañana", "inicio": "08:00", "fin": "16:00"}]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400, r.text
