"""Tests del REDISENO de la Texto: metadatos transversales, binding a pipelines y
versionado git. PUROS (sin Postgres): solo aislan `KENI_PROMPTS_DIR` en un tmp.

Cubren:
  - round-trip de los campos nuevos (etiquetas/pipelines/rol/prioridad) por frontmatter.
  - auto-adjunto editorial filtrado por PIPELINE + orden por PRIORIDAD.
  - resolucion del prompt base de un pipeline (defecto del registro + rebindeo por doc).
  - preview del prompt ensamblado ("lo que inyectas es lo que ves").
  - listado con facetas.
  - versionado git: historial, lectura de una version y rollback no destructivo.
"""

from __future__ import annotations

import shutil

import pytest

from keni_consola import libprompts


@pytest.fixture(autouse=True)
def _texto_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Round-trip de los campos nuevos                                             #
# --------------------------------------------------------------------------- #


def test_campos_nuevos_round_trip_editorial():
    doc = libprompts.crear(
        "Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="Tono cercano.",
        etiquetas=["Tono", "tono", "  Piloto "], pipelines=["redactar"], prioridad=5,
    )
    leido = libprompts.obtener(doc.id)
    assert leido is not None
    assert leido.etiquetas == ["tono", "piloto"]  # normalizadas + de-dup
    assert leido.pipelines == ["redactar"]
    assert leido.prioridad == 5
    assert leido.rol == ""  # editorial no lleva rol


def test_rol_solo_para_prompt_y_defaults():
    p = libprompts.crear("Copy base", tipo="prompt", cuerpo="...", rol="redactar", pipelines=["redactar"])
    assert libprompts.obtener(p.id).rol == "redactar"
    # Un editorial ignora rol (queda vacio aunque se intente).
    e = libprompts.crear("Reglas", tipo="editorial", clase="reglas", cuerpo="...")
    assert e.etiquetas == [] and e.prioridad == 0


def test_guardar_preserva_y_actualiza_campos():
    doc = libprompts.crear("Marca", tipo="editorial", clase="marca", marcas=["unotv"], cuerpo="x")
    libprompts.guardar(doc.id, etiquetas=["clave"], prioridad=-3)
    leido = libprompts.obtener(doc.id)
    assert leido.etiquetas == ["clave"]
    assert leido.prioridad == -3
    assert leido.clase == "marca"  # no se toco


def test_pipeline_desconocido_lanza():
    with pytest.raises(libprompts.PromptsError):
        libprompts.crear("X", tipo="editorial", clase="reglas", pipelines=["inexistente"])


# --------------------------------------------------------------------------- #
# Auto-adjunto: filtro por pipeline + orden por prioridad                     #
# --------------------------------------------------------------------------- #


def test_editoriales_filtra_por_pipeline():
    # Global sin pipelines declarados -> aplica a TODOS (retrocompat).
    libprompts.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="p")
    # Acotado a copy: NO debe entrar en verificación.
    libprompts.crear("Solo copy", tipo="editorial", clase="reglas", cuerpo="c", pipelines=["redactar"])
    ids_copy = {d.id for d in libprompts.editoriales_de_marca("unotv", pipeline="redactar")}
    ids_verificacion = {d.id for d in libprompts.editoriales_de_marca("unotv", pipeline="verificar")}
    assert "editorial/plataformas" in ids_copy and "editorial/plataformas" in ids_verificacion
    assert "editorial/solo-copy" in ids_copy
    assert "editorial/solo-copy" not in ids_verificacion


def test_editoriales_acota_priorizar():
    # `priorizar` es pipeline de primera clase: un editorial acotado a [redactar] NO entra en
    # priorizar; uno acotado a [redactar, priorizar] sí. Antes priorizar tragaba TODO (sin filtro).
    libprompts.crear("Voz", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="v", pipelines=["redactar", "priorizar"])
    libprompts.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="p", pipelines=["redactar"])
    ids = {d.id for d in libprompts.editoriales_de_marca("unotv", pipeline="priorizar")}
    assert "editorial/voz" in ids
    assert "editorial/plataformas" not in ids


def test_editoriales_ordena_por_prioridad():
    libprompts.crear("Reglas A", tipo="editorial", clase="reglas", cuerpo="a", prioridad=10)
    libprompts.crear("Tropi B", tipo="editorial", clase="tropicalizacion", cuerpo="b", prioridad=-5)
    orden = [d.id for d in libprompts.editoriales_de_marca("unotv")]
    assert orden.index("editorial/tropi-b") < orden.index("editorial/reglas-a")


