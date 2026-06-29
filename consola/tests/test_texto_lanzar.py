"""Tests de la primitiva de lanzamiento de prompts de la texto (dominio puro).

Aisla `KENI_PROMPTS_DIR` y `KENI_CONSOLA_GENERACIONES` en tmp e INTERCEPTA
`generaciones.encolar_job_claude` (no toca la cola ni `claude`). Verifica la composicion
del prompt (prompt + linea editorial + contexto), el registro de generacion (tipo "prompt")
y la validacion de marca.
"""

from __future__ import annotations

import pytest

from keni_consola import libprompts, generaciones, marcas
from keni_consola import config
from keni_consola.dominio import prompts_lanzar, jobspec

_MARCA = marcas.opciones()[0][0]


@pytest.fixture(autouse=True)
def _entorno_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))  # aisla dir_config() (cwd_generacion)
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))
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

    ed = libprompts.crear("Voz", tipo="editorial", clase="voz", marcas=[_MARCA], cuerpo="tono cercano")
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

    ed = libprompts.crear(
        "Voz", tipo="editorial", clase="voz", marcas=[_MARCA], cuerpo="tono cercano"
    )
    final = generar.componer(
        "Haz X", [ed], "la nota variable", redes_ids=["x"],
    )
    i_cuerpo = final.index("Haz X")
    i_editorial = final.index("tono cercano")
    i_redes = final.index("Genera el copy SOLO para estas redes")
    i_contexto = final.index("la nota variable")
    assert i_cuerpo < i_editorial < i_redes < i_contexto
    # El contexto del usuario es el ÚLTIMO bloque del prompt.
    assert i_contexto > max(i_cuerpo, i_editorial, i_redes)


def test_componer_partes_separa_estable_de_dinamico():
    """`componer_partes` reparte: ESTABLE (cuerpo base + editorial + indicaciones) vs DINÁMICO
    (instrucción de redes + CONTEXTO de la fuente). `componer` = unión byte-idéntica de ambas."""
    from keni_consola.dominio import generar

    ed = libprompts.crear(
        "Voz", tipo="editorial", clase="voz", marcas=[_MARCA], cuerpo="tono cercano"
    )
    estable, dinamico = generar.componer_partes(
        "Haz X", [ed], "la nota variable", redes_ids=["x"], indicaciones="lineamiento del día",
    )
    # Estable: contenido CONFIABLE; el CONTEXTO no confiable NO aparece aquí.
    assert "Haz X" in estable and "tono cercano" in estable and "lineamiento del día" in estable
    assert "la nota variable" not in estable and "contenido_usuario" not in estable
    # Dinámico: instrucción de redes + la fuente envuelta en el envelope anti-inyección.
    assert "Genera el copy SOLO para estas redes" in dinamico
    assert "la nota variable" in dinamico and "contenido_usuario" in dinamico
    # `componer` une ambas partes (estable primero); salvo el nonce del envoltorio
    # anti-inyección, que es aleatorio por llamada, la unión es byte a byte.
    import re

    final = generar.componer(
        "Haz X", [ed], "la nota variable", redes_ids=["x"], indicaciones="lineamiento del día",
    )
    sin_nonce = lambda s: re.sub(r"contenido_usuario_[0-9a-f]+", "contenido_usuario_NONCE", s)  # noqa: E731
    assert sin_nonce(final) == sin_nonce(estable + "\n\n" + dinamico)


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

    vacio = libprompts.crear(
        "Esqueleto", tipo="editorial", clase="voz", marcas=[_MARCA],
        cuerpo="# Tono\n\n## Qué evitar\n",
    )
    lleno = libprompts.crear(
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
    prompt = libprompts.crear("Genera copy", tipo="prompt", cuerpo="Convierte la nota en copy.")
    ed = libprompts.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="máx 280 caracteres")

    reg = prompts_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, adjuntos_ids=[ed.id], bloque_contexto="Nota: gol en el 90'",
    )

    assert reg["tipo"] == "prompt"
    assert reg["marca"] == _MARCA
    # El prompt final compuesto llego al encolado.
    final = encolado["prompt"]
    assert "Convierte la nota en copy." in final
    assert "máx 280 caracteres" in final
    assert "gol en el 90'" in final
    # El pin de modelo es SOLO para copy: un prompt de texto NO fija modelo (default de la cuenta).
    assert "modelo" not in (encolado["spec"].get("endurecer") or {})
    # El spec usa el post-procesado IDENTIDAD de la texto.
    assert encolado["spec"]["procesar"]["kind"] == jobspec.PROC_PROMPT
    # Y ese procesar no crea artefactos.
    assert encolado["procesar"]("salida cualquiera", None) == {}
    # El registro quedo persistido y recuperable.
    assert generaciones.obtener(reg["id"]) is not None


