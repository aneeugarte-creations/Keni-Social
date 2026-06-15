"""Tests de la primitiva de lanzamiento de prompts de la texto (dominio puro).

Aisla `KENI_TEXTO_DIR` y `KENI_CONSOLA_GENERACIONES` en tmp e INTERCEPTA
`generaciones.encolar_job_claude` (no toca la cola ni `claude`). Verifica la composicion
del prompt (prompt + linea editorial + contexto), el registro de generacion (tipo "prompt")
y la validacion de marca.
"""

from __future__ import annotations

import pytest

from keni_consola import libtexto, generaciones, marcas
from keni_consola.dominio import texto_lanzar, jobspec

_MARCA = marcas.opciones()[0][0]


@pytest.fixture(autouse=True)
def _entorno_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))  # aisla dir_config() (cwd_generacion)
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    return tmp_path


@pytest.fixture
def encolado(monkeypatch):
    """Intercepta `encolar_job_claude` y captura los kwargs (prompt, spec, ...)."""
    capturado: dict = {}

    def fake(gen_id, *, prompt, cwd, procesar, dir_temporal=None, spec=None):  # noqa: ANN001
        capturado.update(gen_id=gen_id, prompt=prompt, cwd=cwd, procesar=procesar, spec=spec)

    monkeypatch.setattr(generaciones, "encolar_job_claude", fake)
    return capturado


# --------------------------------------------------------------------------- #
# Composicion                                                                  #
# --------------------------------------------------------------------------- #


def test_componer_incluye_solo_secciones_presentes():
    from keni_consola.dominio import generar

    solo = generar.componer("Haz X", [], "")
    assert solo == "Haz X"

    ed = libtexto.crear("Voz", tipo="editorial", clase="voz", marcas=[_MARCA], cuerpo="tono cercano")
    con_todo = generar.componer("Haz X", [ed], "una nota")
    assert "Haz X" in con_todo
    assert "LÍNEA EDITORIAL" in con_todo and "tono cercano" in con_todo
    assert "CONTEXTO" in con_todo and "una nota" in con_todo


def test_componer_orden_estable_primero_contexto_al_final():
    """PROMPT CACHING: lo estable POR MARCA (cuerpo + instrucciones fijas + editorial) va
    ANTES; lo variable POR LANZAMIENTO (la instrucción de redes, que cambia con las redes
    pedidas, y la nota del CONTEXTO) va AL FINAL. Así dos copies de la misma marca comparten
    el prefijo del prompt y el proveedor puede cachearlo (antes `instruccion_redes` iba antes
    del bloque editorial y rompía el prefijo común)."""
    from keni_consola.dominio import generar

    ed = libtexto.crear(
        "Voz", tipo="editorial", clase="voz", marcas=[_MARCA], cuerpo="tono cercano"
    )
    final = generar.componer(
        "Haz X", [ed], "la nota variable", sin_emojis=True, redes_ids=["x"],
    )
    i_cuerpo = final.index("Haz X")
    i_emojis = final.index(generar.INSTRUCCION_SIN_EMOJIS)
    i_editorial = final.index("tono cercano")
    i_redes = final.index("Genera el copy SOLO para estas redes")
    i_contexto = final.index("la nota variable")
    assert i_cuerpo < i_emojis < i_editorial < i_redes < i_contexto
    # El contexto del usuario es el ÚLTIMO bloque del prompt.
    assert i_contexto > max(i_cuerpo, i_emojis, i_editorial, i_redes)


def test_instruccion_redes_ancla_limites_desde_el_codigo():
    """Los límites por red del prompt salen de `keni_shared.limites_plataforma` (fuente
    única), no van hardcodeados: el prompt no puede divergir del código que valida."""
    from keni_shared import limites_plataforma

    from keni_consola.dominio import generar

    instr = generar.instruccion_redes(["x", "facebook"])
    assert f"máx {limites_plataforma.limite_de('x')} caracteres" in instr
    assert "sin tope técnico" in instr  # facebook no tiene tope
    # El contrato de piezas compuestas (hilo/carrusel DENTRO de "texto") es explícito.
    assert "UNA pieza por cada red pedida" in instr
    assert "HILO" in instr and "CARRUSEL" in instr and "---" in instr


