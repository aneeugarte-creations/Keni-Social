"""Tests del versionado de esquema de los YAML (#125): `migrar` / `sellar`.

Cubre el contrato del registro: `sellar` estampa la version actual; `migrar` sube
de version (ausencia => 0 => 1 identidad), es idempotente, no muta la entrada y
falla ruidosamente ante un tipo desconocido.
"""

from __future__ import annotations

import pytest

from keni_shared import esquema_yaml
from keni_shared.esquema_yaml import VERSIONES, migrar, sellar


def test_sellar_estampa_version_actual():
    sellado = sellar("publicacion", {"titulo": "Hola"})
    assert sellado["version"] == VERSIONES["publicacion"] == 1
    assert sellado["titulo"] == "Hola"


def test_sellar_no_muta_la_entrada():
    original = {"titulo": "Hola"}
    sellar("publicacion", original)
    assert "version" not in original  # copia, no mutacion


def test_sellar_pone_version_primero():
    sellado = sellar("plantilla", {"nombre": "X", "red": "x"})
    # `version` como PRIMERA clave (orden de insercion = orden de diff).
    assert list(sellado)[0] == "version"


def test_sellar_reemplaza_version_existente_sin_duplicar():
    sellado = sellar("run", {"version": 99, "estado": "ejecutando"})
    assert sellado["version"] == VERSIONES["run"]
    # No queda duplicada ni desplazada: sigue siendo la primera y unica.
    assert list(sellado).count("version") == 1
    assert list(sellado)[0] == "version"


def test_migrar_estampa_version_cuando_falta():
    # Un YAML legado SIN version se trata como version 0 -> sube a 1 (identidad).
    migrado = migrar("marca", {"id": "unotv", "etiqueta": "UnoTV"})
    assert migrado["version"] == 1
    assert migrado["id"] == "unotv"
    assert migrado["etiqueta"] == "UnoTV"


def test_migrar_version_no_entera_se_trata_como_cero():
    migrado = migrar("prompt", {"version": "no-es-int", "nombre": "X"})
    assert migrado["version"] == VERSIONES["prompt"]


def test_migrar_version_bool_no_cuenta_como_int():
    # True es un int en Python; aqui NO debe contar como una version valida.
    migrado = migrar("prompt", {"version": True, "nombre": "X"})
    assert migrado["version"] == VERSIONES["prompt"]


def test_migrar_es_idempotente():
    una_vez = migrar("fuente_rss", {"url": "https://x/feed"})
    dos_veces = migrar("fuente_rss", una_vez)
    assert una_vez == dos_veces
    assert dos_veces["version"] == 1


def test_migrar_no_muta_la_entrada():
    original = {"url": "https://x/feed"}
    migrar("fuente_rss", original)
    assert "version" not in original


def test_migrar_aplica_migraciones_registradas_en_orden(monkeypatch):
    # Registro temporal: tipo "publicacion" sube a v3 con dos migraciones encadenadas.
    pasos: list[int] = []

    def m_1_a_2(datos: dict) -> dict:
        pasos.append(1)
        return {**datos, "a": 1}

    def m_2_a_3(datos: dict) -> dict:
        pasos.append(2)
        return {**datos, "b": 2}

    monkeypatch.setitem(esquema_yaml.VERSIONES, "publicacion", 3)
    monkeypatch.setitem(esquema_yaml.MIGRACIONES, "publicacion", [m_1_a_2, m_2_a_3])

    # Sin version (=0): 0->1 identidad, 1->2 (m_1_a_2), 2->3 (m_2_a_3).
    migrado = migrar("publicacion", {"titulo": "T"})
    assert pasos == [1, 2]
    assert migrado == {"titulo": "T", "a": 1, "b": 2, "version": 3}

    # Partiendo de v2 solo corre el ultimo paso.
    pasos.clear()
    migrado2 = migrar("publicacion", {"titulo": "T", "version": 2})
    assert pasos == [2]
    assert migrado2["version"] == 3


def test_migrar_tipo_desconocido_lanza():
    with pytest.raises(KeyError):
        migrar("inexistente", {"x": 1})


def test_sellar_tipo_desconocido_lanza():
    with pytest.raises(KeyError):
        sellar("inexistente", {"x": 1})


def test_todos_los_tipos_en_v1():
    # Hoy toda entidad esta en la version 1 (la forma actual) y sin migraciones.
    assert all(v == 1 for v in VERSIONES.values())
    assert all(esquema_yaml.MIGRACIONES[t] == [] for t in VERSIONES)
    esperados = {
        "publicacion", "plantilla", "fuente_rss", "grupo_hashtags",
        "historial_prompt", "marca", "franjas", "rss_vistos", "run",
        "agente", "generacion", "prompt",
    }
    assert set(VERSIONES) == esperados
