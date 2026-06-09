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
    assert [e["clave"] for e in run["etapas"]] == ["jerarquia", "ci", "qa", "cd", "aprobacion"]
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    # Sin historia (cluster) asociada, la Jerarquización se pinta "saltada" (no bloquea).
    assert etapas == {
        "jerarquia": "saltada", "ci": "ok", "qa": "ok", "cd": "ok", "aprobacion": "pendiente"
    }
    assert run["estado_global"] == "pendiente"
    assert run["cluster"] is None
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
    assert etapas == {
        "jerarquia": "saltada", "ci": "ok", "qa": "saltada", "cd": "ok", "aprobacion": "pendiente"
    }
    assert run["estado_global"] == "pendiente"


def test_marca_con_noticias_off_sigue_localizable(cliente, monkeypatch):
    """Una marca con 'Crear noticias' (CI) apagada SIGUE listando sus runs (la etapa CI se pinta
    'saltada', pero la run NO desaparece): así no quedan posts en el feed sin pipeline que hallar.
    """
    monkeypatch.setattr(
        "keni_consola.ajustes.obtener",
        lambda clave: "0" if clave == config.clave_por_marca(config.ENV_INGESTA, "claro-sports") else None,
    )
    _tema_pipeline("Run claro", marca="claro-sports")
    _tema_pipeline("Run uno", marca="unotv")
    pipelines = cliente.get("/api/pipelines").json()["pipelines"]
    titulos = {x["titulo"] for x in pipelines}
    assert "Run uno" in titulos
    assert "Run claro" in titulos  # ya NO se oculta
    claro = next(x for x in pipelines if x["titulo"] == "Run claro")
    ci = next(e for e in claro["etapas"] if e["clave"] == "ci")
    assert ci["estado"] == "saltada"


def _historia_de(tema_id: str, marca: str = "unotv", **campos) -> dict:
    """Crea una HISTORIA (cluster) enlazada a un tema del pipeline (`contenido_id`)."""
    base = {
        "marca": marca, "titulo": "Historia", "n_items": 1, "n_fuentes": 1,
        "score": 0.5, "breaking": 0, "verificacion": "unica_fuente",
        "estado": "usado", "contenido_id": tema_id,
    }
    base.update(campos)
    return repos.upsert_noticia_cluster(base)


def test_jerarquia_ok_desde_historia(cliente):
    """Un tema promovido de una HISTORIA muestra Jerarquización 'ok' + la procedencia IA real
    (corroboración, fusión, score, verificación), y la etapa CI refleja la promoción."""
    tema = _tema_pipeline("Tema con historia")
    _historia_de(
        tema["id"], n_items=5, n_fuentes=3, score=0.82, breaking=1, verificacion="corroborada",
    )
    run = _run_por_titulo(cliente, "Tema con historia")
    assert run is not None
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas["jerarquia"] == "ok"
    assert etapas["ci"] == "ok"
    cl = run["cluster"]
    assert cl is not None
    assert cl["n_fuentes"] == 3
    assert cl["n_items"] == 5
    assert cl["breaking"] is True
    assert cl["verificacion"] == "corroborada"
    assert cl["score"] == pytest.approx(0.82)
    jer = next(e for e in run["etapas"] if e["clave"] == "jerarquia")
    assert "3 fuente" in jer["detalle"]
    assert "breaking" in jer["detalle"]
    ci = next(e for e in run["etapas"] if e["clave"] == "ci")
    assert "promovida a tema" in ci["detalle"].lower()


def test_cluster_por_contenido_reverso(cliente):
    """Lookup reverso historia<-tema: single y por lote; "" y faltantes se ignoran."""
    tema = _tema_pipeline("Tema reverso")
    hist = _historia_de(tema["id"], n_fuentes=2, score=0.5)
    c = repos.cluster_por_contenido(tema["id"])
    assert c is not None and c["id"] == hist["id"]
    mapa = repos.clusters_por_contenidos([tema["id"], "no-existe"])
    assert mapa[tema["id"]]["id"] == hist["id"]
    assert "no-existe" not in mapa
    assert repos.cluster_por_contenido("") is None
    assert repos.clusters_por_contenidos([]) == {}


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


def test_paginacion_envelope_y_offset(cliente):
    """La lista trae `paginacion:{total,limite,desplazamiento}` y respeta offset+limite (sin solape)."""
    for i in range(5):
        _tema_pipeline(f"Pag {i}")
    base = cliente.get("/api/pipelines").json()
    assert base["paginacion"]["total"] >= 5
    p1 = cliente.get("/api/pipelines?limite=2&desplazamiento=0").json()
    assert len(p1["pipelines"]) == 2
    assert p1["paginacion"]["limite"] == 2
    assert p1["paginacion"]["desplazamiento"] == 0
    p2 = cliente.get("/api/pipelines?limite=2&desplazamiento=2").json()
    ids1 = {x["id"] for x in p1["pipelines"]}
    ids2 = {x["id"] for x in p2["pipelines"]}
    assert ids1.isdisjoint(ids2)  # páginas distintas, sin solape


def test_etapa_actual_y_filtro_por_etapa(cliente):
    """`etapa_actual` = la etapa donde está parada; `?etapa=` filtra por ella."""
    aprob = _tema_pipeline("Run aprobada", qa_veredicto="no_verificado")
    repos.crear_contenido_plataforma(
        contenido_id=aprob["id"], red="x", estado="aprobado", copy="C.", veredicto="no_verificado",
    )
    _tema_pipeline("Run en QA")  # sin veredicto: la QA queda 'pendiente'
    en_qa = _run_por_titulo(cliente, "Run en QA")
    assert en_qa["etapa_actual"] == "qa"
    aprobada = _run_por_titulo(cliente, "Run aprobada")
    assert aprobada["etapa_actual"] == ""  # todo ok/saltada: no está parada en ninguna

    titulos_qa = {x["titulo"] for x in cliente.get("/api/pipelines?etapa=qa").json()["pipelines"]}
    assert "Run en QA" in titulos_qa
    assert "Run aprobada" not in titulos_qa


def test_filtro_por_estado_global_e_invalido_se_ignora(cliente):
    """`?estado=` filtra por estado_global; un valor inválido se ignora (no 400)."""
    _tema_pipeline("Run pendiente")  # QA pendiente -> estado_global 'pendiente'
    pend = {x["titulo"] for x in cliente.get("/api/pipelines?estado=pendiente").json()["pipelines"]}
    assert "Run pendiente" in pend
    # Filtro inválido: se ignora, devuelve 200 con el conjunto sin filtrar (no rompe la UI).
    r = cliente.get("/api/pipelines?estado=zzz&etapa=no-existe")
    assert r.status_code == 200
    assert "Run pendiente" in {x["titulo"] for x in r.json()["pipelines"]}


def test_detalle_run(cliente):
    tema = _tema_pipeline("Tema detalle")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador", copy="Copy.",
    )
    d = cliente.get(f"/api/pipelines/{tema['id']}")
    assert d.status_code == 200
    body = d.json()
    assert body["pipeline"]["id"] == tema["id"]
    assert [e["clave"] for e in body["pipeline"]["etapas"]] == [
        "jerarquia", "ci", "qa", "cd", "aprobacion"
    ]
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
