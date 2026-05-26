#!/usr/bin/env python3
"""Tests del outpainting generativo expandir.py (OpenRouter).

Pillow real, SIN red: el proveedor (`_PROVEEDOR_EXPANDIR`) se parchea para no llamar
a ninguna API. No corre en el CI estático de skills (que no instala Pillow); se
ejecuta en local:

    pytest skills-copy/.claude/skills/estudio-imagen/test_expandir.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import expandir  # noqa: E402


def _args(foto, **kw):
    base = dict(foto=foto, formato="feed", modelo=None, strength=0.4,
                lado="auto", marca=None, prompt=None, salida=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _guardar(img, ruta):
    img.save(ruta, "PNG")
    return str(ruta)


def _mock_relleno(color):
    """Devuelve un proveedor OpenRouter falso que rellena TODO el lienzo con `color`."""
    llamado = {}

    def _fake(canvas, prompt, *, clave, modelo, strength):
        llamado.update(clave=clave, modelo=modelo, strength=strength, prompt=prompt)
        w, h = Image.open(io.BytesIO(canvas)).size
        buf = io.BytesIO()
        Image.new("RGB", (w, h), color).save(buf, "PNG")
        return buf.getvalue()

    _fake.llamado = llamado
    return _fake


# --------------------------------------------------------------------------- #
# Sin API key: modo dirección de arte (no falla)                              #
# --------------------------------------------------------------------------- #

def test_sin_key_cae_a_direccion_de_arte(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Si por accidente llamara al proveedor, que truene el test:
    monkeypatch.setattr(expandir, "_PROVEEDOR_EXPANDIR",
                        lambda *a, **k: pytest.fail("no debió llamar al proveedor sin key"))
    foto = _guardar(Image.new("RGB", (1000, 1000), (0, 200, 0)), tmp_path / "f.png")
    rc = expandir.expandir(_args(foto))
    assert rc == 0  # modo dirección de arte (no falla)


# --------------------------------------------------------------------------- #
# Camino feliz: el sujeto se re-compone (intacto), la banda la pone la IA      #
# --------------------------------------------------------------------------- #

def test_expandir_recompone_sujeto_y_rellena_banda(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake = _mock_relleno((200, 0, 0))  # la IA "rellena" de rojo
    monkeypatch.setattr(expandir, "_PROVEEDOR_EXPANDIR", fake)

    # Sujeto verde, cuadrado -> feed añade alto (banda arriba+abajo).
    foto = _guardar(Image.new("RGB", (1000, 1000), (0, 200, 0)), tmp_path / "f.png")
    info = expandir.expandir(_args(foto, salida=str(tmp_path / "out.png")))

    assert info["aplicado"] == "expandir-ia"
    assert fake.llamado["clave"] == "sk-or-test"
    assert info["modelo"] == expandir._MODELO_DEFECTO  # default cuando no se fuerza
    assert info["salidas"][0]["tamano"] == "1080x1350"

    with Image.open(info["salidas"][0]["salida"]) as out:
        assert out.size == (1080, 1350)
        cx = out.width // 2
        centro = out.getpixel((cx, out.height // 2))   # zona del sujeto
        arriba = out.getpixel((cx, 5))                 # banda superior (IA)
    assert centro[1] > centro[0] and centro[1] > centro[2]   # verde domina -> sujeto intacto
    assert arriba[0] > arriba[1] and arriba[0] > arriba[2]   # rojo domina -> banda de IA


def test_modelo_configurable(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake = _mock_relleno((10, 10, 10))
    monkeypatch.setattr(expandir, "_PROVEEDOR_EXPANDIR", fake)
    foto = _guardar(Image.new("RGB", (1000, 1000), (0, 200, 0)), tmp_path / "f.png")
    info = expandir.expandir(_args(foto, modelo="bytedance/seedream-4.5"))
    assert info["modelo"] == "bytedance/seedream-4.5"
    assert fake.llamado["modelo"] == "bytedance/seedream-4.5"
    assert fake.llamado["strength"] == 0.4


def test_ya_en_proporcion_solo_redimensiona(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setattr(expandir, "_PROVEEDOR_EXPANDIR",
                        lambda *a, **k: pytest.fail("no debió llamar al proveedor"))
    foto = _guardar(Image.new("RGB", (800, 1000), (0, 200, 0)), tmp_path / "f.png")
    info = expandir.expandir(_args(foto))
    assert info["aplicado"] == "resize"
    assert info["salidas"][0]["tamano"] == "1080x1350"


# --------------------------------------------------------------------------- #
# Geometría (puro)                                                            #
# --------------------------------------------------------------------------- #

def test_geometria_cuadrado_a_feed_anade_alto():
    geo = expandir.geometria(1000, 1000, 1080, 1350, "auto")
    assert geo["eje"] == "v"
    assert geo["fw"] == 1000 and geo["fh"] == 1250
    assert {l for l, _ in geo["bandas"]} == {"arriba", "abajo"}


def test_geometria_lado_forzado_arriba():
    geo = expandir.geometria(1000, 1000, 1080, 1350, "arriba")
    assert geo["bandas"] == [("arriba", 250)]
    assert geo["oy"] == 250


def test_geometria_ya_en_proporcion_es_none():
    assert expandir.geometria(800, 1000, 1080, 1350, "auto") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
