"""Tests de la capa REPOSITORIO: fachada UNICA de persistencia (E5/H2).

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
    # Se excluyen: las de tareas (ficheros delega en db; repos las toma de db) y las
    # utilidades de filesystem/indice que NO forman parte del contrato de la fachada.
    de_tareas = {"listar_tareas", "crear_tarea", "obtener_tarea", "actualizar_estado_tarea", "borrar_tarea"}
    utilidades = {"raiz_datos", "carpeta_marca", "reconstruir_indice"}
    # Plantillas de copy plano: el concepto se FUSIONÓ en el catálogo unificado
    # `plantilla_contenido` (Postgres). Las funciones planas de YAML siguen en `ficheros`
    # SOLO como origen legado de la migración one-shot; ya no tienen fachada en `repos`.
    plano_legado = {
        "listar_plantillas", "contar_plantillas", "obtener_plantilla",
        "crear_plantilla", "actualizar_plantilla", "borrar_plantilla",
    }
    funcs_ficheros = _funciones_publicas(ficheros) - de_tareas - utilidades - plano_legado
    funcs_repos = _funciones_publicas(repos)
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
    assert repos.ESTADOS_PUBLICACION == estados.ESTADOS_PUBLICACION
    assert repos.ESTADOS_COMERCIAL == estados.ESTADOS_COMERCIAL
    assert repos.ESTADO_COMERCIAL_ACTIVA == estados.ESTADO_COMERCIAL_ACTIVA
    assert repos.METRICAS_COMERCIAL == estados.METRICAS_COMERCIAL


# --------------------------------------------------------------------------- #
# Guards: un solo backend (sin conmutador)                                     #
# --------------------------------------------------------------------------- #


def test_no_hay_conmutador():
    # El conmutador `_backend()` y la lectura de `KENI_CONSOLA_BACKEND` se retiraron.
    assert not hasattr(repos, "_backend")
    fuente = inspect.getsource(repos)
    assert "KENI_CONSOLA_BACKEND" not in fuente


def test_publicaciones_persisten_en_postgres_no_en_yaml(entorno, monkeypatch):
    # Tras la fusión (paso 3), las publicaciones viven en Postgres (modelo `contenido`),
    # NO como YAML en disco. El viejo KENI_CONSOLA_BACKEND ya no influye.
    monkeypatch.setenv("KENI_CONSOLA_BACKEND", "sqlite")
    pub = repos.crear_publicacion("unotv", "x", titulo="T", contenido="C")
    # Ya NO se escribe ningún .yaml de la publicación en disco.
    yamls = list((entorno / "datos").rglob(f"{pub['id']}.yaml"))
    assert not yamls, "la publicacion ya no debe escribirse como YAML"
    # Se lee desde Postgres por repos y por db (misma fuente).
    assert repos.obtener_publicacion(pub["id"])["marca"] == "unotv"
    assert db.obtener_publicacion(pub["id"])["titulo"] == "T"


# --------------------------------------------------------------------------- #
# Enrutado por efecto: contenido->ficheros, operacional->db                    #
# --------------------------------------------------------------------------- #


def test_delega_en_db_tareas(entorno):
    # Las tareas viven en Postgres: escribir por repos -> leer por db (mismo Postgres).
    tarea = repos.crear_tarea("proy", "Mi tarea", "detalle")
    leida = db.obtener_tarea(tarea["id"])
    assert leida is not None
    assert leida["titulo"] == "Mi tarea"
    assert any(t["id"] == tarea["id"] for t in repos.listar_tareas())


def test_delega_en_db_comercial(entorno):
    # El comercial vive en Postgres: escribir por repos -> leer por db.
    pub = repos.crear_publicacion_comercial("https://x.com/a/1", titulo="Pieza", marca="unotv")
    assert db.obtener_publicacion_comercial(pub["id"])["titulo"] == "Pieza"
    repos.registrar_snapshot_comercial(pub["id"], "2026-05-25T10:00:00", 10, 100)
    assert db.ultimo_snapshot_comercial(pub["id"])["interacciones"] == 10


def test_delega_en_db_publicaciones(entorno):
    # Tras la fusión, las publicaciones viven en Postgres: escribir por repos -> leer por db.
    pub = repos.crear_publicacion("unotv", "x", titulo="T", contenido="C")
    leida = db.obtener_publicacion(pub["id"])
    assert leida is not None
    assert leida["marca"] == "unotv"
    # Editar por repos -> ver el cambio por db (misma fuente).
    repos.actualizar_publicacion(pub["id"], {"titulo": "Z"})
    assert db.obtener_publicacion(pub["id"])["titulo"] == "Z"


def test_delega_en_ficheros_contenido_reutilizable(entorno):
    f = repos.crear_franja(2, "09:00", marca="unotv", red="x")
    assert any(x["id"] == f["id"] for x in ficheros.listar_franjas())
    g = repos.crear_grupo_hashtags("Deportes", marca="unotv", hashtags=["#gol"])
    assert ficheros.obtener_grupo_hashtags(g["id"])["nombre"] == "Deportes"
    fr = repos.crear_fuente_rss("Diario", "https://example.com/feed.xml", marca="unotv")
    assert ficheros.obtener_fuente_rss(fr["id"])["nombre"] == "Diario"


def test_historial_skill_por_repos(entorno):
    hid = repos.registrar_historial_skill("copy-desde-nota", "unotv", "RES", titulo="T")
    leido = ficheros.obtener_historial_skill(hid)
    assert leido is not None
    assert leido["skill"] == "copy-desde-nota"
