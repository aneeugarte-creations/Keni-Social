"""Tests del endpoint `/api/pipelines` (vista estilo GitLab del pipeline de contenido).

Cada `contenido` con `origen='pipeline'` es una RUN; sus etapas (CI/CD/QA/Aprobación) se
DERIVAN del estado real de la pieza y sus publicaciones por plataforma. Aquí montamos ese
estado a mano (sin daemon ni `claude`) y comprobamos la derivación + el detalle + la
exclusión de lo que NO es del pipeline. Usa la fixture `cliente` (entorno aislado + Postgres).
"""

from __future__ import annotations

import pytest

from keni_consola import config, generaciones, repos
from keni_consola.api.pipelines import _estado_global
from keni_consola.pipeline_contenido import ETAPA_CD, ORIGEN_PIPELINE, registrar_etapa


@pytest.fixture(autouse=True)
def _etapas_activas(monkeypatch):
    """Activa los 3 maestros togglables (Noticias/QA/Copy) para estos tests.

    El default de cada toggle es OFF; sin esto, `_etapas_de_run` pintaría todo "saltada" y el
    listado ocultaría los runs (la etapa de entrada CI estaría off). Los tests que ejercitan el
    caso "saltada" apagan el toggle puntual (global o por marca) por encima de esto.
    """
    monkeypatch.setenv(config.ENV_INGESTA, "1")
    monkeypatch.setenv(config.ENV_QA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE, "1")


def _tema_pipeline(titulo: str, marca: str = "unotv", **campos) -> dict:
    return repos.crear_contenido(
        clase="contenido", titulo=titulo, marca=marca, origen=ORIGEN_PIPELINE, **campos
    )


def _run_por_titulo(cliente, titulo: str) -> dict | None:
    r = cliente.get("/api/pipelines")
    assert r.status_code == 200
    return next((x for x in r.json()["pipelines"] if x["titulo"] == titulo), None)


def test_run_qa_no_verificado_con_copy(cliente):
    """Tema con QA `no_verificado` + copy en borrador: CI/QA/CD ok, aprobación pendiente.

    Orden NUEVO (rediseño QPC): CI -> Criba de la fuente (QA) -> Copy (CD) -> Aprobación.
    """
    tema = _tema_pipeline("Tema apto", qa_veredicto="no_verificado")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador",
        copy="Copy válido y corto.", veredicto="no_verificado",
    )
    run = _run_por_titulo(cliente, "Tema apto")
    assert run is not None
    assert [e["clave"] for e in run["etapas"]] == ["ci", "qa", "cd", "aprobacion"]
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas == {"ci": "ok", "qa": "ok", "cd": "ok", "aprobacion": "pendiente"}
    assert run["estado_global"] == "pendiente"
    # La criba de la fuente surface el aviso ⚠️.
    assert run["qa_fuente"]["no_verificado"] is True
    assert run["qa_fuente"]["problema"] is False


def test_run_sin_qa_todo_pendiente(cliente):
    """Tema sin veredicto de QA todavía: QA y CD pendientes (la QA va antes del copy)."""
    tema = _tema_pipeline("Tema sin criba")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador", copy="",
    )
    run = _run_por_titulo(cliente, "Tema sin criba")
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas["ci"] == "ok"
    assert etapas["qa"] == "pendiente"
    assert etapas["cd"] == "pendiente"


def test_run_qa_problema_omite_copy(cliente):
    """QA `problema` -> etapa QA 'revisar', CD pendiente (copy omitido) y ❗ con hallazgos."""
    hallazgos = (
        '{"resumen": "Dato falso", '
        '"hallazgos": [{"tipo": "dato", "gravedad": "error", "explicacion": "x"}]}'
    )
    _tema_pipeline("Tema con problema", qa_veredicto="problema", qa_hallazgos=hallazgos)
    run = _run_por_titulo(cliente, "Tema con problema")
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas["qa"] == "revisar"
    assert etapas["cd"] == "pendiente"
    qa = run["qa_fuente"]
    assert qa["problema"] is True
    assert qa["copy_omitido"] is True
    assert qa["hallazgos"] and qa["hallazgos"][0]["tipo"] == "dato"


def test_run_aprobado(cliente):
    """Pieza aprobada con QA `no_verificado` -> aprobación ok y estado_global ok."""
    tema = _tema_pipeline("Tema aprobado", qa_veredicto="no_verificado")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="aprobado",
        copy="Copy.", veredicto="no_verificado",
    )
    run = _run_por_titulo(cliente, "Tema aprobado")
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas["aprobacion"] == "ok"
    assert run["estado_global"] == "ok"


def test_run_qa_saltada_genera_copy(cliente, monkeypatch):
    """QA desactivada para la marca (`KENI_QA::unotv=0`): etapa QA 'saltada' y el copy se genera
    igual (CD 'ok'). 'saltada' no bloquea: el estado_global lo marca la aprobación pendiente."""
    monkeypatch.setattr(
        "keni_consola.ajustes.obtener",
        lambda clave: "0" if clave == config.clave_por_marca(config.ENV_QA, "unotv") else None,
    )
    tema = _tema_pipeline("Tema sin QA", qa_veredicto="saltada")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador",
        copy="Copy generado sin criba.", veredicto="no_verificado",
    )
    run = _run_por_titulo(cliente, "Tema sin QA")
    assert run is not None
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas == {"ci": "ok", "qa": "saltada", "cd": "ok", "aprobacion": "pendiente"}
    assert run["estado_global"] == "pendiente"


