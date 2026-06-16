"""Tests del almacen UNICO de la Texto (prompts + linea editorial).

PUROS (sin Postgres): solo aislan `KENI_PROMPTS_DIR` en un tmp. Cubren el CRUD, la
papelera (borrar/restaurar), el filtro por tipo, el auto-adjunto editorial por marca y el
reparación contra path-traversal.
"""

from __future__ import annotations

import pytest

from keni_consola import libprompts


@pytest.fixture(autouse=True)
def _texto_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
    return tmp_path


# --------------------------------------------------------------------------- #
# CRUD basico                                                                  #
# --------------------------------------------------------------------------- #


def test_crear_y_obtener_prompt():
    doc = libprompts.crear("Resumen Ejecutivo", tipo="prompt", carpeta="investigacion", cuerpo="Resume esto.")
    assert doc.id == "prompt/investigacion/resumen-ejecutivo"
    assert doc.tipo == "prompt"
    assert doc.carpeta == "investigacion"
    leido = libprompts.obtener(doc.id)
    assert leido is not None
    assert leido.titulo == "Resumen Ejecutivo"
    assert leido.cuerpo.strip() == "Resume esto."
    assert leido.creado and leido.creado == leido.actualizado


def test_descripcion_round_trip_y_separada_del_cuerpo():
    # La descripcion es metadata HUMANA: se persiste en frontmatter y NO forma parte del cuerpo
    # (lo unico que se inyecta en la IA). Round-trip crear -> obtener -> guardar.
    doc = libprompts.crear(
        "Validación", tipo="prompt", cuerpo="Eres el revisor…",
        descripcion="Verificación editorial de la fuente antes de generar copy.",
    )
    leido = libprompts.obtener(doc.id)
    assert leido is not None
    assert leido.descripcion == "Verificación editorial de la fuente antes de generar copy."
    assert "Verificación editorial" not in leido.cuerpo  # separada del contenido inyectable
    assert leido.a_dict()["descripcion"] == leido.descripcion
    # Editar solo la descripcion no toca el cuerpo.
    libprompts.guardar(doc.id, descripcion="Otra cosa.")
    leido2 = libprompts.obtener(doc.id)
    assert leido2.descripcion == "Otra cosa."
    assert leido2.cuerpo.strip() == "Eres el revisor…"


def test_crear_id_unico_cuando_choca_el_slug():
    a = libprompts.crear("Nota", tipo="prompt")
    b = libprompts.crear("Nota", tipo="prompt")
    assert a.id == "prompt/nota"
    assert b.id == "prompt/nota-2"


def test_tipo_invalido_lanza():
    with pytest.raises(libprompts.PromptsError):
        libprompts.crear("X", tipo="otro")


def test_titulo_vacio_lanza():
    with pytest.raises(libprompts.PromptsError):
        libprompts.crear("   ", tipo="prompt")


# --------------------------------------------------------------------------- #
# Listado / filtros                                                            #
# --------------------------------------------------------------------------- #


