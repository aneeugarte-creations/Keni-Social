"""Tests del endpoint `/api/pipelines` (vista estilo GitLab del pipeline de contenido).

Cada `contenido` con `origen='pipeline'` es una RUN; sus etapas (CI/CD/QA/Aprobación) se
DERIVAN del estado real de la pieza y sus publicaciones por plataforma. Aquí montamos ese
estado a mano (sin daemon ni `claude`) y comprobamos la derivación + el detalle + la
exclusión de lo que NO es del pipeline. Usa la fixture `cliente` (entorno aislado + Postgres).
"""

from __future__ import annotations

from keni_consola import repos
from keni_consola.pipeline_contenido import ORIGEN_PIPELINE


def _tema_pipeline(titulo: str, marca: str = "unotv") -> dict:
    return repos.crear_contenido(
        clase="contenido", titulo=titulo, marca=marca, origen=ORIGEN_PIPELINE
    )


def _run_por_titulo(cliente, titulo: str) -> dict | None:
    r = cliente.get("/api/pipelines")
    assert r.status_code == 200
    return next((x for x in r.json()["pipelines"] if x["titulo"] == titulo), None)


def test_run_con_copy_y_veredicto_listo(cliente):
    """Tema con copy + veredicto 'listo' en borrador: CI/CD/QA ok, aprobación pendiente."""
    tema = _tema_pipeline("Tema listo")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador",
        copy="Copy válido y corto.", veredicto="listo",
    )
    run = _run_por_titulo(cliente, "Tema listo")
    assert run is not None
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas == {"ci": "ok", "cd": "ok", "qa": "ok", "aprobacion": "pendiente"}
    # estado_global = primera no-ok en orden = aprobación (pendiente).
    assert run["estado_global"] == "pendiente"
    assert any(p["red"] == "x" for p in run["piezas"])


def test_run_sin_copy_cd_pendiente(cliente):
    """Tema sin copy todavía: CD y QA pendientes."""
    tema = _tema_pipeline("Tema sin copy")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador", copy="",
    )
    run = _run_por_titulo(cliente, "Tema sin copy")
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas["ci"] == "ok"
    assert etapas["cd"] == "pendiente"
    assert etapas["qa"] == "pendiente"


def test_run_qa_revisar(cliente):
    """Veredicto 'revisar' -> etapa QA en 'revisar'."""
    tema = _tema_pipeline("Tema revisar")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="borrador",
        copy="Copy.", veredicto="revisar",
    )
    run = _run_por_titulo(cliente, "Tema revisar")
    assert {e["clave"]: e["estado"] for e in run["etapas"]}["qa"] == "revisar"


def test_run_aprobado(cliente):
    """Pieza aprobada -> etapa de aprobación ok y, con todo ok, estado_global ok."""
    tema = _tema_pipeline("Tema aprobado")
    repos.crear_contenido_plataforma(
        contenido_id=tema["id"], red="x", estado="aprobado",
        copy="Copy.", veredicto="listo",
    )
    run = _run_por_titulo(cliente, "Tema aprobado")
    etapas = {e["clave"]: e["estado"] for e in run["etapas"]}
    assert etapas["aprobacion"] == "ok"
    assert run["estado_global"] == "ok"


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
    assert [e["clave"] for e in body["pipeline"]["etapas"]] == ["ci", "cd", "qa", "aprobacion"]
    assert "actividad" in body
    # El detalle trae las piezas COMPLETAS: el copy real + observaciones de la validación.
    pieza = body["pipeline"]["piezas"][0]
    assert pieza["copy"] == "Copy."
    assert "observaciones" in pieza
    assert "copy_in" in pieza and "imagen_url" in pieza


def test_detalle_404(cliente):
    assert cliente.get("/api/pipelines/no-existe-xyz").status_code == 404