def test_editoriales_scoping_por_carpeta():
    # Estructura rrss -> marca -> categoria: la marca se deriva de la CARPETA (sin campo `marcas`).
    libprompts.crear("Marca", tipo="editorial", carpeta="rrss/unotv", cuerpo="v")
    libprompts.crear("Reglas", tipo="editorial", carpeta="rrss/claro-sports/legal", cuerpo="r")
    # `global` en cualquier segmento (p. ej. rrss/global) aplica a TODAS las marcas.
    libprompts.crear("Plataformas", tipo="editorial", carpeta="rrss/global", cuerpo="p")

    ids_unotv = {d.id for d in libprompts.editoriales_de_marca("unotv")}
    assert "editorial/rrss/unotv/marca" in ids_unotv
    assert "editorial/rrss/global/plataformas" in ids_unotv  # global, para todas
    assert "editorial/rrss/claro-sports/legal/reglas" not in ids_unotv  # otra marca

    ids_claro = {d.id for d in libprompts.editoriales_de_marca("claro-sports")}
    assert "editorial/rrss/claro-sports/legal/reglas" in ids_claro
    assert "editorial/rrss/global/plataformas" in ids_claro
    assert "editorial/rrss/unotv/marca" not in ids_claro


# --------------------------------------------------------------------------- #
# Resolucion de pipeline + preview                                           #
# --------------------------------------------------------------------------- #


def test_prompt_base_defecto_cuando_nadie_rebindea():
    assert libprompts.prompt_base_de("redactar") =="prompt/redactar"
    assert libprompts.prompt_base_de("verificar") == "prompt/verificar"


def test_prompt_base_rebindeo_por_documento():
    # Un prompt activo con rol=redactar que declara el pipeline redactar GANA al defecto del registro.
    nuevo = libprompts.crear("Copy v2", tipo="prompt", cuerpo="...", rol="redactar", pipelines=["redactar"])
    assert libprompts.prompt_base_de("redactar") ==nuevo.id


def test_previsualizar_pipeline_ensambla_base_y_adjuntos():
    libprompts.crear("Copy base", tipo="prompt", carpeta="", cuerpo="INSTRUCCION BASE", rol="redactar", pipelines=["redactar"])
    libprompts.crear("Reglas", tipo="editorial", clase="reglas", cuerpo="REGLA EDITORIAL")
    prev = libprompts.previsualizar_pipeline("redactar", "unotv", "CONTEXTO DE PRUEBA")
    assert prev["falta_base"] is False
    assert "INSTRUCCION BASE" in prev["prompt_efectivo"]
    assert "REGLA EDITORIAL" in prev["prompt_efectivo"]
    assert "CONTEXTO DE PRUEBA" in prev["prompt_efectivo"]
    assert any(a["id"] == "editorial/reglas" for a in prev["adjuntos"])


def test_previsualizar_pipeline_copy_es_fiel_al_lanzamiento():
    """El preview del pipeline `copy` pasa por la MISMA composición que `lanzar_copy`:
    instrucción de copy UNIFICADO + reglas de imagen adjuntas.
    Sin `redes_ids` se previsualiza con TODAS las redes (un lanzamiento real siempre las trae)."""
    libprompts.crear("Copy base", tipo="prompt", carpeta="", cuerpo="BASE", rol="redactar", pipelines=["redactar"])
    prev = libprompts.previsualizar_pipeline("redactar", "unotv", "CTX")
    # La instrucción unificada pide un solo copy acotado al límite más estricto entre todas las
    # redes (Instagram = 2200), sin versión corta aparte.
    assert "Este copy se publicará TAL CUAL en estas redes" in prev["prompt_efectivo"]
    assert "texto_corto" not in prev["prompt_efectivo"]
    assert "2200 caracteres" in prev["prompt_efectivo"]  # Instagram, el más estricto, desde el código
    assert any(a["id"] == "editorial/reglas/imagen" for a in prev["adjuntos"])

    # Con redes explícitas, solo esas entran en la instrucción.
    prev_x = libprompts.previsualizar_pipeline("redactar", "unotv", "CTX", redes_ids=["x"])
    assert "Este copy se publicará TAL CUAL en estas redes: X." in prev_x["prompt_efectivo"]


def test_previsualizar_pipeline_sin_prompt_base():
    # Sin store ni inicial del prompt de verificación -> falta_base True (no revienta).
    prev = libprompts.previsualizar_pipeline("verificar", "unotv")
    assert "falta_base" in prev


# --------------------------------------------------------------------------- #
# Listado con facetas                                                         #
# --------------------------------------------------------------------------- #


def test_listar_filtra_por_etiqueta():
    libprompts.crear("A", tipo="prompt", cuerpo="x", etiquetas=["destacado"])
    libprompts.crear("B", tipo="prompt", cuerpo="y")
    etiquetados = libprompts.listar(etiqueta="destacado")
    assert {d.id for d in etiquetados} == {"prompt/a"}


# --------------------------------------------------------------------------- #
# Versionado git (se EJERCITA con git activo; se salta si no hay git)         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def _git_activo(monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    monkeypatch.setenv("KENI_PROMPTS_GIT", "1")


