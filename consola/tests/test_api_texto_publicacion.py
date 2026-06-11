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

from keni_consola import generaciones, libtexto, marcas
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
    hist = c.get(f"/api/texto/{doc_id}/historial").json()["historial"]
    assert hist, "el doc debería tener al menos un commit"
    return hist[0]["sha"]


# --------------------------------------------------------------------------- #
# Publicar (solo admin) + campos nuevos del documento                          #
# --------------------------------------------------------------------------- #


def test_publicar_mueve_el_puntero_y_expone_campos(entorno_pub):
    c = _cliente(_ADMIN)
    doc = _crear_doc(c)
    head = _head(c, doc["id"])

    # Antes de publicar: sin puntero, sin_publicar False (la working copy ES lo inyectado).
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"] is None
    assert d["sin_publicar"] is False
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

    # Editar tras publicar: el puntero NO se mueve y el doc queda "sin publicar".
    c.put(f"/api/texto/{doc['id']}", json={"cuerpo": "V2"})
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"]["sha"] == head
    assert d["sha_actual"] != head
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


def test_sin_puntero_se_inyecta_la_working_copy(entorno_pub):
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="WORKING COPY")
    assert libtexto.cuerpo_efectivo(doc["id"]) is not None
    assert "WORKING COPY" in libtexto.cuerpo_efectivo(doc["id"])
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"] is None
    assert d["sin_publicar"] is False


def test_sin_postgres_todo_degrada_a_working_copy(entorno_sin_pg):
    """Migración suave: sin BD no hay puntero; leer/listar/componer NUNCA rompen."""
    c = _cliente(_ADMIN)
    doc = _crear_doc(c, cuerpo="SOLO WORKING")
    d = c.get(f"/api/texto/{doc['id']}").json()["documento"]
    assert d["produccion"] is None
    assert d["sin_publicar"] is False
    assert "SOLO WORKING" in (libtexto.cuerpo_efectivo(doc["id"]) or "")
    # El listado también responde con los campos nuevos degradados.
    fila = c.get("/api/texto").json()["documentos"][0]
    assert fila["produccion"] is None and fila["sin_publicar"] is False


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
    # Variables REALES del código (perfil editorial, fusión, traducción, sugerencias, importadores).
    assert {"MARCA", "MAX_KEYWORDS", "EDITORIAL", "HISTORIAS", "ITEMS", "PLATAFORMA", "RUTA"} <= nombres


def test_maquina_riel_y_capas(entorno_sin_pg):
    c = _cliente()
    # Una capa editorial propia de la marca, para verla aparecer en `capas`.
    voz = _crear_doc(c, titulo="Voz", cuerpo="tono", tipo="editorial", clase="voz", marcas=[_MARCA])

    r = c.get("/api/texto/maquina", params={"marca": _MARCA})
    assert r.status_code == 200
    cuerpo = r.json()
    grupos = cuerpo["grupos"]
    assert [g["id"] for g in grupos] == ["ingesta", "priorizacion", "produccion", "talleres"]

    # Producción en su ORDEN real: qa -> copy -> arte, con los doc_id del registro.
    produccion = next(g for g in grupos if g["id"] == "produccion")
    assert [e["id"] for e in produccion["etapas"]] == ["qa", "copy", "arte"]
    por_id = {e["id"]: e for e in produccion["etapas"]}
    assert por_id["qa"]["doc_id"] == "prompt/validacion"
    assert por_id["copy"]["doc_id"] == "prompt/copy"
    assert por_id["arte"]["doc_id"] == "prompt/arte"
    # Toda etapa lleva el estado de publicación (degradado sin BD: sin puntero).
    for g in grupos:
        for e in g["etapas"]:
            assert {"id", "titulo", "doc_id", "produccion", "sha_actual", "sin_publicar"} <= set(e)
            assert e["produccion"] is None

    # Ingesta en el orden real del barrido: fusión -> verificación -> traducción.
    ingesta = next(g for g in grupos if g["id"] == "ingesta")
    assert [e["doc_id"] for e in ingesta["etapas"]] == [
        "prompt/fusion", "prompt/fusion-verificacion", "prompt/traduccion",
    ]

    # Capas: el ensamblaje editorial de la marca, con orden 1..n y la voz creada dentro.
    capas = cuerpo["capas"]
    assert [x["orden"] for x in capas] == list(range(1, len(capas) + 1))
    la_voz = next(x for x in capas if x["doc_id"] == voz["id"])
    assert la_voz["clase"] == "voz"
    assert {"doc_id", "titulo", "clase", "orden", "produccion", "sha_actual", "sin_publicar"} <= set(la_voz)
