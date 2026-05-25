"""Tests del conjunto ABIERTO de agentes: crear/renombrar/borrar/conectar genericos.

Las 5 MARCAS vienen de serie (`es_marca=True`; no se borran ni se renombran) y, ademas,
se pueden CREAR/CONECTAR/RENOMBRAR/BORRAR agentes GENERICOS (carpeta + manifiesto
`.keni/agente.yaml` + CLAUDE.md + runs; `es_marca=False`). Todo aislado en tmp
(fixture `entorno`); NUNCA se llama a `claude` real.
"""

from __future__ import annotations

import pytest

from keni_consola import agentes, marcas

from .conftest import _cliente

_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# Listado: marcas primero, luego genericos; cada uno con `es_marca`            #
# --------------------------------------------------------------------------- #


def test_listar_marcas_primero_luego_genericos(entorno):
    c = _cliente()
    c.post("/api/agentes", json={"nombre": "Mi Agente"})
    agentes_lista = c.get("/api/agentes").json()["agentes"]
    ids = [a["id"] for a in agentes_lista]
    # Las marcas conservan su orden de catalogo al inicio.
    assert ids[: len(marcas.ids())] == marcas.ids()
    # El generico va despues, con es_marca=False.
    assert ids[-1] == "mi-agente"
    generico = agentes_lista[-1]
    assert generico["es_marca"] is False
    assert generico["nombre"] == "Mi Agente"
    assert generico["n_publicaciones"] == 0
    for a in agentes_lista[: len(marcas.ids())]:
        assert a["es_marca"] is True


# --------------------------------------------------------------------------- #
# POST /api/agentes (crear generico)                                          #
# --------------------------------------------------------------------------- #


def test_crear_generico_crea_carpeta_manifiesto_y_claude_md(entorno):
    c = _cliente()
    r = c.post("/api/agentes", json={"nombre": "Náutica Pro", "tipo": "general"})
    assert r.status_code == 200
    agente = r.json()["agente"]
    # El slug normaliza acentos y minusculas.
    assert agente["id"] == "nautica-pro"
    assert agente["es_marca"] is False
    assert agente["nombre"] == "Náutica Pro"
    base = entorno / "datos" / "nautica-pro"
    assert (base / "CLAUDE.md").is_file()
    assert (base / ".keni" / "agente.yaml").is_file()
    # El CLAUDE.md se renderizo con el nombre (sin marcador sin sustituir).
    texto = (base / "CLAUDE.md").read_text(encoding="utf-8")
    assert "{NOMBRE}" not in texto


def test_crear_generico_tipo_por_defecto_general(entorno):
    c = _cliente()
    r = c.post("/api/agentes", json={"nombre": "Solo Nombre"})
    assert r.status_code == 200
    manifiesto = agentes._leer_manifiesto("solo-nombre")
    assert manifiesto["tipo"] == "general"
    assert manifiesto["nombre"] == "Solo Nombre"
    assert manifiesto["creado"]


def test_crear_generico_tipo_desconocido_cae_a_general(entorno):
    c = _cliente()
    c.post("/api/agentes", json={"nombre": "Con Tipo Raro", "tipo": "no-existe"})
    assert agentes._leer_manifiesto("con-tipo-raro")["tipo"] == "general"


def test_crear_sin_nombre_400(entorno):
    r = _cliente().post("/api/agentes", json={})
    assert r.status_code == 400


def test_crear_nombre_vacio_400(entorno):
    r = _cliente().post("/api/agentes", json={"nombre": "   "})
    assert r.status_code == 400


def test_crear_nombre_sin_caracteres_utiles_400(entorno):
    r = _cliente().post("/api/agentes", json={"nombre": "!!!"})
    assert r.status_code == 400


def test_crear_colision_con_marca_400(entorno):
    """Un nombre cuyo slug coincide con una marca de serie se rechaza con 400."""
    c = _cliente()
    r = c.post("/api/agentes", json={"nombre": "unotv"})
    assert r.status_code == 400
    assert "marca" in r.json()["error"].lower()


