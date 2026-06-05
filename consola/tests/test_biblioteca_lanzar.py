"""Tests de la primitiva de lanzamiento de prompts de la biblioteca (dominio puro).

Aisla `KENI_BIBLIOTECA_DIR` y `KENI_CONSOLA_GENERACIONES` en tmp e INTERCEPTA
`generaciones.encolar_job_claude` (no toca la cola ni `claude`). Verifica la composicion
del prompt (prompt + linea editorial + contexto), el registro de generacion (tipo "prompt")
y la validacion de marca.
"""

from __future__ import annotations

import pytest

from keni_consola import biblioteca, generaciones, marcas
from keni_consola.dominio import biblioteca_lanzar, jobspec

_MARCA = marcas.opciones()[0][0]


@pytest.fixture(autouse=True)
def _entorno_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))  # aisla dir_config() (cwd_generacion)
    monkeypatch.setenv("KENI_BIBLIOTECA_DIR", str(tmp_path / "biblioteca"))
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
    solo = biblioteca_lanzar.componer("Haz X", [], "")
    assert solo == "Haz X"

    ed = biblioteca.crear("Voz", tipo="editorial", clase="voz", marcas=[_MARCA], cuerpo="tono cercano")
    con_todo = biblioteca_lanzar.componer("Haz X", [ed], "una nota")
    assert "Haz X" in con_todo
    assert "LÍNEA EDITORIAL" in con_todo and "tono cercano" in con_todo
    assert "CONTEXTO" in con_todo and "una nota" in con_todo


# --------------------------------------------------------------------------- #
# Lanzar                                                                       #
# --------------------------------------------------------------------------- #


def test_lanzar_prompt_de_biblioteca_compone_y_encola(encolado):
    prompt = biblioteca.crear("Genera copy", tipo="prompt", cuerpo="Convierte la nota en copy.")
    ed = biblioteca.crear("Plataformas", tipo="editorial", clase="plataforma", cuerpo="máx 280 caracteres")

    reg = biblioteca_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, adjuntos_ids=[ed.id], bloque_contexto="Nota: gol en el 90'",
    )

    assert reg["tipo"] == "prompt"
    assert reg["marca"] == _MARCA
    # El prompt final compuesto llego al encolado.
    final = encolado["prompt"]
    assert "Convierte la nota en copy." in final
    assert "máx 280 caracteres" in final
    assert "gol en el 90'" in final
    # El spec usa el post-procesado IDENTIDAD de la biblioteca.
    assert encolado["spec"]["procesar"]["kind"] == jobspec.PROC_PROMPT
    # Y ese procesar no crea artefactos.
    assert encolado["procesar"]("salida cualquiera", None) == {}
    # El registro quedo persistido y recuperable.
    assert generaciones.obtener(reg["id"]) is not None


def test_lanzar_texto_ad_hoc(encolado):
    reg = biblioteca_lanzar.lanzar(texto="Resume esto en 3 puntos", marca=_MARCA)
    assert reg["tipo"] == "prompt"
    assert "Resume esto en 3 puntos" in encolado["prompt"]


def test_lanzar_marca_invalida_lanza(encolado):
    p = biblioteca.crear("P", tipo="prompt", cuerpo="x")
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca_lanzar.lanzar(prompt_id=p.id, marca="marca-inexistente")
    assert encolado == {}  # no se encolo nada


def test_lanzar_sin_prompt_ni_texto_lanza():
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca_lanzar.lanzar(marca=_MARCA)


def test_lanzar_prompt_inexistente_lanza():
    with pytest.raises(biblioteca.BibliotecaError):
        biblioteca_lanzar.lanzar(prompt_id="prompt/no-existe", marca=_MARCA)


