"""Test de la siembra de la Texto (`keni_consola.inicializar`). PURO: no toca el store."""

from __future__ import annotations

from keni_consola import libtexto, inicializar


def test_main_invoca_importar_inicial_y_devuelve_0(monkeypatch, capsys):
    monkeypatch.setattr(libtexto, "importar_inicial", lambda: 7)
    rc = inicializar.main()
    assert rc == 0
    assert "7 documento" in capsys.readouterr().out
