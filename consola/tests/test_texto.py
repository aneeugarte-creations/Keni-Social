"""Tests del almacen UNICO de la Texto (prompts + linea editorial).

PUROS (sin Postgres): solo aislan `KENI_TEXTO_DIR` en un tmp. Cubren el CRUD, la
papelera (borrar/restaurar), el filtro por tipo, el auto-adjunto editorial por marca y el
saneo contra path-traversal.
"""

from __future__ import annotations

import pytest

from keni_consola import libtexto


@pytest.fixture(autouse=True)
def _texto_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    return tmp_path


# --------------------------------------------------------------------------- #
# CRUD basico                                                                  #
# --------------------------------------------------------------------------- #


def test_crear_y_obtener_prompt():
    doc = libtexto.crear("Resumen Ejecutivo", tipo="prompt", carpeta="investigacion", cuerpo="Resume esto.")
    assert doc.id == "prompt/investigacion/resumen-ejecutivo"
    assert doc.tipo == "prompt"
    assert doc.carpeta == "investigacion"
    leido = libtexto.obtener(doc.id)
    assert leido is not None
    assert leido.titulo == "Resumen Ejecutivo"
    assert leido.cuerpo.strip() == "Resume esto."
    assert leido.creado and leido.creado == leido.actualizado


def test_crear_id_unico_cuando_choca_el_slug():
    a = libtexto.crear("Nota", tipo="prompt")
    b = libtexto.crear("Nota", tipo="prompt")
    assert a.id == "prompt/nota"
    assert b.id == "prompt/nota-2"


def test_tipo_invalido_lanza():
    with pytest.raises(libtexto.TextoError):
        libtexto.crear("X", tipo="otro")


def test_titulo_vacio_lanza():
    with pytest.raises(libtexto.TextoError):
        libtexto.crear("   ", tipo="prompt")


# --------------------------------------------------------------------------- #
# Listado / filtros                                                            #
# --------------------------------------------------------------------------- #