def test_listar_filtra_por_tipo_y_busqueda():
    libprompts.crear("Prompt copy", tipo="prompt", cuerpo="genera copy")
    libprompts.crear("Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="tono cercano")

    prompts = libprompts.listar(tipo="prompt")
    assert [d.id for d in prompts] == ["prompt/prompt-copy"]

    editoriales = libprompts.listar(tipo="editorial")
    assert [d.id for d in editoriales] == ["editorial/voz-unotv"]

    todo = libprompts.listar()
    assert len(todo) == 2

    assert [d.id for d in libprompts.listar(q="cercano")] == ["editorial/voz-unotv"]
    assert libprompts.listar(q="inexistente") == []


def test_listar_filtra_por_carpeta_prefijo():
    libprompts.crear("A", tipo="prompt", carpeta="x/y")
    libprompts.crear("B", tipo="prompt", carpeta="z")
    assert [d.id for d in libprompts.listar(tipo="prompt", carpeta="x")] == ["prompt/x/y/a"]


def test_listar_carpetas_incluye_ancestras():
    libprompts.crear("A", tipo="prompt", carpeta="x/y")
    assert libprompts.listar_carpetas(tipo="prompt") == ["prompt/x", "prompt/x/y"]


# --------------------------------------------------------------------------- #
# Guardar (incl. renombrado que mueve el fichero)                              #
# --------------------------------------------------------------------------- #


def test_guardar_cuerpo_en_sitio():
    doc = libprompts.crear("Uno", tipo="prompt", cuerpo="viejo")
    actualizado = libprompts.guardar(doc.id, cuerpo="nuevo")
    assert actualizado.id == doc.id
    assert libprompts.obtener(doc.id).cuerpo.strip() == "nuevo"


def test_guardar_renombra_mueve_y_conserva_creado():
    doc = libprompts.crear("Uno", tipo="prompt", cuerpo="x")
    creado = doc.creado
    movido = libprompts.guardar(doc.id, titulo="Dos")
    assert movido.id == "prompt/dos"
    assert movido.creado == creado
    assert libprompts.obtener("prompt/uno") is None
    assert libprompts.obtener("prompt/dos") is not None


def test_guardar_cambia_carpeta():
    doc = libprompts.crear("Uno", tipo="prompt", carpeta="a")
    movido = libprompts.guardar(doc.id, carpeta="b")
    assert movido.id == "prompt/b/uno"
    assert libprompts.obtener("prompt/a/uno") is None


# --------------------------------------------------------------------------- #
# Papelera: borrar / restaurar / vaciar                                        #
# --------------------------------------------------------------------------- #


def test_borrar_va_a_papelera_y_se_restaura():
    doc = libprompts.crear("Borrame", tipo="prompt", cuerpo="contenido")
    libprompts.borrar(doc.id)
    assert libprompts.obtener(doc.id) is None
    assert libprompts.listar(tipo="prompt") == []

    papelera = libprompts.listar_papelera()
    assert len(papelera) == 1
    assert papelera[0]["origen"] == doc.id

    restaurado = libprompts.restaurar(papelera[0]["id"])
    assert restaurado.id == doc.id
    assert libprompts.obtener(doc.id).cuerpo.strip() == "contenido"
    assert libprompts.listar_papelera() == []


def test_restaurar_choca_si_existe_el_original():
    doc = libprompts.crear("Dup", tipo="prompt")
    libprompts.borrar(doc.id)
    libprompts.crear("Dup", tipo="prompt")  # re-crea en la ubicacion original
    pid = libprompts.listar_papelera()[0]["id"]
    with pytest.raises(libprompts.PromptsError):
        libprompts.restaurar(pid)


def test_vaciar_papelera():
    doc = libprompts.crear("X", tipo="prompt")
    libprompts.borrar(doc.id)
    libprompts.vaciar_papelera()
    assert libprompts.listar_papelera() == []


# --------------------------------------------------------------------------- #
# Auto-adjunto editorial por marca                                             #
# --------------------------------------------------------------------------- #


def test_editoriales_de_marca_incluye_globales_y_especificos():
    libprompts.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="limites")  # global
    libprompts.crear("Voz UnoTV", tipo="editorial", clase="voz", marcas=["unotv"], cuerpo="tono")
    libprompts.crear("Voz Claro", tipo="editorial", clase="voz", marcas=["claro-sports"], cuerpo="tono")
    libprompts.crear("Un prompt", tipo="prompt")  # los prompts no se adjuntan

    ids_unotv = {d.id for d in libprompts.editoriales_de_marca("unotv")}
    assert ids_unotv == {"editorial/plataformas", "editorial/voz-unotv"}

    ids_claro = {d.id for d in libprompts.editoriales_de_marca("claro-sports")}
    assert ids_claro == {"editorial/plataformas", "editorial/voz-claro"}


def test_clase_invalida_lanza():
    with pytest.raises(libprompts.PromptsError):
        libprompts.crear("X", tipo="editorial", clase="inexistente")


# --------------------------------------------------------------------------- #
# Seguridad: path-traversal                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("malo", ["../etc/passwd", "prompt/../../x", "otro/x", "prompts", "..", "prompt/a/../b"])
def test_obtener_rechaza_ids_invalidos(malo):
    assert libprompts.obtener(malo) is None