def test_lanzar_texto_ad_hoc(encolado):
    reg = prompts_lanzar.lanzar(texto="Resume esto en 3 puntos", marca=_MARCA)
    assert reg["tipo"] == "prompt"
    assert "Resume esto en 3 puntos" in encolado["prompt"]


def test_lanzar_marca_invalida_lanza(encolado):
    p = libprompts.crear("P", tipo="prompt", cuerpo="x")
    with pytest.raises(libprompts.PromptsError):
        prompts_lanzar.lanzar(prompt_id=p.id, marca="marca-inexistente")
    assert encolado == {}  # no se encolo nada


def test_lanzar_sin_prompt_ni_texto_lanza():
    with pytest.raises(libprompts.PromptsError):
        prompts_lanzar.lanzar(marca=_MARCA)


def test_lanzar_prompt_inexistente_lanza():
    with pytest.raises(libprompts.PromptsError):
        prompts_lanzar.lanzar(prompt_id="prompt/no-existe", marca=_MARCA)


def test_lanzar_prompt_piezas_con_redes_crea_spec_copy(encolado):
    """Un prompt salida=piezas + redes lanza con el post-procesado de COPY (no identidad)."""
    prompt = libprompts.crear(
        "Copy desde nota", tipo="prompt", cuerpo="Convierte la nota en copy por red."
    )
    # `crear` no fija `salida`; lo escribimos como lo haria el editor de la Texto.
    libprompts.guardar(prompt.id, cuerpo=prompt.cuerpo)
    doc = libprompts.obtener(prompt.id)
    # Forzamos salida=piezas via el almacen (el frontmatter lo soporta).
    ruta = libprompts._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    assert libprompts.obtener(prompt.id).salida == "piezas"

    redes_ids = ["instagram", "x"]
    reg = prompts_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, redes_ids=redes_ids,
        bloque_contexto="Nota: gol en el 90'",
    )
    assert reg["tipo"] == "copy"
    spec = encolado["spec"]["procesar"]
    assert spec["kind"] == jobspec.PROC_COPY
    assert spec["redes_ids"] == redes_ids
    assert spec["prompt_id"] == doc.id.rsplit("/", 1)[-1]
    # El copy se rutea a sonnet por defecto (`config.copy_modelo()`), no al default opus de la cuenta.
    assert encolado["spec"]["endurecer"]["modelo"] == config.copy_modelo()
    # El prompt compuesto pide el bloque json de piezas por red, con sus límites técnicos.
    assert "piezas" in encolado["prompt"]
    assert "máx 25000 caracteres" in encolado["prompt"]
    # La política de emojis vive en el prompt de copy + editorial, NO en un hardcode del lanzamiento.
    assert "No uses emojis en el copy." not in encolado["prompt"]
    # El camino COPY (piezas) es SALIDA ESTRUCTURADA (se parsea a piezas por red; el usuario no
    # ve la salida cruda), así que NO veta la web por-callsite. El `endurecer` del spec solo rutea
    # el modelo de copy (sonnet); la veta de herramientas es la GLOBAL `Bash Write Edit` (en `_argv_claude`).
    assert "disallowed_tools" not in encolado["spec"]["endurecer"]


