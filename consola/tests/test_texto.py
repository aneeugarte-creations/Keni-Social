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


def test_descripcion_round_trip_y_separada_del_cuerpo():
    # La descripcion es metadata HUMANA: se persiste en frontmatter y NO forma parte del cuerpo
    # (lo unico que se inyecta en la IA). Round-trip crear -> obtener -> guardar.
    doc = libtexto.crear(
        "Validación", tipo="prompt", cuerpo="Eres el revisor…",
        descripcion="Criba editorial de la fuente antes de generar copy.",
    )
    leido = libtexto.obtener(doc.id)
    assert leido is not None
    assert leido.descripcion == "Criba editorial de la fuente antes de generar copy."
    assert "Criba editorial" not in leido.cuerpo  # separada del contenido inyectable
    assert leido.a_dict()["descripcion"] == leido.descripcion
    # Editar solo la descripcion no toca el cuerpo.
    libtexto.guardar(doc.id, descripcion="Otra cosa.")
    leido2 = libtexto.obtener(doc.id)
    assert leido2.descripcion == "Otra cosa."
    assert leido2.cuerpo.strip() == "Eres el revisor…"


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


def test_semilla_trae_prompt_qa_fuente_editable():
    # La criba pre-copy de la FUENTE se migró de `_DEFAULT_QA_CRITERIOS` a un prompt EDITABLE de
    # la Biblioteca: su cuerpo efectivo lo trae la semilla del paquete (visible en «Prompts»).
    cuerpo = libtexto.cuerpo_efectivo("prompt/validacion")
    assert cuerpo and "CRIBA PREVIA" in cuerpo


def test_importar_semilla_no_pisa_lo_editado():
    docs = libtexto.importar_semilla()
    assert docs > 0
    prompt = libtexto.listar(tipo="prompt")[0]
    libtexto.guardar(prompt.id, cuerpo="EDITADO POR EL EQUIPO")
    libtexto.importar_semilla()  # no debe restaurar el original
    assert libtexto.obtener(prompt.id).cuerpo.strip() == "EDITADO POR EL EQUIPO"


def test_migrar_nombres_biblioteca_renombra_refresca_y_preserva():
    # Simula un store con el ID VIEJO (de antes del rediseño), un patrones (script) y un doc del
    # equipo que NO está en la semilla (termometro). La migración renombra/refresca sin pisar esos.
    from keni_consola.libtexto._rutas import raiz
    (raiz() / "prompt").mkdir(parents=True, exist_ok=True)
    (raiz() / "prompt" / "qa-fuente.md").write_text("---\ntitulo: QA fuente\n---\nVIEJO", encoding="utf-8")
    (raiz() / "prompt" / "termometro-mundial.md").write_text("---\ntitulo: Termometro\n---\ndel equipo", encoding="utf-8")
    (raiz() / "editorial" / "rrss" / "unotv").mkdir(parents=True, exist_ok=True)
    (raiz() / "editorial" / "rrss" / "unotv" / "patrones.md").write_text(
        "---\ntitulo: Patrones SCRIPT\n---\nBANDAS DEL SCRIPT", encoding="utf-8")

    n = libtexto.migrar_nombres_biblioteca()
    assert n > 0
    # El id viejo desaparece; el nuevo existe con el título nuevo.
    assert libtexto.obtener("prompt/qa-fuente") is None
    val = libtexto.obtener("prompt/validacion")
    assert val is not None and val.titulo == "Validación"
    # patrones (script) y termometro (equipo) NO se pisan.
    assert libtexto.obtener("editorial/rrss/unotv/patrones").cuerpo.strip() == "BANDAS DEL SCRIPT"
    assert libtexto.obtener("prompt/termometro-mundial") is not None
    # Idempotente: segunda pasada no hace nada (sentinela).
    assert libtexto.migrar_nombres_biblioteca() == 0


def test_sembrar_migra_antes_de_importar_sin_duplicar():
    # REGRESIÓN del bug de duplicados: el paso de DEPLOY (`sembrar`, que corre bajo uvicorn, no
    # `__main__`) DEBE migrar los ids ANTES de importar. Si no, `importar_semilla` crea el id NUEVO
    # junto al VIEJO del store = duplicado.
    from keni_consola import sembrar
    from keni_consola.libtexto._rutas import raiz

    (raiz() / "prompt").mkdir(parents=True, exist_ok=True)
    (raiz() / "prompt" / "qa-fuente.md").write_text("---\ntitulo: QA fuente\n---\nVIEJO", encoding="utf-8")
    sembrar.main()
    ids = {d.id for d in libtexto.listar(tipo="prompt")}
    assert "prompt/validacion" in ids
    assert "prompt/qa-fuente" not in ids  # el viejo NO sobrevive (no se duplica)


# --------------------------------------------------------------------------- #
# Renombre del almacén de documentos: …/biblioteca -> …/texto (idempotente)    #
# --------------------------------------------------------------------------- #


def test_migrar_dir_legacy_renombra_biblioteca_a_texto(tmp_path, monkeypatch):
    """Una instalación previa guarda los documentos bajo `…/biblioteca`; la migración los
    mueve a `…/texto` para que `libtexto.raiz()` (renombrado) los vea. Sin override por env."""
    from keni_consola import rutas

    monkeypatch.delenv("KENI_TEXTO_DIR", raising=False)
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    base = rutas.dir_config()
    viejo = base / "biblioteca"
    (viejo / "prompt").mkdir(parents=True)
    (viejo / "prompt" / "x.md").write_text("hola", encoding="utf-8")

    assert libtexto.migrar_dir_legacy() is True
    assert (base / "texto" / "prompt" / "x.md").read_text(encoding="utf-8") == "hola"
    assert not viejo.exists()
    # Idempotente: ya migrado -> no actúa.
    assert libtexto.migrar_dir_legacy() is False


def test_migrar_dir_legacy_noop_con_override_env(tmp_path, monkeypatch):
    """Con `KENI_TEXTO_DIR` fijado (tests/instalaciones a medida) NO renombra nada."""
    from keni_consola import rutas

    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "custom"))
    (rutas.dir_config() / "biblioteca").mkdir(parents=True)
    assert libtexto.migrar_dir_legacy() is False
    assert (rutas.dir_config() / "biblioteca").is_dir()
