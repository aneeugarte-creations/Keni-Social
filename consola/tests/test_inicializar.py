"""Test de la siembra de la Texto (`keni_consola.inicializar`). PURO: no toca el store."""

from __future__ import annotations

from keni_consola import libprompts, inicializar


def _silenciar_migraciones(monkeypatch):
    """Deja en 0 (no-op) todas las migraciones de arranque salvo las que el test fija aparte."""
    for nombre in (
        "migrar_nombres_prompts",
        "limpiar_prompts_obsoletos",
        "migrar_descripciones_editorial",
        "migrar_contrato_salida",
        "migrar_redactar_v1",
        "migrar_parrilla_v1",
        "migrar_titulos_prompts",
        "migrar_descripciones_prompt",
        "migrar_alcance_editorial",
        "asegurar_linea_base",
    ):
        monkeypatch.setattr(libprompts, nombre, lambda: 0)


def test_main_invoca_importar_inicial_y_devuelve_0(monkeypatch, capsys):
    _silenciar_migraciones(monkeypatch)
    monkeypatch.setattr(libprompts, "importar_inicial", lambda: 7)
    monkeypatch.setattr(libprompts, "reformatear_prompts", lambda: 0)
    monkeypatch.setattr(libprompts, "publicar_linea_base", lambda: 0)
    rc = inicializar.main()
    assert rc == 0
    assert "7 documento" in capsys.readouterr().out


def test_main_anuncia_reformato_y_publicacion(monkeypatch, capsys):
    _silenciar_migraciones(monkeypatch)
    monkeypatch.setattr(libprompts, "importar_inicial", lambda: 0)
    monkeypatch.setattr(libprompts, "reformatear_prompts", lambda: 3)
    monkeypatch.setattr(libprompts, "publicar_linea_base", lambda: 5)
    rc = inicializar.main()
    assert rc == 0
    salida = capsys.readouterr().out
    assert "3 prompt(s) reformateados" in salida
    assert "5 documento(s) publicados" in salida
