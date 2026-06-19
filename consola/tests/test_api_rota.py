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
mano (el coordinador de la rota asigna). Las pruebas de aprobacion (solo-admin) usan una sesion admin real.
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

# Marca canonica del piloto (la rejilla por defecto del grid por marca).
MARCA = "claro-sports"


def _crear_equipo(n: int = 2, *, cobertura: bool = True) -> list[dict]:
    """Crea n usuarios (miembros del equipo) directos en la BD; devuelve su forma pública.

    Por defecto los crea con `cobertura=True` para que el endpoint `/api/rota/equipo`
    (que filtra por cobertura) los devuelva. Tests que quieran un usuario fuera de la
    rota pueden pasar `cobertura=False`.
    """
    nombres = ["ana", "beto", "caro", "dani"]
    return [
        auth.crear_usuario(nombres[i], CLAVE, "editor", cobertura=cobertura)
        for i in range(n)
    ]


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
    marca: str = "",
) -> dict:
    """Siembra un TURNO en la BD (el coordinador de la rota asigna a mano; el backend solo persiste).

    El turno es el horario del miembro en `(fecha, franja)`. NO va atado a un evento.

    GRID POR MARCA: por defecto `marca=""` (rejilla legada, visible en "Todas"). Pasa
    `marca="claro-sports"` cuando el test ejerce una rejilla concreta (aprobar/copiar): el
    literal `franja` siembra las franjas por defecto DE ESA marca y el turno queda en ella.
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
        marca=marca,
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


def test_equipo_filtra_por_cobertura(cliente):
    """`/api/rota/equipo` solo devuelve usuarios con `cobertura=True` por defecto."""
    auth.crear_usuario("cubre", CLAVE, "editor", cobertura=True)
    auth.crear_usuario("nocubre", CLAVE, "editor", cobertura=False)
    r = cliente.get("/api/rota/equipo")
    assert r.status_code == 200
    nombres = {m["nombre"] for m in r.json()["equipo"]}
    assert "cubre" in nombres
    assert "nocubre" not in nombres


def test_equipo_todos_incluye_no_cobertura(cliente):
    """`?todos=1` devuelve TODOS los usuarios, incluido el que no cubre."""
    auth.crear_usuario("cubre", CLAVE, "editor", cobertura=True)
    auth.crear_usuario("nocubre", CLAVE, "editor", cobertura=False)
    r = cliente.get("/api/rota/equipo?todos=1")
    assert r.status_code == 200
    nombres = {m["nombre"] for m in r.json()["equipo"]}
    assert {"cubre", "nocubre"} <= nombres


def test_equipo_incluye_marcas_de_cada_miembro(cliente):
    """`/api/rota/equipo` incluye `marcas` por miembro (organigrama del cliente).

    El frontend filtra por vertical en el cliente; el backend devuelve el conjunto sin
    filtrar y la rota actual se limita a `claro-sports` en la UI.
    """
    auth.crear_usuario(
        "cs", CLAVE, "editor", cobertura=True, marcas=["claro-sports"],
    )
    auth.crear_usuario(
        "ng", CLAVE, "editor", cobertura=True, marcas=["nacion-gamer"],
    )
    r = cliente.get("/api/rota/equipo")
    assert r.status_code == 200
    por_nombre = {m["nombre"]: m for m in r.json()["equipo"]}
    assert por_nombre["cs"]["marcas"] == ["claro-sports"]
    assert por_nombre["ng"]["marcas"] == ["nacion-gamer"]


def test_equipo_incluye_puede_coordinar_por_miembro(cliente):
    """`/api/rota/equipo?todos=1` expone `puede_coordinar` por miembro (ola "coord").

    El flag lo marca el admin desde `/usuarios` (no hay seed). El frontend necesita este
    campo para listar candidatos a coordinador por celda en el calendario (sin él, el
    dropdown muestra "Sin candidatos"). Aquí se crea un candidato y un no-candidato y se
    comprueba que el endpoint refleja el flag fielmente.
    """
    auth.crear_usuario(
        "coord", CLAVE, "editor", cobertura=True, puede_coordinar=True,
        marcas=["claro-sports"],
    )
    auth.crear_usuario(
        "nocoord", CLAVE, "editor", cobertura=True, puede_coordinar=False,
        marcas=["claro-sports"],
    )
    r = cliente.get("/api/rota/equipo?todos=1")
    assert r.status_code == 200
    por_nombre = {m["nombre"]: m for m in r.json()["equipo"]}
    assert por_nombre["coord"]["puede_coordinar"] is True
    assert por_nombre["nocoord"]["puede_coordinar"] is False


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
# Eventos RECURRENTES (serie materializada: una fila por ocurrencia)           #
# --------------------------------------------------------------------------- #
#
# LUNES1 = 2026-05-25 (lunes). La semana 25..31 may = L M X J V S D.
_MIE = "2026-05-27"  # miércoles de esa semana
_VIE = "2026-05-29"  # viernes de esa semana


def _crear_serie(cli, **campos) -> dict:
    """POST /api/rota/eventos con recurrencia; devuelve el cuerpo {eventos, serie_id, total}."""
    base = {
        "titulo": "Peloteando",
        "fecha": LUNES1,
        "dias_semana": [0, 1, 2, 3, 4],
        "repetir_hasta": _VIE,
    }
    base.update(campos)
    r = cli.post("/api/rota/eventos", json=base)
    assert r.status_code == 201, r.text
    return r.json()


def test_crear_evento_suelto_devuelve_evento_con_serie_vacia(cliente):
    """Sin recurrencia el contrato no cambia: {evento} con serie_id="" (evento suelto)."""
    ev = _crear_evento(cliente)
    assert ev["serie_id"] == ""


def test_crear_serie_laborables_materializa_una_fila_por_dia(cliente):
    cuerpo = _crear_serie(cliente)
    assert cuerpo["total"] == 5  # L M X J V
    assert len(cuerpo["eventos"]) == 5
    assert cuerpo["serie_id"]
    fechas = [e["fecha"] for e in cuerpo["eventos"]]
    assert fechas == ["2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]
    # Todas las ocurrencias comparten el mismo serie_id (no vacío).
    assert {e["serie_id"] for e in cuerpo["eventos"]} == {cuerpo["serie_id"]}
    # Y aparecen en el listado del calendario con su serie_id.
    listados = cliente.get("/api/rota/eventos").json()["eventos"]
    de_la_serie = [e for e in listados if e["serie_id"] == cuerpo["serie_id"]]
    assert len(de_la_serie) == 5


def test_crear_serie_sin_repetir_hasta_400(cliente):
    r = cliente.post(
        "/api/rota/eventos",
        json={"titulo": "X", "fecha": LUNES1, "dias_semana": [0, 2, 4]},
    )
    assert r.status_code == 400


def test_crear_serie_dias_invalidos_400(cliente):
    r = cliente.post(
        "/api/rota/eventos",
        json={"titulo": "X", "fecha": LUNES1, "dias_semana": [9], "repetir_hasta": _VIE},
    )
    assert r.status_code == 400


def test_crear_serie_fin_anterior_a_la_base_400(cliente):
    r = cliente.post(
        "/api/rota/eventos",
        json={"titulo": "X", "fecha": _VIE, "dias_semana": [0], "repetir_hasta": LUNES1},
    )
    assert r.status_code == 400


def test_borrar_alcance_serie_borra_todas_las_ocurrencias(cliente):
    cuerpo = _crear_serie(cliente)
    sid = cuerpo["serie_id"]
    medio = cuerpo["eventos"][2]  # miércoles
    d = cliente.delete(f"/api/rota/eventos/{medio['id']}?alcance=serie")
    assert d.status_code == 200
    assert d.json()["eliminados"] == 5
    listados = cliente.get("/api/rota/eventos").json()["eventos"]
    assert [e for e in listados if e["serie_id"] == sid] == []


def test_borrar_alcance_siguientes_conserva_las_anteriores(cliente):
    cuerpo = _crear_serie(cliente)
    sid = cuerpo["serie_id"]
    miercoles = next(e for e in cuerpo["eventos"] if e["fecha"] == _MIE)
    d = cliente.delete(f"/api/rota/eventos/{miercoles['id']}?alcance=siguientes")
    assert d.status_code == 200
    assert d.json()["eliminados"] == 3  # X J V
    quedan = sorted(
        e["fecha"] for e in cliente.get("/api/rota/eventos").json()["eventos"] if e["serie_id"] == sid
    )
    assert quedan == ["2026-05-25", "2026-05-26"]  # L M


def test_borrar_alcance_invalido_400(cliente):
    ev = _crear_evento(cliente)
    r = cliente.delete(f"/api/rota/eventos/{ev['id']}?alcance=humo")
    assert r.status_code == 400


def test_borrar_alcance_serie_en_evento_suelto_borra_solo_ese(cliente):
    """Un evento sin serie ignora el alcance: borra solo ese (no falla)."""
    ev = _crear_evento(cliente)
    d = cliente.delete(f"/api/rota/eventos/{ev['id']}?alcance=serie")
    assert d.status_code == 200
    assert cliente.get("/api/rota/eventos").json()["eventos"] == []


def _titulos_por_fecha(cliente, serie_id):
    """{fecha: titulo} de las ocurrencias de una serie (para comprobar la propagación)."""
    return {
        e["fecha"]: e["titulo"]
        for e in cliente.get("/api/rota/eventos").json()["eventos"]
        if e["serie_id"] == serie_id
    }


def test_editar_alcance_serie_propaga_a_todas_menos_la_fecha(cliente):
    cuerpo = _crear_serie(cliente)
    sid = cuerpo["serie_id"]
    primero = cuerpo["eventos"][0]  # lunes 2026-05-25
    # Renombra (se propaga) y mueve SU fecha a un día FUERA de la semana de la serie (2026-06-15):
    # así las fechas no chocan y se ve claro que la fecha NO se propaga a las demás ocurrencias.
    r = cliente.patch(
        f"/api/rota/eventos/{primero['id']}?alcance=serie",
        json={"titulo": "Renombrado", "fecha": "2026-06-15"},
    )
    assert r.status_code == 200
    assert r.json()["propagados"] == 4  # las otras 4 ocurrencias
    serie = [
        e for e in cliente.get("/api/rota/eventos").json()["eventos"] if e["serie_id"] == sid
    ]
    # El título se propaga a TODA la serie...
    assert {e["titulo"] for e in serie} == {"Renombrado"}
    # ...pero la fecha NO: las otras 4 conservan su día (L-V) y solo la editada se movió al 15.
    assert sorted(e["fecha"] for e in serie) == [
        "2026-05-26",
        "2026-05-27",
        "2026-05-28",
        "2026-05-29",
        "2026-06-15",
    ]


def test_editar_alcance_siguientes_no_toca_las_anteriores(cliente):
    cuerpo = _crear_serie(cliente)
    sid = cuerpo["serie_id"]
    miercoles = next(e for e in cuerpo["eventos"] if e["fecha"] == _MIE)
    r = cliente.patch(
        f"/api/rota/eventos/{miercoles['id']}?alcance=siguientes",
        json={"titulo": "Desde el miércoles"},
    )
    assert r.status_code == 200
    assert r.json()["propagados"] == 2  # jueves y viernes (el miércoles se editó aparte)
    titulos = _titulos_por_fecha(cliente, sid)
    assert titulos["2026-05-25"] == "Peloteando"  # lunes intacto
    assert titulos["2026-05-26"] == "Peloteando"  # martes intacto
    assert titulos["2026-05-27"] == "Desde el miércoles"
    assert titulos["2026-05-28"] == "Desde el miércoles"
    assert titulos["2026-05-29"] == "Desde el miércoles"


def test_editar_alcance_este_no_propaga(cliente):
    cuerpo = _crear_serie(cliente)
    sid = cuerpo["serie_id"]
    primero = cuerpo["eventos"][0]
    r = cliente.patch(f"/api/rota/eventos/{primero['id']}", json={"titulo": "Solo este"})
    assert r.status_code == 200
    assert r.json()["propagados"] == 0
    titulos = _titulos_por_fecha(cliente, sid)
    assert titulos["2026-05-25"] == "Solo este"
    assert titulos["2026-05-26"] == "Peloteando"  # el resto intacto


def test_editar_alcance_invalido_400(cliente):
    ev = _crear_evento(cliente)
    r = cliente.patch(f"/api/rota/eventos/{ev['id']}?alcance=humo", json={"titulo": "X"})
    assert r.status_code == 400


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
# Eventos multi-tenant por marca                                               #
# --------------------------------------------------------------------------- #


def test_crear_evento_con_marca_y_serializa_marca_nombre(cliente):
    """POST /api/rota/eventos con `marca` la persiste y la API devuelve marca + marca_nombre."""
    r = cliente.post(
        "/api/rota/eventos",
        json={"titulo": "Partido Claro", "fecha": SAB1, "marca": "claro-sports"},
    )
    assert r.status_code == 201, r.text
    ev = r.json()["evento"]
    assert ev["marca"] == "claro-sports"
    assert ev["marca_nombre"] != ""


def test_crear_evento_sin_marca_devuelve_cadena_vacia(cliente):
    """Un evento sin marca tiene marca="" y marca_nombre="" en la respuesta."""
    ev = _crear_evento(cliente, titulo="Sin marca")
    assert ev["marca"] == ""
    assert ev["marca_nombre"] == ""


def test_crear_evento_marca_invalida_400(cliente):
    """POST /api/rota/eventos con una marca desconocida responde 400."""
    r = cliente.post(
        "/api/rota/eventos",
        json={"titulo": "X", "fecha": SAB1, "marca": "marca-inexistente-xyz"},
    )
    assert r.status_code == 400


def test_filtro_marca_eventos(cliente):
    """`GET /api/rota/eventos?marca=` filtra por marca; sin param devuelve todos."""
    ev_cs = _crear_evento(cliente, titulo="CS", marca="claro-sports")
    ev_unotv = _crear_evento(cliente, titulo="UV", marca="unotv")
    ev_sin = _crear_evento(cliente, titulo="Sin", )

    # Filtrar por claro-sports: solo el de esa marca.
    r_cs = cliente.get("/api/rota/eventos?marca=claro-sports")
    ids_cs = {e["id"] for e in r_cs.json()["eventos"]}
    assert ev_cs["id"] in ids_cs
    assert ev_unotv["id"] not in ids_cs
    assert ev_sin["id"] not in ids_cs

    # Sin filtro: todos.
    r_todos = cliente.get("/api/rota/eventos")
    ids_todos = {e["id"] for e in r_todos.json()["eventos"]}
    assert ev_cs["id"] in ids_todos
    assert ev_unotv["id"] in ids_todos
    assert ev_sin["id"] in ids_todos


def test_filtro_marca_invalida_400(cliente):
    """`GET /api/rota/eventos?marca=` con valor desconocido responde 400."""
    r = cliente.get("/api/rota/eventos?marca=marca-inexistente-xyz")
    assert r.status_code == 400


def test_patch_evento_actualiza_marca(cliente):
    """PATCH /api/rota/eventos/{id} acepta `marca` y la persiste."""
    ev = _crear_evento(cliente, titulo="Editable")
    assert ev["marca"] == ""

    r = cliente.patch(f"/api/rota/eventos/{ev['id']}", json={"marca": "claro-sports"})
    assert r.status_code == 200
    assert r.json()["evento"]["marca"] == "claro-sports"
    assert r.json()["evento"]["marca_nombre"] != ""


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
    # Sin horas propias el turno HEREDA las de su franja (Mañana por defecto 08:00–16:00).
    assert turno["horario_propio"] is False
    assert (turno["inicio"], turno["fin"]) == ("08:00", "16:00")


def test_crear_turno_con_horario_a_medida(cliente):
    """El turno puede llevar HORAS PROPIAS que sobrescriben las de su franja: el caso de
    Elías (una persona con horario distinto ese día). `horario_propio` lo marca como cambiado.
    """
    equipo = _crear_equipo(1)
    r = cliente.post(
        "/api/rota/turnos",
        json={
            "fecha": LUNES1,
            "miembro_id": equipo[0]["id"],
            "franja": "matutino",
            "inicio": "07:00",
            "fin": "15:00",
        },
    )
    assert r.status_code == 201, r.text
    turno = r.json()["turno"]
    assert (turno["inicio"], turno["fin"]) == ("07:00", "15:00")
    assert turno["horario_propio"] is True


def test_crear_turno_hora_a_medida_invalida_400(cliente):
    equipo = _crear_equipo(1)
    r = cliente.post(
        "/api/rota/turnos",
        json={
            "fecha": LUNES1,
            "miembro_id": equipo[0]["id"],
            "franja": "matutino",
            "inicio": "9am",
            "fin": "15:00",
        },
    )
    assert r.status_code == 400


def test_actualizar_turno_horario_a_medida_y_vuelta_a_heredar(cliente):
    """PATCH pone horas a medida (admite cruce de medianoche) y, con inicio/fin '', vuelve a
    heredar de la franja."""
    equipo = _crear_equipo(1)
    turno = _crear_turno(LUNES1, LUNES1, equipo[0])
    r = cliente.patch(
        f"/api/rota/turnos/{turno['id']}", json={"inicio": "17:00", "fin": "01:00"}
    )
    assert r.status_code == 200, r.text
    t = r.json()["turno"]
    assert (t["inicio"], t["fin"]) == ("17:00", "01:00")  # cruza medianoche: válido
    assert t["horario_propio"] is True
    # Vaciar las horas vuelve a heredar las de la franja.
    r2 = cliente.patch(f"/api/rota/turnos/{turno['id']}", json={"inicio": "", "fin": ""})
    assert r2.status_code == 200, r2.text
    assert r2.json()["turno"]["horario_propio"] is False


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
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino", marca=MARCA)
    assert (
        token_cli.get(f"/api/rota/turnos?lunes={LUNES1}&marca={MARCA}").json()["aprobada"]
        is False
    )
    admin = _cli_admin_sesion(app)
    # GRID POR MARCA: aprobar exige una marca concreta (no "Todas").
    r = admin.post(
        "/api/rota/turnos/aprobar", json={"lunes": LUNES1, "marca": MARCA}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["aprobada"] is True
    assert all(t["estado"] == "aprobado" for t in r.json()["turnos"])


def test_aprobar_turnos_sin_turnos_400(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    admin = _cli_admin_sesion(app)
    r = admin.post(
        "/api/rota/turnos/aprobar", json={"lunes": LUNES1, "marca": MARCA}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_aprobar_turnos_sin_marca_400(entorno):
    """GRID POR MARCA: aprobar SIN una marca concreta (vista "Todas") -> 400."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino", marca=MARCA)
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


