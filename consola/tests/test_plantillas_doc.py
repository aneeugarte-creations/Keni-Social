"""Tests del store de PLANTILLAS como documentos (files-as-truth) — Fase 4.

PUROS (sin Postgres): aíslan `KENI_BIBLIOTECA_DIR` en un tmp. Cubren el CRUD con la MISMA
forma de dict que `repos.*_plantilla_contenido` (para que la API no note el cambio de store),
el filtrado del listado y la migración idempotente desde Postgres (con un repos falso).
"""

from __future__ import annotations

import json

import pytest

from keni_consola import plantillas_doc


@pytest.fixture(autouse=True)
def _biblioteca_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_BIBLIOTECA_DIR", str(tmp_path / "biblioteca"))
    monkeypatch.setenv("KENI_BIBLIOTECA_GIT", "0")
    return tmp_path


def test_crear_estructura_forma_repos():
    p = plantillas_doc.crear_plantilla_contenido(
        nombre="Gol", modo="estructura", estructura="¡GOL de {{equipo}}!",
        variables=json.dumps([{"clave": "equipo", "etiqueta": "Equipo", "ejemplo": "Águilas"}]),
        marca="unotv",
    )
    assert p["id"] == "gol"
    assert p["modo"] == "estructura"
    assert p["estructura"] == "¡GOL de {{equipo}}!"
    assert p["contenido"] == ""
    # variables es un STRING JSON (como devolvía la BD).
    assert json.loads(p["variables"])[0]["clave"] == "equipo"
    leido = plantillas_doc.obtener_plantilla_contenido("gol")
    assert leido is not None and leido["marca"] == "unotv"


def test_crear_plano_y_round_trip():
    p = plantillas_doc.crear_plantilla_contenido(
        nombre="Despedida", modo="plano", contenido="¡Gracias!",
    )
    assert p["modo"] == "plano"
    assert p["contenido"] == "¡Gracias!"
    assert p["estructura"] == ""
    assert plantillas_doc.obtener_plantilla_contenido(p["id"])["contenido"] == "¡Gracias!"


def test_id_unico_en_colision():
    a = plantillas_doc.crear_plantilla_contenido(nombre="Nota", modo="plano", contenido="x")
    b = plantillas_doc.crear_plantilla_contenido(nombre="Nota", modo="plano", contenido="y")
    assert a["id"] == "nota"
    assert b["id"] == "nota-2"


def test_listar_filtra_y_ordena():
    plantillas_doc.crear_plantilla_contenido(nombre="A", modo="plano", contenido="x", marca="unotv", creado="2026-01-01T00:00:00+00:00")
    plantillas_doc.crear_plantilla_contenido(nombre="B", modo="plano", contenido="y", marca="claro-sports", creado="2026-02-01T00:00:00+00:00", activo=False)
    todas = plantillas_doc.listar_plantillas_contenido()
    assert [p["id"] for p in todas] == ["b", "a"]  # recientes primero
    assert {p["id"] for p in plantillas_doc.listar_plantillas_contenido(marca="unotv")} == {"a"}
    assert {p["id"] for p in plantillas_doc.listar_plantillas_contenido(solo_activas=True)} == {"a"}


def test_actualizar_parcial():
    p = plantillas_doc.crear_plantilla_contenido(nombre="Edit", modo="estructura", estructura="hola {{x}}")
    out = plantillas_doc.actualizar_plantilla_contenido(p["id"], {"estructura": "adiós {{y}}", "activo": False})
    assert out["estructura"] == "adiós {{y}}"
    assert out["activo"] is False
    assert plantillas_doc.obtener_plantilla_contenido(p["id"])["estructura"] == "adiós {{y}}"


def test_borrar():
    p = plantillas_doc.crear_plantilla_contenido(nombre="Tmp", modo="plano", contenido="x")
    assert plantillas_doc.borrar_plantilla_contenido(p["id"]) is True
    assert plantillas_doc.obtener_plantilla_contenido(p["id"]) is None
    assert plantillas_doc.borrar_plantilla_contenido(p["id"]) is False


def test_id_invalido_no_revienta():
    assert plantillas_doc.obtener_plantilla_contenido("../escape") is None
    assert plantillas_doc.obtener_plantilla_contenido("a/b") is None


def test_importar_de_postgres_idempotente(monkeypatch):
    filas = [
        {"id": "42", "nombre": "Desde BD", "modo": "estructura", "estructura": "{{x}}",
         "contenido": "", "variables": "[]", "marca": "unotv", "red": "", "tipo_nota": "gol",
         "descripcion": "d", "activo": True, "autor_id": "u1", "autor_nombre": "Ana",
         "creado": "2026-01-01T00:00:00+00:00", "actualizado": "2026-01-01T00:00:00+00:00"},
    ]
    from keni_consola import repos
    monkeypatch.setattr(repos, "listar_plantillas_contenido", lambda *a, **k: filas)

    assert plantillas_doc.importar_de_postgres() == 1
    docs = plantillas_doc.listar_plantillas_contenido()
    assert len(docs) == 1
    assert docs[0]["nombre"] == "Desde BD"
    assert docs[0]["origen_pg"] == "42"
    # Segunda corrida: NO reimporta (idempotente).
    assert plantillas_doc.importar_de_postgres() == 0
    assert len(plantillas_doc.listar_plantillas_contenido()) == 1


def test_importar_sin_bd_no_revienta(monkeypatch):
    from keni_consola import repos
    def _boom(*a, **k):
        raise RuntimeError("sin postgres")
    monkeypatch.setattr(repos, "listar_plantillas_contenido", _boom)
    assert plantillas_doc.importar_de_postgres() == 0