def test_marca_con_noticias_off_no_aparece(cliente, monkeypatch):
    """Una marca con 'Crear noticias' (CI) apagada (`KENI_INGESTA::marca=0`) NO lista sus runs;
    otra marca activa sí (la ingesta es la entrada del pipeline: sin ella, no hay pipeline)."""
    monkeypatch.setattr(
        "keni_consola.ajustes.obtener",
        lambda clave: "0" if clave == config.clave_por_marca(config.ENV_INGESTA, "claro-sports") else None,
    )
    _tema_pipeline("Run claro", marca="claro-sports")
    _tema_pipeline("Run uno", marca="unotv")
    titulos = {x["titulo"] for x in cliente.get("/api/pipelines").json()["pipelines"]}
    assert "Run uno" in titulos
    assert "Run claro" not in titulos


def test_estado_global_saltada_no_bloquea():
    """`_estado_global` puro: 'saltada' cuenta como 'ok' (no bloquea ni falla)."""
    def _e(estado):
        return {"estado": estado}
    assert _estado_global([_e("ok"), _e("saltada"), _e("ok"), _e("pendiente")]) == "pendiente"
    assert _estado_global([_e("ok"), _e("saltada"), _e("saltada"), _e("ok")]) == "ok"
    assert _estado_global([_e("ok"), _e("fallo"), _e("saltada"), _e("ok")]) == "fallo"


def test_excluye_contenido_no_pipeline(cliente):
    """Un contenido de otro origen NO aparece como pipeline."""
    repos.crear_contenido(clase="contenido", titulo="Manual", marca="unotv", origen="equipo")
    r = cliente.get("/api/pipelines")
    assert all(x["titulo"] != "Manual" for x in r.json()["pipelines"])


def test_filtro_por_marca(cliente):
    _tema_pipeline("Solo claro", marca="claro-sports")
    _tema_pipeline("Solo uno", marca="unotv")
    titulos = {x["titulo"] for x in cliente.get("/api/pipelines?marca=claro-sports").json()["pipelines"]}
    assert "Solo claro" in titulos
    assert "Solo uno" not in titulos


def test_marca_invalida_400(cliente):
    assert cliente.get("/api/pipelines?marca=no-existe").status_code == 400


def test_detalle_run(cliente):
    tema = _tema_pipeline("Tema detalle")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador", copy="Copy.",
    )
    d = cliente.get(f"/api/pipelines/{tema['id']}")
    assert d.status_code == 200
    body = d.json()
    assert body["pipeline"]["id"] == tema["id"]
    assert [e["clave"] for e in body["pipeline"]["etapas"]] == ["ci", "qa", "cd", "aprobacion"]
    assert "actividad" in body
    assert "qa_fuente" in body["pipeline"]
    # El detalle trae las piezas COMPLETAS: el copy real + observaciones de la validación.
    pieza = body["pipeline"]["piezas"][0]
    assert pieza["copy"] == "Copy."
    assert "observaciones" in pieza
    assert "copy_in" in pieza and "imagen_url" in pieza


def test_detalle_404(cliente):
    assert cliente.get("/api/pipelines/no-existe-xyz").status_code == 404


def test_detalle_expone_stream_de_la_etapa(cliente):
    """Un marcador de etapa CD con `gen_id` -> el detalle surface el STREAM de esa generación.

    Crea una generación REAL (con `salida` = el proceso del agente) y un marcador de etapa
    CD que la referencia por `gen_id`; el detalle debe traer `generaciones_por_etapa["CD"]`
    con esa `salida` y su estado.
    """
    tema = _tema_pipeline("Tema con stream")
    gen = generaciones.crear({
        "tipo": "pipeline",
        "marca": "unotv",
        "etiqueta": "Copy · UnoTV",
        "salida": "Razonando sobre la nota… escribiendo el copy…",
        "fase": generaciones.FASE_COMPLETADO,
        "estado": generaciones.ESTADO_COMPLETADO,
    })
    registrar_etapa(
        ETAPA_CD, "unotv", "Generación de copy", contenido_id=tema["id"], gen_id=gen["id"],
    )

    d = cliente.get(f"/api/pipelines/{tema['id']}")
    assert d.status_code == 200
    body = d.json()
    por_etapa = body["generaciones_por_etapa"]
    assert "CD" in por_etapa
    cd = por_etapa["CD"]
    assert cd["id"] == gen["id"]
    assert cd["salida"] == "Razonando sobre la nota… escribiendo el copy…"
    assert cd["estado"] == generaciones.ESTADO_COMPLETADO
    assert cd["fase"] == generaciones.FASE_COMPLETADO


def test_detalle_sin_gen_id_no_trae_generacion(cliente):
    """Back-compat: un marcador SIN `gen_id` no añade nada a `generaciones_por_etapa`."""
    tema = _tema_pipeline("Tema sin stream")
    registrar_etapa(ETAPA_CD, "unotv", "Generación de copy", contenido_id=tema["id"])
    body = cliente.get(f"/api/pipelines/{tema['id']}").json()
    assert body["generaciones_por_etapa"] == {}
