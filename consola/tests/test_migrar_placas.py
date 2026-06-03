"""Migración placa de marca -> plantilla del estudio: idempotencia y conversión vía `desde_spec`."""

from __future__ import annotations

import json

from keni_consola import migrar_placas
from keni_consola.motores.estudio_imagen import documento as doc_capas


def test_idempotente_no_duplica(monkeypatch):
    # La marca ya tiene su "Placa de marca": no se vuelve a crear.
    monkeypatch.setattr(
        migrar_placas.repos, "listar_plantillas_diseno",
        lambda *, marca=None, **k: [{"nombre": "Placa de marca"}],
    )
    creadas: list = []
    monkeypatch.setattr(
        migrar_placas.repos, "crear_plantilla_diseno",
        lambda **k: creadas.append(k),
    )
    assert migrar_placas.migrar_una("claro-sports") == "ya-existe"
    assert creadas == []


def test_crea_con_hueco_de_foto(monkeypatch):
    monkeypatch.setattr(
        migrar_placas.repos, "listar_plantillas_diseno", lambda *, marca=None, **k: []
    )
    # Un documento mínimo con hueco de foto (lo que devolvería `desde_spec`).
    doc = {
        "version": 1,
        "formato": {"w": 1080, "h": 1350},
        "capas": [{"tipo": "imagen", "z": 0, "objeto": "", "w": 1080, "h": 1350, "es_foto": True}],
    }
    monkeypatch.setattr(migrar_placas.plantillas_marca, "obtener_spec", lambda m: {"marca": m})
    monkeypatch.setattr(migrar_placas.doc_capas, "desde_spec", lambda spec, fmt: doc)
    monkeypatch.setattr(
        migrar_placas.estudio_imagen, "renderizar_documento",
        lambda d, bindings=None: {"id": "mini.png", "url": "/x"},
    )
    creadas: list = []
    monkeypatch.setattr(
        migrar_placas.repos, "crear_plantilla_diseno", lambda **k: creadas.append(k)
    )

    assert migrar_placas.migrar_una("claro-sports") == "creada"
    assert len(creadas) == 1
    kw = creadas[0]
    assert kw["marca"] == "claro-sports"
    assert kw["nombre"] == "Placa de marca"
    assert kw["miniatura"] == "mini.png"
    # El documento persistido conserva el hueco de foto (es_foto) que resuelve `capa_foto`.
    doc_persistido = json.loads(kw["documento"])
    assert doc_capas.capa_foto(doc_persistido) is not None


def test_sin_node_crea_sin_miniatura(monkeypatch):
    monkeypatch.setattr(
        migrar_placas.repos, "listar_plantillas_diseno", lambda *, marca=None, **k: []
    )
    monkeypatch.setattr(migrar_placas.plantillas_marca, "obtener_spec", lambda m: {"marca": m})
    monkeypatch.setattr(
        migrar_placas.doc_capas, "desde_spec",
        lambda spec, fmt: {"formato": {"w": 1080, "h": 1350}, "capas": []},
    )

    def _revienta(d, bindings=None):
        raise RuntimeError("node ausente")

    monkeypatch.setattr(migrar_placas.estudio_imagen, "renderizar_documento", _revienta)
    creadas: list = []
    monkeypatch.setattr(
        migrar_placas.repos, "crear_plantilla_diseno", lambda **k: creadas.append(k)
    )
    assert migrar_placas.migrar_una("unotv") == "creada-sin-miniatura"
    assert creadas[0]["miniatura"] == ""
