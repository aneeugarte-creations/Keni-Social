"""Tests del REDISENO de la Texto: metadatos transversales, binding a pipelines y
versionado git. PUROS (sin Postgres): solo aislan `KENI_TEXTO_DIR` en un tmp.

Cubren:
  - round-trip de los campos nuevos (estado/etiquetas/pipelines/rol/prioridad) por frontmatter.
  - auto-adjunto editorial filtrado por ESTADO y por PIPELINE + orden por PRIORIDAD.
  - resolucion del prompt base de un pipeline (defecto del registro + rebindeo por doc).
  - preview del prompt ensamblado ("lo que inyectas es lo que ves").
  - listado con facetas.
  - versionado git: historial, lectura de una version y rollback no destructivo.
"""

from __future__ import annotations

import shutil

import pytest

from keni_consola import libtexto


@pytest.fixture(autouse=True)
def _texto_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Round-trip de los campos nuevos                                             #
# --------------------------------------------------------------------------- #


def test_campos_nuevos_round_trip_editorial():
    doc = libtexto.crear(
        "Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="Tono cercano.",
        estado="borrador", etiquetas=["Tono", "tono", "  Piloto "], pipelines=["copy"], prioridad=5,
    )
    leido = libtexto.obtener(doc.id)
    assert leido is not None
    assert leido.estado == "borrador"
    assert leido.etiquetas == ["tono", "piloto"]  # normalizadas + de-dup
    assert leido.pipelines == ["copy"]
    assert leido.prioridad == 5
    assert leido.rol == ""  # editorial no lleva rol


def test_rol_solo_para_prompt_y_defaults():
    p = libtexto.crear("Copy base", tipo="prompt", cuerpo="...", rol="copy", pipelines=["copy"])
    assert libtexto.obtener(p.id).rol == "copy"
    # Un editorial ignora rol (queda vacio aunque se intente).
    e = libtexto.crear("Reglas", tipo="editorial", clase="reglas", cuerpo="...")
    assert e.estado == "activo" and e.etiquetas == [] and e.prioridad == 0


def test_guardar_preserva_y_actualiza_campos():
    doc = libtexto.crear("Marca", tipo="editorial", clase="marca", marcas=["unotv"], cuerpo="x")
    libtexto.guardar(doc.id, estado="archivado", etiquetas=["clave"], prioridad=-3)
    leido = libtexto.obtener(doc.id)
    assert leido.estado == "archivado"
    assert leido.etiquetas == ["clave"]
    assert leido.prioridad == -3
    assert leido.clase == "marca"  # no se toco


def test_pipeline_desconocido_lanza():
    with pytest.raises(libtexto.TextoError):
        libtexto.crear("X", tipo="editorial", clase="reglas", pipelines=["inexistente"])


def test_estado_invalido_lanza():
    with pytest.raises(libtexto.TextoError):
        libtexto.crear("X", tipo="prompt", estado="raro")


# --------------------------------------------------------------------------- #
# Auto-adjunto: filtro por estado / pipeline + orden por prioridad           #
# --------------------------------------------------------------------------- #


def test_editoriales_excluye_no_activos():
    libtexto.crear("Reglas", tipo="editorial", clase="reglas", cuerpo="r")
    libtexto.crear("Borrador", tipo="editorial", clase="tropicalizacion", cuerpo="t", estado="borrador")
    ids = {d.id for d in libtexto.editoriales_de_marca("unotv")}
    assert "editorial/reglas" in ids
    assert "editorial/borrador" not in ids  # borrador no inyecta