def test_carpeta_con_traversal_lanza():
    with pytest.raises(libprompts.PromptsError):
        libprompts.crear("X", tipo="prompt", carpeta="../fuera")


# --------------------------------------------------------------------------- #
# Siembra (importar_inicial)                                                    #
# --------------------------------------------------------------------------- #


def test_importar_inicial_puebla_y_es_idempotente():
    # La inicial del paquete trae editorial (línea editorial) + prompts base.
    n = libprompts.importar_inicial()
    assert n > 0
    # Hay al menos un prompt y un editorial tras importar.
    assert libprompts.listar(tipo="prompt"), "la inicial debe traer prompts"
    assert libprompts.listar(tipo="editorial"), "la inicial debe traer editorial"
    # Idempotente: una segunda importación no duplica (no pisa lo existente).
    assert libprompts.importar_inicial() == 0


def test_inicial_trae_prompt_verificacion_fuente_editable():
    # La verificación pre-copy de la FUENTE es un prompt EDITABLE de la Prompts cuyo cuerpo efectivo
    # lo trae la inicial del paquete (visible en «Prompts»).
    cuerpo = libprompts.cuerpo_efectivo("prompt/verificar")
    assert cuerpo and "VERIFICACIÓN PREVIA" in cuerpo


def test_importar_inicial_no_pisa_lo_editado():
    docs = libprompts.importar_inicial()
    assert docs > 0
    prompt = libprompts.listar(tipo="prompt")[0]
    libprompts.guardar(prompt.id, cuerpo="EDITADO POR EL EQUIPO")
    libprompts.importar_inicial()  # no debe restaurar el original
    assert libprompts.obtener(prompt.id).cuerpo.strip() == "EDITADO POR EL EQUIPO"


def test_inicial_trae_los_prompts_migrados_del_codigo():
    # Los prompts son inicial EDITABLE con sus variables {{...}} en el cuerpo (las sustituye
    # el módulo que los inyecta).
    casos = {
        "prompt/clasificar-marca": ("{{MARCAS}}", "{{MARCA_FALLBACK}}", "{{NOTICIA}}"),
        "prompt/hashtags": ("{{MARCA}}", "{{RED}}", "{{TEXTO}}"),
        "prompt/asistente/variantes": (),
        "prompt/asistente/resumir": (),
    }
    for doc_id, marcadores in casos.items():
        cuerpo = libprompts.cuerpo_efectivo(doc_id)
        assert cuerpo and cuerpo.strip(), f"inicial vacía o ausente: {doc_id}"
        for m in marcadores:
            assert m in cuerpo, f"{doc_id} sin el marcador {m}"


def test_importar_inicial_materializa_docs_nuevos_en_store_existente():
    # SEED-SYNC: un store YA inicializado (deploy viejo) recibe los seeds NUEVOS en el
    # siguiente `python -m keni_consola.inicializar` (deploy.sh lo corre en cada deploy):
    # `importar_inicial` copia SOLO lo que falta, sin pisar lo editado por el equipo.
    from keni_consola.libprompts._rutas import raiz

    assert libprompts.importar_inicial() > 0
    # Simula el store viejo: aún no tenía uno de los docs nuevos, y otro está editado.
    (raiz() / "prompt" / "clasificar-marca.md").unlink()
    libprompts.guardar("prompt/hashtags", cuerpo="EDITADO POR EL EQUIPO")
    assert libprompts.importar_inicial() == 1  # solo el que faltaba
    cuerpo = libprompts.cuerpo_efectivo("prompt/clasificar-marca")
    assert cuerpo and "{{MARCAS}}" in cuerpo
    assert libprompts.obtener("prompt/hashtags").cuerpo.strip() == "EDITADO POR EL EQUIPO"