def test_cuerpo_sin_texto_detecta_solo_headings():
    from keni_consola.dominio import generar

    assert generar.cuerpo_sin_texto("")
    assert generar.cuerpo_sin_texto("# Título\n\n## Sección\n\n---\n")
    assert not generar.cuerpo_sin_texto("# Título\n\nprosa real")
    # Un hashtag NO es un heading: es contenido editorial.
    assert not generar.cuerpo_sin_texto("#UnoTV #México")


def test_componer_filtra_adjuntos_sin_texto():
    """Un editorial "esqueleto" (solo headings) no se inyecta: no aporta y gasta tokens."""
    from keni_consola.dominio import generar

    vacio = libtexto.crear(
        "Esqueleto", tipo="editorial", clase="voz", marcas=[_MARCA],
        cuerpo="# Tono\n\n## Qué evitar\n",
    )
    lleno = libtexto.crear(
        "Voz real", tipo="editorial", clase="voz", marcas=[_MARCA], cuerpo="tono cercano"
    )
    final = generar.componer("Haz X", [vacio, lleno], "")
    assert "tono cercano" in final
    assert "Esqueleto" not in final

    # Si TODOS los adjuntos están vacíos, no se emite siquiera el bloque editorial.
    solo_vacio = generar.componer("Haz X", [vacio], "")
    assert "LÍNEA EDITORIAL" not in solo_vacio


# --------------------------------------------------------------------------- #
# Lanzar                                                                       #
# --------------------------------------------------------------------------- #


def test_lanzar_prompt_de_texto_compone_y_encola(encolado):
    prompt = libtexto.crear("Genera copy", tipo="prompt", cuerpo="Convierte la nota en copy.")
    ed = libtexto.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="máx 280 caracteres")

    reg = texto_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, adjuntos_ids=[ed.id], bloque_contexto="Nota: gol en el 90'",
    )

    assert reg["tipo"] == "prompt"
    assert reg["marca"] == _MARCA
    # El prompt final compuesto llego al encolado.
    final = encolado["prompt"]
    assert "Convierte la nota en copy." in final
    assert "máx 280 caracteres" in final
    assert "gol en el 90'" in final
    # El spec usa el post-procesado IDENTIDAD de la texto.
    assert encolado["spec"]["procesar"]["kind"] == jobspec.PROC_PROMPT
    # Y ese procesar no crea artefactos.
    assert encolado["procesar"]("salida cualquiera", None) == {}
    # El registro quedo persistido y recuperable.
    assert generaciones.obtener(reg["id"]) is not None


def test_lanzar_texto_ad_hoc(encolado):
    reg = texto_lanzar.lanzar(texto="Resume esto en 3 puntos", marca=_MARCA)
    assert reg["tipo"] == "prompt"
    assert "Resume esto en 3 puntos" in encolado["prompt"]


def test_lanzar_marca_invalida_lanza(encolado):
    p = libtexto.crear("P", tipo="prompt", cuerpo="x")
    with pytest.raises(libtexto.TextoError):
        texto_lanzar.lanzar(prompt_id=p.id, marca="marca-inexistente")
    assert encolado == {}  # no se encolo nada


def test_lanzar_sin_prompt_ni_texto_lanza():
    with pytest.raises(libtexto.TextoError):
        texto_lanzar.lanzar(marca=_MARCA)


def test_lanzar_prompt_inexistente_lanza():
    with pytest.raises(libtexto.TextoError):
        texto_lanzar.lanzar(prompt_id="prompt/no-existe", marca=_MARCA)