def test_editoriales_filtra_por_pipeline():
    # Global sin pipelines declarados -> aplica a TODOS (retrocompat).
    libtexto.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="p")
    # Acotado a copy: NO debe entrar en qa.
    libtexto.crear("Solo copy", tipo="editorial", clase="reglas", cuerpo="c", pipelines=["copy"])
    ids_copy = {d.id for d in libtexto.editoriales_de_marca("unotv", pipeline="copy")}
    ids_qa = {d.id for d in libtexto.editoriales_de_marca("unotv", pipeline="qa")}
    assert "editorial/plataformas" in ids_copy and "editorial/plataformas" in ids_qa
    assert "editorial/solo-copy" in ids_copy
    assert "editorial/solo-copy" not in ids_qa


def test_editoriales_ordena_por_prioridad():
    libtexto.crear("Reglas A", tipo="editorial", clase="reglas", cuerpo="a", prioridad=10)
    libtexto.crear("Tropi B", tipo="editorial", clase="tropicalizacion", cuerpo="b", prioridad=-5)
    orden = [d.id for d in libtexto.editoriales_de_marca("unotv")]
    assert orden.index("editorial/tropi-b") < orden.index("editorial/reglas-a")


def test_editoriales_scoping_por_carpeta():
    # Estructura rrss -> marca -> categoria: la marca se deriva de la CARPETA (sin campo `marcas`).
    libtexto.crear("Marca", tipo="editorial", carpeta="rrss/unotv", cuerpo="v")
    libtexto.crear("Reglas", tipo="editorial", carpeta="rrss/claro-sports/legal", cuerpo="r")
    # `global` en cualquier segmento (p. ej. rrss/global) aplica a TODAS las marcas.
    libtexto.crear("Plataformas", tipo="editorial", carpeta="rrss/global", cuerpo="p")

    ids_unotv = {d.id for d in libtexto.editoriales_de_marca("unotv")}
    assert "editorial/rrss/unotv/marca" in ids_unotv
    assert "editorial/rrss/global/plataformas" in ids_unotv  # global, para todas
    assert "editorial/rrss/claro-sports/legal/reglas" not in ids_unotv  # otra marca

    ids_claro = {d.id for d in libtexto.editoriales_de_marca("claro-sports")}
    assert "editorial/rrss/claro-sports/legal/reglas" in ids_claro
    assert "editorial/rrss/global/plataformas" in ids_claro
    assert "editorial/rrss/unotv/marca" not in ids_claro


# --------------------------------------------------------------------------- #
# Resolucion de pipeline + preview                                           #
# --------------------------------------------------------------------------- #


def test_prompt_base_defecto_cuando_nadie_rebindea():
    assert libtexto.prompt_base_de("copy") == "prompt/copy"
    assert libtexto.prompt_base_de("qa") == "prompt/validacion"


def test_prompt_base_rebindeo_por_documento():
    # Un prompt activo con rol=copy que declara el pipeline copy GANA al defecto del registro.
    nuevo = libtexto.crear("Copy v2", tipo="prompt", cuerpo="...", rol="copy", pipelines=["copy"])
    assert libtexto.prompt_base_de("copy") == nuevo.id
    # Un borrador NO rebindea (estado != activo).
    libtexto.guardar(nuevo.id, estado="borrador")
    assert libtexto.prompt_base_de("copy") == "prompt/copy"


def test_previsualizar_pipeline_ensambla_base_y_adjuntos():
    libtexto.crear("Copy base", tipo="prompt", carpeta="", cuerpo="INSTRUCCION BASE", rol="copy", pipelines=["copy"])
    libtexto.crear("Reglas", tipo="editorial", clase="reglas", cuerpo="REGLA EDITORIAL")
    prev = libtexto.previsualizar_pipeline("copy", "unotv", "CONTEXTO DE PRUEBA")
    assert prev["falta_base"] is False
    assert "INSTRUCCION BASE" in prev["prompt_efectivo"]
    assert "REGLA EDITORIAL" in prev["prompt_efectivo"]
    assert "CONTEXTO DE PRUEBA" in prev["prompt_efectivo"]
    assert any(a["id"] == "editorial/reglas" for a in prev["adjuntos"])