def test_migrar_nombres_prompts_renombra_refresca_y_preserva():
    # Simula un store con el ID VIEJO, un patrones (script) y un doc del
    # equipo que NO está en la inicial (termometro). La migración renombra/refresca sin pisar esos.
    from keni_consola.libprompts._rutas import raiz
    (raiz() / "prompt").mkdir(parents=True, exist_ok=True)
    (raiz() / "prompt" / "verificacion-fuente.md").write_text("---\ntitulo: verificación fuente\n---\nVIEJO", encoding="utf-8")
    (raiz() / "prompt" / "termometro-mundial.md").write_text("---\ntitulo: Termometro\n---\ndel equipo", encoding="utf-8")
    (raiz() / "editorial" / "rrss" / "unotv").mkdir(parents=True, exist_ok=True)
    (raiz() / "editorial" / "rrss" / "unotv" / "patrones.md").write_text(
        "---\ntitulo: Patrones SCRIPT\n---\nBANDAS DEL SCRIPT", encoding="utf-8")

    n = libprompts.migrar_nombres_prompts()
    assert n > 0
    # El id viejo desaparece; el nuevo existe con el título nuevo.
    assert libprompts.obtener("prompt/verificacion-fuente") is None
    val = libprompts.obtener("prompt/verificar")
    assert val is not None and val.titulo == "Verificar"
    # patrones (script) y termometro (equipo) NO se pisan.
    assert libprompts.obtener("editorial/rrss/unotv/patrones").cuerpo.strip() == "BANDAS DEL SCRIPT"
    assert libprompts.obtener("prompt/termometro-mundial") is not None
    # Idempotente: segunda pasada no hace nada (sentinela).
    assert libprompts.migrar_nombres_prompts() == 0


def test_inicializar_migra_antes_de_importar_sin_duplicar():
    # REGRESIÓN del bug de duplicados: el paso de DEPLOY (`inicializar`, que corre bajo uvicorn, no
    # `__main__`) DEBE migrar los ids ANTES de importar. Si no, `importar_inicial` crea el id NUEVO
    # junto al VIEJO del store = duplicado.
    from keni_consola import inicializar
    from keni_consola.libprompts._rutas import raiz

    (raiz() / "prompt").mkdir(parents=True, exist_ok=True)
    (raiz() / "prompt" / "verificacion-fuente.md").write_text("---\ntitulo: verificación fuente\n---\nVIEJO", encoding="utf-8")
    inicializar.main()
    ids = {d.id for d in libprompts.listar(tipo="prompt")}
    assert "prompt/verificar" in ids
    assert "prompt/verificacion-fuente" not in ids  # el viejo NO sobrevive (no se duplica)


def test_limpiar_prompts_obsoletos_borra_y_es_idempotente():
    # Prompts retirados (fusionados/borrados) se eliminan del store al desplegar; one-shot.
    from keni_consola.libprompts._rutas import raiz

    (raiz() / "prompt").mkdir(parents=True, exist_ok=True)
    (raiz() / "prompt" / "arte-sistema.md").write_text("---\ntitulo: X\n---\nv", encoding="utf-8")
    n = libprompts.limpiar_prompts_obsoletos()
    assert n >= 1
    assert libprompts.obtener("prompt/arte-sistema") is None
    assert libprompts.limpiar_prompts_obsoletos() == 0  # sentinela: no repite


def test_migrar_descripciones_editorial_corrige_plantillas_y_respeta_ediciones():
    # Las descripciones-plantilla se corrigen en el store; cualquier descripción editada por el
    # equipo NO casa con la plantilla y se respeta. El título de los globales pierde el paréntesis
    # SIN mover el fichero (id estable).
    from keni_consola.libprompts._rutas import raiz

    base = raiz() / "editorial" / "rrss"
    (base / "piso-15").mkdir(parents=True, exist_ok=True)
    (base / "global").mkdir(parents=True, exist_ok=True)
    (base / "piso-15" / "plataformas.md").write_text(
        '---\ntitulo: "Formato por red · Piso 15"\n'
        'descripcion: "Ajustes de formato por red propios de Piso 15, sobre el formato común."\n'
        "tipo: editorial\nclase: plataforma\nmarcas: [piso-15]\n---\nCUERPO DEL EQUIPO",
        encoding="utf-8",
    )
    (base / "piso-15" / "voz.md").write_text(
        '---\ntitulo: "Voz y tono · Piso 15"\n'
        'descripcion: "Nuestra voz, ojo con el sarcasmo."\n'
        "tipo: editorial\nclase: voz\nmarcas: [piso-15]\n---\nvoz",
        encoding="utf-8",
    )
    (base / "global" / "plataformas.md").write_text(
        '---\ntitulo: "Formato por red (común)"\n'
        'descripcion: "Convenciones de formato por red comunes a todas las marcas."\n'
        "tipo: editorial\nclase: plataforma\nmarcas: []\n---\ncomun",
        encoding="utf-8",
    )

    n = libprompts.migrar_descripciones_editorial()
    assert n == 2
    doc = libprompts.obtener("editorial/rrss/piso-15/plataformas")
    assert doc is not None
    assert doc.descripcion == "Excepciones de la marca sobre el formato común."
    assert doc.cuerpo.strip() == "CUERPO DEL EQUIPO"  # el cuerpo no se toca
    editada = libprompts.obtener("editorial/rrss/piso-15/voz")
    assert editada is not None and editada.descripcion == "Nuestra voz, ojo con el sarcasmo."
    # El global cambia de título pero conserva su id/ruta (nada se mueve).
    g = libprompts.obtener("editorial/rrss/global/plataformas")
    assert g is not None and g.titulo == "Formato por red · común"
    assert g.descripcion == "Base común de formato; cada marca añade sus excepciones."
    assert libprompts.migrar_descripciones_editorial() == 0  # sentinela: no repite