def test_lanzar_prompt_piezas_con_redes_crea_spec_copy(encolado):
    """Un prompt salida=piezas + redes lanza con el post-procesado de COPY (no identidad)."""
    prompt = biblioteca.crear(
        "Copy desde nota", tipo="prompt", cuerpo="Convierte la nota en copy por red."
    )
    # `crear` no fija `salida`; lo escribimos como lo haria el editor de la Biblioteca.
    biblioteca.guardar(prompt.id, cuerpo=prompt.cuerpo)
    doc = biblioteca.obtener(prompt.id)
    # Forzamos salida=piezas via el almacen (el frontmatter lo soporta).
    ruta = biblioteca._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    assert biblioteca.obtener(prompt.id).salida == "piezas"

    redes_ids = ["instagram", "x"]
    reg = biblioteca_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, redes_ids=redes_ids,
        bloque_contexto="Nota: gol en el 90'",
    )
    assert reg["tipo"] == "copy"
    spec = encolado["spec"]["procesar"]
    assert spec["kind"] == jobspec.PROC_COPY
    assert spec["redes_ids"] == redes_ids
    assert spec["skill"] == doc.id.rsplit("/", 1)[-1]
    # El prompt compuesto pide el bloque json de piezas por red.
    assert "piezas" in encolado["prompt"]
    # ANTI-EXFILTRACIÓN: el camino COPY (piezas) endurece el run vetando la web. El
    # `endurecer` viaja EN EL SPEC, que es justo lo que el worker lee (`jobspec.endurecer`)
    # y pasa a `_argv_claude`. Así el subproceso `claude -p` no puede sacar el OAuth token
    # por WebFetch/WebSearch aunque el material (la nota) traiga un prompt-injection.
    endurecer = encolado["spec"]["endurecer"]
    assert endurecer is not None
    assert set(endurecer["disallowed_tools"]) == {"WebFetch", "WebSearch"}


def test_lanzar_piezas_titulo_contenido_titula_los_borradores(encolado):
    """`titulo_contenido` (titular real de la URL) va a `titulo_dado` del spec de copy.

    Evita que el borrador se titule con la 1ª línea del bloque (en una URL, el AVISO de
    extracción automática). Sin `titulo_contenido` el `titulo_dado` queda "" (se deriva).
    """
    prompt = biblioteca.crear("Copy desde nota", tipo="prompt", cuerpo="copy por red")
    ruta = biblioteca._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    biblioteca_lanzar.lanzar(
        prompt_id=prompt.id, marca=_MARCA, redes_ids=["x"],
        bloque_contexto="AVISO: extraído automáticamente…\n\nCuerpo de la nota.",
        titulo_contenido="  Ni volcán ni géiser: expertos de la UNAM  ",
    )
    spec = encolado["spec"]["procesar"]
    assert spec["kind"] == jobspec.PROC_COPY
    assert spec["titulo_dado"] == "Ni volcán ni géiser: expertos de la UNAM"


def test_lanzar_prompt_piezas_sin_redes_cae_a_identidad(encolado):
    """Sin redes, un prompt salida=piezas usa el camino IDENTIDAD (no crea borradores)."""
    prompt = biblioteca.crear("Copy", tipo="prompt", cuerpo="haz copy")
    ruta = biblioteca._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )
    reg = biblioteca_lanzar.lanzar(prompt_id=prompt.id, marca=_MARCA)
    assert reg["tipo"] == "prompt"
    assert encolado["spec"]["procesar"]["kind"] == jobspec.PROC_PROMPT
    # El camino IDENTIDAD NO endurece la web: puede enrutar prompts de INVESTIGACIÓN
    # (brief-tendencias / termometro-mundial) que la usan legítimamente.
    assert encolado["spec"]["endurecer"] is None


def test_spec_prompt_round_trip_reconstruye_identidad():
    """El spec PROC_PROMPT sobrevive serializar/deserializar (compat worker)."""
    spec = jobspec.construir(prompt="hola", procesar=jobspec.construir_prompt_lib())
    revivido = jobspec.deserializar(jobspec.serializar(spec))
    assert revivido["procesar"]["kind"] == jobspec.PROC_PROMPT
    procesar = jobspec.reconstruir_procesar(revivido)
    assert procesar("cualquier salida", None) == {}
