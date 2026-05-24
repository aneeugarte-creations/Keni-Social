"""Tests de la API Proyectos (/api/proyectos). OFFLINE, allowlist en tmp.

`abrir` se mockea: NUNCA se lanza Claude Code real.
"""

from __future__ import annotations

from pathlib import Path

from keni_consola import proyectos

from .conftest import _cliente


def _config_con_proyecto(tmp_path: Path) -> Path:
    """Crea una carpeta de proyecto permitida + su CLAUDE.md y la registra."""
    carpeta = tmp_path / "proyecto-a"
    carpeta.mkdir()
    (carpeta / "CLAUDE.md").write_text("# Proyecto A\nContenido original.\n", encoding="utf-8")
    (tmp_path / "consola.toml").write_text(
        f'[[proyecto]]\nnombre = "Proyecto A"\nruta = "{carpeta}"\n', encoding="utf-8"
    )
    return carpeta


# --------------------------------------------------------------------------- #
# GET /api/proyectos                                                          #
# --------------------------------------------------------------------------- #


def test_listar_vacio(cliente):
    datos = cliente.get("/api/proyectos").json()
    assert datos == {"proyectos": []}


def test_listar_proyecto_con_claude_md(entorno):
    _config_con_proyecto(entorno)
    c = _cliente()
    datos = c.get("/api/proyectos").json()
    assert len(datos["proyectos"]) == 1
    p = datos["proyectos"][0]
    assert set(p) == {"id", "nombre", "ruta", "existe", "tiene_claude_md", "claude_md"}
    assert p["nombre"] == "Proyecto A"
    assert p["existe"] is True
    assert p["tiene_claude_md"] is True
    assert "Contenido original." in p["claude_md"]


def test_listar_proyecto_sin_carpeta(entorno):
    (entorno / "consola.toml").write_text(
        f'[[proyecto]]\nnombre = "Fantasma"\nruta = "{entorno / "no-existe"}"\n', encoding="utf-8"
    )
    p = _cliente().get("/api/proyectos").json()["proyectos"][0]
    assert p["existe"] is False
    assert p["claude_md"] is None


# --------------------------------------------------------------------------- #
# POST /api/proyectos (anadir)                                                #
# --------------------------------------------------------------------------- #


def test_anadir_carpeta_valida(entorno, tmp_path):
    nueva = entorno / "proyecto-b"
    nueva.mkdir()
    r = _cliente().post("/api/proyectos", json={"nombre": "Proyecto B", "ruta": str(nueva)})
    assert r.status_code == 200
    proys = proyectos.cargar_proyectos()
    assert any(p.nombre == "Proyecto B" and p.ruta == nueva.resolve() for p in proys)


def test_anadir_carpeta_inexistente_400(entorno):
    r = _cliente().post(
        "/api/proyectos", json={"nombre": "X", "ruta": str(entorno / "no-existe")}
    )
    assert r.status_code == 400
    assert "no existe" in r.json()["error"].lower()


def test_anadir_ruta_que_es_archivo_400(entorno):
    archivo = entorno / "soy-archivo.txt"
    archivo.write_text("x", encoding="utf-8")
    r = _cliente().post("/api/proyectos", json={"nombre": "X", "ruta": str(archivo)})
    assert r.status_code == 400
    assert "carpeta" in r.json()["error"].lower()


def test_anadir_faltan_campos_400(entorno):
    r = _cliente().post("/api/proyectos", json={"nombre": "X"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# PUT /api/proyectos/{id}/claude-md                                           #
# --------------------------------------------------------------------------- #


def test_guardar_claude_md_en_carpeta_permitida(entorno):
    carpeta = _config_con_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    nuevo = "# Proyecto A\nContenido NUEVO editado.\n"
    r = _cliente().put(f"/api/proyectos/{pid}/claude-md", json={"contenido": nuevo})
    assert r.status_code == 200
    assert (carpeta / "CLAUDE.md").read_text(encoding="utf-8") == nuevo


def test_guardar_claude_md_id_fuera_de_allowlist_400(entorno):
    _config_con_proyecto(entorno)
    r = _cliente().put("/api/proyectos/idfalso000/claude-md", json={"contenido": "x"})
    assert r.status_code == 400
    assert "error" in r.json()


def test_guardar_claude_md_sin_contenido_400(entorno):
    _config_con_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    r = _cliente().put(f"/api/proyectos/{pid}/claude-md", json={})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# POST /api/proyectos/{id}/abrir (mock, sin lanzar nada)                       #
# --------------------------------------------------------------------------- #


def test_abrir_llama_a_la_funcion_con_la_ruta_correcta(entorno):
    carpeta = _config_con_proyecto(entorno)
    pid = proyectos.cargar_proyectos()[0].id
    llamadas: list[Path] = []

    def abrir_mock(ruta):
        llamadas.append(ruta)
        return "Claude Code abriendose (mock)."

    c = _cliente(abrir=abrir_mock)
    r = c.post(f"/api/proyectos/{pid}/abrir")
    assert r.status_code == 200
    assert llamadas == [carpeta.resolve()]
    assert "mock" in r.json()["mensaje"]


def test_abrir_id_fuera_de_allowlist_400_sin_lanzar(entorno):
    _config_con_proyecto(entorno)
    llamadas = []
    c = _cliente(abrir=lambda r: llamadas.append(r))
    r = c.post("/api/proyectos/noexiste0000/abrir")
    assert r.status_code == 400
    assert llamadas == []
