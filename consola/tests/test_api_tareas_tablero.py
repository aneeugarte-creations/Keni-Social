"""Tests del TABLERO de pendientes COMPARTIDO del equipo (#145, F5).

Cubren lo que F5 anade sobre el single-user: asignar un RESPONSABLE (usuario real), el
ciclo de ESTADO (pendiente -> en_curso -> hecha), el ENLACE de accion opcional, el listado
COMPARTIDO con la lista de usuarios asignables, y el ACOTADO por proyecto (`?proyecto=`).

Multiusuario: dos sesiones distintas ven y editan el MISMO tablero, cada una con su
identidad. La auth/CSRF/sesion no se toca (reusa el TestClient con login real del resto).

Todo OFFLINE; reusa el aislamiento de `entorno` y los fakes de `conftest`.
"""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, proyectos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba"


def _app():
    # `bootstrap=False`: no ejecutar `bootstrap_admin` ni `sembrar_equipo` en tests.
    # El seed del equipo AMX (`auth.sembrar_equipo`) crea entre otros un "luis" con la
    # password de bootstrap; los tests del tablero crean su propio "luis" con otra clave
    # y chocarian por UNIQUE → 401 al hacer login.
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)


def _cli_con_usuario(usuario: str) -> TestClient:
    """TestClient con SESION de `usuario` (login real). Devuelve el cliente."""
    auth.crear_usuario(usuario, _CLAVE, "editor")
    c = TestClient(_app())
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _id_usuario(nombre: str) -> str:
    """Id estable de un usuario por su nombre (debe existir)."""
    for u in auth.listar_usuarios():
        if u["usuario"] == nombre:
            return u["id"]
    raise AssertionError(f"usuario {nombre!r} no existe")


# --------------------------------------------------------------------------- #
# Crear con responsable / enlace                                               #
# --------------------------------------------------------------------------- #


def _crear_proyecto(tmp_path: Path, nombre: str = "Proyecto A", sub: str = "proy-a") -> str:
    """Anade un proyecto a la allowlist (consola.toml) y devuelve su id estable."""
    carpeta = tmp_path / sub
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "CLAUDE.md").write_text(f"# {nombre}\n", encoding="utf-8")
    ruta_toml = tmp_path / "consola.toml"
    bloque = f'[[proyecto]]\nnombre = "{nombre}"\nruta = "{carpeta}"\n'
    existente = ruta_toml.read_text(encoding="utf-8") if ruta_toml.exists() else ""
    ruta_toml.write_text(existente + ("\n" if existente else "") + bloque, encoding="utf-8")
    # Resolvemos el id por nombre (estable derivado de la ruta) desde la allowlist ya escrita.
    return next(p.id for p in proyectos.cargar_proyectos() if p.nombre == nombre)