def test_crear_colision_con_generico_existente_400(entorno):
    c = _cliente()
    assert c.post("/api/agentes", json={"nombre": "Repetido"}).status_code == 200
    r = c.post("/api/agentes", json={"nombre": "Repetido"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# POST /api/agentes/conectar (registrar carpeta existente)                    #
# --------------------------------------------------------------------------- #


def test_conectar_carpeta_existente(entorno):
    # Creamos una subcarpeta a mano (como si ya viviera ahi un proyecto).
    base = entorno / "datos" / "carpeta-suelta"
    base.mkdir(parents=True)
    c = _cliente()
    r = c.post("/api/agentes/conectar", json={"carpeta": "carpeta-suelta"})
    assert r.status_code == 200
    agente = r.json()["agente"]
    assert agente["id"] == "carpeta-suelta"
    assert agente["es_marca"] is False
    # Escribio el manifiesto y un CLAUDE.md minimo.
    assert (base / ".keni" / "agente.yaml").is_file()
    assert (base / "CLAUDE.md").is_file()
    # Y ahora aparece en el listado.
    ids = [a["id"] for a in c.get("/api/agentes").json()["agentes"]]
    assert "carpeta-suelta" in ids


def test_conectar_respeta_claude_md_existente(entorno):
    base = entorno / "datos" / "con-claude"
    base.mkdir(parents=True)
    (base / "CLAUDE.md").write_text("# Ya tenia contexto\n", encoding="utf-8")
    c = _cliente()
    c.post("/api/agentes/conectar", json={"carpeta": "con-claude"})
    assert (base / "CLAUDE.md").read_text(encoding="utf-8") == "# Ya tenia contexto\n"


def test_conectar_inexistente_400(entorno):
    r = _cliente().post("/api/agentes/conectar", json={"carpeta": "no-existe"})
    assert r.status_code == 400


def test_conectar_marca_400(entorno):
    r = _cliente().post("/api/agentes/conectar", json={"carpeta": "unotv"})
    assert r.status_code == 400


def test_conectar_ya_conectado_400(entorno):
    base = entorno / "datos" / "doble"
    base.mkdir(parents=True)
    c = _cliente()
    assert c.post("/api/agentes/conectar", json={"carpeta": "doble"}).status_code == 200
    r = c.post("/api/agentes/conectar", json={"carpeta": "doble"})
    assert r.status_code == 400


@pytest.mark.parametrize("malo", ["../fuera", "a/b", "..", ".", "/abs"])
def test_conectar_traversal_400(entorno, malo):
    r = _cliente().post("/api/agentes/conectar", json={"carpeta": malo})
    assert r.status_code == 400


def test_conectar_sin_carpeta_400(entorno):
    r = _cliente().post("/api/agentes/conectar", json={})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# PATCH /api/agentes/{id} (renombrar display de un generico)                  #
# --------------------------------------------------------------------------- #


def test_renombrar_generico_cambia_display_no_slug(entorno):
    c = _cliente()
    c.post("/api/agentes", json={"nombre": "Viejo Nombre"})
    r = c.patch("/api/agentes/viejo-nombre", json={"nombre": "Nombre Nuevo"})
    assert r.status_code == 200
    agente = r.json()["agente"]
    # El slug/id NO cambia; solo el display.
    assert agente["id"] == "viejo-nombre"
    assert agente["nombre"] == "Nombre Nuevo"
    # La carpeta sigue siendo la misma (no se rompen referencias).
    assert (entorno / "datos" / "viejo-nombre").is_dir()
    assert agentes._leer_manifiesto("viejo-nombre")["nombre"] == "Nombre Nuevo"


def test_renombrar_marca_400(entorno):
    r = _cliente().patch(f"/api/agentes/{_MARCA}", json={"nombre": "Otra Cosa"})
    assert r.status_code == 400
    assert "marca" in r.json()["error"].lower()


def test_renombrar_inexistente_400(entorno):
    r = _cliente().patch("/api/agentes/no-existe", json={"nombre": "X"})
    assert r.status_code == 400


def test_renombrar_nombre_vacio_400(entorno):
    c = _cliente()
    c.post("/api/agentes", json={"nombre": "Tiene Nombre"})
    r = c.patch("/api/agentes/tiene-nombre", json={"nombre": "   "})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# DELETE /api/agentes/{id} (borrar generico)                                  #
# --------------------------------------------------------------------------- #


def test_borrar_generico(entorno):
    c = _cliente()
    c.post("/api/agentes", json={"nombre": "Borrame"})
    base = entorno / "datos" / "borrame"
    assert base.is_dir()
    r = c.delete("/api/agentes/borrame")
    assert r.status_code == 200
    assert not base.exists()
    ids = [a["id"] for a in c.get("/api/agentes").json()["agentes"]]
    assert "borrame" not in ids


def test_borrar_marca_400(entorno):
    r = _cliente().delete(f"/api/agentes/{_MARCA}")
    assert r.status_code == 400
    assert "marca" in r.json()["error"].lower()
    # La carpeta de la marca no se toca (no se crea ni se borra nada).
    assert not (entorno / "datos" / _MARCA).exists()


def test_borrar_inexistente_404(entorno):
    r = _cliente().delete("/api/agentes/no-existe")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# CLAUDE.md / contextos / runs FUNCIONAN sobre un agente generico             #
# --------------------------------------------------------------------------- #


def test_detalle_de_generico(entorno):
    c = _cliente()
    c.post("/api/agentes", json={"nombre": "Para Detalle"})
    datos = c.get("/api/agentes/para-detalle").json()
    assert datos["id"] == "para-detalle"
    assert datos["es_marca"] is False
    assert datos["nombre"] == "Para Detalle"
    assert datos["claude_md"]  # sembrado al crear


def test_claude_md_de_generico(entorno):
    c = _cliente()
    c.post("/api/agentes", json={"nombre": "Edita Claude"})
    nuevo = "# Edita Claude\nContexto propio.\n"
    r = c.put("/api/agentes/edita-claude/claude-md", json={"contenido": nuevo})
    assert r.status_code == 200
    archivo = entorno / "datos" / "edita-claude" / "CLAUDE.md"
    assert archivo.read_text(encoding="utf-8") == nuevo


def test_contextos_de_generico(entorno):
    c = _cliente()
    c.post("/api/agentes", json={"nombre": "Con Contexto"})
    r = c.put("/api/agentes/con-contexto/contextos/notas", json={"contenido": "apuntes"})
    assert r.status_code == 200
    assert (entorno / "datos" / "con-contexto" / "contexto" / "notas.md").is_file()
    listado = c.get("/api/agentes/con-contexto/contextos").json()["sub_contextos"]
    assert listado == [{"nombre": "notas.md", "contenido": "apuntes"}]


def test_runs_de_generico(entorno):
    def lanzar(marca_id, run_id, prompt, *, cwd):  # noqa: ANN001
        agentes.actualizar_run(
            marca_id, run_id,
            {"estado": "completado", "salida": "hecho", "fecha_fin": agentes.ahora_iso()},
        )

    c = _cliente(lanzar_run=lanzar)
    c.post("/api/agentes", json={"nombre": "Con Run"})
    r = c.post("/api/agentes/con-run/runs", json={"prompt": "haz algo"})
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["estado"] == "completado"
    assert (entorno / "datos" / "con-run" / "runs" / f"{run['id']}.yaml").is_file()
    # Y aparece en los runs globales con su agente.
    globales = c.get("/api/runs").json()["runs"]
    assert any(g["agente"] == "con-run" for g in globales)


# --------------------------------------------------------------------------- #
# Dominio: distincion marca vs generico y seguridad                           #
# --------------------------------------------------------------------------- #


def test_dominio_es_agente_resuelve_marca_y_generico(entorno):
    agentes.crear_agente("Generico Dom")
    assert agentes.es_agente(_MARCA) is True
    assert agentes.es_agente("generico-dom") is True
    assert agentes.es_generico("generico-dom") is True
    assert agentes.es_generico(_MARCA) is False
    assert agentes.es_agente("nada") is False


def test_dominio_borrar_marca_no_permitido(entorno):
    with pytest.raises(agentes.OperacionNoPermitida):
        agentes.borrar_agente(_MARCA)


def test_dominio_borrar_inexistente_invalido(entorno):
    with pytest.raises(agentes.AgenteInvalido):
        agentes.borrar_agente("no-existe")


def test_dominio_carpeta_agente_resuelve_generico(entorno):
    agentes.crear_agente("Carpeta Dom")
    carpeta = agentes.carpeta_agente("carpeta-dom", crear=False)
    assert carpeta == (entorno / "datos" / "carpeta-dom").resolve()