def test_listar_filtra_por_tipo_y_busqueda():
    libtexto.crear("Prompt copy", tipo="prompt", cuerpo="genera copy")
    libtexto.crear("Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="tono cercano")

    prompts = libtexto.listar(tipo="prompt")
    assert [d.id for d in prompts] == ["prompt/prompt-copy"]

    editoriales = libtexto.listar(tipo="editorial")
    assert [d.id for d in editoriales] == ["editorial/voz-unotv"]

    todo = libtexto.listar()
    assert len(todo) == 2

    assert [d.id for d in libtexto.listar(q="cercano")] == ["editorial/voz-unotv"]
    assert libtexto.listar(q="inexistente") == []


def test_listar_filtra_por_carpeta_prefijo():
    libtexto.crear("A", tipo="prompt", carpeta="x/y")
    libtexto.crear("B", tipo="prompt", carpeta="z")
    assert [d.id for d in libtexto.listar(tipo="prompt", carpeta="x")] == ["prompt/x/y/a"]


def test_listar_carpetas_incluye_ancestras():
    libtexto.crear("A", tipo="prompt", carpeta="x/y")
    assert libtexto.listar_carpetas(tipo="prompt") == ["prompt/x", "prompt/x/y"]


# --------------------------------------------------------------------------- #
# Guardar (incl. renombrado que mueve el fichero)                              #
# --------------------------------------------------------------------------- #


def test_guardar_cuerpo_en_sitio():
    doc = libtexto.crear("Uno", tipo="prompt", cuerpo="viejo")
    actualizado = libtexto.guardar(doc.id, cuerpo="nuevo")
    assert actualizado.id == doc.id
    assert libtexto.obtener(doc.id).cuerpo.strip() == "nuevo"


def test_guardar_renombra_mueve_y_conserva_creado():
    doc = libtexto.crear("Uno", tipo="prompt", cuerpo="x")
    creado = doc.creado
    movido = libtexto.guardar(doc.id, titulo="Dos")
    assert movido.id == "prompt/dos"
    assert movido.creado == creado
    assert libtexto.obtener("prompt/uno") is None
    assert libtexto.obtener("prompt/dos") is not None


def test_guardar_cambia_carpeta():
    doc = libtexto.crear("Uno", tipo="prompt", carpeta="a")
    movido = libtexto.guardar(doc.id, carpeta="b")
    assert movido.id == "prompt/b/uno"
    assert libtexto.obtener("prompt/a/uno") is None


# --------------------------------------------------------------------------- #
# Papelera: borrar / restaurar / vaciar                                        #
# --------------------------------------------------------------------------- #


def test_borrar_va_a_papelera_y_se_restaura():
    doc = libtexto.crear("Borrame", tipo="prompt", cuerpo="contenido")
    libtexto.borrar(doc.id)
    assert libtexto.obtener(doc.id) is None
    assert libtexto.listar(tipo="prompt") == []

    papelera = libtexto.listar_papelera()
    assert len(papelera) == 1
    assert papelera[0]["origen"] == doc.id

    restaurado = libtexto.restaurar(papelera[0]["id"])
    assert restaurado.id == doc.id
    assert libtexto.obtener(doc.id).cuerpo.strip() == "contenido"
    assert libtexto.listar_papelera() == []


def test_restaurar_choca_si_existe_el_original():
    doc = libtexto.crear("Dup", tipo="prompt")
    libtexto.borrar(doc.id)
    libtexto.crear("Dup", tipo="prompt")  # re-crea en la ubicacion original
    pid = libtexto.listar_papelera()[0]["id"]
    with pytest.raises(libtexto.TextoError):
        libtexto.restaurar(pid)


def test_vaciar_papelera():
    doc = libtexto.crear("X", tipo="prompt")
    libtexto.borrar(doc.id)
    libtexto.vaciar_papelera()
    assert libtexto.listar_papelera() == []


# --------------------------------------------------------------------------- #
# Auto-adjunto editorial por marca                                             #
# --------------------------------------------------------------------------- #


def test_editoriales_de_marca_incluye_globales_y_especificos():
    libtexto.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="limites")  # global
    libtexto.crear("Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="tono")
    libtexto.crear("Voz Claro", tipo="editorial", clase="voz", marcas=["claro-sports"], cuerpo="tono")
    libtexto.crear("Un prompt", tipo="prompt")  # los prompts no se adjuntan

    ids_unotv = {d.id for d in libtexto.editoriales_de_marca("unotv")}
    assert ids_unotv == {"editorial/plataformas", "editorial/voz-unotv"}

    ids_claro = {d.id for d in libtexto.editoriales_de_marca("claro-sports")}
    assert ids_claro == {"editorial/plataformas", "editorial/voz-claro"}


def test_clase_invalida_lanza():
    with pytest.raises(libtexto.TextoError):
        libtexto.crear("X", tipo="editorial", clase="inexistente")


# --------------------------------------------------------------------------- #
# Seguridad: path-traversal                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("malo", ["../etc/passwd", "prompt/../../x", "otro/x", "prompts", "..", "prompt/a/../b"])
def test_obtener_rechaza_ids_invalidos(malo):
    assert libtexto.obtener(malo) is None


def test_carpeta_con_traversal_lanza():
    with pytest.raises(libtexto.TextoError):
        libtexto.crear("X", tipo="prompt", carpeta="../fuera")


# --------------------------------------------------------------------------- #
# Siembra (importar_semilla)                                                    #
# --------------------------------------------------------------------------- #


def test_importar_semilla_puebla_y_es_idempotente():
    # La semilla del paquete trae editorial (línea editorial) + prompts base.
    n = libtexto.importar_semilla()
    assert n > 0
    # Hay al menos un prompt y un editorial tras importar.
    assert libtexto.listar(tipo="prompt"), "la semilla debe traer prompts"
    assert libtexto.listar(tipo="editorial"), "la semilla debe traer editorial"
    # Idempotente: una segunda importación no duplica (no pisa lo existente).
    assert libtexto.importar_semilla() == 0


def test_importar_semilla_no_pisa_lo_editado():
    docs = libtexto.importar_semilla()
    assert docs > 0
    prompt = libtexto.listar(tipo="prompt")[0]
    libtexto.guardar(prompt.id, cuerpo="EDITADO POR EL EQUIPO")
    libtexto.importar_semilla()  # no debe restaurar el original
    assert libtexto.obtener(prompt.id).cuerpo.strip() == "EDITADO POR EL EQUIPO"