def test_autosave_no_versiona_solo_fijar_version_comitea(_git_activo):
    """Versionado INTENCIONADO: `guardar` (autosave) NO crea commit; solo `crear` y
    `fijar_version` (publicar/solicitar) comitean. El HEAD git no se mueve al teclear."""
    from keni_consola import versionado

    doc = libprompts.crear("Doc versionado", tipo="prompt", cuerpo="VERSION 1")
    # Tras crear: UN commit (la creación).
    assert len(versionado.historial(doc.id)) == 1
    sha_v1 = versionado.sha_documento(doc.id)

    # Dos autosaves: el working copy cambia, pero NO hay commits nuevos.
    libprompts.guardar(doc.id, cuerpo="VERSION 2")
    libprompts.guardar(doc.id, cuerpo="VERSION 3")
    assert len(versionado.historial(doc.id)) == 1
    assert versionado.sha_documento(doc.id) == sha_v1  # HEAD intacto

    # `fijar_version` (lo que dispara publicar/solicitar) SÍ comitea el working copy.
    sha_v3 = libprompts.fijar_version(doc.id, nota="congelo V3")
    assert sha_v3 and sha_v3 != sha_v1
    assert len(versionado.historial(doc.id)) == 2
    assert versionado.historial(doc.id)[0]["mensaje"] == "congelo V3"


def test_version_lee_un_sha_y_restaurar_trae_al_borrador(_git_activo):
    """`version` lee el `.md` de un sha; `restaurar_version` ("Traer al borrador") carga ese
    contenido en el working copy SIN crear commit (no es un rollback con commit)."""
    from keni_consola import versionado

    doc = libprompts.crear("Doc", tipo="prompt", cuerpo="VERSION 1")
    sha_v1 = versionado.sha_documento(doc.id)
    libprompts.guardar(doc.id, cuerpo="VERSION 2")
    sha_v2 = libprompts.fijar_version(doc.id, nota="v2")
    assert sha_v2 != sha_v1

    assert "VERSION 1" in (libprompts.version(doc.id, sha_v1).cuerpo)
    assert "VERSION 2" in (libprompts.version(doc.id, sha_v2).cuerpo)

    # Traer V1 al borrador: el working copy vuelve a V1 SIN nuevo commit (HEAD sigue en V2).
    traido = libprompts.restaurar_version(doc.id, sha_v1)
    assert "VERSION 1" in traido.cuerpo
    assert libprompts.obtener(doc.id).cuerpo.strip() == "VERSION 1"
    assert versionado.sha_documento(doc.id) == sha_v2  # no se commiteó nada


def test_historial_sin_postgres_es_vacio(_git_activo):
    """`libprompts.historial` es el de PUBLICACIONES: sin Postgres devuelve [] (best-effort),
    aunque haya commits git de creación/versión por debajo."""
    doc = libprompts.crear("Sin BD", tipo="prompt", cuerpo="x")
    libprompts.fijar_version(doc.id, nota="v1")
    assert libprompts.historial(doc.id) == []


def test_versionado_apagado_no_da_historial(monkeypatch):
    monkeypatch.setenv("KENI_PROMPTS_GIT", "0")
    doc = libprompts.crear("Sin git", tipo="prompt", cuerpo="x")
    assert libprompts.historial(doc.id) == []


# --------------------------------------------------------------------------- #
# Concurrencia optimista (rev / ETag) — pura, sin git ni Postgres            #
# --------------------------------------------------------------------------- #


def test_rev_documento_estable_y_cambia_al_guardar():
    """El `rev` es estable entre lecturas del mismo fichero y cambia tras cada guardado."""
    doc = libprompts.crear("Rev", tipo="prompt", cuerpo="uno")
    rev1 = libprompts.rev_documento(libprompts.obtener(doc.id))
    assert libprompts.rev_documento(libprompts.obtener(doc.id)) == rev1  # releer sin cambios
    libprompts.guardar(doc.id, cuerpo="dos")
    assert libprompts.rev_documento(libprompts.obtener(doc.id)) != rev1


def test_guardar_con_rev_correcto_ok():
    """Guardar con el `rev` que se cargó procede sin conflicto."""
    doc = libprompts.crear("Rev ok", tipo="prompt", cuerpo="uno")
    rev = libprompts.rev_documento(libprompts.obtener(doc.id))
    libprompts.guardar(doc.id, cuerpo="dos", rev_base=rev)
    assert libprompts.obtener(doc.id).cuerpo == "dos"


def test_guardar_con_rev_obsoleto_lanza_conflicto():
    """Si el working copy cambió debajo, guardar con el rev viejo lanza ConflictoEdicion y NO escribe."""
    doc = libprompts.crear("Rev choque", tipo="prompt", cuerpo="uno")
    rev_viejo = libprompts.rev_documento(libprompts.obtener(doc.id))
    libprompts.guardar(doc.id, cuerpo="dos")  # otro editor guarda primero (mueve el rev)
    with pytest.raises(libprompts.ConflictoEdicion):
        libprompts.guardar(doc.id, cuerpo="tres", rev_base=rev_viejo)
    assert libprompts.obtener(doc.id).cuerpo == "dos"  # no se pisó al otro editor


def test_guardar_sin_rev_no_chequea():
    """Sin `rev_base` no hay chequeo (autosave legado / last-write-wins)."""
    doc = libprompts.crear("Rev legado", tipo="prompt", cuerpo="uno")
    libprompts.guardar(doc.id, cuerpo="dos")  # sin rev_base
    libprompts.guardar(doc.id, cuerpo="tres")
    assert libprompts.obtener(doc.id).cuerpo == "tres"
