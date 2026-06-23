"""Tests del orquestador PURO de auto-desarrollo + los kinds/carril dev de `jobspec`.

OFFLINE: lógica pura, sin BD ni subprocess.
"""

from __future__ import annotations

from keni_consola.dominio import desarrollo, jobspec

# --------------------------------------------------------------------------- #
# Pipeline de fases (desarrollo)                                              #
# --------------------------------------------------------------------------- #


def test_pipeline_por_complejidad():
    assert desarrollo.pipeline_de("simple") == ("build", "review")
    assert desarrollo.pipeline_de("standard") == ("analyze", "plan", "build", "review")
    assert desarrollo.pipeline_de("complex") == ("analyze", "plan", "build", "review")
    # Complejidad ilegible/vacía cae al defecto (standard).
    assert desarrollo.pipeline_de("") == desarrollo.pipeline_de("standard")


def test_primera_y_siguiente_fase():
    assert desarrollo.primera_fase("simple") == "build"
    assert desarrollo.primera_fase("standard") == "analyze"
    assert desarrollo.siguiente_fase("standard", "analyze") == "plan"
    assert desarrollo.siguiente_fase("standard", "build") == "review"
    # Última fase del pipeline -> None.
    assert desarrollo.siguiente_fase("standard", "review") is None
    assert desarrollo.siguiente_fase("simple", "review") is None
    # Fase ajena al pipeline -> None.
    assert desarrollo.siguiente_fase("simple", "analyze") is None


def test_checkpoints_por_complejidad():
    # complex pausa tras plan y tras review; standard/simple solo tras review.
    assert desarrollo.es_checkpoint("complex", "plan") is True
    assert desarrollo.es_checkpoint("complex", "review") is True
    assert desarrollo.es_checkpoint("standard", "plan") is False
    assert desarrollo.es_checkpoint("standard", "review") is True
    assert desarrollo.es_checkpoint("simple", "review") is True


def test_estado_tras_fase():
    # Tras un checkpoint -> revision; en otro caso -> building (sigue el pipeline).
    assert desarrollo.estado_tras_fase("standard", "analyze") == "building"
    assert desarrollo.estado_tras_fase("standard", "review") == "revision"
    assert desarrollo.estado_tras_fase("complex", "plan") == "revision"


def test_modelo_por_fase_nolan_v2():
    assert desarrollo.modelo_de("analyze") == "sonnet"
    assert desarrollo.modelo_de("plan") == "sonnet"
    assert desarrollo.modelo_de("build") == "opus"
    assert desarrollo.modelo_de("review") == "sonnet"
    assert desarrollo.modelo_de("desconocida") == desarrollo.MODELO_DEFECTO


def test_requiere_discovery():
    assert desarrollo.requiere_discovery("simple") is False
    assert desarrollo.requiere_discovery("standard") is True
    assert desarrollo.requiere_discovery("") is True


def test_parsear_discovery_extrae_complejidad():
    salida = "# SPEC\nHacer X.\n\ncomplejidad: complex\n"
    datos = desarrollo.parsear_discovery(salida)
    assert datos["complejidad"] == "complex"
    assert "Hacer X." in datos["spec"]
    # Sin marcador legible -> defecto standard.
    assert desarrollo.parsear_discovery("solo texto")["complejidad"] == "standard"


def test_parsear_fase():
    assert desarrollo.parsear_fase("mi plan", "plan") == {"plan": "mi plan"}
    assert desarrollo.parsear_fase("hecho", "build") == {"diff_resumen": "hecho"}
    assert desarrollo.parsear_fase("revisado", "review") == {"diff_resumen": "revisado"}
    assert desarrollo.parsear_fase("x", "analyze") == {}


def test_componer_prompt_envuelve_datos():
    sug = {"titulo": "T", "detalle": "D", "spec": "S", "plan": "P", "categoria": "bug"}
    prompt = desarrollo.componer_prompt("BASE", sug, "build")
    assert prompt.startswith("BASE")
    assert "Fase actual: build" in prompt
    for dato in ("T", "D", "S", "P", "bug"):
        assert dato in prompt


def test_componer_prompt_inyecta_nota_efimera():
    # Sin nota: no aparece bloque ni aviso. Con `nota`: bloque propio + aviso, sin tocar el detalle.
    sug = {"titulo": "T", "detalle": "D", "spec": "S", "plan": "P", "categoria": "bug"}
    assert "Nota del usuario" not in desarrollo.componer_prompt("BASE", sug, "build")

    prompt = desarrollo.componer_prompt("BASE", sug, "build", nota="  ojo con X  ")
    assert "Nota del usuario para esta etapa" in prompt
    assert "ojo con X" in prompt
    assert "El humano escribió" in prompt
    # La nota es efímera: no se mete en el dict de la sugerencia.
    assert sug["detalle"] == "D"


def test_componer_prompt_nota_vacia_no_anade_bloque():
    sug = {"titulo": "T", "detalle": "D", "spec": "S", "plan": "P", "categoria": "bug"}
    assert "Nota del usuario" not in desarrollo.componer_prompt("BASE", sug, "build", nota="   ")


# --------------------------------------------------------------------------- #
# Kinds y carril de desarrollo (jobspec)                                      #
# --------------------------------------------------------------------------- #


def test_carril_por_defecto_inferencia():
    spec = jobspec.construir(prompt="p", procesar=jobspec.construir_prompt_lib())
    assert jobspec.carril(spec) == jobspec.CARRIL_INFERENCIA


def test_carril_proceso_derivado_del_kind_raiz():
    spec = jobspec.construir_proceso(jobspec.PROC_RENDER_VIDEO, {"x": 1})
    assert jobspec.carril(spec) == jobspec.CARRIL_PROCESO


def test_carril_dev_explicito():
    spec = jobspec.construir(
        prompt="p", procesar=jobspec.construir_dev_discovery(sugerencia_id="s1"),
        carril=jobspec.CARRIL_DEV,
    )
    assert spec["carril"] == jobspec.CARRIL_DEV
    assert jobspec.carril(spec) == jobspec.CARRIL_DEV


def test_carril_spec_invalido_cae_a_inferencia():
    assert jobspec.carril({}) == jobspec.CARRIL_INFERENCIA
    assert jobspec.carril(None) == jobspec.CARRIL_INFERENCIA  # type: ignore[arg-type]


def test_builders_dev_shape():
    d = jobspec.construir_dev_discovery(sugerencia_id="abc")
    assert d == {"kind": jobspec.PROC_DEV_DISCOVERY, "sugerencia_id": "abc"}
    f = jobspec.construir_dev_fase(sugerencia_id="abc", fase="build", modelo="opus")
    assert f == {
        "kind": jobspec.PROC_DEV_FASE, "sugerencia_id": "abc", "fase": "build", "modelo": "opus",
    }