def test_crear_pendiente_con_responsable_real(entorno):
    """Crear un pendiente asignado a un usuario REAL persiste su id y nombre."""
    c = _cli_con_usuario("ana")
    _cli_con_usuario("luis")  # luis existe como usuario asignable
    proyecto_id = _crear_proyecto(entorno)
    luis_id = _id_usuario("luis")

    r = c.post(
        "/api/tareas",
        json={
            "proyecto": proyecto_id,
            "titulo": "Revisar copy",
            "responsable_id": luis_id,
            "enlace": "/asistente?skill=copy",
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    tarea = r.json()["tarea"]
    assert tarea["autor_nombre"] == "ana"  # quien la creo
    assert tarea["responsable_id"] == luis_id  # a quien se le asigno
    assert tarea["responsable_nombre"] == "luis"
    assert tarea["enlace"] == "/asistente?skill=copy"


def test_crear_pendiente_con_responsable_inexistente_falla(entorno):
    """Un responsable que no es un usuario real se rechaza (no se confia en el cliente)."""
    c = _cli_con_usuario("ana")
    proyecto_id = _crear_proyecto(entorno)
    r = c.post(
        "/api/tareas",
        json={"proyecto": proyecto_id, "titulo": "T", "responsable_id": "noexiste"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    assert "responsable" in r.json()["error"].lower()


def test_crear_pendiente_sin_responsable_queda_sin_asignar(entorno):
    """Sin responsable, el pendiente nace sin asignar (campos vacios)."""
    c = _cli_con_usuario("ana")
    proyecto_id = _crear_proyecto(entorno)
    tarea = c.post(
        "/api/tareas",
        json={"proyecto": proyecto_id, "titulo": "Suelta"},
        headers=_ORIGIN,
    ).json()["tarea"]
    assert tarea["responsable_id"] == ""
    assert tarea["responsable_nombre"] == ""
    assert tarea["enlace"] == ""


# --------------------------------------------------------------------------- #
# Listado compartido + usuarios asignables                                     #
# --------------------------------------------------------------------------- #


def test_listado_incluye_usuarios_asignables(entorno):
    """El listado expone los usuarios reales para el selector de responsable."""
    c = _cli_con_usuario("ana")
    _cli_con_usuario("luis")
    cuerpo = c.get("/api/tareas").json()
    nombres = {u["usuario"] for u in cuerpo["usuarios"]}
    assert {"ana", "luis"} <= nombres
    # Solo id + nombre (sin rol ni mas estado).
    assert all(set(u.keys()) == {"id", "usuario"} for u in cuerpo["usuarios"])


def test_tablero_compartido_entre_dos_sesiones(entorno):
    """Ana crea un pendiente y Luis lo ve y lo edita: tablero UNICO compartido."""
    ana = _cli_con_usuario("ana")
    luis = _cli_con_usuario("luis")
    proyecto_id = _crear_proyecto(entorno)

    creada = ana.post(
        "/api/tareas",
        json={"proyecto": proyecto_id, "titulo": "Pendiente del equipo"},
        headers=_ORIGIN,
    ).json()["tarea"]

    # Luis (otra sesion) la ve en el tablero compartido.
    vistas_por_luis = luis.get("/api/tareas").json()["tareas"]
    assert any(t["id"] == creada["id"] for t in vistas_por_luis)

    # Luis la toma para si (responsable) y la pasa a en_curso.
    luis_id = _id_usuario("luis")
    r = luis.patch(
        f"/api/tareas/{creada['id']}",
        json={"estado": "en_curso", "responsable_id": luis_id},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    actualizada = r.json()["tarea"]
    assert actualizada["estado"] == "en_curso"
    assert actualizada["responsable_nombre"] == "luis"

    # Ana ve el cambio (mismo tablero), conservando su autoria.
    vista_por_ana = next(
        t for t in ana.get("/api/tareas").json()["tareas"] if t["id"] == creada["id"]
    )
    assert vista_por_ana["autor_nombre"] == "ana"
    assert vista_por_ana["responsable_nombre"] == "luis"
    assert vista_por_ana["estado"] == "en_curso"


# --------------------------------------------------------------------------- #
# Acotado por proyecto/marca                                                   #
# --------------------------------------------------------------------------- #


def test_listado_acotado_por_proyecto(entorno):
    """`?proyecto=<id>` acota el tablero a un proyecto (acotado por marca/proyecto)."""
    c = _cli_con_usuario("ana")
    proy_a = _crear_proyecto(entorno, "Proyecto A", "proy-a")
    proy_b = _crear_proyecto(entorno, "Proyecto B", "proy-b")
    c.post("/api/tareas", json={"proyecto": proy_a, "titulo": "De A"}, headers=_ORIGIN)
    c.post("/api/tareas", json={"proyecto": proy_b, "titulo": "De B"}, headers=_ORIGIN)

    solo_a = c.get(f"/api/tareas?proyecto={proy_a}").json()["tareas"]
    assert [t["titulo"] for t in solo_a] == ["De A"]
    # Sin filtro: todo el tablero.
    assert len(c.get("/api/tareas").json()["tareas"]) == 2
    # Un proyecto fuera de la allowlist devuelve vacio sin error.
    fuera = c.get("/api/tareas?proyecto=noexiste")
    assert fuera.status_code == 200
    assert fuera.json()["tareas"] == []


# --------------------------------------------------------------------------- #
# Estado / desasignar via PATCH                                                #
# --------------------------------------------------------------------------- #


def test_patch_estado_invalido_se_rechaza(entorno):
    c = _cli_con_usuario("ana")
    proyecto_id = _crear_proyecto(entorno)
    creada = c.post(
        "/api/tareas", json={"proyecto": proyecto_id, "titulo": "T"}, headers=_ORIGIN
    ).json()["tarea"]
    r = c.patch(f"/api/tareas/{creada['id']}", json={"estado": "inventado"}, headers=_ORIGIN)
    assert r.status_code == 400


def test_patch_desasigna_responsable(entorno):
    """Mandar responsable_id vacio limpia el responsable (desasignar)."""
    c = _cli_con_usuario("ana")
    proyecto_id = _crear_proyecto(entorno)
    ana_id = _id_usuario("ana")
    creada = c.post(
        "/api/tareas",
        json={"proyecto": proyecto_id, "titulo": "T", "responsable_id": ana_id},
        headers=_ORIGIN,
    ).json()["tarea"]
    assert creada["responsable_nombre"] == "ana"

    r = c.patch(f"/api/tareas/{creada['id']}", json={"responsable_id": ""}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["tarea"]["responsable_id"] == ""
    assert r.json()["tarea"]["responsable_nombre"] == ""


def test_patch_vacio_se_rechaza(entorno):
    c = _cli_con_usuario("ana")
    proyecto_id = _crear_proyecto(entorno)
    creada = c.post(
        "/api/tareas", json={"proyecto": proyecto_id, "titulo": "T"}, headers=_ORIGIN
    ).json()["tarea"]
    r = c.patch(f"/api/tareas/{creada['id']}", json={}, headers=_ORIGIN)
    assert r.status_code == 400


def test_patch_tarea_inexistente_404(entorno):
    c = _cli_con_usuario("ana")
    _crear_proyecto(entorno)
    r = c.patch("/api/tareas/noexiste", json={"estado": "hecha"}, headers=_ORIGIN)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Pendientes unificados: proyecto opcional, evento_id, abrir sin proyecto      #
# --------------------------------------------------------------------------- #


def test_crear_pendiente_sin_proyecto(entorno):
    """El proyecto es OPCIONAL: una tarea libre (solo titulo) se crea y persiste."""
    c = _cli_con_usuario("ana")
    r = c.post("/api/tareas", json={"titulo": "Tarea libre"}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    tarea = r.json()["tarea"]
    assert tarea["titulo"] == "Tarea libre"
    assert tarea["proyecto"] == ""
    assert tarea["proyecto_nombre"] == ""
    assert tarea["proyecto_existe"] is False
    assert tarea["evento_id"] == ""

    # Persiste en el tablero compartido.
    listado = c.get("/api/tareas").json()["tareas"]
    assert any(t["id"] == tarea["id"] and t["proyecto"] == "" for t in listado)


def test_crear_pendiente_sin_titulo_400(entorno):
    """Regresion: el titulo sigue siendo obligatorio (sin proyecto NO basta)."""
    c = _cli_con_usuario("ana")
    r = c.post("/api/tareas", json={"detalle": "x"}, headers=_ORIGIN)
    assert r.status_code == 400


def test_crear_pendiente_con_evento_valido(entorno):
    """Una tarea atada a un evento existente de la rota hidrata `evento_titulo/fecha/hora`."""
    c = _cli_con_usuario("ana")
    # Creamos un evento de la rota directamente con la API ya existente.
    r_ev = c.post(
        "/api/rota/eventos",
        json={"titulo": "Final", "fecha": "2026-05-30", "hora": "20:00"},
        headers=_ORIGIN,
    )
    assert r_ev.status_code == 201, r_ev.text
    evento = r_ev.json()["evento"]

    r = c.post(
        "/api/tareas",
        json={"titulo": "Cubrir final", "evento_id": evento["id"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    tarea = r.json()["tarea"]
    assert tarea["evento_id"] == evento["id"]
    assert tarea["evento_titulo"] == "Final"
    assert tarea["evento_fecha"] == "2026-05-30"
    assert tarea["evento_hora"] == "20:00"

    # El listado tambien la hidrata.
    listado = c.get("/api/tareas").json()["tareas"]
    en_lista = next(t for t in listado if t["id"] == tarea["id"])
    assert en_lista["evento_titulo"] == "Final"
    assert en_lista["evento_fecha"] == "2026-05-30"
    assert en_lista["evento_hora"] == "20:00"


def test_crear_pendiente_con_evento_inexistente_400(entorno):
    """`evento_id` inventado: 400 explicito (no se confia en el cliente)."""
    c = _cli_con_usuario("ana")
    r = c.post(
        "/api/tareas",
        json={"titulo": "T", "evento_id": "noexiste"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    assert "rota" in r.json()["error"].lower()


def test_listado_devuelve_eventos_sin_cubrir(entorno):
    """GET /api/tareas devuelve `eventos_sin_cubrir` con los eventos de la rota sin asignar."""
    c = _cli_con_usuario("ana")
    # Evento de esta semana, sin turno todavia -> debe aparecer como sin cubrir.
    r_a = c.post(
        "/api/rota/eventos",
        json={"titulo": "Sin cubrir aun", "fecha": "2026-05-30", "hora": "16:00"},
        headers=_ORIGIN,
    )
    assert r_a.status_code == 201, r_a.text
    ev_a = r_a.json()["evento"]

    cuerpo = c.get("/api/tareas").json()
    assert "eventos_sin_cubrir" in cuerpo
    ids = [e["id"] for e in cuerpo["eventos_sin_cubrir"]]
    assert ev_a["id"] in ids

    # Forma del item: id/titulo/fecha/hora/contenido/tipo_cobertura/prioridad.
    sin_cubrir = next(e for e in cuerpo["eventos_sin_cubrir"] if e["id"] == ev_a["id"])
    assert sin_cubrir["titulo"] == "Sin cubrir aun"
    assert sin_cubrir["fecha"] == "2026-05-30"
    assert sin_cubrir["hora"] == "16:00"
    assert sin_cubrir["tipo_cobertura"] == "transmision"
    assert sin_cubrir["prioridad"] == "media"


def test_eventos_sin_cubrir_excluye_los_asignados(entorno):
    """Un evento cubierto (turno en su franja+fecha) NO aparece en `eventos_sin_cubrir`.

    Modelo ola back3: la cobertura es DERIVADA. Un evento esta cubierto si existe algun
    turno en `rota_turnos` cuyo `(fecha, franja)` coincide con el del evento (franja
    derivada de su hora). Sembrar un turno con la misma fecha y franja vespertino lo
    saca de la lista de pendientes.
    """
    from keni_consola import repos as repos_mod

    c = _cli_con_usuario("ana")
    ana_id = _id_usuario("ana")

    r_ev = c.post(
        "/api/rota/eventos",
        json={"titulo": "Ya asignado", "fecha": "2026-05-30", "hora": "18:00"},
        headers=_ORIGIN,
    )
    assert r_ev.status_code == 201, r_ev.text
    ev = r_ev.json()["evento"]

    # Sembramos un turno de ana en la franja vespertino del 2026-05-30 (cubre el evento de 18:00).
    repos_mod.crear_turno_rota(
        "2026-05-25",
        "2026-05-30",
        miembro_id=ana_id,
        miembro_nombre="ana",
        franja="vespertino",
    )

    cuerpo = c.get("/api/tareas").json()
    ids = [e["id"] for e in cuerpo["eventos_sin_cubrir"]]
    assert ev["id"] not in ids


def test_abrir_tarea_sin_proyecto_400(entorno):
    """Una tarea libre (sin proyecto) NO se puede abrir en Claude Code: 400 explicito."""
    c = _cli_con_usuario("ana")
    creada = c.post(
        "/api/tareas", json={"titulo": "Libre"}, headers=_ORIGIN
    ).json()["tarea"]
    r = c.post(f"/api/tareas/{creada['id']}/abrir", headers=_ORIGIN)
    assert r.status_code == 400
    assert "proyecto" in r.json()["error"].lower()
