"""Tests de la capa REPOSITORIO (#83): fachada que reexporta `db` y delega 1:1.

En esta fase NO hay cambio de comportamiento: `repos` debe exponer TODAS las
funciones publicas de `db` con firmas IDENTICAS y delegar directamente en `db`
(mismo SQLite). Aqui lo comprobamos por introspeccion (firmas) y por efecto
(escribir por `repos`, leer por `db` y viceversa).
"""

from __future__ import annotations

import inspect

import pytest

from keni_consola import db, repos


def _funciones_publicas(modulo) -> set[str]:
    """Nombres de funciones publicas (sin guion_bajo) definidas EN ese modulo."""
    return {
        nombre
        for nombre, obj in vars(modulo).items()
        if inspect.isfunction(obj)
        and not nombre.startswith("_")
        and obj.__module__ == modulo.__name__
    }


def test_reexporta_todas_las_funciones_publicas_de_db():
    funcs_db = _funciones_publicas(db)
    funcs_repos = _funciones_publicas(repos)
    # repos cubre TODAS las funciones publicas de db (puede no anadir ninguna extra).
    faltan = funcs_db - funcs_repos
    assert not faltan, f"repos no reexporta: {sorted(faltan)}"


def test_firmas_identicas():
    for nombre in _funciones_publicas(db):
        firma_db = inspect.signature(getattr(db, nombre))
        firma_repos = inspect.signature(getattr(repos, nombre))
        assert firma_repos == firma_db, f"firma distinta en {nombre}"


def test_reexporta_constantes_publicas():
    assert repos.ESTADOS_TAREA == db.ESTADOS_TAREA
    assert repos.ESTADOS_PUBLICACION == db.ESTADOS_PUBLICACION


def test_delega_en_db_tareas(entorno):
    # Las tareas viven SIEMPRE en SQLite (en ambos backends): escribir por repos ->
    # leer por db (misma SQLite por debajo).
    tarea = repos.crear_tarea("proy", "Mi tarea", "detalle")
    leida = db.obtener_tarea(tarea["id"])
    assert leida is not None
    assert leida["titulo"] == "Mi tarea"
    # Y al reves: listar por repos ve lo escrito.
    assert any(t["id"] == tarea["id"] for t in repos.listar_tareas())


def test_delega_en_db_publicaciones(entorno, monkeypatch):
    # Con el backend SQLite explicito, repos debe delegar 1:1 en db.
    monkeypatch.setenv("KENI_CONSOLA_BACKEND", "sqlite")
    pub = repos.crear_publicacion("unotv", "x", titulo="T", contenido="C")
    # repos.ruta_db apunta al mismo fichero que db.ruta_db.
    assert repos.ruta_db() == db.ruta_db()
    leida = db.obtener_publicacion(pub["id"])
    assert leida is not None
    assert leida["marca"] == "unotv"
    # actualizar por db -> ver el cambio por repos.
    db.actualizar_publicacion(pub["id"], {"titulo": "Z"})
    assert repos.obtener_publicacion(pub["id"])["titulo"] == "Z"


def test_delega_en_db_contenido_reutilizable(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_BACKEND", "sqlite")
    f = repos.crear_franja(2, "09:00", marca="unotv", red="x")
    assert any(x["id"] == f["id"] for x in db.listar_franjas())
    g = repos.crear_grupo_hashtags("Deportes", marca="unotv", hashtags=["#gol"])
    assert db.obtener_grupo_hashtags(g["id"])["nombre"] == "Deportes"
    p = repos.crear_plantilla("Saludo", marca="unotv", red="x", contenido="Hola")
    assert db.obtener_plantilla(p["id"])["nombre"] == "Saludo"
    fr = repos.crear_fuente_rss("Diario", "https://example.com/feed.xml", marca="unotv")
    assert db.obtener_fuente_rss(fr["id"])["nombre"] == "Diario"


def test_historial_skill_por_repos(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_BACKEND", "sqlite")
    hid = repos.registrar_historial_skill("copy-desde-nota", "unotv", "RES", titulo="T")
    leido = db.obtener_historial_skill(hid)
    assert leido is not None
    assert leido["skill"] == "copy-desde-nota"


@pytest.mark.parametrize("nombre", sorted(_funciones_publicas(db)))
def test_cada_funcion_repos_es_callable(nombre):
    assert callable(getattr(repos, nombre))
