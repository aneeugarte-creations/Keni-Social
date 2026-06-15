"""Tests del MODELO DE PUBLICACIÓN de la Biblioteca (rediseño): versiones inmutables +
puntero "producción" + solicitudes + catálogo de variables + riel de la máquina.

Estrategia mixta:
  - Igual que `test_api_texto`: app Starlette mínima con `api.texto.RUTAS` (sin el
    middleware real de auth). El ROL se inyecta con un middleware de test que deja el
    usuario en `scope["state"]` EXACTAMENTE como lo haría `SeguridadConsola`, así
    `permisos.es_admin` (la fuente única) se ejercita de verdad.
  - Los endpoints de publicar/solicitar usan Postgres (`pg`) + git (`KENI_TEXTO_GIT=1`).
  - El fallback "sin puntero / sin BD" se prueba SIN Postgres: nada debe romperse
    (migración suave: working copy como siempre).
"""

from __future__ import annotations

import shutil

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from keni_consola import generaciones, libtexto, marcas, versionado
from keni_consola.api import texto as api_texto
from keni_consola.dominio import generar

_MARCA = marcas.opciones()[0][0]

_ADMIN = {"id": "u-admin", "usuario": "Root", "rol": "admin"}
_EDITOR = {"id": "u-editor", "usuario": "Edi", "rol": "editor"}


class _ConUsuario:
    """Middleware ASGI de test: inyecta el usuario de sesión en `scope['state']`.

    Es el MISMO contrato que deja `SeguridadConsola` (`request.state.usuario`), así los
    handlers ejercitan `permisos.es_admin` y `seguridad.autor_de_peticion` reales.
    """

    def __init__(self, app, usuario):
        self.app = app
        self.usuario = usuario

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["usuario"] = self.usuario
        await self.app(scope, receive, send)


def _cliente(usuario=None) -> TestClient:
    app = Starlette(routes=list(api_texto.RUTAS))
    if usuario is not None:
        app = _ConUsuario(app, usuario)
    return TestClient(app)


@pytest.fixture
def entorno_pub(monkeypatch, tmp_path, pg):
    """Texto aislada en tmp + git ON + Postgres de pruebas (skip sin git o sin Postgres)."""
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    monkeypatch.setenv("KENI_TEXTO_GIT", "1")
    monkeypatch.setattr(generaciones, "encolar_job_claude", lambda *a, **k: None)
    yield