def test_lanzar_prompt_piezas_con_redes_crea_spec_copy(encolado):
    """Un prompt salida=piezas + redes lanza con el post-procesado de COPY (no identidad)."""
    prompt = libtexto.crear(
        "Copy desde nota", tipo="prompt", cuerpo="Convierte la nota en copy por red."
    )
    # `crear` no fija `salida`; lo escribimos como lo haria el editor de la Texto.
    libtexto.guardar(prompt.id, cuerpo=prompt.cuerpo)
    doc = libtexto.obtener(prompt.id)
    # Forzamos salida=piezas via el almacen (el frontmatter lo soporta).
    ruta = libtexto._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    assert libtexto.obtener(prompt.id).salida == "piezas"

    redes_ids = ["instagram", "x"]
    reg = texto_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, redes_ids=redes_ids,
        bloque_contexto="Nota: gol en el 90'",
    )
    assert reg["tipo"] == "copy"
    spec = encolado["spec"]["procesar"]
    assert spec["kind"] == jobspec.PROC_COPY
    assert spec["redes_ids"] == redes_ids
    assert spec["prompt_id"] == doc.id.rsplit("/", 1)[-1]
    # El prompt compuesto pide el bloque json de piezas por red, con sus límites técnicos.
    assert "piezas" in encolado["prompt"]
    assert "máx 25000 caracteres" in encolado["prompt"]
    # La política de emojis vive en el prompt/editorial, NO en un hardcode del lanzamiento.
    from keni_consola.dominio import generar

    assert generar.INSTRUCCION_SIN_EMOJIS not in encolado["prompt"]
    # El camino COPY (piezas) es SALIDA ESTRUCTURADA (se parsea a piezas por red; el usuario no
    # ve la salida cruda), así que NO veta la web por-callsite. El `endurecer` del spec queda en
    # None; la única veta es la GLOBAL `Bash Write Edit` (en `_argv_claude`).
    assert encolado["spec"]["endurecer"] is None


def test_lanzar_piezas_titulo_contenido_titula_los_borradores(encolado):
    """`titulo_contenido` (titular real de la URL) va a `titulo_dado` del spec de copy.

    Evita que el borrador se titule con la 1ª línea del bloque (en una URL, el AVISO de
    extracción automática). Sin `titulo_contenido` el `titulo_dado` queda "" (se deriva).
    """
    prompt = libtexto.crear("Copy desde nota", tipo="prompt", cuerpo="copy por red")
    ruta = libtexto._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    texto_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, redes_ids=["x"],
        bloque_contexto="AVISO: extraído automáticamente…\n\nCuerpo de la nota.",
        titulo_contenido="  Ni volcán ni géiser: expertos de la UNAM  ",
    )
    spec = encolado["spec"]["procesar"]
    assert spec["kind"] == jobspec.PROC_COPY
    assert spec["titulo_dado"] == "Ni volcán ni géiser: expertos de la UNAM"


