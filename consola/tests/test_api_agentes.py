"""Tests de la API Agentes (/api/agentes). OFFLINE.

Un agente = una marca = su carpeta `<KENI_CONSOLA_RAIZ>/<marca>/`. Todo aislado en
tmp (env vars del fixture `entorno`); NUNCA se llama a `claude` real (se parchea
`skills._runner`) ni se lanza Claude Code (el `abrir` inyectado es un mock).
"""

from __future__ import annotations

from pathlib import Path

from keni_consola import agentes, marcas
from keni_consola.api import skills

from .conftest import _cliente

# Una marca real del catalogo para las pruebas.
_MARCA = "unotv"


def _mock_runner(salida: str):
    """Runner que ignora el prompt y devuelve `salida` fija (como en los tests de skills)."""

    def runner(prompt, *, cwd, timeout):  # noqa: ANN001
        return salida

    return runner


# --------------------------------------------------------------------------- #
# GET /api/agentes (listado = marcas)                                         #
# --------------------------------------------------------------------------- #


def test_listar_agentes_son_las_marcas(cliente):
    datos = cliente.get("/api/agentes").json()
    ids = [a["id"] for a in datos["agentes"]]
    assert ids == marcas.ids()
    for a in datos["agentes"]:
        assert set(a) == {"id", "nombre", "ruta", "tiene_claude_md", "n_publicaciones", "n_runs"}


def test_listar_no_materializa_carpetas(entorno):
    """El listado NO debe crear carpetas de agente en disco (resumen con crear=False)."""
    _cliente().get("/api/agentes")
    raiz = entorno / "datos"
    assert not raiz.exists() or not any(raiz.iterdir())


# --------------------------------------------------------------------------- #
# GET /api/agentes/{id} (detalle)                                             #
# --------------------------------------------------------------------------- #


def test_detalle_crea_claude_md_on_demand(entorno):
    datos = _cliente().get(f"/api/agentes/{_MARCA}").json()
    assert datos["id"] == _MARCA
    assert datos["nombre"] == marcas.etiqueta_de(_MARCA)
    assert datos["sub_contextos"] == []
    assert datos["runs"] == []
    # CLAUDE.md se sembro desde la plantilla por tipo (unotv -> noticias).
    assert datos["claude_md"]
    assert "{NOMBRE}" not in datos["claude_md"]
    assert (entorno / "datos" / _MARCA / "CLAUDE.md").is_file()


def test_detalle_marca_inexistente_404(entorno):
    r = _cliente().get("/api/agentes/no-existe-marca")
    assert r.status_code == 404
    assert "error" in r.json()


# --------------------------------------------------------------------------- #
# PUT /api/agentes/{id}/claude-md                                             #
# --------------------------------------------------------------------------- #


def test_guardar_claude_md(entorno):
    nuevo = "# UnoTV\nContexto editado del agente.\n"
    r = _cliente().put(f"/api/agentes/{_MARCA}/claude-md", json={"contenido": nuevo})
    assert r.status_code == 200
    archivo = entorno / "datos" / _MARCA / "CLAUDE.md"
    assert archivo.read_text(encoding="utf-8") == nuevo
    # Y se relee por el detalle.
    assert _cliente().get(f"/api/agentes/{_MARCA}").json()["claude_md"] == nuevo


def test_guardar_claude_md_sin_contenido_400(entorno):
    r = _cliente().put(f"/api/agentes/{_MARCA}/claude-md", json={})
    assert r.status_code == 400


