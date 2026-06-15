"""Tests del endpoint `/api/pipelines` (vista estilo GitLab del pipeline de contenido).

Cada `contenido` con `origen='pipeline'` es una RUN; sus etapas (CI/CD/QA/Aprobación) se
DERIVAN del estado real de la pieza y sus publicaciones por plataforma. Aquí montamos ese
estado a mano (sin daemon ni `claude`) y comprobamos la derivación + el detalle + la
exclusión de lo que NO es del pipeline. Usa la fixture `cliente` (entorno aislado + Postgres).
"""

from __future__ import annotations

import json

import pytest

from keni_consola import config, generaciones, repos
from keni_consola.api.pipelines import _estado_global
from keni_consola.pipeline_contenido import ETAPA_CD, ORIGEN_PIPELINE, registrar_etapa


@pytest.fixture(autouse=True)
def _etapas_activas(monkeypatch):
    """Activa los maestros togglables de las etapas (Fusión/Editorial/Selección/Validación/Copy) para
    estos tests.

    El default de cada toggle es OFF; sin esto, `_etapas_de_run` pintaría todo "saltada". Los tests
    que ejercitan el caso "saltada" apagan el toggle puntual (global o por marca) por encima de esto.
    (Arte se deja OFF por defecto; el test de Arte lo enciende a propósito.)
    """
    monkeypatch.setenv(config.ENV_PIPELINE_FUSION, "1")
    monkeypatch.setenv(config.ENV_RANKING_PERFIL_IA, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_SELECCION, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_VALIDACION, "1")
    monkeypatch.setenv(config.ENV_PIPELINE_COPY, "1")


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
    """
    tema = _tema_pipeline("Tema apto", qa_veredicto="no_verificado")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador",
        copy="Copy válido y corto.", veredicto="no_verificado",
    )
    run = _run_por_titulo(cliente, "Tema apto")
    assert run is not None
    assert [e["clave"] for e in run["etapas"]] == [
        "fusion", "editorial", "ci", "qa", "cd", "arte", "aprobacion"
    ]
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    # Sin cluster -> Fusión/Editorial saltadas; Arte saltada (toggle off). Ninguna bloquea.
    assert etapas == {
        "fusion": "saltada", "editorial": "saltada", "ci": "ok", "qa": "ok",
        "cd": "ok", "arte": "saltada", "aprobacion": "pendiente",
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


def test_aprobacion_esperando_humano_es_pendiente(cliente):
    """Piezas EN REVISIÓN sin ninguna aprobada = la run espera al HUMANO: 'pendiente' (con el
    detalle 'En revisión'), no 'en_curso' — la máquina no está haciendo nada."""
    tema = _tema_pipeline("Run en revisión", qa_veredicto="no_verificado")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="en_revision",
        copy="Copy.", veredicto="no_verificado",
    )
    run = _run_por_titulo(cliente, "Run en revisión")
    ap = next(e for e in run["etapas"] if e["clave"] == "aprobacion")
    assert ap["estado"] == "pendiente"
    assert ap["detalle"] == "En revisión"
    assert run["estado_global"] == "pendiente"


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
    """QA desactivada para la marca (`KENI_PIPELINE_VALIDACION::unotv=0`): etapa QA 'saltada' y el copy se genera
    igual (CD 'ok'). 'saltada' no bloquea: el estado_global lo marca la aprobación pendiente."""
    monkeypatch.setattr(
        "keni_consola.ajustes.obtener",
        lambda clave: "0" if clave == config.clave_por_marca(config.ENV_PIPELINE_VALIDACION, "unotv") else None,
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
        "fusion": "saltada", "editorial": "saltada", "ci": "ok", "qa": "saltada",
        "cd": "ok", "arte": "saltada", "aprobacion": "pendiente",
    }
    assert run["estado_global"] == "pendiente"


def test_marca_con_noticias_off_sigue_localizable(cliente, monkeypatch):
    """Una marca con 'Crear noticias' (CI) apagada SIGUE listando sus runs, y la etapa CI se
    pinta por la EVIDENCIA, no por el toggle de hoy: el tema EXISTE, luego la selección corrió
    ('ok'). Apagar el interruptor después no re-pinta la historia de la run.
    """
    monkeypatch.setattr(
        "keni_consola.ajustes.obtener",
        lambda clave: "0" if clave == config.clave_por_marca(config.ENV_PIPELINE_SELECCION, "claro-sports") else None,
    )
    _tema_pipeline("Run claro", marca="claro-sports")
    _tema_pipeline("Run uno", marca="unotv")
    pipelines = cliente.get("/api/pipelines").json()["pipelines"]
    titulos = {x["titulo"] for x in pipelines}
    assert "Run uno" in titulos
    assert "Run claro" in titulos  # ya NO se oculta
    claro = next(x for x in pipelines if x["titulo"] == "Run claro")
    ci = next(e for e in claro["etapas"] if e["clave"] == "ci")
    assert ci["estado"] == "ok"  # la run existe: la selección CORRIÓ, diga lo que diga el toggle


def test_etapas_ejecutadas_no_se_repintan_con_toggles_off(cliente, monkeypatch):
    """Una run COMPLETADA pinta sus etapas por lo EJECUTADO aunque hoy TODOS los toggles estén
    apagados: encender/apagar interruptores no ilumina ni apaga la historia de las runs."""
    tema = _tema_pipeline("Run histórica", qa_veredicto="no_verificado")
    _historia_de(tema["id"], n_fuentes=3, n_items=4, score=0.8)
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="aprobado",
        copy="Copy hecho.", veredicto="no_verificado",
    )
    for env in (config.ENV_PIPELINE_FUSION, config.ENV_RANKING_PERFIL_IA,
                config.ENV_PIPELINE_SELECCION, config.ENV_PIPELINE_VALIDACION,
                config.ENV_PIPELINE_COPY, config.ENV_PIPELINE_ARTE):
        monkeypatch.delenv(env, raising=False)
    run = _run_por_titulo(cliente, "Run histórica")
    estados = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert estados["fusion"] == "ok"      # hay historia enlazada: la fusión corrió
    assert estados["editorial"] == "ok"   # hay score: el encaje corrió
    assert estados["ci"] == "ok"          # el tema existe: la selección corrió
    assert estados["qa"] == "ok"          # veredicto persistido: la criba corrió
    assert estados["cd"] == "ok"          # hay copy persistido: la etapa corrió


def test_run_caducada_se_pinta_cerrada(cliente):
    """Una run CADUCADA (TTL de frescura) queda CERRADA sin producto: Validación 'saltada' con
    el motivo, Copy/Aprobación 'saltada' (no un 'pendiente' eterno) y estado_global 'ok'."""
    _tema_pipeline("Run caducada", qa_veredicto="caducada")
    run = _run_por_titulo(cliente, "Run caducada")
    etapas = {e["clave"]: e for e in run["etapas"]}
    assert etapas["qa"]["estado"] == "saltada"
    assert "Caducada" in etapas["qa"]["detalle"]
    assert etapas["cd"]["estado"] == "saltada"
    assert etapas["aprobacion"]["estado"] == "saltada"
    assert run["estado_global"] == "ok"  # cerrada: no bloquea ni queda pendiente


def _historia_de(tema_id: str, marca: str = "unotv", **campos) -> dict:
    """Crea una HISTORIA (cluster) enlazada a un tema del pipeline (`contenido_id`)."""
    base = {
        "marca": marca, "titulo": "Historia", "n_items": 1, "n_fuentes": 1,
        "score": 0.5, "breaking": 0, "verificacion": "unica_fuente",
        "estado": "usado", "contenido_id": tema_id,
    }
    base.update(campos)
    return repos.upsert_noticia_cluster(base)


def test_fusion_y_editorial_ok_desde_historia(cliente):
    """Un tema de una HISTORIA: Fusión y Editorial 'ok' con sus señales (fuentes/notas, score)."""
    tema = _tema_pipeline("Tema con historia")
    _historia_de(
        tema["id"], n_items=5, n_fuentes=3, score=0.82, breaking=1, verificacion="corroborada",
    )
    run = _run_por_titulo(cliente, "Tema con historia")
    assert run is not None
    etapas = {e["clave"]: e for e in run["etapas"]}
    assert etapas["fusion"]["estado"] == "ok"
    assert etapas["editorial"]["estado"] == "ok"
    cl = run["cluster"]
    assert cl is not None
    assert cl["n_fuentes"] == 3
    assert cl["n_items"] == 5
    assert cl["breaking"] is True
    assert cl["score"] == pytest.approx(0.82)
    # Fusión = dedup (fuentes/notas); Editorial = score (+ breaking).
    assert "3 fuentes" in etapas["fusion"]["detalle"]
    assert "5 notas" in etapas["fusion"]["detalle"]
    assert "0.82" in etapas["editorial"]["detalle"]


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
        "fusion", "editorial", "ci", "qa", "cd", "arte", "aprobacion"
    ]
    assert "actividad" in body
    assert "qa_fuente" in body["pipeline"]
    # El detalle trae las piezas COMPLETAS: el copy real + observaciones de la validación.
    pieza = body["pipeline"]["piezas"][0]
    assert pieza["copy"] == "Copy."
    assert "observaciones" in pieza
    assert "copy_in" in pieza and "imagen_url" in pieza


def test_detalle_enlaza_haiku_del_pool_por_etapa(cliente):
    """El detalle enlaza el Haiku del pool por etapa: 'Fusión...' -> FUSION, 'Encaje...' -> EDITORIAL,
    cada uno con su prompt + salida REALES."""
    tema = _tema_pipeline("Tema con pool", marca="unotv")
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "etiqueta": "Fusión de historias — UnoTV",
        "prompt": "PROMPT-FUSION", "salida": "SALIDA-FUSION",
        "estado": generaciones.ESTADO_COMPLETADO, "fase": generaciones.FASE_COMPLETADO,
    })
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "etiqueta": "Encaje editorial — UnoTV",
        "prompt": "PROMPT-ENCAJE", "salida": "SALIDA-ENCAJE",
        "estado": generaciones.ESTADO_COMPLETADO, "fase": generaciones.FASE_COMPLETADO,
    })
    por_etapa = cliente.get(f"/api/pipelines/{tema['id']}").json()["generaciones_por_etapa"]
    assert por_etapa["FUSION"]["prompt"] == "PROMPT-FUSION"
    assert por_etapa["FUSION"]["salida"] == "SALIDA-FUSION"
    assert por_etapa["EDITORIAL"]["prompt"] == "PROMPT-ENCAJE"
    assert por_etapa["EDITORIAL"]["salida"] == "SALIDA-ENCAJE"


def test_etapa_arte_exige_evidencia_de_arte_ia(cliente, monkeypatch):
    """La etapa Arte se deriva de la EVIDENCIA de arte GENERADO (generación/marcador de
    auto-arte correlacionado), no de que la pieza tenga imagen: la FOTO de la nota de una
    fuente propia (bajada en ingesta) no es arte IA."""
    # Toggle Arte off (default) + pieza CON imagen (foto de fuente): saltada, NO ok.
    tema = _tema_pipeline("Tema foto de fuente")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador", copy="C.",
        imagen="foto-fuente.png", falta_imagen=False,
    )
    run = _run_por_titulo(cliente, "Tema foto de fuente")
    arte = next(e for e in run["etapas"] if e["clave"] == "arte")
    assert arte["estado"] == "saltada"
    # Con EVIDENCIA de arte IA (la generación que deja el auto-arte) -> ok, aunque el toggle
    # de HOY esté apagado (la evidencia no se re-pinta con interruptores).
    tema2 = _tema_pipeline("Tema arte ia")
    repos.crear_contenido_plataforma(
        contenido_id=tema2["id"], red="x", estado="borrador", copy="C.",
        imagen="arte-ia.png", falta_imagen=False,
    )
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "contenido_id": tema2["id"],
        "etiqueta": "Arte — Tema arte ia", "estado": generaciones.ESTADO_COMPLETADO,
    })
    run2 = _run_por_titulo(cliente, "Tema arte ia")
    arte2 = next(e for e in run2["etapas"] if e["clave"] == "arte")
    assert arte2["estado"] == "ok"
    # Toggle ON pero sin evidencia: pendiente (el arte aún no corrió), tampoco 'ok'.
    monkeypatch.setenv(config.ENV_PIPELINE_ARTE, "1")
    tema3 = _tema_pipeline("Tema arte pendiente")
    repos.crear_contenido_plataforma(
        contenido_id=tema3["id"], red="x", estado="borrador", copy="C.",
        imagen="foto-fuente.png", falta_imagen=False,
    )
    run3 = _run_por_titulo(cliente, "Tema arte pendiente")
    arte3 = next(e for e in run3["etapas"] if e["clave"] == "arte")
    assert arte3["estado"] == "pendiente"


def test_etapas_marcan_ia_y_detalle_trae_prompts(cliente):
    """Cada etapa trae `es_ia` (IA vs no-IA: Selección/Aprobación NO); el detalle expone
    `prompts_por_etapa` (plantilla del prompt de cada etapa IA)."""
    tema = _tema_pipeline("Tema ia flags")
    run = _run_por_titulo(cliente, "Tema ia flags")
    ia = {e["clave"]: e["es_ia"] for e in run["etapas"]}
    assert ia["fusion"] is True and ia["editorial"] is True
    assert ia["qa"] is True and ia["cd"] is True and ia["arte"] is True
    assert ia["ci"] is False and ia["aprobacion"] is False
    body = cliente.get(f"/api/pipelines/{tema['id']}").json()
    assert isinstance(body["prompts_por_etapa"], dict)


def test_detalle_404(cliente):
    assert cliente.get("/api/pipelines/no-existe-xyz").status_code == 404


# --------------------------------------------------------------------------- #
# GET /api/pipelines/problemas: temas bloqueados (veredicto `problema`)         #
# --------------------------------------------------------------------------- #


def test_problemas_lista_temas_bloqueados(cliente):
    """Lista los temas `problema` con etapa, intentos, último error y timestamps; excluye el resto."""
    pend = json.dumps({"nota": "n", "qa_intentos": 1, "cd_intentos": 3})
    hallazgos = json.dumps({
        "resumen": "Fallo repetido de la etapa",
        "hallazgos": [{
            "tipo": "sistema", "gravedad": "error", "fragmento": "Copy",
            "explicacion": "La generación de copy falló 3 veces.",
            "sugerencia": "Revisa la generación o relanza a mano.",
        }],
    })
    _tema_pipeline(
        "Tema bloqueado", qa_veredicto="problema", qa_hallazgos=hallazgos, copy_pendiente=pend,
    )
    _tema_pipeline("Tema sano", qa_veredicto="no_verificado")

    r = cliente.get("/api/pipelines/problemas")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    p = body["problemas"][0]
    assert p["titulo"] == "Tema bloqueado"
    assert p["marca"] == "unotv" and p["marca_nombre"]
    assert p["etapa"] == "Copy"  # el hallazgo de sistema trae la etapa que agotó reintentos
    assert p["intentos"] == {"qa": 1, "cd": 3}
    assert "falló 3 veces" in p["error"]
    assert p["hallazgos"] and p["hallazgos"][0]["tipo"] == "sistema"
    assert p["creado"] and p["actualizado"]


def test_problemas_criba_roja_es_validacion(cliente):
    """Un 🔴 de la propia criba (hallazgo no-sistema) se atribuye a la etapa Validación."""
    hallazgos = json.dumps({
        "resumen": "Dato falso evidente",
        "hallazgos": [{"tipo": "dato", "gravedad": "error", "explicacion": "es falso"}],
    })
    _tema_pipeline("Criba roja", qa_veredicto="problema", qa_hallazgos=hallazgos)
    p = cliente.get("/api/pipelines/problemas").json()["problemas"][0]
    assert p["etapa"] == "Validación"
    assert p["error"] == "es falso"
    assert p["intentos"] == {"qa": 0, "cd": 0}  # sin copy_pendiente no hay contadores


def test_problemas_filtra_por_marca_y_valida(cliente):
    _tema_pipeline("P claro", marca="claro-sports", qa_veredicto="problema")
    _tema_pipeline("P uno", marca="unotv", qa_veredicto="problema")
    titulos = {
        x["titulo"]
        for x in cliente.get("/api/pipelines/problemas?marca=claro-sports").json()["problemas"]
    }
    assert titulos == {"P claro"}
    assert cliente.get("/api/pipelines/problemas?marca=no-existe").status_code == 400


def test_problemas_vacio_sin_bloqueados(cliente):
    _tema_pipeline("Todo bien", qa_veredicto="no_verificado")
    body = cliente.get("/api/pipelines/problemas").json()
    assert body == {"problemas": [], "total": 0}


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


# --------------------------------------------------------------------------- #
# Feed UNIFICADO (página Producción): runs + actividad suelta en una lista     #
# --------------------------------------------------------------------------- #


def _gen_suelta(etiqueta: str = "Copy manual", marca: str = "unotv", **extra) -> dict:
    base = {
        "tipo": "copy", "marca": marca, "etiqueta": etiqueta,
        "estado": generaciones.ESTADO_COMPLETADO,
        "metricas": {"tokens_in": 100, "tokens_out": 50, "total_cost_usd": 0.02,
                     "duration_ms": 3000, "num_turns": 2},
    }
    base.update(extra)
    return generaciones.crear(base)


def test_feed_unificado_mezcla_runs_y_actividad_suelta(cliente):
    """La lista trae las runs (`clase='run'`) Y la actividad suelta (`clase='actividad'`)
    como item de UNA etapa (su tipo de trabajo) con métricas; los marcadores de etapa NO salen."""
    _tema_pipeline("Run del feed")
    _gen_suelta("Copy a mano")
    generaciones.crear({  # marcador de etapa: sin coste, fuera del feed
        "tipo": "pipeline_etapa", "marca": "unotv", "etiqueta": "CD · Generación de copy",
        "estado": generaciones.ESTADO_COMPLETADO,
    })
    items = cliente.get("/api/pipelines").json()["pipelines"]
    por_titulo = {x["titulo"]: x for x in items}
    assert por_titulo["Run del feed"]["clase"] == "run"
    suelta = por_titulo["Copy a mano"]
    assert suelta["clase"] == "actividad"
    assert suelta["estado_global"] == "ok"
    assert len(suelta["etapas"]) == 1
    assert suelta["etapas"][0]["clave"] == "trabajo"
    assert suelta["etapas"][0]["es_ia"] is True
    assert suelta["tipo"] == "copy"
    assert suelta["metricas"]["tokens"] == 150
    assert suelta["metricas"]["coste_usd"] == pytest.approx(0.02)
    assert suelta["metricas"]["duration_ms"] == 3000
    assert all(x["titulo"] != "CD · Generación de copy" for x in items)


def test_run_suma_metricas_de_sus_generaciones(cliente):
    """Una generación correlacionada a la run (contenido_id) NO sale suelta: su coste se
    SUMA en `metricas` de la run."""
    tema = _tema_pipeline("Run con coste")
    _gen_suelta("Copy de la run", contenido_id=tema["id"])
    _gen_suelta("Arte de la run", tipo="imagen", contenido_id=tema["id"],
                metricas={"tokens_in": 10, "tokens_out": 10, "total_cost_usd": 0.005,
                          "duration_ms": 1000})
    items = cliente.get("/api/pipelines").json()["pipelines"]
    titulos = {x["titulo"] for x in items}
    assert "Copy de la run" not in titulos
    assert "Arte de la run" not in titulos
    run = next(x for x in items if x["titulo"] == "Run con coste")
    assert run["metricas"]["items"] == 2
    assert run["metricas"]["tokens"] == 150 + 20
    assert run["metricas"]["coste_usd"] == pytest.approx(0.025)
    assert run["metricas"]["duration_ms"] == 4000
    # El detalle trae las MISMAS métricas (no se contradicen tarjeta y página).
    det = cliente.get(f"/api/pipelines/{tema['id']}").json()["pipeline"]
    assert det["metricas"] == run["metricas"]


def test_filtros_clase_y_tipo(cliente):
    """`?clase=` separa runs de actividad suelta; `?tipo=` filtra los sueltos por su trabajo."""
    _tema_pipeline("Run filtrable")
    _gen_suelta("Suelta copy")
    _gen_suelta("Suelta imagen", tipo="imagen")
    solo_runs = cliente.get("/api/pipelines?clase=run").json()["pipelines"]
    assert all(x["clase"] == "run" for x in solo_runs)
    solo_actividad = cliente.get("/api/pipelines?clase=actividad").json()["pipelines"]
    assert all(x["clase"] == "actividad" for x in solo_actividad)
    imagenes = cliente.get("/api/pipelines?tipo=imagen").json()["pipelines"]
    assert {x["titulo"] for x in imagenes} == {"Suelta imagen"}
    # Valor inválido de clase: se ignora (200 con el conjunto sin filtrar).
    assert cliente.get("/api/pipelines?clase=zzz").status_code == 200


def test_fusion_editorial_no_saltada_si_el_pool_corrio(cliente):
    """Run SIN historia pero con la IA del pool corrida (generaciones Fusión/Encaje de la
    marca): Fusión y Editorial se pintan 'ok' con detalle honesto, NO 'saltada'."""
    tema = _tema_pipeline("Run sin grupo")
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "etiqueta": "Fusión de historias — UnoTV",
        "prompt": "P", "salida": "S",
        "estado": generaciones.ESTADO_COMPLETADO, "fase": generaciones.FASE_COMPLETADO,
    })
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "etiqueta": "Encaje editorial — UnoTV",
        "prompt": "P", "salida": "S",
        "estado": generaciones.ESTADO_COMPLETADO, "fase": generaciones.FASE_COMPLETADO,
    })
    run = _run_por_titulo(cliente, "Run sin grupo")
    etapas = {e["clave"]: e for e in run["etapas"]}
    assert etapas["fusion"]["estado"] == "ok"
    assert "Sin grupo" in etapas["fusion"]["detalle"]
    assert etapas["editorial"]["estado"] == "ok"
    # El detalle deriva IGUAL (misma evidencia) y además enlaza la generación del pool.
    det = cliente.get(f"/api/pipelines/{tema['id']}").json()
    det_etapas = {e["clave"]: e for e in det["pipeline"]["etapas"]}
    assert det_etapas["fusion"]["estado"] == "ok"
    assert det_etapas["editorial"]["estado"] == "ok"
    assert det["generaciones_por_etapa"]["FUSION"]["salida"] == "S"
    # Sin pool ni historia (otra marca): sigue 'saltada' (sin evidencia no se inventa nada).
    _tema_pipeline("Run sin evidencia", marca="claro-sports")
    sin = _run_por_titulo(cliente, "Run sin evidencia")
    sin_etapas = {e["clave"]: e["estado"] for e in sin["etapas"]}
    assert sin_etapas["fusion"] == "saltada"
    assert sin_etapas["editorial"] == "saltada"


def test_lista_trae_sumatorio_de_metricas(cliente):
    """La lista responde `totales`: la SUMA de métricas de todos los items que casan el filtro
    (no solo la página), para el sumatorio de la página Producción."""
    tema = _tema_pipeline("Run sumada")
    _gen_suelta("Copy de la run sumada", contenido_id=tema["id"])
    _gen_suelta("Suelta sumada")
    body = cliente.get("/api/pipelines").json()
    t = body["totales"]
    assert t["items"] == 2
    assert t["tokens"] == 300
    assert t["coste_usd"] == pytest.approx(0.04)
    assert t["duration_ms"] == 6000
    # Con un filtro, el sumatorio se acota a lo filtrado.
    solo_runs = cliente.get("/api/pipelines?clase=run").json()["totales"]
    assert solo_runs["items"] == 1
    assert solo_runs["tokens"] == 150


# --------------------------------------------------------------------------- #
# Temas del TABLERO trabajados por el pipeline: son RUNS del feed              #
# --------------------------------------------------------------------------- #


def test_tema_de_tablero_trabajado_sale_como_run(cliente):
    """Un tema del tablero (origen de `ORIGENES_AUTOGEN`) que la etapa de copy REDACTÓ es una
    RUN del feed (no una entrada suelta "Auto-copy"): su trabajo se ve dentro de la run, con
    etapas honestas (Fusión/Editorial/Criba "no aplica": no pasó por el pool)."""
    tema = repos.crear_contenido(
        clase="contenido", titulo="Breaking usada a mano", marca="unotv", origen="historia",
    )
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador", copy="Copy.",
    )
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "contenido_id": tema["id"],
        "etiqueta": "Breaking usada a mano · UnoTV",
        "estado": generaciones.ESTADO_COMPLETADO,
        "metricas": {"tokens_in": 100, "tokens_out": 50, "total_cost_usd": 0.02,
                     "duration_ms": 3000},
    })
    # Pool de la marca corrido: NO se hereda (el tema no vino del pool).
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "etiqueta": "Fusión de historias — UnoTV",
        "estado": generaciones.ESTADO_COMPLETADO,
    })
    items = cliente.get("/api/pipelines").json()["pipelines"]
    run = next(x for x in items if x["titulo"] == "Breaking usada a mano")
    assert run["clase"] == "run"
    etapas = {e["clave"]: e for e in run["etapas"]}
    assert etapas["fusion"]["estado"] == "saltada"
    assert "No aplica" in etapas["fusion"]["detalle"]
    assert etapas["editorial"]["estado"] == "saltada"
    assert etapas["qa"]["estado"] == "saltada"
    assert "Sin criba" in etapas["qa"]["detalle"] or "No aplica" in etapas["qa"]["detalle"]
    assert etapas["ci"]["estado"] == "ok"
    assert "historia" in etapas["ci"]["detalle"]
    assert etapas["cd"]["estado"] == "ok"  # el copy persistido
    assert run["metricas"]["tokens"] == 150
    # El trabajo NO sale duplicado como entrada suelta.
    assert all(
        x["clase"] == "run" or x["titulo"] != "Breaking usada a mano · UnoTV" for x in items
    )
    # Y su detalle es accesible (misma página que cualquier run).
    det = cliente.get(f"/api/pipelines/{tema['id']}")
    assert det.status_code == 200
    det_etapas = {e["clave"]: e for e in det.json()["pipeline"]["etapas"]}
    assert det_etapas["fusion"]["estado"] == "saltada"  # coherente con la lista


def test_autogen_legacy_correlacionado_se_pliega_en_su_run(cliente):
    """Una generación LEGADA `tipo='autogen'` correlacionada a un tema del tablero también
    convierte el tema en run y se pliega en sus métricas (no queda suelta como "Auto-copy")."""
    tema = repos.crear_contenido(
        clase="contenido", titulo="Tema con autogen legado", marca="unotv", origen="equipo",
    )
    generaciones.crear({
        "tipo": "autogen", "marca": "unotv", "contenido_id": tema["id"],
        "etiqueta": "Auto-copy · UnoTV", "estado": generaciones.ESTADO_COMPLETADO,
        "metricas": {"tokens_in": 10, "tokens_out": 5, "total_cost_usd": 0.001,
                     "duration_ms": 500},
    })
    items = cliente.get("/api/pipelines").json()["pipelines"]
    run = next(x for x in items if x["titulo"] == "Tema con autogen legado")
    assert run["clase"] == "run"
    assert run["metricas"]["tokens"] == 15
    assert all(x["titulo"] != "Auto-copy · UnoTV" for x in items)


def test_metricas_de_run_via_marcador_sin_contenido_id(cliente):
    """Una generación SIN `contenido_id` en el registro (los previos a sellarlo en `lanzar`)
    se atribuye a su run por el MARCADOR de etapa (`gen_id` -> `contenido_id`): la tarjeta
    suma sus métricas en vez de salir a cero (el bug visible: runs sin tokens/coste/tiempo)."""
    tema = _tema_pipeline("Run correlada por marcador")
    gen = generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "etiqueta": "Copy · UnoTV",  # SIN contenido_id
        "estado": generaciones.ESTADO_COMPLETADO,
        "metricas": {"tokens_in": 200, "tokens_out": 100, "total_cost_usd": 0.03,
                     "duration_ms": 5000},
    })
    registrar_etapa(
        ETAPA_CD, "unotv", "Generación de copy", contenido_id=tema["id"], gen_id=gen["id"],
    )
    run = _run_por_titulo(cliente, "Run correlada por marcador")
    assert run["metricas"]["items"] == 1
    assert run["metricas"]["tokens"] == 300
    assert run["metricas"]["coste_usd"] == pytest.approx(0.03)
    assert run["metricas"]["duration_ms"] == 5000
    # Si ADEMÁS el registro llevara contenido_id, no se duplica (dedup por generación).
    det = cliente.get(f"/api/pipelines/{tema['id']}").json()["pipeline"]
    assert det["metricas"] == run["metricas"]


def test_lanzar_sella_contenido_id_en_el_registro(cliente, monkeypatch):
    """`dominio.generar.lanzar` persiste `contenido_id` en el REGISTRO de la generación (no
    solo en el spec del job): es la correlación que usa Producción para sumar por run."""
    from keni_consola.dominio import generar as dom_generar
    from keni_consola.dominio import jobspec

    monkeypatch.setattr(
        dom_generar.generaciones, "encolar_job_claude", lambda *a, **k: None
    )
    spec_proc = jobspec.construir_hashtags()
    gen = dom_generar.lanzar(
        tipo="pipeline", titulo="t", marca="unotv", prompt="p",
        procesar=jobspec.reconstruir_procesar({"procesar": spec_proc}),
        procesar_spec=spec_proc, clave_idem="k-correlacion",
        contenido_id="tema-xyz",
    )
    assert (generaciones.obtener(gen["id"]) or {}).get("contenido_id") == "tema-xyz"


def test_run_de_pipeline_suma_tambien_las_etapas_de_pool(cliente):
    """La tarjeta de una run del pipeline cuadra con el AGREGADO de sus etapas: además de las
    generaciones correlacionadas (copy/criba/arte), suma las etapas de POOL que su detalle
    enlaza (la Fusión y el Encaje más recientes de la marca). Un tema del TABLERO no las suma
    (el pool no le aplica)."""
    tema = _tema_pipeline("Run con pool sumado")
    _gen_suelta("Copy de la run", contenido_id=tema["id"])  # 150 tok · 0.02 · 3000 ms
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "etiqueta": "Fusión de historias — UnoTV",
        "estado": generaciones.ESTADO_COMPLETADO,
        "metricas": {"tokens_in": 10, "tokens_out": 90, "total_cost_usd": 0.01,
                     "duration_ms": 2000},
    })
    generaciones.crear({
        "tipo": "pipeline", "marca": "unotv", "etiqueta": "Encaje editorial — UnoTV",
        "estado": generaciones.ESTADO_COMPLETADO,
        "metricas": {"tokens_in": 5, "tokens_out": 45, "total_cost_usd": 0.005,
                     "duration_ms": 1000},
    })
    run = _run_por_titulo(cliente, "Run con pool sumado")
    assert run["metricas"]["items"] == 3  # copy + fusión + encaje
    assert run["metricas"]["tokens"] == 150 + 100 + 50
    assert run["metricas"]["coste_usd"] == pytest.approx(0.035)
    assert run["metricas"]["duration_ms"] == 6000
    # El detalle cuadra con la tarjeta (misma suma).
    det = cliente.get(f"/api/pipelines/{tema['id']}").json()["pipeline"]
    assert det["metricas"] == run["metricas"]
    # Un tema del TABLERO trabajado NO hereda el pool de la marca.
    tablero = repos.crear_contenido(
        clase="contenido", titulo="Tablero sin pool", marca="unotv", origen="equipo",
    )
    _gen_suelta("Copy tablero", tipo="pipeline", contenido_id=tablero["id"])
    run_t = _run_por_titulo(cliente, "Tablero sin pool")
    assert run_t["metricas"]["items"] == 1
    assert run_t["metricas"]["tokens"] == 150