def test_migrar_titulos_prompts_renombra_y_respeta_ediciones():
    # Los prompts del sistema con el título VIEJO conocido pasan a una palabra; los editados por el
    # equipo (su título ya no casa) se respetan; el cuerpo no se toca. Idempotente por sentinela.
    from keni_consola.libprompts._rutas import raiz

    base = raiz() / "prompt"
    base.mkdir(parents=True, exist_ok=True)
    (base / "fusionar-verificar.md").write_text(
        '---\ntitulo: "Fusionar · verificar"\ntipo: prompt\n---\nCUERPO COTEJAR',
        encoding="utf-8",
    )
    (base / "critica.md").write_text(
        '---\ntitulo: "Mi título propio"\ntipo: prompt\n---\nCUERPO CRITICA',
        encoding="utf-8",
    )

    n = libprompts.migrar_titulos_prompts()
    assert n == 1  # solo el que casa el título viejo
    renombrado = libprompts.obtener("prompt/fusionar-verificar")
    assert renombrado is not None and renombrado.titulo == "Cotejar"
    assert renombrado.cuerpo.strip() == "CUERPO COTEJAR"  # el cuerpo no se toca
    editado = libprompts.obtener("prompt/critica")
    assert editado is not None and editado.titulo == "Mi título propio"  # respetado
    assert libprompts.migrar_titulos_prompts() == 0  # sentinela: no repite


def test_migrar_descripciones_prompt_acorta_y_respeta_ediciones():
    # Los prompts del sistema con la descripción VIEJA larga conocida pasan al one-liner; los que el
    # equipo ya editó (su descripción no casa) se respetan; el cuerpo no se toca. Idempotente.
    from keni_consola.libprompts._rutas import raiz

    base = raiz() / "prompt" / "envoltorios"
    base.mkdir(parents=True, exist_ok=True)
    (base / "sin-emojis.md").write_text(
        '---\ntitulo: "Limpio"\ndescripcion: "Instrucción aditiva opt-in que se inyecta tras el '
        "prompt base en flujos cuya salida nunca lleva emojis (evergreen/termómetro). El copy NO la "
        'usa: su política de emojis vive en el prompt de copy y la editorial de la marca."\n'
        "tipo: prompt\n---\nNo uses emojis en el copy.",
        encoding="utf-8",
    )
    (base / "redes.md").write_text(
        '---\ntitulo: "Redes"\ndescripcion: "Mi descripción propia"\ntipo: prompt\n---\nCUERPO REDES',
        encoding="utf-8",
    )

    n = libprompts.migrar_descripciones_prompt()
    assert n == 1  # solo el que casa la descripción vieja
    acortado = libprompts.obtener("prompt/envoltorios/sin-emojis")
    assert acortado is not None
    assert acortado.descripcion == "Envoltorio opt-in para flujos sin emojis (evergreen/termómetro)."
    assert acortado.cuerpo.strip() == "No uses emojis en el copy."  # el cuerpo no se toca
    editado = libprompts.obtener("prompt/envoltorios/redes")
    assert editado is not None and editado.descripcion == "Mi descripción propia"  # respetado
    assert libprompts.migrar_descripciones_prompt() == 0  # sentinela: no repite