def test_despublicar_turnos_revierte_a_borrador(entorno):
    """Tras aprobar, el admin puede despublicar la semana para volver a editarla."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino", marca=MARCA)
    admin = _cli_admin_sesion(app)
    admin.post(
        "/api/rota/turnos/aprobar", json={"lunes": LUNES1, "marca": MARCA}, headers=_ORIGIN
    )
    r = admin.post(
        "/api/rota/turnos/despublicar",
        json={"lunes": LUNES1, "marca": MARCA},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["aprobada"] is False
    assert all(t["estado"] == "propuesto" for t in r.json()["turnos"])


def test_despublicar_sin_turnos_400(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    admin = _cli_admin_sesion(app)
    r = admin.post(
        "/api/rota/turnos/despublicar",
        json={"lunes": LUNES1, "marca": MARCA},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_despublicar_sin_marca_400(entorno):
    """GRID POR MARCA: despublicar SIN una marca concreta (vista "Todas") -> 400."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino", marca=MARCA)
    admin = _cli_admin_sesion(app)
    admin.post(
        "/api/rota/turnos/aprobar", json={"lunes": LUNES1, "marca": MARCA}, headers=_ORIGIN
    )
    r = admin.post("/api/rota/turnos/despublicar", json={"lunes": LUNES1}, headers=_ORIGIN)
    assert r.status_code == 400


