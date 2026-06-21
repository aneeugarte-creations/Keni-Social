"""Tests de la capa REPOSITORIO: fachada UNICA de persistencia.

Tras retirar el conmutador (`KENI_CONSOLA_BACKEND`), `repos` enruta cada entidad a su
almacen de forma FIJA:
  - CONTENIDO editorial -> ficheros YAML por marca (`ficheros.py`).
  - OPERACIONAL (tareas + comercial) -> SQLite (`db.py`).

Las firmas publicas siguen ESTABLES (ningun `api/*.py` cambia). Aqui lo comprobamos
por introspeccion (firmas) y por efecto (escribir por `repos`, leer por el almacen
concreto), y con guards de "un solo backend".
"""

from __future__ import annotations

import inspect

from keni_consola import db, estados, ficheros, repos


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
    # repos cubre TODAS las funciones publicas de db (tareas + comercial + ruta_db).
    faltan = funcs_db - funcs_repos
    assert not faltan, f"repos no reexporta de db: {sorted(faltan)}"


def test_reexporta_funciones_de_contenido_de_ficheros():
    # Las funciones de CONTENIDO (CRUD por entidad) de ficheros estan en la fachada.
    # Se excluyen las utilidades de filesystem/indice que NO forman parte del contrato
    # de la fachada.
    utilidades = {"raiz_datos", "carpeta_marca", "reconstruir_indice"}
    # Plantillas de copy plano: el concepto se FUSIONÓ en el catálogo unificado
    # `plantilla_contenido` (Postgres). Las funciones planas de YAML siguen en `ficheros`
    # SOLO como origen legado de la migración one-shot; ya no tienen fachada en `repos`.
    plano_legado = {
        "listar_plantillas", "contar_plantillas", "obtener_plantilla",
        "crear_plantilla", "actualizar_plantilla", "borrar_plantilla",
    }
    funcs_ficheros = _funciones_publicas(ficheros) - utilidades - plano_legado
    # `repos` es una FACHADA (barrel) que RE-EXPORTA: una función re-exportada conserva el
    # `__module__` de su submódulo, así que `_funciones_publicas(repos)` (que filtra por
    # __module__) no la ve. Aquí basta con que el NOMBRE esté accesible en la fachada
    # (`vars(repos)`), que es justo el contrato "repos re-exporta X".
    funcs_repos = {
        nombre
        for nombre, obj in vars(repos).items()
        if inspect.isfunction(obj) and not nombre.startswith("_")
    }
    faltan = funcs_ficheros - funcs_repos
    assert not faltan, f"repos no reexporta de ficheros: {sorted(faltan)}"


def test_firmas_identicas_con_db():
    for nombre in _funciones_publicas(db):
        firma_db = inspect.signature(getattr(db, nombre))
        firma_repos = inspect.signature(getattr(repos, nombre))
        assert firma_repos == firma_db, f"firma distinta en {nombre}"


def test_reexporta_constantes_publicas():
    # Las constantes de dominio se reexportan desde el modulo neutro `estados`.
    assert repos.ESTADOS_TAREA == estados.ESTADOS_TAREA
    assert repos.ESTADOS_PIEZA == estados.ESTADOS_PIEZA


# --------------------------------------------------------------------------- #
# Guards: un solo backend (sin conmutador)                                     #
# --------------------------------------------------------------------------- #


def test_no_hay_conmutador():
    assert not hasattr(repos, "_backend")
    fuente = inspect.getsource(repos)
    assert "KENI_CONSOLA_BACKEND" not in fuente


def test_publicaciones_persisten_en_postgres_no_en_yaml(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_BACKEND", "sqlite")
    pub = repos.crear_pieza("unotv", "x", titulo="T", contenido="C")
    yamls = list((entorno / "datos").rglob(f"{pub['id']}.yaml"))
    assert not yamls, "la pieza ya no debe escribirse como YAML"
    assert repos.obtener_pieza(pub["id"])["marca"] == "unotv"
    assert db.obtener_pieza(pub["id"])["titulo"] == "T"


# --------------------------------------------------------------------------- #
# Enrutado por efecto: contenido->ficheros, operacional->db                    #
# --------------------------------------------------------------------------- #


def test_delega_en_db_campania(entorno):
    # Las campañas viven en Postgres: escribir por repos -> leer por db.
    cam = repos.crear_campania(marcas=["unotv"], nombre="Camp", hashtags=["x"])
    assert db.obtener_campania(cam["id"])["nombre"] == "Camp"
    assert repos.borrar_campania(cam["id"]) is True


def test_delega_en_db_publicaciones(entorno):
    # Tras la fusión, las piezas viven en Postgres: escribir por repos -> leer por db.
    pub = repos.crear_pieza("unotv", "x", titulo="T", contenido="C")
    leida = db.obtener_pieza(pub["id"])
    assert leida is not None
    assert leida["marca"] == "unotv"
    # Editar por repos -> ver el cambio por db (misma fuente).
    repos.actualizar_pieza(pub["id"], {"titulo": "Z"})
    assert db.obtener_pieza(pub["id"])["titulo"] == "Z"


def test_delega_en_db_editorial_reutilizable(entorno):
    # Tras cerrar el rezago (ADR 0006), franjas / fuentes RSS viven en Postgres: escribir por
    # repos -> leer por db (misma fuente), no por ficheros.
    f = repos.crear_franja(2, "09:00", marca="unotv", red="x")
    assert any(x["id"] == f["id"] for x in db.listar_franjas())
    fr = repos.crear_fuente_rss("Diario", "https://example.com/feed.xml", marca="unotv")
    assert db.obtener_fuente_rss(fr["id"])["nombre"] == "Diario"


def test_historial_prompt_por_repos(entorno):
    hid = repos.registrar_historial_prompt("copy-desde-nota", "unotv", "RES", titulo="T")
    leido = ficheros.obtener_historial_prompt(hid)
    assert leido is not None
    assert leido["prompt"] == "copy-desde-nota"