def test_guardar_claude_md_marca_inexistente_404(entorno):
    r = _cliente().put("/api/agentes/no-existe/claude-md", json={"contenido": "x"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Sub-contextos (contexto/*.md)                                               #
# --------------------------------------------------------------------------- #


def test_crear_listar_y_borrar_contexto(entorno):
    c = _cliente()
    r = c.put(f"/api/agentes/{_MARCA}/contextos/guia", json={"contenido": "# Guía\nApuntes.\n"})
    assert r.status_code == 200
    # El fichero vive en contexto/ con extension .md.
    archivo = entorno / "datos" / _MARCA / "contexto" / "guia.md"
    assert archivo.is_file()

    listado = c.get(f"/api/agentes/{_MARCA}/contextos").json()["sub_contextos"]
    assert listado == [{"nombre": "guia.md", "contenido": "# Guía\nApuntes.\n"}]

    # El detalle expone nombre + contenido (la UI edita desde el detalle).
    sub = c.get(f"/api/agentes/{_MARCA}").json()["sub_contextos"]
    assert sub == [{"nombre": "guia.md", "contenido": "# Guía\nApuntes.\n"}]

    r_del = c.delete(f"/api/agentes/{_MARCA}/contextos/guia.md")
    assert r_del.status_code == 200
    assert not archivo.exists()


def test_borrar_contexto_inexistente_404(entorno):
    r = _cliente().delete(f"/api/agentes/{_MARCA}/contextos/no-hay")
    assert r.status_code == 404


def test_contexto_rechaza_nombre_peligroso(entorno):
    """Un nombre con caracteres peligrosos (no separadores de ruta, que el cliente
    HTTP normaliza) es rechazado por el saneo del dominio con 400."""
    c = _cliente()
    # `:` y `*` no son separadores de ruta pero NO son nombres de contexto validos.
    for malo in ("a:b", "a*b", "a|b"):
        r = c.put(f"/api/agentes/{_MARCA}/contextos/{malo}", json={"contenido": "x"})
        assert r.status_code == 400, malo
    # Nada se escribio en contexto/.
    carpeta = entorno / "datos" / _MARCA / "contexto"
    assert not carpeta.exists() or not any(carpeta.iterdir())


def test_contexto_no_md_se_normaliza_a_md(entorno):
    """Un nombre sin extension se guarda como `<nombre>.md` (solo *.md)."""
    c = _cliente()
    r = c.put(f"/api/agentes/{_MARCA}/contextos/notas", json={"contenido": "hola"})
    assert r.status_code == 200
    assert (entorno / "datos" / _MARCA / "contexto" / "notas.md").is_file()


def test_contexto_marca_inexistente_404(entorno):
    r = _cliente().get("/api/agentes/no-existe/contextos")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Runs headless (mock runner, NUNCA claude real)                              #
# --------------------------------------------------------------------------- #


def test_run_headless_completado(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner("salida del asistente"))
    r = _cliente().post(
        f"/api/agentes/{_MARCA}/runs", json={"prompt": "haz algo", "modo": "headless"}
    )
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["modo"] == "headless"
    assert run["estado"] == "completado"
    assert run["salida"] == "salida del asistente"
    assert run["prompt"] == "haz algo"
    assert run["fecha_inicio"] and run["fecha_fin"]
    # Persistido como runs/<id>.yaml.
    assert (entorno / "datos" / _MARCA / "runs" / f"{run['id']}.yaml").is_file()


def test_run_headless_corre_en_la_carpeta_del_agente(entorno, monkeypatch):
    """El cwd del runner debe ser la carpeta del agente."""
    capturado = {}

    def runner(prompt, *, cwd, timeout):  # noqa: ANN001
        capturado["cwd"] = Path(cwd)
        capturado["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(skills, "_runner", runner)
    _cliente().post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p", "modo": "headless"})
    assert capturado["cwd"] == (entorno / "datos" / _MARCA).resolve()
    assert capturado["prompt"] == "p"


def test_run_headless_error_se_guarda_como_error(entorno, monkeypatch):
    def runner(prompt, *, cwd, timeout):  # noqa: ANN001
        raise skills.SkillError("El asistente terminó con error: detalle")

    monkeypatch.setattr(skills, "_runner", runner)
    r = _cliente().post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"})
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["estado"] == "error"
    assert "error" in run["salida"].lower()


def test_run_modo_por_defecto_es_headless(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner("x"))
    r = _cliente().post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"})
    assert r.json()["run"]["modo"] == "headless"


def test_run_sin_prompt_400(entorno):
    r = _cliente().post(f"/api/agentes/{_MARCA}/runs", json={"modo": "headless"})
    assert r.status_code == 400


def test_run_modo_invalido_400(entorno):
    r = _cliente().post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p", "modo": "raro"})
    assert r.status_code == 400


def test_run_marca_inexistente_404(entorno):
    r = _cliente().post("/api/agentes/no-existe/runs", json={"prompt": "p"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Run interactivo (mock del lanzador, NUNCA abre Terminal real)               #
# --------------------------------------------------------------------------- #


def test_run_interactivo_usa_el_lanzador(entorno):
    llamadas: list[Path] = []

    def abrir_mock(ruta):
        llamadas.append(ruta)
        return "Claude Code abriendose (mock)."

    c = _cliente(abrir=abrir_mock)
    r = c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "hola", "modo": "interactivo"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert "mock" in cuerpo["mensaje"]
    assert cuerpo["run"]["modo"] == "interactivo"
    assert cuerpo["run"]["estado"] == "lanzado"
    assert llamadas == [(entorno / "datos" / _MARCA).resolve()]
    # Persistido.
    assert (entorno / "datos" / _MARCA / "runs" / f"{cuerpo['run']['id']}.yaml").is_file()


# --------------------------------------------------------------------------- #
# Listar / obtener runs                                                       #
# --------------------------------------------------------------------------- #


def test_listar_runs(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner("ok"))
    c = _cliente()
    c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "uno"})
    c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "dos"})
    runs = c.get(f"/api/agentes/{_MARCA}/runs").json()["runs"]
    assert len(runs) == 2
    prompts = {r["prompt"] for r in runs}
    assert prompts == {"uno", "dos"}


def test_obtener_run_completo(entorno, monkeypatch):
    monkeypatch.setattr(skills, "_runner", _mock_runner("contenido completo"))
    c = _cliente()
    run_id = c.post(f"/api/agentes/{_MARCA}/runs", json={"prompt": "p"}).json()["run"]["id"]
    r = c.get(f"/api/agentes/{_MARCA}/runs/{run_id}")
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["id"] == run_id
    assert run["salida"] == "contenido completo"
    assert set(run) == {"id", "prompt", "modo", "estado", "salida", "fecha_inicio", "fecha_fin"}


def test_obtener_run_inexistente_404(entorno):
    r = _cliente().get(f"/api/agentes/{_MARCA}/runs/noexiste")
    assert r.status_code == 404


def test_obtener_run_marca_inexistente_404(entorno):
    r = _cliente().get("/api/agentes/no-existe/runs/algo")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Dominio: defensa de escritura (sin pasar por la API)                        #
# --------------------------------------------------------------------------- #


def test_dominio_carpeta_agente_rechaza_marca_invalida(entorno):
    import pytest

    with pytest.raises(agentes.AgenteInvalido):
        agentes.carpeta_agente("no-existe")


def test_dominio_contexto_rechaza_nombre_con_separador(entorno):
    import pytest

    with pytest.raises(agentes.NombreContextoInvalido):
        agentes.guardar_contexto(_MARCA, "a/b", "x")
    with pytest.raises(agentes.NombreContextoInvalido):
        agentes.guardar_contexto(_MARCA, "../x", "x")
