"""Veredicto por símbolo ✅/⚠️/❌ + verificación de voz en el post-procesado.

PUROS (sin DB): `stream.derivar_verdicto` y `dominio.copy.verificar_voz`.
"""

from __future__ import annotations

import json

from keni_consola.dominio import copy as dom_copy
from keni_consola.dominio import stream

# --------------------------------------------------------------------------- #
# derivar_verdicto: símbolo ✅/⚠️/❌ de la primera línea                        #
# --------------------------------------------------------------------------- #


def test_verdicto_por_simbolo():
    assert stream.derivar_verdicto("✅ Todo bien\n…") == "listo"
    assert stream.derivar_verdicto("⚠️ Ojo\n…") == "revisar"
    assert stream.derivar_verdicto("❌ No\n…") == "no_publicar"


def test_verdicto_sin_simbolo_no_deriva():
    # Sin un símbolo de veredicto en la primera línea no se deriva nada: ni las palabras
    # del contrato viejo ("LISTO PARA APROBAR") ni un emoji cualquiera cuelan veredicto.
    assert stream.derivar_verdicto("LISTO PARA APROBAR\n\nLeyenda: …") == ""
    assert stream.derivar_verdicto("EL TRI ESTÁ LISTO PARA LA FINAL 🔥") == ""
    assert stream.derivar_verdicto("Texto cualquiera sin veredicto") == ""


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
