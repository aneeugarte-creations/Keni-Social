"""Verificación de VOZ en el post-procesado del copy (`dominio.copy.verificar_voz`).

PURO (sin DB): la degradación `listo` -> `revisar` cuando el copy se sale de los patrones
medidos de la marca, y los avisos que viajan al humano.
"""

from __future__ import annotations

import json

from keni_consola.dominio import copy as dom_copy

# --------------------------------------------------------------------------- #
# verificar_voz: degradación listo -> revisar con avisos                       #
# --------------------------------------------------------------------------- #


def _perfil(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path))
    perfil = {
        "version": 1,
        "marca": "marca-test",
        "redes": {
            "facebook": {
                "lint": {
                    "longitud_max": 300, "longitud_min": None, "emojis_max": 0,
                    "hashtags_max": 2, "gancho_mayusculas": None, "pregunta": None,
                }
            }
        },
    }
    (tmp_path / "marca-test.json").write_text(json.dumps(perfil), encoding="utf-8")


def test_verificar_voz_degrada_listo_a_revisar(tmp_path, monkeypatch):
    _perfil(tmp_path, monkeypatch)
    piezas = [{"red": "facebook", "contenido": "Con emoji fuera de patrón 🔥"}]
    verdicto, avisos = dom_copy.verificar_voz("marca-test", piezas, "listo")
    assert verdicto == "revisar"
    assert avisos and "emoji" in avisos[0]


def test_verificar_voz_respeta_veredictos_no_listos(tmp_path, monkeypatch):
    _perfil(tmp_path, monkeypatch)
    piezas = [{"red": "facebook", "contenido": "Con emoji 🔥"}]
    # Un `no_publicar`/`revisar`/heredado ya pide ojos humanos: no se toca.
    assert dom_copy.verificar_voz("marca-test", piezas, "no_publicar")[0] == "no_publicar"
    assert dom_copy.verificar_voz("marca-test", piezas, "revisar")[0] == "revisar"
    assert dom_copy.verificar_voz("marca-test", piezas, "")[0] == ""


def test_verificar_voz_dentro_de_patron_no_toca(tmp_path, monkeypatch):
    _perfil(tmp_path, monkeypatch)
    piezas = [{"red": "facebook", "contenido": "El dato manda y la fuente lo respalda."}]
    verdicto, avisos = dom_copy.verificar_voz("marca-test", piezas, "listo")
    assert (verdicto, avisos) == ("listo", [])


def test_verificar_voz_sin_perfil_no_degrada():
    piezas = [{"red": "facebook", "contenido": "Texto sin perfil de marca."}]
    assert dom_copy.verificar_voz("marca-sin-perfil", piezas, "listo") == ("listo", [])