def test_lanzar_piezas_titulo_contenido_titula_los_borradores(encolado):
    """`titulo_contenido` (titular real de la URL) va a `titulo_dado` del spec de copy.

    Evita que el borrador se titule con la 1ª línea del bloque (en una URL, el AVISO de
    extracción automática). Sin `titulo_contenido` el `titulo_dado` queda "" (se deriva).
    """
    prompt = libprompts.crear("Copy desde nota", tipo="prompt", cuerpo="copy por red")
    ruta = libprompts._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    prompts_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, redes_ids=["x"],
        bloque_contexto="AVISO: extraído automáticamente…\n\nCuerpo de la nota.",
        titulo_contenido="  Ni volcán ni géiser: expertos de la UNAM  ",
    )
    spec = encolado["spec"]["procesar"]
    assert spec["kind"] == jobspec.PROC_COPY
    assert spec["titulo_dado"] == "Ni volcán ni géiser: expertos de la UNAM"


def _prompt_piezas(titulo: str = "Copy desde nota"):
    """Crea un prompt y lo marca `salida: piezas` (como haría el editor de la Texto)."""
    doc = libprompts.crear(titulo, tipo="prompt", cuerpo="Convierte la nota en copy por red.")
    ruta = libprompts._ruta_de_id(doc.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    return doc


def _inicializar_indicacion(repos, *, fecha: str, marca: str, titulo: str) -> None:
    """Siembra una indicación en el cajón `contexto` (mismo patrón que test_indicaciones_copy)."""
    lote = repos.crear_insumo_lote(fecha=fecha, cajon="contexto", estado="listo")
    repos.crear_insumo_items([
        {"lote_id": lote["id"], "cajon": "contexto", "tipo": "contexto",
         "fecha": fecha, "marca": marca, "titulo": titulo},
    ])


def test_lanzar_piezas_inyecta_indicaciones_vigentes_de_la_marca(entorno, encolado):
    """MODO PIEZAS crea piezas REALES, así que (como el resto del copy, cuyo punto único es
    `componer_copy`) inyecta las indicaciones VIGENTES del equipo. Con una indicación inicializada
    para claro-sports el prompt encolado lleva el bloque OBLIGATORIO; una marca sin
    indicaciones no cambia ni un byte (best-effort)."""
    from keni_consola import repos
    from keni_consola.dominio import indicaciones
    from keni_consola.tiempo import hoy_utc

    _inicializar_indicacion(
        repos, fecha=hoy_utc().isoformat(), marca="claro-sports",
        titulo="Hoy prioridad al Mundial",
    )
    prompt = _prompt_piezas()

    prompts_lanzar.lanzar(
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
    prompts_lanzar.lanzar(
        prompt_id=prompt.id, marca="unotv", redes_ids=["x"],
        bloque_contexto="Nota: gol en el 90'",
    )
    assert indicaciones.ENCABEZADO_INDICACIONES not in encolado["prompt"]


def test_lanzar_prompt_piezas_sin_redes_cae_a_identidad(encolado):
    """Sin redes, un prompt salida=piezas usa el camino IDENTIDAD (no crea borradores)."""
    prompt = libprompts.crear("Copy", tipo="prompt", cuerpo="haz copy")
    ruta = libprompts._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    reg = prompts_lanzar.lanzar(prompt_id=prompt.id, marca=_MARCA)
    assert reg["tipo"] == "prompt"
    assert encolado["spec"]["procesar"]["kind"] == jobspec.PROC_PROMPT
    # El camino IDENTIDAD NO endurece la web: puede enrutar prompts de INVESTIGACIÓN
    # (brief-tendencias) que la usan legítimamente.
    assert encolado["spec"]["endurecer"] is None


def test_lanzar_copy_adjunta_reglas_de_imagen_y_sin_hardcode_de_emojis(encolado):
    """El copy redacta el `copy_in` (texto sobre la placa): adjunta las reglas de imagen
    (best-effort, de la inicial si el store no las tiene) y NO inyecta el hardcode de
    emojis (la política vive en el prompt + editorial adjunta).

    Con el gate `KENI_COPY_SYSTEM_PROMPT` (def ON) la línea editorial (incl. las reglas de
    imagen) viaja como `--system-prompt`; el contrato JSON se queda en el mensaje de usuario."""
    from keni_consola.dominio import generar

    generar.lanzar_copy(
        marca=_MARCA, contexto="Nota: gol en el 90'", redes_ids=["x"], titulo="Copy",
    )
    user = encolado["prompt"]
    sistema = encolado["spec"]["endurecer"]["system_prompt"]
    # La línea editorial (reglas de imagen) va en el system prompt, no en el mensaje de usuario.
    assert "Reglas de imagen" in sistema  # título del adjunto `editorial/reglas/imagen`
    assert "Reglas de imagen" not in user
    assert "No uses emojis en el copy." not in sistema and "No uses emojis en el copy." not in user
    # Contrato JSON (dinámico): se queda en el mensaje de usuario. Modo UNIFICADO: el tope viene
    # del límite más estricto de las redes pedidas (X = 25000).
    assert "más estricto" in user and "25000 caracteres" in user
    assert "UN SOLO copy" in user


def test_lanzar_copy_sin_gate_compone_un_solo_mensaje(entorno, encolado, monkeypatch):
    """Gate OFF (`KENI_COPY_SYSTEM_PROMPT=0`): todo en un único mensaje de usuario, sin
    `--system-prompt` (comportamiento previo)."""
    from keni_consola.dominio import generar

    monkeypatch.setenv("KENI_COPY_SYSTEM_PROMPT", "0")
    generar.lanzar_copy(
        marca=_MARCA, contexto="Nota: gol en el 90'", redes_ids=["x"], titulo="Copy",
    )
    final = encolado["prompt"]
    # Editorial Y contrato JSON conviven en el mismo mensaje; no se fija system_prompt.
    assert "Reglas de imagen" in final and "UN SOLO copy" in final
    assert "system_prompt" not in (encolado["spec"]["endurecer"] or {})


def test_previsualizar_copy_compone_igual_que_lanzar_copy(encolado):
    """Previsualización FIEL: la Prompts muestra el MISMO contenido que recibe `claude -p`,
    aunque al lanzar la línea editorial estable viaje como `--system-prompt`. El prompt de la
    preview = system prompt + mensaje de usuario, salvo el nonce del envoltorio anti-inyección."""
    import re

    from keni_consola.dominio import generar

    generar.lanzar_copy(
        marca=_MARCA, contexto="Nota: gol en el 90'", redes_ids=["x"], titulo="Copy",
    )
    prev = libprompts.previsualizar_pipeline("redactar", _MARCA, "Nota: gol en el 90'", redes_ids=["x"])

    sin_nonce = lambda s: re.sub(r"contenido_usuario_[0-9a-f]+", "contenido_usuario_NONCE", s)  # noqa: E731
    sistema = encolado["spec"]["endurecer"]["system_prompt"]
    efectivo = sistema + "\n\n" + encolado["prompt"]
    assert sin_nonce(prev["prompt_efectivo"]) == sin_nonce(efectivo)
    # Los adjuntos listados incluyen las reglas de imagen.
    assert any(a["id"] == "editorial/reglas/imagen" for a in prev["adjuntos"])


def test_spec_prompt_round_trip_reconstruye_identidad():
    """El spec PROC_PROMPT sobrevive serializar/deserializar (compat worker)."""
    spec = jobspec.construir(prompt="hola", procesar=jobspec.construir_prompt_lib())
    revivido = jobspec.deserializar(jobspec.serializar(spec))
    assert revivido["procesar"]["kind"] == jobspec.PROC_PROMPT
    procesar = jobspec.reconstruir_procesar(revivido)
    assert procesar("cualquier salida", None) == {}
