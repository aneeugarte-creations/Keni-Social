"""Util común de escritura atómica (`io_atomico.escribir_atomico`) — H7/N2 · H3/E1.

Verifica las garantías: el destino nunca queda a medias, el padre se crea,
el temporal se borra al fallar, y `modo` aplica permisos (p.ej. 0600 para secretos).

La implementación está en `keni_shared.io_atomico` (H3/E1); `keni_consola` la reexporta.
Este test importa por el reexport de la consola (que es como la usan los módulos de dominio)
y monkeypatchea sobre `keni_shared.io_atomico`.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from keni_consola.io_atomico import escribir_atomico


def test_escribe_texto_utf8(tmp_path: Path):
    destino = tmp_path / "salida.txt"
    escribir_atomico(destino, "hola — café 🎉")
    assert destino.read_text(encoding="utf-8") == "hola — café 🎉"


def test_crea_directorios_padre(tmp_path: Path):
    destino = tmp_path / "a" / "b" / "c.yaml"
    escribir_atomico(destino, "x: 1\n")
    assert destino.exists()
    assert destino.read_text(encoding="utf-8") == "x: 1\n"


def test_reemplaza_contenido_existente(tmp_path: Path):
    destino = tmp_path / "f.json"
    destino.write_text("viejo", encoding="utf-8")
    escribir_atomico(destino, "nuevo")
    assert destino.read_text(encoding="utf-8") == "nuevo"


def test_modo_aplica_permisos_0600(tmp_path: Path):
    destino = tmp_path / "secretos.toml"
    escribir_atomico(destino, "[imagen]\n", modo=0o600)
    perms = stat.S_IMODE(destino.stat().st_mode)
    assert perms == 0o600


def test_no_deja_temporales_al_terminar(tmp_path: Path):
    destino = tmp_path / "f.yaml"
    escribir_atomico(destino, "ok")
    # Solo el destino: ningun `.tmp-*` huerfano en el directorio.
    restantes = [p.name for p in tmp_path.iterdir()]
    assert restantes == ["f.yaml"]


def test_sufijo_por_defecto_es_la_extension_del_destino(tmp_path: Path, monkeypatch):
    # Capturamos el sufijo del temporal interceptando mkstemp.
    import tempfile as _tf

    capturado: dict[str, str] = {}
    real_mkstemp = _tf.mkstemp

    def fake_mkstemp(*args, **kwargs):
        capturado["suffix"] = kwargs.get("suffix", "")
        capturado["prefix"] = kwargs.get("prefix", "")
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr("keni_shared.io_atomico.tempfile.mkstemp", fake_mkstemp)
    escribir_atomico(tmp_path / "doc.md", "# hola")
    assert capturado["suffix"] == ".md"
    assert capturado["prefix"] == ".tmp-"


def test_fallo_de_escritura_borra_temporal_y_no_toca_destino(tmp_path: Path, monkeypatch):
    destino = tmp_path / "f.txt"
    destino.write_text("intacto", encoding="utf-8")

    # Forzamos un fallo durante la escritura (replace nunca llega a ejecutarse).
    original_replace = os.replace
    monkeypatch.setattr(
        "keni_shared.io_atomico.os.replace",
        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(OSError):
        escribir_atomico(destino, "nuevo")
    monkeypatch.setattr("keni_shared.io_atomico.os.replace", original_replace)

    # El destino queda intacto y no hay temporales huerfanos.
    assert destino.read_text(encoding="utf-8") == "intacto"
    huerfanos = [p.name for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]
    assert huerfanos == []
