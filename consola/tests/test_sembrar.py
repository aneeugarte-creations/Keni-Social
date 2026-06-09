"""Test de la siembra de la Texto (`keni_consola.sembrar`). PURO: no toca el store."""

from __future__ import annotations

from keni_consola import libtexto, sembrar


def test_main_invoca_importar_semilla_y_devuelve_0(monkeypatch, capsys):
    monkeypatch.setattr(libtexto, "importar_semilla", lambda: 7)
    rc = sembrar.main()
    assert rc == 0
    assert "7 documento" in capsys.readouterr().out