def test_editor_no_puede_despublicar_403(entorno):
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino")
    auth.crear_usuario("editora", CLAVE, "editor")
    editor_cli = TestClient(app)
    editor_cli.post(
        "/api/auth/login", json={"usuario": "editora", "password": CLAVE}, headers=_ORIGIN
    )
    r = editor_cli.post(
        "/api/rota/turnos/despublicar", json={"lunes": LUNES1}, headers=_ORIGIN
    )
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


def test_mis_turnos_mes_acota_a_usuario_y_mes(entorno):
    """El calendario mensual devuelve SOLO los turnos del usuario actual dentro del mes:
    cruza varias semanas, excluye otros meses y a otros miembros."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(2)
    # Usuario 0: dos turnos en JUNIO (en semanas distintas) + uno en MAYO (fuera del mes).
    _crear_turno("2026-06-01", "2026-06-03", equipo[0], franja="matutino")
    _crear_turno("2026-06-08", "2026-06-10", equipo[0], franja="vespertino")
    _crear_turno(LUNES1, "2026-05-27", equipo[0], franja="matutino")
    # Usuario 1: un turno en junio (debe quedar fuera: no es el usuario de la sesión).
    _crear_turno("2026-06-01", "2026-06-03", equipo[1], franja="matutino")
    cli = TestClient(app)
    cli.post(
        "/api/auth/login",
        json={"usuario": equipo[0]["usuario"], "password": CLAVE},
        headers=_ORIGIN,
    )
    r = cli.get("/api/rota/mis-turnos/mes?mes=2026-06")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["mes"] == "2026-06"
    assert datos["desde"] == "2026-06-01"
    assert datos["hasta"] == "2026-06-30"
    assert datos["miembro_id"] == equipo[0]["id"]
    fechas = sorted(t["fecha"] for t in datos["mis_turnos"])
    assert fechas == ["2026-06-03", "2026-06-10"]
    assert datos["total"] == 2
    assert all(t["miembro_id"] == equipo[0]["id"] for t in datos["mis_turnos"])
    # El horario resuelto de la franja viaja (el front no cruza franjas): vespertino = "Tarde".
    jun10 = next(t for t in datos["mis_turnos"] if t["fecha"] == "2026-06-10")
    assert jun10["franja_nombre"] == "Tarde"
    assert jun10["inicio"] and jun10["fin"]


def test_mis_turnos_mes_sin_sesion_avisa(cliente):
    r = cliente.get("/api/rota/mis-turnos/mes?mes=2026-06")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["mis_turnos"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["aviso"]


def test_mis_turnos_mes_invalido_400(cliente):
    r = cliente.get("/api/rota/mis-turnos/mes?mes=2026-13")
    assert r.status_code == 400
    r2 = cliente.get("/api/rota/mis-turnos/mes?mes=junio")
    assert r2.status_code == 400


def test_turnos_mes_equipo_todos_los_miembros(cliente):
    """El calendario mensual del EQUIPO trae los turnos de TODOS en el mes (no filtra por
    usuario) y excluye los de otros meses."""
    equipo = _crear_equipo(2)
    _crear_turno("2026-06-01", "2026-06-03", equipo[0], franja="matutino")
    _crear_turno("2026-06-08", "2026-06-10", equipo[1], franja="vespertino")
    _crear_turno(LUNES1, "2026-05-27", equipo[0], franja="matutino")  # mayo: fuera
    r = cliente.get("/api/rota/turnos/mes?mes=2026-06")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["mes"] == "2026-06"
    assert datos["desde"] == "2026-06-01"
    assert datos["hasta"] == "2026-06-30"
    miembros = {t["miembro_id"] for t in datos["turnos"]}
    assert miembros == {equipo[0]["id"], equipo[1]["id"]}
    fechas = sorted(t["fecha"] for t in datos["turnos"])
    assert fechas == ["2026-06-03", "2026-06-10"]


def test_turnos_mes_invalido_400(cliente):
    assert cliente.get("/api/rota/turnos/mes?mes=2026-00").status_code == 400
    assert cliente.get("/api/rota/turnos/mes?mes=xxxx").status_code == 400


# --------------------------------------------------------------------------- #
# Cobertura DERIVADA                                                           #
# --------------------------------------------------------------------------- #


def test_cobertura_semana_derivada(cliente):
    """Para cada evento de la semana, devuelve los miembros con turno en su franja+fecha."""
    equipo = _crear_equipo(2)
    luis, tescu = equipo[0], equipo[1]
    ev_tarde = _crear_evento(cliente, titulo="Final", fecha=SAB1, hora="18:00")
    ev_madru = _crear_evento(cliente, titulo="Madrugada", fecha=SAB1, hora="03:00")
    # Inicializamos: tescu vespertino SAB1 (cubre el de 18:00), luis vespertino SAB1 tambien.
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


def test_cobertura_semana_filtra_por_marca(cliente):
    """`GET /api/rota/cobertura?marca=` acota los eventos a esa marca; sin param, todas."""
    _crear_equipo(1)
    ev_cs = _crear_evento(cliente, titulo="Final CS", fecha=SAB1, marca="claro-sports")
    ev_uv = _crear_evento(cliente, titulo="Nota UV", fecha=SAB1, marca="unotv")

    # Sin filtro: aparecen ambos (vista "Todas" agregada).
    todos = cliente.get(f"/api/rota/cobertura?lunes={LUNES1}").json()["eventos"]
    ids_todos = {e["id"] for e in todos}
    assert {ev_cs["id"], ev_uv["id"]} <= ids_todos

    # Filtrar por claro-sports: solo el de esa marca.
    solo_cs = cliente.get(f"/api/rota/cobertura?lunes={LUNES1}&marca=claro-sports").json()["eventos"]
    ids_cs = {e["id"] for e in solo_cs}
    assert ev_cs["id"] in ids_cs
    assert ev_uv["id"] not in ids_cs


def test_cobertura_semana_marca_invalida_400(cliente):
    """`GET /api/rota/cobertura?marca=` con valor desconocido responde 400."""
    r = cliente.get(f"/api/rota/cobertura?lunes={LUNES1}&marca=marca-inexistente-xyz")
    assert r.status_code == 400


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
    _crear_turno(LUNES1, "2026-05-25", luis, franja="matutino", marca=MARCA)
    _crear_turno(LUNES1, "2026-05-25", tescu, franja="vespertino", marca=MARCA)
    _crear_turno(LUNES1, SAB1, luis, franja="descanso", marca=MARCA)
    _crear_turno(LUNES1, SAB1, tescu, franja="matutino", marca=MARCA)
    # GRID POR MARCA: copiar exige una marca concreta (copia solo esa rejilla).
    r = cliente.post(
        "/api/rota/copiar-semana",
        json={"de_lunes": LUNES1, "a_lunes": LUNES2, "marca": MARCA},
    )
    assert r.status_code == 200, r.text
    assert r.json()["copiados"] == 4
    semana2 = cliente.get(f"/api/rota/turnos?lunes={LUNES2}&marca={MARCA}").json()
    fechas_franjas = {(t["fecha"], t["miembro_id"], t["franja"]) for t in semana2["turnos"]}
    assert (LUNES2, luis["id"], "matutino") in fechas_franjas
    assert (LUNES2, tescu["id"], "vespertino") in fechas_franjas
    assert (SAB2, luis["id"], "descanso") in fechas_franjas
    assert (SAB2, tescu["id"], "matutino") in fechas_franjas
    assert all(t["estado"] == "propuesto" for t in semana2["turnos"])


def test_copiar_semana_preserva_horario_a_medida(cliente):
    """Copiar arrastra el HORARIO PROPIO del turno, no solo su franja. Regresión: al añadir
    las columnas inicio/fin a `rota_turnos`, el clon de `copiar_turnos_rota` no las incluía y
    el INSERT reventaba (KeyError) tumbando toda la copia.
    """
    equipo = _crear_equipo(1)
    repos.crear_turno_rota(
        LUNES1,
        "2026-05-25",
        miembro_id=equipo[0]["id"],
        miembro_nombre=equipo[0]["usuario"],
        franja="matutino",
        inicio="07:00",
        fin="15:00",
        marca=MARCA,
    )
    r = cliente.post(
        "/api/rota/copiar-semana",
        json={"de_lunes": LUNES1, "a_lunes": LUNES2, "marca": MARCA},
    )
    assert r.status_code == 200, r.text
    assert r.json()["copiados"] == 1
    semana2 = cliente.get(f"/api/rota/turnos?lunes={LUNES2}&marca={MARCA}").json()
    clon = semana2["turnos"][0]
    assert (clon["inicio"], clon["fin"]) == ("07:00", "15:00")
    assert clon["horario_propio"] is True


def test_copiar_semana_misma_origen_destino_400(cliente):
    r = cliente.post(
        "/api/rota/copiar-semana",
        json={"de_lunes": LUNES1, "a_lunes": LUNES1, "marca": MARCA},
    )
    assert r.status_code == 400


def test_copiar_semana_sin_marca_400(cliente):
    """GRID POR MARCA: copiar SIN una marca concreta (vista "Todas") -> 400."""
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, "2026-05-25", equipo[0], franja="matutino", marca=MARCA)
    r = cliente.post(
        "/api/rota/copiar-semana",
        json={"de_lunes": LUNES1, "a_lunes": LUNES2},
    )
    assert r.status_code == 400


def test_copiar_semana_reemplazar(cliente):
    equipo = _crear_equipo(1)
    luis = equipo[0]
    _crear_turno(LUNES1, "2026-05-25", luis, franja="matutino", marca=MARCA)
    _crear_turno(LUNES2, LUNES2, luis, franja="descanso", marca=MARCA)
    r = cliente.post(
        "/api/rota/copiar-semana",
        json={"de_lunes": LUNES1, "a_lunes": LUNES2, "reemplazar": True, "marca": MARCA},
    )
    assert r.status_code == 200, r.text
    assert r.json()["copiados"] == 1
    semana2 = cliente.get(f"/api/rota/turnos?lunes={LUNES2}&marca={MARCA}").json()
    assert semana2["total"] == 1
    assert semana2["turnos"][0]["franja"] == "matutino"


def test_semana_nueva_se_prellena_desde_anterior(entorno):
    """Al abrir por PRIMERA vez una semana nueva (admin, marca concreta), sus turnos se
    prellenan copiando la anterior como borrador (propuesto). Ocurre una sola vez: reabrir
    no duplica."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(2)
    ana, beto = equipo[0], equipo[1]
    _crear_turno(LUNES1, LUNES1, ana, franja="matutino", marca=MARCA)
    _crear_turno(LUNES1, SAB1, beto, franja="vespertino", marca=MARCA)

    admin = _cli_admin_sesion(app)
    datos = admin.get(f"/api/rota/turnos?lunes={LUNES2}&marca={MARCA}").json()
    assert datos["total"] == 2
    assert datos["aprobada"] is False
    assert all(t["estado"] == "propuesto" for t in datos["turnos"])
    fechas = {(t["fecha"], t["miembro_id"]) for t in datos["turnos"]}
    assert (LUNES2, ana["id"]) in fechas
    assert (SAB2, beto["id"]) in fechas

    # Reabrir NO duplica: la semana ya tiene franjas, deja de ser virgen.
    assert admin.get(f"/api/rota/turnos?lunes={LUNES2}&marca={MARCA}").json()["total"] == 2


