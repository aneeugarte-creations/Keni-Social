"""Tests del almacen UNICO de la Biblioteca (prompts + linea editorial).

PUROS (sin Postgres): solo aislan `KENI_BIBLIOTECA_DIR` en un tmp. Cubren el CRUD, la
papelera (borrar/restaurar), el filtro por tipo, el auto-adjunto editorial por marca y el
saneo contra path-traversal.
"""

from __future__ import annotations

import pytest

from keni_consola import biblioteca


@pytest.fixture(autouse=True)
def _biblioteca_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_BIBLIOTECA_DIR", str(tmp_path / "biblioteca"))
    return tmp_path


# --------------------------------------------------------------------------- #
# CRUD basico                                                                  #
# --------------------------------------------------------------------------- #


def test_crear_y_obtener_prompt():
    doc = biblioteca.crear("Resumen Ejecutivo", tipo="prompt", carpeta="investigacion", cuerpo="Resume esto.")
    assert doc.id == "prompt/investigacion/resumen-ejecutivo"
    assert doc.tipo == "prompt"
    assert doc.carpeta == "investigacion"
    leido = biblioteca.obtener(doc.id)
    assert leido is not None
    assert leido.titulo == "Resumen Ejecutivo"
    assert leido.cuerpo.strip() == "Resume esto."
    assert leido.creado and leido.creado == leido.actualizado


def test_crear_id_unico_cuando_choca_el_slug():
    a = biblioteca.crear("Nota", tipo="prompt")
    b = biblioteca.crear("Nota", tipo="prompt")
    assert a.id == "prompt/nota"
    assert b.id == "prompt/nota-2"


def test_tipo_invalido_lanza():
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca.crear("X", tipo="otro")


def test_titulo_vacio_lanza():
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca.crear("   ", tipo="prompt")


# --------------------------------------------------------------------------- #
# Listado / filtros                                                            #
# --------------------------------------------------------------------------- #


def test_listar_filtra_por_tipo_y_busqueda():
    biblioteca.crear("Prompt copy", tipo="prompt", cuerpo="genera copy")
    biblioteca.crear("Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="tono cercano")

    prompts = biblioteca.listar(tipo="prompt")
    assert [d.id for d in prompts] == ["prompt/prompt-copy"]

    editoriales = biblioteca.listar(tipo="editorial")
    assert [d.id for d in editoriales] == ["editorial/voz-unotv"]

    todo = biblioteca.listar()
    assert len(todo) == 2

    assert [d.id for d in biblioteca.listar(q="cercano")] == ["editorial/voz-unotv"]
    assert biblioteca.listar(q="inexistente") == []


def test_listar_filtra_por_carpeta_prefijo():
    biblioteca.crear("A", tipo="prompt", carpeta="x/y")
    biblioteca.crear("B", tipo="prompt", carpeta="z")
    assert [d.id for d in biblioteca.listar(tipo="prompt", carpeta="x")] == ["prompt/x/y/a"]


def test_listar_carpetas_incluye_ancestras():
    biblioteca.crear("A", tipo="prompt", carpeta="x/y")
    assert biblioteca.listar_carpetas(tipo="prompt") == ["prompt/x", "prompt/x/y"]


# --------------------------------------------------------------------------- #
# Guardar (incl. renombrado que mueve el fichero)                              #
# --------------------------------------------------------------------------- #


def test_guardar_cuerpo_en_sitio():
    doc = biblioteca.crear("Uno", tipo="prompt", cuerpo="viejo")
    actualizado = biblioteca.guardar(doc.id, cuerpo="nuevo")
    assert actualizado.id == doc.id
    assert biblioteca.obtener(doc.id).cuerpo.strip() == "nuevo"


def test_guardar_renombra_mueve_y_conserva_creado():
    doc = biblioteca.crear("Uno", tipo="prompt", cuerpo="x")
    creado = doc.creado
    movido = biblioteca.guardar(doc.id, titulo="Dos")
    assert movido.id == "prompt/dos"
    assert movido.creado == creado
    assert biblioteca.obtener("prompt/uno") is None
    assert biblioteca.obtener("prompt/dos") is not None


def test_guardar_cambia_carpeta():
    doc = biblioteca.crear("Uno", tipo="prompt", carpeta="a")
    movido = biblioteca.guardar(doc.id, carpeta="b")
    assert movido.id == "prompt/b/uno"
    assert biblioteca.obtener("prompt/a/uno") is None


# --------------------------------------------------------------------------- #
# Papelera: borrar / restaurar / vaciar                                        #
# --------------------------------------------------------------------------- #


def test_borrar_va_a_papelera_y_se_restaura():
    doc = biblioteca.crear("Borrame", tipo="prompt", cuerpo="contenido")
    biblioteca.borrar(doc.id)
    assert biblioteca.obtener(doc.id) is None
    assert biblioteca.listar(tipo="prompt") == []

    papelera = biblioteca.listar_papelera()
    assert len(papelera) == 1
    assert papelera[0]["origen"] == doc.id

    restaurado = biblioteca.restaurar(papelera[0]["id"])
    assert restaurado.id == doc.id
    assert biblioteca.obtener(doc.id).cuerpo.strip() == "contenido"
    assert biblioteca.listar_papelera() == []


def test_restaurar_choca_si_existe_el_original():
    doc = biblioteca.crear("Dup", tipo="prompt")
    biblioteca.borrar(doc.id)
    biblioteca.crear("Dup", tipo="prompt")  # re-crea en la ubicacion original
    pid = biblioteca.listar_papelera()[0]["id"]
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca.restaurar(pid)


def test_vaciar_papelera():
    doc = biblioteca.crear("X", tipo="prompt")
    biblioteca.borrar(doc.id)
    biblioteca.vaciar_papelera()
    assert biblioteca.listar_papelera() == []


# --------------------------------------------------------------------------- #
# Auto-adjunto editorial por marca                                             #
# --------------------------------------------------------------------------- #


def test_editoriales_de_marca_incluye_globales_y_especificos():
    biblioteca.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="limites")  # global
    biblioteca.crear("Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="tono")
    biblioteca.crear("Voz Claro", tipo="editorial", clase="voz", marcas=["claro-sports"], cuerpo="tono")
    biblioteca.crear("Un prompt", tipo="prompt")  # los prompts no se adjuntan

    ids_unotv = {d.id for d in biblioteca.editoriales_de_marca("unotv")}
    assert ids_unotv == {"editorial/plataformas", "editorial/voz-unotv"}

    ids_claro = {d.id for d in biblioteca.editoriales_de_marca("claro-sports")}
    assert ids_claro == {"editorial/plataformas", "editorial/voz-claro"}


def test_clase_invalida_lanza():
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca.crear("X", tipo="editorial", clase="inexistente")


# --------------------------------------------------------------------------- #
# Seguridad: path-traversal                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("malo", ["../etc/passwd", "prompt/../../x", "otro/x", "prompts", "..", "prompt/a/../b"])
def test_obtener_rechaza_ids_invalidos(malo):
    assert biblioteca.obtener(malo) is None


def test_carpeta_con_traversal_lanza():
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca.crear("X", tipo="prompt", carpeta="../fuera")
