"""Tests del REDISENO de la Biblioteca: metadatos transversales, binding a pipelines y
versionado git. PUROS (sin Postgres): solo aislan `KENI_BIBLIOTECA_DIR` en un tmp.

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

from keni_consola import biblioteca


@pytest.fixture(autouse=True)
def _biblioteca_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_BIBLIOTECA_DIR", str(tmp_path / "biblioteca"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Round-trip de los campos nuevos                                             #
# --------------------------------------------------------------------------- #


def test_campos_nuevos_round_trip_editorial():
    doc = biblioteca.crear(
        "Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="Tono cercano.",
        estado="borrador", etiquetas=["Tono", "tono", "  Piloto "], pipelines=["copy"], prioridad=5,
    )
    leido = biblioteca.obtener(doc.id)
    assert leido is not None
    assert leido.estado == "borrador"
    assert leido.etiquetas == ["tono", "piloto"]  # normalizadas + de-dup
    assert leido.pipelines == ["copy"]
    assert leido.prioridad == 5
    assert leido.rol == ""  # editorial no lleva rol


def test_rol_solo_para_prompt_y_defaults():
    p = biblioteca.crear("Copy base", tipo="prompt", cuerpo="...", rol="copy", pipelines=["copy"])
    assert biblioteca.obtener(p.id).rol == "copy"
    # Un editorial ignora rol (queda vacio aunque se intente).
    e = biblioteca.crear("Reglas", tipo="editorial", clase="reglas", cuerpo="...")
    assert e.estado == "activo" and e.etiquetas == [] and e.prioridad == 0


def test_guardar_preserva_y_actualiza_campos():
    doc = biblioteca.crear("Marca", tipo="editorial", clase="marca", marcas=["unotv"], cuerpo="x")
    biblioteca.guardar(doc.id, estado="archivado", etiquetas=["clave"], prioridad=-3)
    leido = biblioteca.obtener(doc.id)
    assert leido.estado == "archivado"
    assert leido.etiquetas == ["clave"]
    assert leido.prioridad == -3
    assert leido.clase == "marca"  # no se toco


def test_pipeline_desconocido_lanza():
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca.crear("X", tipo="editorial", clase="reglas", pipelines=["inexistente"])


def test_estado_invalido_lanza():
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca.crear("X", tipo="prompt", estado="raro")


# --------------------------------------------------------------------------- #
# Auto-adjunto: filtro por estado / pipeline + orden por prioridad           #
# --------------------------------------------------------------------------- #


def test_editoriales_excluye_no_activos():
    biblioteca.crear("Reglas", tipo="editorial", clase="reglas", cuerpo="r")
    biblioteca.crear("Borrador", tipo="editorial", clase="tropicalizacion", cuerpo="t", estado="borrador")
    ids = {d.id for d in biblioteca.editoriales_de_marca("unotv")}
    assert "editorial/reglas" in ids
    assert "editorial/borrador" not in ids  # borrador no inyecta


def test_editoriales_filtra_por_pipeline():
    # Global sin pipelines declarados -> aplica a TODOS (retrocompat).
    biblioteca.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="p")
    # Acotado a copy: NO debe entrar en qa.
    biblioteca.crear("Solo copy", tipo="editorial", clase="reglas", cuerpo="c", pipelines=["copy"])
    ids_copy = {d.id for d in biblioteca.editoriales_de_marca("unotv", pipeline="copy")}
    ids_qa = {d.id for d in biblioteca.editoriales_de_marca("unotv", pipeline="qa")}
    assert "editorial/plataformas" in ids_copy and "editorial/plataformas" in ids_qa
    assert "editorial/solo-copy" in ids_copy
    assert "editorial/solo-copy" not in ids_qa


def test_editoriales_ordena_por_prioridad():
    biblioteca.crear("Reglas A", tipo="editorial", clase="reglas", cuerpo="a", prioridad=10)
    biblioteca.crear("Tropi B", tipo="editorial", clase="tropicalizacion", cuerpo="b", prioridad=-5)
    orden = [d.id for d in biblioteca.editoriales_de_marca("unotv")]
    assert orden.index("editorial/tropi-b") < orden.index("editorial/reglas-a")


def test_editoriales_scoping_por_carpeta():
    # Estructura rrss -> marca -> categoria: la marca se deriva de la CARPETA (sin campo `marcas`).
    biblioteca.crear("Marca", tipo="editorial", carpeta="rrss/unotv", cuerpo="v")
    biblioteca.crear("Reglas", tipo="editorial", carpeta="rrss/claro-sports/legal", cuerpo="r")
    # `global` en cualquier segmento (p. ej. rrss/global) aplica a TODAS las marcas.
    biblioteca.crear("Plataformas", tipo="editorial", carpeta="rrss/global", cuerpo="p")

    ids_unotv = {d.id for d in biblioteca.editoriales_de_marca("unotv")}
    assert "editorial/rrss/unotv/marca" in ids_unotv
    assert "editorial/rrss/global/plataformas" in ids_unotv  # global, para todas
    assert "editorial/rrss/claro-sports/legal/reglas" not in ids_unotv  # otra marca

    ids_claro = {d.id for d in biblioteca.editoriales_de_marca("claro-sports")}
    assert "editorial/rrss/claro-sports/legal/reglas" in ids_claro
    assert "editorial/rrss/global/plataformas" in ids_claro
    assert "editorial/rrss/unotv/marca" not in ids_claro


# --------------------------------------------------------------------------- #
# Resolucion de pipeline + preview                                           #
# --------------------------------------------------------------------------- #


def test_prompt_base_defecto_cuando_nadie_rebindea():
    assert biblioteca.prompt_base_de("copy") == "prompt/copy-desde-nota"
    assert biblioteca.prompt_base_de("qa") == "prompt/qa-editorial"


def test_prompt_base_rebindeo_por_documento():
    # Un prompt activo con rol=copy que declara el pipeline copy GANA al defecto del registro.
    nuevo = biblioteca.crear("Copy v2", tipo="prompt", cuerpo="...", rol="copy", pipelines=["copy"])
    assert biblioteca.prompt_base_de("copy") == nuevo.id
    # Un borrador NO rebindea (estado != activo).
    biblioteca.guardar(nuevo.id, estado="borrador")
    assert biblioteca.prompt_base_de("copy") == "prompt/copy-desde-nota"


def test_previsualizar_pipeline_ensambla_base_y_adjuntos():
    biblioteca.crear("Copy base", tipo="prompt", carpeta="", cuerpo="INSTRUCCION BASE", rol="copy", pipelines=["copy"])
    biblioteca.crear("Reglas", tipo="editorial", clase="reglas", cuerpo="REGLA EDITORIAL")
    prev = biblioteca.previsualizar_pipeline("copy", "unotv", "CONTEXTO DE PRUEBA")
    assert prev["falta_base"] is False
    assert "INSTRUCCION BASE" in prev["prompt_efectivo"]
    assert "REGLA EDITORIAL" in prev["prompt_efectivo"]
    assert "CONTEXTO DE PRUEBA" in prev["prompt_efectivo"]
    assert any(a["id"] == "editorial/reglas" for a in prev["adjuntos"])


def test_previsualizar_pipeline_sin_prompt_base():
    # Sin store ni semilla del prompt de qa -> falta_base True (no revienta).
    prev = biblioteca.previsualizar_pipeline("qa", "unotv")
    assert "falta_base" in prev


# --------------------------------------------------------------------------- #
# Listado con facetas                                                         #
# --------------------------------------------------------------------------- #


def test_listar_filtra_por_estado_y_etiqueta():
    biblioteca.crear("A", tipo="prompt", cuerpo="x", etiquetas=["destacado"])
    biblioteca.crear("B", tipo="prompt", cuerpo="y", estado="archivado")
    activos = biblioteca.listar(estado="activo")
    assert {d.id for d in activos} == {"prompt/a"}
    etiquetados = biblioteca.listar(etiqueta="destacado")
    assert {d.id for d in etiquetados} == {"prompt/a"}


# --------------------------------------------------------------------------- #
# Versionado git (se EJERCITA con git activo; se salta si no hay git)         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def _git_activo(monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    monkeypatch.setenv("KENI_BIBLIOTECA_GIT", "1")


def test_versionado_historial_y_rollback(_git_activo):
    doc = biblioteca.crear("Doc versionado", tipo="prompt", cuerpo="VERSION 1")
    biblioteca.guardar(doc.id, cuerpo="VERSION 2")
    biblioteca.guardar(doc.id, cuerpo="VERSION 3")

    hist = biblioteca.historial(doc.id)
    assert len(hist) >= 3
    assert all(h["sha"] and h["fecha"] and h["autor"] for h in hist)

    # La version mas antigua (ultima de la lista) contiene "VERSION 1".
    sha_inicial = hist[-1]["sha"]
    antiguo = biblioteca.version(doc.id, sha_inicial)
    assert antiguo is not None and "VERSION 1" in antiguo.cuerpo

    # Rollback NO destructivo: el cuerpo vuelve a V1 y crece el historial.
    revertido = biblioteca.restaurar_version(doc.id, sha_inicial)
    assert "VERSION 1" in revertido.cuerpo
    assert biblioteca.obtener(doc.id).cuerpo.strip() == "VERSION 1"
    assert len(biblioteca.historial(doc.id)) >= 4


def test_versionado_apagado_no_da_historial(monkeypatch):
    monkeypatch.setenv("KENI_BIBLIOTECA_GIT", "0")
    doc = biblioteca.crear("Sin git", tipo="prompt", cuerpo="x")
    assert biblioteca.historial(doc.id) == []