def test_semana_nueva_no_se_prellena_sin_anterior(entorno):
    """Sin semana anterior con turnos, la semana nueva queda vacía (nada que copiar)."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    _crear_equipo(1)
    admin = _cli_admin_sesion(app)
    assert admin.get(f"/api/rota/turnos?lunes={LUNES2}&marca={MARCA}").json()["total"] == 0


def test_semana_nueva_no_se_prellena_para_no_admin(entorno):
    """Solo el coordinador (sesión admin) dispara el prellenado; un GET por token (no admin)
    deja la semana virgen vacía (no escribe turnos)."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    equipo = _crear_equipo(1)
    _crear_turno(LUNES1, LUNES1, equipo[0], franja="matutino", marca=MARCA)
    token_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert token_cli.get(f"/api/rota/turnos?lunes={LUNES2}&marca={MARCA}").json()["total"] == 0


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


# --------------------------------------------------------------------------- #
# GRID POR MARCA: aislamiento de rejillas entre marcas                          #
# --------------------------------------------------------------------------- #


def _cli_admin(app) -> TestClient:
    """TestClient autenticado como admin (sesion); para los endpoints solo-admin."""
    auth.crear_usuario("elias", CLAVE, "admin")
    cli = TestClient(app)
    r = cli.post(
        "/api/auth/login", json={"usuario": "elias", "password": CLAVE}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    return cli


def test_franjas_independientes_por_marca_misma_semana(cliente):
    """(a) Dos marcas tienen franjas INDEPENDIENTES la misma semana (inicializado por marca).

    GET con `?marca=` siembra y devuelve SOLO la rejilla de esa marca; cada marca recibe sus
    propias franjas por defecto (la "Mañana" de una NO es la "Mañana" de la otra).
    """
    cs = cliente.get(f"/api/rota/semana/{LUNES1}/franjas?marca=claro-sports").json()[
        "franjas"
    ]
    uv = cliente.get(f"/api/rota/semana/{LUNES1}/franjas?marca=unotv").json()["franjas"]
    # Ambas reciben "Mañana" (mismo nombre permitido en marcas distintas).
    assert "Mañana" in {f["nombre"] for f in cs}
    assert "Mañana" in {f["nombre"] for f in uv}
    # Pero son franjas DISTINTAS (ids disjuntos) y cada una etiquetada con su marca.
    ids_cs = {f["id"] for f in cs}
    ids_uv = {f["id"] for f in uv}
    assert ids_cs.isdisjoint(ids_uv)
    assert all(f["marca"] == "claro-sports" for f in cs)
    assert all(f["marca"] == "unotv" for f in uv)


def test_crear_franja_mismo_nombre_en_dos_marcas_ok(entorno):
    """(a) Crear una franja "Cobertura" en DOS marcas la misma semana NO choca (unicidad por
    `(marca, lunes, nombre)`)."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    for marca in ("claro-sports", "unotv"):
        r = cli.post(
            f"/api/rota/semana/{LUNES1}/franjas?marca={marca}",
            json={"nombre": "Cobertura", "inicio": "17:00", "fin": "21:00"},
            headers=_ORIGIN,
        )
        assert r.status_code == 201, r.text
        assert r.json()["marca"] == marca


def test_turnos_aislados_por_marca(cliente):
    """(b) Un turno creado en la rejilla de la marca A NO aparece al listar la marca B."""
    equipo = _crear_equipo(1)
    ana = equipo[0]
    _crear_turno(LUNES1, LUNES1, ana, franja="matutino", marca="claro-sports")
    # Listando claro-sports: aparece.
    cs = cliente.get(f"/api/rota/turnos?lunes={LUNES1}&marca=claro-sports").json()
    assert cs["total"] == 1
    assert cs["turnos"][0]["marca"] == "claro-sports"
    # Listando unotv: NO aparece (otra rejilla).
    uv = cliente.get(f"/api/rota/turnos?lunes={LUNES1}&marca=unotv").json()
    assert uv["total"] == 0


def test_vista_todas_agrega_ambas_marcas(cliente):
    """(c) La vista "Todas" (sin `?marca`) agrega los turnos Y franjas de ambas marcas."""
    equipo = _crear_equipo(2)
    ana, beto = equipo[0], equipo[1]
    _crear_turno(LUNES1, LUNES1, ana, franja="matutino", marca="claro-sports")
    _crear_turno(LUNES1, LUNES1, beto, franja="vespertino", marca="unotv")
    todas = cliente.get(f"/api/rota/turnos?lunes={LUNES1}").json()
    # Los dos turnos, cada uno etiquetado con su marca.
    assert todas["total"] == 2
    marcas_turnos = {t["marca"] for t in todas["turnos"]}
    assert marcas_turnos == {"claro-sports", "unotv"}
    # Las franjas inicializadas de ambas rejillas tambien se apilan en "Todas".
    marcas_franjas = {f["marca"] for f in todas["franjas"]}
    assert {"claro-sports", "unotv"} <= marcas_franjas


def test_turno_hereda_marca_de_su_franja(cliente):
    """POST /api/rota/turnos con `franja_id` de una rejilla -> el turno hereda esa marca."""
    equipo = _crear_equipo(1)
    ana = equipo[0]
    franjas = cliente.get(
        f"/api/rota/semana/{LUNES1}/franjas?marca=claro-sports"
    ).json()["franjas"]
    manana = next(f for f in franjas if f["nombre"] == "Mañana")
    r = cliente.post(
        "/api/rota/turnos",
        json={"fecha": LUNES1, "miembro_id": ana["id"], "franja_id": manana["id"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["turno"]["marca"] == "claro-sports"


def test_franjas_vacias_sin_marca_no_siembra(cliente):
    """(d-bis) Sin `?marca`, una semana fresca NO siembra: devuelve [] (no hay rejilla)."""
    r = cliente.get(f"/api/rota/semana/{LUNES1}/franjas")
    assert r.status_code == 200, r.text
    assert r.json()["franjas"] == []


def test_post_franja_sin_marca_400(entorno):
    """(d) POST franja SIN una marca concreta -> 400 (no hay rejilla que crear)."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.post(
        f"/api/rota/semana/{LUNES1}/franjas",
        json={"nombre": "Cobertura", "inicio": "17:00", "fin": "21:00"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_patch_config_franjas_sin_marca_400(entorno):
    """(d) PATCH plantilla de franjas SIN una marca concreta -> 400 (la plantilla es por marca)."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        "/api/rota/config/franjas",
        json={"franjas": [{"nombre": "Mañana", "inicio": "08:00", "fin": "16:00"}]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_patch_config_franjas_con_marca_ok(entorno):
    """PATCH plantilla con una marca concreta guarda la LISTA de franjas de esa marca."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        "/api/rota/config/franjas?marca=claro-sports",
        json={
            "franjas": [
                {"nombre": "Mañana", "inicio": "09:00", "fin": "15:00"},
                {"nombre": "Tarde", "inicio": "15:00", "fin": "23:00"},
            ]
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    franjas = r.json()["franjas"]
    assert franjas[0]["nombre"] == "Mañana"
    assert franjas[0]["inicio"] == "09:00"


def test_patch_config_franjas_solape_permitido(entorno):
    """Dos franjas con rangos que SE SOLAPAN son plantilla válida (#185): la cobertura hace UNION.

    El modelo viejo exigia franjas excluyentes; se eliminó. Una franja que termina DESPUÉS de
    que empieza otra es válida -> 200. (Solo se valida `inicio < fin` por franja.)
    """
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    r = cli.patch(
        "/api/rota/config/franjas?marca=claro-sports",
        json={
            "franjas": [
                {"nombre": "Mañana", "inicio": "08:00", "fin": "18:00"},  # solapa con Tarde
                {"nombre": "Tarde", "inicio": "12:00", "fin": "22:00"},
            ]
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    franjas = r.json()["franjas"]
    manana = next(f for f in franjas if f["nombre"] == "Mañana")
    tarde = next(f for f in franjas if f["nombre"] == "Tarde")
    assert manana["fin"] == "18:00"
    assert tarde["inicio"] == "12:00"
