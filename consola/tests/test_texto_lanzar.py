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
    solo = texto_lanzar.componer("Haz X", [], "")
    assert solo == "Haz X"

    ed = libtexto.crear("Voz", tipo="editorial", clase="voz", marcas=[_MARCA], cuerpo="tono cercano")
    con_todo = texto_lanzar.componer("Haz X", [ed], "una nota")
    assert "Haz X" in con_todo
    assert "LÍNEA EDITORIAL" in con_todo and "tono cercano" in con_todo
    assert "CONTEXTO" in con_todo and "una nota" in con_todo


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
    # El prompt compuesto pide el bloque json de piezas por red.
    assert "piezas" in encolado["prompt"]
    # POLÍTICA REVISADA: el camino COPY (piezas) es SALIDA ESTRUCTURADA (se parsea a piezas por
    # red; el usuario no ve la salida cruda), así que NO veta la web por-callsite. El `endurecer`
    # del spec queda en None; la única veta es la GLOBAL `Bash Write Edit` (en `_argv_claude`).
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
    # El camino IDENTIDAD NO endurece la web (igual que hoy): puede enrutar prompts de
    # INVESTIGACIÓN (brief-tendencias / termometro-mundial) que la usan legítimamente.
    assert encolado["spec"]["endurecer"] is None


def test_spec_prompt_round_trip_reconstruye_identidad():
    """El spec PROC_PROMPT sobrevive serializar/deserializar (compat worker)."""
    spec = jobspec.construir(prompt="hola", procesar=jobspec.construir_prompt_lib())
    revivido = jobspec.deserializar(jobspec.serializar(spec))
    assert revivido["procesar"]["kind"] == jobspec.PROC_PROMPT
    procesar = jobspec.reconstruir_procesar(revivido)
    assert procesar("cualquier salida", None) == {}