@pytest.fixture
def entorno_sin_pg(monkeypatch, tmp_path):
    """Texto aislada en tmp, SIN Postgres (DATABASE_URL fuera): camino degradado."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    monkeypatch.setattr(generaciones, "encolar_job_claude", lambda *a, **k: None)
    yield


def _crear_doc(c: TestClient, titulo="Doc", cuerpo="V1", tipo="prompt", **extra) -> dict:
    r = c.post("/api/texto", json={"titulo": titulo, "tipo": tipo, "cuerpo": cuerpo, **extra})
    assert r.status_code == 200
    return r.json()["documento"]


def _head(c: TestClient, doc_id: str) -> str:
    """SHA del último commit git del doc (`sha_actual`).

    Tras el rediseño del versionado intencionado, `/historial` devuelve PUBLICACIONES (no el
    git log), así que un doc recién creado tiene historial vacío; el sha del commit de
    creación se lee de `sha_actual` del propio documento.
    """
    d = c.get(f"/api/texto/{doc_id}").json()["documento"]
    assert d["sha_actual"], "el doc debería tener al menos un commit (creación)"
    return d["sha_actual"]


# --------------------------------------------------------------------------- #
# Publicar (solo admin) + campos nuevos del documento                          #
# --------------------------------------------------------------------------- #


def test_publicar_mueve_el_puntero_y_expone_campos(entorno_pub):
    c = _cliente(_ADMIN)
    doc = _crear_doc(c)
    head = _head(c, doc["id"])

    # Antes de publicar: sin puntero pero CON contenido nunca publicado -> sin_publicar True
    # (rediseño intencionado: aparece el botón "Publicar").
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"] is None
    assert d["sin_publicar"] is True
    assert d["sha_actual"] == head

    r = c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "primera"})
    assert r.status_code == 200
    d = r.json()["documento"]
    assert d["produccion"]["sha"] == head
    assert d["produccion"]["autor"] == "Root"
    assert d["produccion"]["nota"] == "primera"
    assert d["produccion"]["creado"]
    assert d["sha_actual"] == head
    assert d["sin_publicar"] is False

    # Editar tras publicar: el puntero NO se mueve y el doc queda "sin publicar" (por
    # CONTENIDO: working copy V2 != cuerpo publicado V1). `sha_actual` (HEAD git) NO se mueve
    # con el autosave.
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": "V2"})
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"]["sha"] == head
    assert d["sha_actual"] == head
    assert d["sin_publicar"] is True

    # El LISTADO trae los mismos campos (resueltos por lote).
    listado = c.get("/api/texto", params={"tipo": "prompt"}).json()["documentos"]
    fila = next(x for x in listado if x["id"] == doc["id"])
    assert fila["produccion"]["sha"] == head
    assert fila["sin_publicar"] is True


def test_publicar_con_sha_explicito(entorno_pub):
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="V1")
    sha_v1 = _head(c, doc["id"])
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": "V2"})

    r = c.post(f"/api/texto/{doc['id']}/publicar", json={"sha": sha_v1, "nota": "fija v1"})
    assert r.status_code == 200
    d = r.json()["documento"]
    assert d["produccion"]["sha"] == sha_v1
    assert d["sin_publicar"] is True  # HEAD (V2) != producción (V1)

    # Un sha que no es una versión del doc -> 400.
    r = c.post(f"/api/texto/{doc['id']}/publicar", json={"sha": "deadbeef", "nota": "x"})
    assert r.status_code == 400


def test_publicar_requiere_admin(entorno_pub):
    admin = _cliente(_ADMIN)
    doc = _crear_doc(admin)
    editor = _cliente(_EDITOR)
    r = editor.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "no"})
    assert r.status_code == 403
    # Sin usuario de sesión (p. ej. token de mantenimiento) tampoco es admin.
    anon = _cliente()
    assert anon.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "no"}).status_code == 403


def test_publicar_doc_inexistente_404(entorno_pub):
    c = _cliente(_ADMIN)
    r = c.post("/api/texto/prompt/no-existe/publicar", json={"nota": "x"})
    assert r.status_code == 404


def test_publicar_dos_veces_sin_cambios_no_duplica_historial(entorno_pub):
    """Publicar dos veces SIN cambios (mismo sha) no crea dos "versiones" idénticas: el log
    de publicaciones es idempotente por sha."""
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="ESTABLE")
    assert c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "v1"}).status_code == 200
    # Segunda publicación sin tocar el documento: mismo sha -> NO añade fila.
    assert c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "otra vez"}).status_code == 200
    hist = c.get(f"/api/texto/{doc['id']}/historial").json()["historial"]
    assert len(hist) == 1
    assert hist[0]["mensaje"] == "v1"  # se conserva la publicación original


def test_publicar_vacio_400(entorno_pub):
    """No se puede publicar un cuerpo en blanco (sin frontmatter): 400 accionable."""
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="ALGO")
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": "   "})
    r = c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "x"})
    assert r.status_code == 400
    assert "vacío" in r.json()["error"].lower()


def test_solicitar_vacio_400(entorno_pub):
    """Solicitar publicación de un cuerpo en blanco también se rechaza (400)."""
    c = _cliente(_EDITOR)
    doc = _crear_doc(c, cuerpo="ALGO")
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": ""})
    r = c.post(f"/api/texto/{doc['id']}/solicitar", json={"nota": "x"})
    assert r.status_code == 400
    assert "vacío" in r.json()["error"].lower()


# --------------------------------------------------------------------------- #
# Historial = PUBLICACIONES (no git log) + commit intencionado                 #
# --------------------------------------------------------------------------- #


def test_historial_son_publicaciones_no_git_log(entorno_pub):
    """El historial es el de PUBLICACIONES (nota = mensaje), no el git log de autosaves."""
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="V1")
    # Un borrador NO es versión: sin publicar -> historial vacío.
    assert c.get(f"/api/texto/{doc['id']}/historial").json()["historial"] == []

    # Publicar crea la versión: una entrada con la NOTA como mensaje.
    c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "primera versión"})
    hist = c.get(f"/api/texto/{doc['id']}/historial").json()["historial"]
    assert len(hist) == 1
    assert hist[0]["mensaje"] == "primera versión"
    assert hist[0]["autor"] == "Root"
    assert hist[0]["sha"] and hist[0]["sha_corto"] == hist[0]["sha"][:8]
    assert hist[0]["fecha"]

    # Editar (autosave) NO añade versión al historial.
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": "V2"})
    assert len(c.get(f"/api/texto/{doc['id']}/historial").json()["historial"]) == 1

    # Publicar de nuevo -> dos versiones, la más reciente primero.
    c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "segunda"})
    hist = c.get(f"/api/texto/{doc['id']}/historial").json()["historial"]
    assert [h["mensaje"] for h in hist] == ["segunda", "primera versión"]


def test_revertir_trae_al_borrador_sin_publicar(entorno_pub):
    """`revertir/{sha}` = "Traer al borrador": carga la versión en el working copy SIN
    publicar ni añadir versión (el puntero de producción no se mueve)."""
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="V1")
    c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "v1"})
    sha_v1 = c.get(f"/api/texto/{doc['id']}/historial").json()["historial"][0]["sha"]
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": "V2"})
    c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "v2"})

    r = c.post(f"/api/texto/{doc['id']}/revertir/{sha_v1}")
    assert r.status_code == 200
    assert "V1" in r.json()["documento"]["cuerpo"]
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert "V1" in d["cuerpo"]
    assert d["produccion"]["nota"] == "v2"  # el puntero sigue en v2
    assert d["sin_publicar"] is True        # el borrador (v1) difiere de lo publicado (v2)
    # No se publicó nada: siguen siendo dos versiones.
    assert len(c.get(f"/api/texto/{doc['id']}/historial").json()["historial"]) == 2


def test_descartar_resetea_al_publicado(entorno_pub):
    """`descartar` reescribe el borrador con el contenido publicado, sin crear versión."""
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="PUBLICADA")
    c.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "v1"})
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": "BORRADOR SUCIO"})
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert "BORRADOR SUCIO" in d["cuerpo"] and d["sin_publicar"] is True

    r = c.post(f"/api/texto/{doc['id']}/descartar")
    assert r.status_code == 200
    doc2 = r.json()["documento"]
    assert "PUBLICADA" in doc2["cuerpo"]
    assert doc2["sin_publicar"] is False  # vuelve a coincidir con lo publicado
    # No crea versión: sigue habiendo UNA publicación.
    assert len(c.get(f"/api/texto/{doc['id']}/historial").json()["historial"]) == 1


def test_descartar_sin_publicacion_400(entorno_pub):
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="X")
    r = c.post(f"/api/texto/{doc['id']}/descartar")
    assert r.status_code == 400
    assert "publicada" in r.json()["error"].lower()


def test_descartar_doc_inexistente_404(entorno_pub):
    c = _cliente(_ADMIN)
    assert c.post("/api/texto/prompt/no-existe/descartar").status_code == 404


# --------------------------------------------------------------------------- #
# Solicitudes: solicitar / listar / aprobar / rechazar                         #
# --------------------------------------------------------------------------- #


def test_solicitar_crea_abierta_y_sustituye_la_anterior(entorno_pub):
    editor = _cliente(_EDITOR)
    doc = _crear_doc(editor, titulo="Mi prompt")
    r = editor.post(f"/api/texto/{doc['id']}/solicitar", json={"nota": "porfa"})
    assert r.status_code == 200
    sol = r.json()["solicitud"]
    assert sol["estado"] == "abierta"
    assert sol["autor"] == "Edi"
    assert sol["nota"] == "porfa"
    assert sol["titulo"] == "Mi prompt"
    assert sol["revisor"] is None and sol["comentario"] is None and sol["resuelto"] is None

    # Una segunda solicitud sobre el MISMO doc SUSTITUYE a la abierta (no se acumulan).
    editor.put(f"/api/texto/{doc['id']}", json={"cuerpo": "V2"})
    r2 = editor.post(f"/api/texto/{doc['id']}/solicitar", json={"nota": "mejor esta"})
    assert r2.status_code == 200
    abiertas = editor.get("/api/texto/solicitudes", params={"estado": "abierta"}).json()["solicitudes"]
    assert len(abiertas) == 1
    assert abiertas[0]["nota"] == "mejor esta"
    assert abiertas[0]["sha_propuesto"] == r2.json()["solicitud"]["sha_propuesto"]


def test_solicitar_doc_inexistente_404_y_estado_invalido_400(entorno_pub):
    c = _cliente(_EDITOR)
    assert c.post("/api/texto/prompt/nada/solicitar", json={"nota": "x"}).status_code == 404
    assert c.get("/api/texto/solicitudes", params={"estado": "rara"}).status_code == 400


def test_aprobar_publica_el_sha_propuesto(entorno_pub):
    editor = _cliente(_EDITOR)
    admin = _cliente(_ADMIN)
    doc = _crear_doc(editor)
    sol = editor.post(f"/api/texto/{doc['id']}/solicitar", json={"nota": "v1 lista"}).json()["solicitud"]

    # Un editor NO puede aprobar.
    assert editor.post(f"/api/texto/solicitudes/{sol['id']}/aprobar", json={}).status_code == 403

    r = admin.post(f"/api/texto/solicitudes/{sol['id']}/aprobar", json={"comentario": "ok"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["solicitud"]["estado"] == "aprobada"
    assert cuerpo["solicitud"]["revisor"] == "Root"
    assert cuerpo["solicitud"]["comentario"] == "ok"
    assert cuerpo["solicitud"]["resuelto"]
    assert cuerpo["documento"]["produccion"]["sha"] == sol["sha_propuesto"]

    # Re-aprobar una resuelta -> 409. Inexistente -> 404.
    assert admin.post(f"/api/texto/solicitudes/{sol['id']}/aprobar", json={}).status_code == 409
    assert admin.post("/api/texto/solicitudes/zzz/aprobar", json={}).status_code == 404


def test_rechazar_no_toca_el_puntero(entorno_pub):
    editor = _cliente(_EDITOR)
    admin = _cliente(_ADMIN)
    doc = _crear_doc(editor)
    sol = editor.post(f"/api/texto/{doc['id']}/solicitar", json={"nota": "v1"}).json()["solicitud"]

    assert editor.post(f"/api/texto/solicitudes/{sol['id']}/rechazar", json={}).status_code == 403
    r = admin.post(f"/api/texto/solicitudes/{sol['id']}/rechazar", json={"comentario": "aún no"})
    assert r.status_code == 200
    assert r.json()["solicitud"]["estado"] == "rechazada"
    assert r.json()["solicitud"]["comentario"] == "aún no"

    d = admin.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"] is None  # rechazar no publica nada
    assert admin.post(f"/api/texto/solicitudes/{sol['id']}/rechazar", json={}).status_code == 409


# --------------------------------------------------------------------------- #
# Ensamblaje: los pipelines inyectan la versión PUBLICADA, no la working copy  #
# --------------------------------------------------------------------------- #


def test_ensamblaje_inyecta_la_version_publicada(entorno_pub, monkeypatch):
    """Test CLAVE del rediseño: tras publicar y EDITAR, lo que se compone/lanza es el
    cuerpo PUBLICADO (sha fijado), no la working copy."""
    admin = _cliente(_ADMIN)
    doc = _crear_doc(admin, titulo="Base", cuerpo="CUERPO PUBLICADO V1")
    assert admin.post(f"/api/texto/{doc['id']}/publicar", json={"nota": "v1"}).status_code == 200
    admin.put(f"/api/texto/{doc['id']}", json={"cuerpo": "CUERPO NUEVO V2"})

    # (a) `cuerpo_efectivo` (lo usan TODOS los pipelines de fondo) devuelve lo publicado.
    assert "CUERPO PUBLICADO V1" in (libtexto.cuerpo_efectivo(doc["id"]) or "")
    assert "V2" not in (libtexto.cuerpo_efectivo(doc["id"]) or "")
    # ... y la working copy sigue siendo la editada (editar es libre).
    assert "V2" in admin.get(f"/api/texto/{doc['id']}").json()["documento"]["cuerpo"]

    # (b) Los ADJUNTOS editoriales también se inyectan en su versión publicada.
    edi = _crear_doc(admin, titulo="Reglas", cuerpo="EDITORIAL V1", tipo="editorial", clase="reglas")
    assert admin.post(f"/api/texto/{edi['id']}/publicar", json={"nota": "v1"}).status_code == 200
    admin.put(f"/api/texto/{edi['id']}", json={"cuerpo": "EDITORIAL V2"})
    prompt = generar.componer("haz algo", [libtexto.obtener(edi["id"])], "")
    assert "EDITORIAL V1" in prompt
    assert "EDITORIAL V2" not in prompt

    # (c) Camino HTTP completo: lanzar el prompt compone con el cuerpo publicado.
    capturado: dict = {}

    def _capturar(gen_id, **kw):
        capturado["prompt"] = kw.get("prompt", "")

    monkeypatch.setattr(generaciones, "encolar_job_claude", _capturar)
    r = admin.post("/api/texto/lanzar", json={
        "prompt_id": doc["id"], "marca": _MARCA, "target": {"tipo": "ninguno"},
    })
    assert r.status_code == 200
    assert "CUERPO PUBLICADO V1" in capturado["prompt"]
    assert "CUERPO NUEVO V2" not in capturado["prompt"]


def test_sin_puntero_sirve_snapshot_estable_no_borrador_vivo(entorno_pub):
    """Sin puntero de producción, los pipelines sirven el SNAPSHOT ESTABLE (último commit
    git), NUNCA el working copy que el autosave reescribe en vivo: un borrador a medias no
    entra a una generación. El doc sigue figurando como NO publicado (produccion None)."""
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="SNAPSHOT V1")
    # Recién creado (un commit "crear"): el cuerpo efectivo es ese snapshot.
    assert "SNAPSHOT V1" in (libtexto.cuerpo_efectivo(doc["id"]) or "")

    # Autosave (PUT) reescribe el working copy SIN commitear ni publicar.
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": "BORRADOR VIVO V2"})
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"] is None                 # sigue sin publicar
    assert "BORRADOR VIVO V2" in d["cuerpo"]        # el working copy sí refleja la edición
    assert d["sin_publicar"] is True               # con contenido y sin publicar -> "Publicar"

    # Pero los pipelines NO ven el borrador a medias: sirven el snapshot estable (HEAD).
    efectivo = libtexto.cuerpo_efectivo(doc["id"]) or ""
    assert "SNAPSHOT V1" in efectivo
    assert "BORRADOR VIVO V2" not in efectivo


def test_adjunto_sin_puntero_sirve_snapshot_estable(entorno_pub):
    """El ensamblaje de adjuntos editoriales también sirve el snapshot estable (HEAD) de un
    adjunto sin publicar, no su working copy editado en vivo."""
    c = _cliente(_ADMIN)
    edi = _crear_doc(c, titulo="Reglas", cuerpo="EDITORIAL HEAD", tipo="editorial", clase="reglas")
    c.put(f"/api/texto/{edi['id']}", json={"cuerpo": "EDITORIAL BORRADOR"})
    prompt = generar.componer("haz algo", [libtexto.obtener(edi["id"])], "")
    assert "EDITORIAL HEAD" in prompt
    assert "EDITORIAL BORRADOR" not in prompt


def test_inicial_recibe_linea_base_git_y_sirve_snapshot(entorno_pub):
    """Los documentos de la INICIAL se escriben sin commit; `asegurar_linea_base` les fija un
    HEAD git, de modo que los pipelines sirven su snapshot estable y NO el working copy que el
    autosave reescribe en vivo (cierra el caso que antes caía al working copy)."""
    n = libtexto.importar_inicial()
    assert n > 0
    doc_id = "prompt/redactar"
    assert libtexto.obtener(doc_id) is not None
    # Recién inicializado: aún sin commit -> sin HEAD.
    assert versionado.sha_documento(doc_id) is None
    # Línea base: queda versionado y devuelve cuántos fijó.
    assert libtexto.asegurar_linea_base() > 0
    assert versionado.sha_documento(doc_id) is not None
    # Idempotente: una segunda pasada no fija nada nuevo.
    assert libtexto.asegurar_linea_base() == 0
    # El autosave reescribe el working copy sin commitear...
    libtexto.guardar(doc_id, cuerpo="BORRADOR VIVO INICIAL")
    efectivo = libtexto.cuerpo_efectivo(doc_id) or ""
    assert efectivo.strip()                          # sirve el snapshot estable, no vacío
    assert "BORRADOR VIVO INICIAL" not in efectivo   # NUNCA el borrador a medias


def test_sin_postgres_todo_degrada_a_working_copy(entorno_sin_pg):
    """Migración suave: sin BD no hay puntero; leer/listar/componer NUNCA rompen."""
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="SOLO WORKING")
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"] is None
    # Sin BD no hay puntero; con contenido -> sin_publicar True (nunca publicado).
    assert d["sin_publicar"] is True
    assert "SOLO WORKING" in (libtexto.cuerpo_efectivo(doc["id"]) or "")
    # El listado también responde con los campos nuevos degradados.
    fila = c.get("/api/texto").json()["documentos"][0]
    assert fila["produccion"] is None and fila["sin_publicar"] is True


# --------------------------------------------------------------------------- #
# Catálogo de variables + riel de la máquina                                   #
# --------------------------------------------------------------------------- #


def test_variables_catalogo(entorno_sin_pg):
    c = _cliente()
    r = c.get("/api/texto/variables")
    assert r.status_code == 200
    vs = r.json()["variables"]
    assert vs, "el catálogo no puede estar vacío"
    assert all({"nombre", "descripcion", "ejemplo", "origen"} <= set(v) for v in vs)
    nombres = {v["nombre"] for v in vs}
    # Variables REALES del código (perfil editorial, fusión, traducción, importadores).
    # (PLATAFORMA se retiró al borrar el agente de sugerencias editoriales.)
    assert {"MARCA", "MAX_KEYWORDS", "EDITORIAL", "HISTORIAS", "ITEMS", "RUTA"} <= nombres


def test_maquina_tres_maquinas(entorno_sin_pg):
    """La forma nueva del riel (ADR 0011): tres máquinas, etapas mecánicas + prompts."""
    c = _cliente()
    r = c.get("/api/texto/maquina", params={"marca": _MARCA})
    assert r.status_code == 200
    cuerpo = r.json()
    # `grupos`/`capas` desaparecieron: el ensamblaje editorial vive en /estrategia.
    assert "grupos" not in cuerpo and "capas" not in cuerpo
    maquinas = cuerpo["maquinas"]
    assert [m["id"] for m in maquinas] == ["investigacion", "produccion", "importacion"]
    inv, prod, imp = maquinas
    assert inv["titulo"] == "Investigación" and inv["subtitulo"] == "El motor de noticias"
    assert prod["titulo"] == "Producción" and prod["subtitulo"] == "La máquina de contenido"
    assert imp["titulo"] == "Herramientas de importación"

    # Investigación: el proceso COMPLETO en orden (la frontera del ADR: Verificar la fuente es
    # Investigación), con las etapas sin prompt de la Biblioteca como `mecanica` (contexto).
    # Ids/títulos de las etapas compartidas casan 1:1 con el riel de la página Investigación
    # (verbos C: Recolectar · Fusionar · Clasificar · Priorizar · Verificar).
    assert [(e["tipo"], e["id"]) for e in inv["etapas"]] == [
        ("mecanica", "recolectar"),
        ("mecanica", "agrupar"),
        ("prompt", "fusionar-verificar"),
        ("prompt", "fusionar"),
        ("prompt", "traducir"),
        ("prompt", "clasificar"),
        ("prompt", "priorizar"),
        ("mecanica", "admitir"),
        ("prompt", "verificar"),
    ]
    por_id = {e["id"]: e for e in inv["etapas"]}
    assert por_id["verificar"]["doc_id"] == "prompt/verificar"  # prompt_base_de("verificar")
    assert por_id["verificar"]["titulo"] == "Verificar"
    assert por_id["priorizar"]["doc_id"] == "prompt/priorizar"
    assert por_id["priorizar"]["titulo"] == "Priorizar"
    assert por_id["fusionar"]["titulo"] == "Fusionar"
    # El clasificador de marca ya es un prompt de la Biblioteca (migrado del hardcodeado).
    assert por_id["clasificar"]["doc_id"] == "prompt/clasificar-marca"
    # Etapas mecánicas: SOLO contexto (sin doc_id ni estado de publicación).
    for eid in ("recolectar", "agrupar", "admitir"):
        assert set(por_id[eid]) == {"tipo", "id", "titulo"}
    assert por_id["recolectar"]["titulo"] == "Recolectar"
    assert por_id["clasificar"]["titulo"] == "Clasificar"
    # Etapas prompt: doc + estado de publicación (degradado sin BD: sin puntero).
    for m in maquinas:
        for e in m["etapas"]:
            if e["tipo"] == "prompt":
                assert {"tipo", "id", "titulo", "doc_id", "produccion", "sha_actual",
                        "sin_publicar"} <= set(e)
                assert e["produccion"] is None

    # Producción: redactar -> revisar -> ilustrar -> aprobar -> publicar, y el taller idear al
    # final (mismo vocabulario que el hub Producción, verbos C: Redactar · Ilustrar · Aprobar).
    assert [(e["tipo"], e["id"]) for e in prod["etapas"]] == [
        ("prompt", "redactar"),
        ("mecanica", "revisar"),
        ("prompt", "ilustrar"),
        ("mecanica", "aprobar"),
        ("mecanica", "publicar"),
        ("prompt", "idear"),
    ]
    pp = {e["id"]: e for e in prod["etapas"]}
    assert pp["redactar"]["doc_id"] == "prompt/redactar"
    assert pp["redactar"]["titulo"] == "Redactar"
    assert pp["ilustrar"]["doc_id"] == "prompt/ilustrar"
    assert pp["ilustrar"]["titulo"] == "Ilustrar"
    assert pp["idear"]["doc_id"] == "prompt/idear"
    # `seccion` es OPCIONAL: solo el taller la lleva.
    assert pp["idear"]["seccion"] == "taller"
    assert "seccion" not in pp["redactar"] and "seccion" not in pp["ilustrar"]

    # Importación: los 4 cajones de Recibir + los 2 importadores, todos `prompt`.
    assert all(e["tipo"] == "prompt" for e in imp["etapas"])
    assert [e["doc_id"] for e in imp["etapas"]] == [
        "prompt/recibir/portal", "prompt/recibir/corresponsales",
        "prompt/recibir/reporteros", "prompt/recibir/eventos-claro",
        "prompt/importar/calendario", "prompt/importar/parrilla",
    ]


def test_maquina_respeta_rebindeo_de_copy(entorno_sin_pg):
    """La etapa Redactar se resuelve por el registro: un prompt activo rol=copy la rebindea."""
    c = _cliente()
    nuevo = _crear_doc(c, titulo="Copy alterno", cuerpo="X", rol="redactar", pipelines=["redactar"])
    r = c.get("/api/texto/maquina")
    prod = next(m for m in r.json()["maquinas"] if m["id"] == "produccion")
    etapa = next(e for e in prod["etapas"] if e["id"] == "redactar")
    assert etapa["doc_id"] == nuevo["id"]


# --------------------------------------------------------------------------- #
# Estrategia de marca (GET /api/texto/estrategia)                              #
# --------------------------------------------------------------------------- #


def test_estrategia_pilares_extras_y_orden(entorno_sin_pg):
    c = _cliente()
    voz = _crear_doc(c, titulo="Voz", cuerpo="tono cercano", tipo="editorial", clase="voz",
                     marcas=[_MARCA])
    en_blanco = _crear_doc(c, titulo="Marca", cuerpo="   ", tipo="editorial", clase="marca",
                           marcas=[_MARCA])
    tropi = _crear_doc(c, titulo="Tropicalización", cuerpo="es-MX", tipo="editorial",
                       clase="tropicalizacion")
    patrones = _crear_doc(c, titulo="Patrones medidos", cuerpo="bandas", tipo="editorial",
                          clase="", marcas=[_MARCA])

    r = c.get("/api/texto/estrategia", params={"marca": _MARCA})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["marca"] == _MARCA

    # SIEMPRE los 4+1 pilares, en orden fijo y con la forma completa.
    pilares = cuerpo["pilares"]
    assert [p["clase"] for p in pilares] == [
        "marca", "voz", "tropicalizacion", "plataforma", "reglas",
    ]
    for p in pilares:
        assert {"clase", "titulo", "doc_id", "vacio", "global", "produccion",
                "sha_actual", "sin_publicar", "actualizado"} <= set(p)
    por = {p["clase"]: p for p in pilares}

    # Pilar de marca con doc y cuerpo: cubierto, no global.
    assert por["voz"]["doc_id"] == voz["id"]
    assert por["voz"]["vacio"] is False and por["voz"]["global"] is False
    assert por["voz"]["titulo"] == "Voz y tono" and por["voz"]["actualizado"]
    # Doc presente pero con cuerpo EN BLANCO: vacio True (mismo criterio que /validacion).
    assert por["marca"]["doc_id"] == en_blanco["id"] and por["marca"]["vacio"] is True
    # Pilar global con doc.
    assert por["tropicalizacion"]["doc_id"] == tropi["id"]
    assert por["tropicalizacion"]["global"] is True
    assert por["tropicalizacion"]["titulo"] == "Tropicalización MX"
    # Pilares SIN documento: presentes igual, doc_id null y todo degradado.
    for clase in ("plataforma", "reglas"):
        p = por[clase]
        assert p["doc_id"] is None and p["vacio"] is True and p["global"] is True
        assert p["produccion"] is None and p["sha_actual"] is None
        assert p["sin_publicar"] is False and p["actualizado"] is None

    # Extras: documentos del auto-adjunto sin clase-pilar, con su PROPIO título.
    assert [x["doc_id"] for x in cuerpo["extras"]] == [patrones["id"]]
    assert cuerpo["extras"][0]["titulo"] == "Patrones medidos"
    assert cuerpo["extras"][0]["global"] is False and cuerpo["extras"][0]["vacio"] is False

    # Completitud: la MISMA lógica que /validacion (marca en blanco y plataforma faltante).
    comp = cuerpo["completitud"]
    assert set(comp) == {"completa", "faltan", "recomendacion"}
    assert comp["completa"] is False
    assert "marca" in comp["faltan"] and "plataforma" in comp["faltan"]
    assert "voz" not in comp["faltan"] and "tropicalizacion" not in comp["faltan"]
    assert comp["recomendacion"]

    # Orden de inyección: EXACTAMENTE los adjuntos reales del copy, en su orden.
    assert cuerpo["orden_inyeccion"] == [d.id for d in generar.adjuntos_copy(_MARCA)]
    assert voz["id"] in cuerpo["orden_inyeccion"]
    assert patrones["id"] in cuerpo["orden_inyeccion"]


def test_estrategia_sin_marca(entorno_sin_pg):
    """Sin marca: los pilares específicos no se cubren y se pide elegir una marca."""
    c = _cliente()
    r = c.get("/api/texto/estrategia")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["marca"] == ""
    assert [p["clase"] for p in cuerpo["pilares"]] == [
        "marca", "voz", "tropicalizacion", "plataforma", "reglas",
    ]
    assert cuerpo["completitud"]["completa"] is False
    assert "marca" in cuerpo["completitud"]["recomendacion"].lower()
