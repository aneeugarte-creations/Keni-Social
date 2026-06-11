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

    # Investigación: el proceso COMPLETO en orden (la frontera del ADR: QA es Investigación),
    # con las etapas sin prompt de la Biblioteca como `mecanica` (contexto del riel).
    assert [(e["tipo"], e["id"]) for e in inv["etapas"]] == [
        ("mecanica", "ingesta"),
        ("mecanica", "clustering"),
        ("prompt", "fusion-verificacion"),
        ("prompt", "fusion"),
        ("prompt", "traduccion"),
        ("mecanica", "clasificacion-marca"),
        ("prompt", "ranking"),
        ("mecanica", "admision"),
        ("prompt", "validacion"),
        ("prompt", "algoritmos"),
    ]
    por_id = {e["id"]: e for e in inv["etapas"]}
    assert por_id["validacion"]["doc_id"] == "prompt/validacion"  # prompt_base_de("qa")
    assert por_id["ranking"]["doc_id"] == "prompt/editorial"
    assert por_id["algoritmos"]["doc_id"] == "prompt/sugerencias"
    # Etapas mecánicas: SOLO contexto (sin doc_id ni estado de publicación).
    for eid in ("ingesta", "clustering", "clasificacion-marca", "admision"):
        assert set(por_id[eid]) == {"tipo", "id", "titulo"}
    assert por_id["clasificacion-marca"]["titulo"] == "Clasificación de marca (IA)"
    # Etapas prompt: doc + estado de publicación (degradado sin BD: sin puntero).
    for m in maquinas:
        for e in m["etapas"]:
            if e["tipo"] == "prompt":
                assert {"tipo", "id", "titulo", "doc_id", "produccion", "sha_actual",
                        "sin_publicar"} <= set(e)
                assert e["produccion"] is None

    # Producción: copy -> arte -> avance -> publicación, y el taller evergreen al final.
    assert [(e["tipo"], e["id"]) for e in prod["etapas"]] == [
        ("prompt", "copy"),
        ("prompt", "arte"),
        ("mecanica", "avance"),
        ("mecanica", "publicacion"),
        ("prompt", "evergreen"),
    ]
    pp = {e["id"]: e for e in prod["etapas"]}
    assert pp["copy"]["doc_id"] == "prompt/copy"
    assert pp["arte"]["doc_id"] == "prompt/arte"
    assert pp["evergreen"]["doc_id"] == "prompt/evergreen"
    # `seccion` es OPCIONAL: solo el taller la lleva.
    assert pp["evergreen"]["seccion"] == "taller"
    assert "seccion" not in pp["copy"] and "seccion" not in pp["arte"]

    # Importación: los 4 buzones de insumos + los 2 importadores, todos `prompt`.
    assert all(e["tipo"] == "prompt" for e in imp["etapas"])
    assert [e["doc_id"] for e in imp["etapas"]] == [
        "prompt/insumos/portal", "prompt/insumos/corresponsales",
        "prompt/insumos/reporteros", "prompt/insumos/eventos-claro",
        "prompt/importar/calendario", "prompt/importar/parrilla",
    ]


def test_maquina_respeta_rebindeo_de_copy(entorno_sin_pg):
    """La etapa de copy se resuelve por el registro: un prompt activo rol=copy la rebindea."""
    c = _cliente()
    nuevo = _crear_doc(c, titulo="Copy alterno", cuerpo="X", rol="copy", pipelines=["copy"])
    r = c.get("/api/texto/maquina")
    prod = next(m for m in r.json()["maquinas"] if m["id"] == "produccion")
    etapa = next(e for e in prod["etapas"] if e["id"] == "copy")
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