def _prompt_piezas(titulo: str = "Copy desde nota"):
    """Crea un prompt y lo marca `salida: piezas` (como haría el editor de la Texto)."""
    doc = libtexto.crear(titulo, tipo="prompt", cuerpo="Convierte la nota en copy por red.")
    ruta = libtexto._ruta_de_id(doc.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    return doc


def _sembrar_indicacion(repos, *, fecha: str, marca: str, titulo: str) -> None:
    """Siembra una indicación en el cajón `contexto` (mismo patrón que test_indicaciones_copy)."""
    lote = repos.crear_insumo_lote(fecha=fecha, cajon="contexto", estado="listo")
    repos.crear_insumo_items([
        {"lote_id": lote["id"], "cajon": "contexto", "tipo": "contexto",
         "fecha": fecha, "marca": marca, "titulo": titulo},
    ])


def test_lanzar_piezas_inyecta_indicaciones_vigentes_de_la_marca(entorno, encolado):
    """MODO PIEZAS crea piezas REALES, así que (como el resto del copy, cuyo punto único es
    `componer_copy`) inyecta las indicaciones VIGENTES del equipo. Con una indicación sembrada
    para claro-sports el prompt encolado lleva el bloque OBLIGATORIO; una marca sin
    indicaciones no cambia ni un byte (best-effort)."""
    from keni_consola import repos
    from keni_consola.dominio import indicaciones
    from keni_consola.tiempo import hoy_utc

    _sembrar_indicacion(
        repos, fecha=hoy_utc().isoformat(), marca="claro-sports",
        titulo="Hoy prioridad al Mundial",
    )
    prompt = _prompt_piezas()

    texto_lanzar.lanzar(
        prompt_id=prompt.id, marca="claro-sports", redes_ids=["x"],
        bloque_contexto="Nota: gol en el 90'",
    )
    final = encolado["prompt"]
    assert indicaciones.ENCABEZADO_INDICACIONES in final
    assert "Hoy prioridad al Mundial" in final
    # Las indicaciones van FUERA del envoltorio anti-inyección y ANTES del CONTEXTO no confiable.
    i_indicaciones = final.index(indicaciones.ENCABEZADO_INDICACIONES)
    i_contexto = final.index("CONTEXTO:")
    assert i_indicaciones < i_contexto
    assert "contenido_usuario" not in final[:i_indicaciones]

    # Otra marca SIN indicaciones vigentes: el prompt de MODO PIEZAS no cambia ni un byte.
    encolado.clear()
    texto_lanzar.lanzar(
        prompt_id=prompt.id, marca="unotv", redes_ids=["x"],
        bloque_contexto="Nota: gol en el 90'",
    )
    assert indicaciones.ENCABEZADO_INDICACIONES not in encolado["prompt"]


def test_lanzar_prompt_piezas_sin_redes_cae_a_identidad(encolado):
    """Sin redes, un prompt salida=piezas usa el camino IDENTIDAD (no crea borradores)."""
    prompt = libtexto.crear("Copy", tipo="prompt", cuerpo="haz copy")
    ruta = libtexto._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    reg = texto_lanzar.lanzar(prompt_id=prompt.id, marca=_MARCA)
    assert reg["tipo"] == "prompt"
    assert encolado["spec"]["procesar"]["kind"] == jobspec.PROC_PROMPT
    # El camino IDENTIDAD NO endurece la web: puede enrutar prompts de INVESTIGACIÓN
    # (brief-tendencias) que la usan legítimamente.
    assert encolado["spec"]["endurecer"] is None


def test_lanzar_copy_adjunta_reglas_de_imagen_y_sin_hardcode_de_emojis(encolado):
    """El copy redacta el `copy_in` (texto sobre la placa): adjunta las reglas de imagen
    (best-effort, de la semilla si el store no las tiene) y NO inyecta el hardcode de
    emojis (la política vive en el prompt + editorial adjunta)."""
    from keni_consola.dominio import generar

    generar.lanzar_copy(
        marca=_MARCA, contexto="Nota: gol en el 90'", redes_ids=["x"], titulo="Copy",
    )
    final = encolado["prompt"]
    assert "Reglas de imagen" in final  # título del adjunto `editorial/reglas/imagen`
    assert generar.INSTRUCCION_SIN_EMOJIS not in final
    # Modo UNIFICADO: el tope viene del límite más estricto de las redes pedidas (X = 25000).
    assert "más estricto" in final and "25000 caracteres" in final
    assert "UN SOLO copy" in final


def test_previsualizar_copy_compone_igual_que_lanzar_copy(encolado):
    """Previsualización FIEL: la Biblioteca muestra el MISMO prompt que recibe `claude -p`
    (misma composición: adjuntos de copy + instrucción de redes), salvo el nonce del
    envoltorio anti-inyección del contexto."""
    import re

    from keni_consola.dominio import generar

    generar.lanzar_copy(
        marca=_MARCA, contexto="Nota: gol en el 90'", redes_ids=["x"], titulo="Copy",
    )
    prev = libtexto.previsualizar_pipeline("copy", _MARCA, "Nota: gol en el 90'", redes_ids=["x"])

    sin_nonce = lambda s: re.sub(r"contenido_usuario_[0-9a-f]+", "contenido_usuario_NONCE", s)  # noqa: E731
    assert sin_nonce(prev["prompt_efectivo"]) == sin_nonce(encolado["prompt"])
    # Los adjuntos listados incluyen las reglas de imagen.
    assert any(a["id"] == "editorial/reglas/imagen" for a in prev["adjuntos"])


def test_spec_prompt_round_trip_reconstruye_identidad():
    """El spec PROC_PROMPT sobrevive serializar/deserializar (compat worker)."""
    spec = jobspec.construir(prompt="hola", procesar=jobspec.construir_prompt_lib())
    revivido = jobspec.deserializar(jobspec.serializar(spec))
    assert revivido["procesar"]["kind"] == jobspec.PROC_PROMPT
    procesar = jobspec.reconstruir_procesar(revivido)
    assert procesar("cualquier salida", None) == {}