def test_previsualizar_pipeline_copy_es_fiel_al_lanzamiento():
    """El preview del pipeline `copy` pasa por la MISMA composición que `lanzar_copy`:
    instrucción de copy UNIFICADO + reglas de imagen adjuntas.
    Sin `redes_ids` se previsualiza con TODAS las redes (un lanzamiento real siempre las trae)."""
    libtexto.crear("Copy base", tipo="prompt", carpeta="", cuerpo="BASE", rol="copy", pipelines=["copy"])
    prev = libtexto.previsualizar_pipeline("copy", "unotv", "CTX")
    # Con TODAS las redes se mezclan AMPLIAS (Instagram/Facebook) y ESTRECHAS (X): la
    # instrucción unificada pide DOS versiones del mismo mensaje (`texto` + `texto_corto`),
    # con la condensada al límite de las estrechas (X = 280).
    assert "Este copy se publicará en estas redes" in prev["prompt_efectivo"]
    assert "texto_corto" in prev["prompt_efectivo"]
    assert "280 caracteres" in prev["prompt_efectivo"]  # el más estricto (X) desde el código
    assert any(a["id"] == "editorial/reglas/imagen" for a in prev["adjuntos"])

    # Con redes explícitas, solo esas entran en la instrucción.
    prev_x = libtexto.previsualizar_pipeline("copy", "unotv", "CTX", redes_ids=["x"])
    assert "Este copy se publicará TAL CUAL en estas redes: X." in prev_x["prompt_efectivo"]


def test_previsualizar_pipeline_sin_prompt_base():
    # Sin store ni semilla del prompt de qa -> falta_base True (no revienta).
    prev = libtexto.previsualizar_pipeline("qa", "unotv")
    assert "falta_base" in prev


# --------------------------------------------------------------------------- #
# Listado con facetas                                                         #
# --------------------------------------------------------------------------- #


def test_listar_filtra_por_estado_y_etiqueta():
    libtexto.crear("A", tipo="prompt", cuerpo="x", etiquetas=["destacado"])
    libtexto.crear("B", tipo="prompt", cuerpo="y", estado="archivado")
    activos = libtexto.listar(estado="activo")
    assert {d.id for d in activos} == {"prompt/a"}
    etiquetados = libtexto.listar(etiqueta="destacado")
    assert {d.id for d in etiquetados} == {"prompt/a"}


# --------------------------------------------------------------------------- #
# Versionado git (se EJERCITA con git activo; se salta si no hay git)         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def _git_activo(monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    monkeypatch.setenv("KENI_TEXTO_GIT", "1")


def test_versionado_historial_y_rollback(_git_activo):
    doc = libtexto.crear("Doc versionado", tipo="prompt", cuerpo="VERSION 1")
    libtexto.guardar(doc.id, cuerpo="VERSION 2")
    libtexto.guardar(doc.id, cuerpo="VERSION 3")

    hist = libtexto.historial(doc.id)
    assert len(hist) >= 3
    assert all(h["sha"] and h["fecha"] and h["autor"] for h in hist)

    # La version mas antigua (ultima de la lista) contiene "VERSION 1".
    sha_inicial = hist[-1]["sha"]
    antiguo = libtexto.version(doc.id, sha_inicial)
    assert antiguo is not None and "VERSION 1" in antiguo.cuerpo

    # Rollback NO destructivo: el cuerpo vuelve a V1 y crece el historial.
    revertido = libtexto.restaurar_version(doc.id, sha_inicial)
    assert "VERSION 1" in revertido.cuerpo
    assert libtexto.obtener(doc.id).cuerpo.strip() == "VERSION 1"
    assert len(libtexto.historial(doc.id)) >= 4


def test_versionado_apagado_no_da_historial(monkeypatch):
    monkeypatch.setenv("KENI_TEXTO_GIT", "0")
    doc = libtexto.crear("Sin git", tipo="prompt", cuerpo="x")
    assert libtexto.historial(doc.id) == []