def test_migrar_alcance_editorial_propaga_pipelines_y_respeta_ediciones():
    # El campo `pipelines` de la inicial se propaga al store SOLO si el doc no acota todavía
    # (pipelines vacío); un doc que el equipo ya acotó se respeta. Idempotente por sentinela.
    from keni_consola.libprompts._rutas import raiz

    base = raiz() / "editorial" / "rrss" / "unotv"
    base.mkdir(parents=True, exist_ok=True)
    # voz sin acotar -> recibe el alcance de la inicial (redactar/idear/priorizar).
    (base / "voz.md").write_text(
        '---\ntitulo: "Voz · UnoTV"\ntipo: editorial\nclase: voz\nmarcas: [unotv]\n---\nvoz',
        encoding="utf-8",
    )
    # marca ya acotada por el equipo -> se respeta (no se pisa).
    (base / "marca.md").write_text(
        '---\ntitulo: "Marca · UnoTV"\ntipo: editorial\nclase: marca\nmarcas: [unotv]\n'
        "pipelines: [redactar]\n---\nmarca",
        encoding="utf-8",
    )

    n = libprompts.migrar_alcance_editorial()
    assert n >= 1  # al menos voz se acota (las globales de la inicial no existen en este store)
    voz = libprompts.obtener("editorial/rrss/unotv/voz")
    assert voz is not None and "idear" in voz.pipelines and "redactar" in voz.pipelines
    marca = libprompts.obtener("editorial/rrss/unotv/marca")
    assert marca is not None and marca.pipelines == ["redactar"]  # respetado
    assert libprompts.migrar_alcance_editorial() == 0  # sentinela: no repite


# --------------------------------------------------------------------------- #
# Renombre del almacén de documentos: …/prompts -> …/texto (idempotente)    #
# --------------------------------------------------------------------------- #


def test_migrar_dir_legacy_renombra_texto_a_prompts(tmp_path, monkeypatch):
    """Los documentos del dir legacy `…/texto` se mueven a `…/prompts` para que
    `libprompts.raiz()` los vea. Sin override por env."""
    from keni_consola import rutas

    monkeypatch.delenv("KENI_PROMPTS_DIR", raising=False)
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    base = rutas.dir_config()
    viejo = base / "texto"
    (viejo / "prompt").mkdir(parents=True)
    (viejo / "prompt" / "x.md").write_text("hola", encoding="utf-8")

    assert libprompts.migrar_dir_legacy() is True
    assert (base / "prompts" / "prompt" / "x.md").read_text(encoding="utf-8") == "hola"
    assert not viejo.exists()
    # Idempotente: ya migrado -> no actúa.
    assert libprompts.migrar_dir_legacy() is False


def test_migrar_dir_legacy_renombra_biblioteca_a_prompts(tmp_path, monkeypatch):
    """Dir aún más antiguo (`…/biblioteca`) también migra a `…/prompts`."""
    from keni_consola import rutas

    monkeypatch.delenv("KENI_PROMPTS_DIR", raising=False)
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    base = rutas.dir_config()
    viejo = base / "biblioteca"
    (viejo / "prompt").mkdir(parents=True)
    (viejo / "prompt" / "x.md").write_text("hola", encoding="utf-8")

    assert libprompts.migrar_dir_legacy() is True
    assert (base / "prompts" / "prompt" / "x.md").read_text(encoding="utf-8") == "hola"
    assert not viejo.exists()
    assert libprompts.migrar_dir_legacy() is False


def test_migrar_dir_legacy_noop_con_override_env(tmp_path, monkeypatch):
    """Con `KENI_PROMPTS_DIR` fijado (tests/instalaciones a medida) NO renombra nada."""
    from keni_consola import rutas

    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "custom"))
    (rutas.dir_config() / "prompts").mkdir(parents=True)
    assert libprompts.migrar_dir_legacy() is False
    assert (rutas.dir_config() / "prompts").is_dir()
