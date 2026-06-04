#!/usr/bin/env python3
"""Tests de las operaciones deterministas de editar.py (comprimir + extender).

Usa Pillow de verdad (sin red, sin IA, sin modelo). Se ejecuta en local, donde
Pillow esta disponible:

    pytest consola/tests/motores/test_editar.py

`importorskip("PIL")` lo salta limpio si faltara Pillow.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

# El motor vive en `keni_consola/motores/estudio_imagen/`.
_MOTOR = (
    Path(__file__).resolve().parents[2]
    / "src" / "keni_consola" / "motores" / "estudio_imagen"
)
sys.path.insert(0, str(_MOTOR))
import editar  # noqa: E402

# --------------------------------------------------------------------------- #
# Helpers de imagenes de prueba                                               #
# --------------------------------------------------------------------------- #

def _gradiente(w: int, h: int) -> Image.Image:
    """Imagen suave (muy comprimible) sin recurrir a numpy."""
    base = Image.new("RGB", (256, 2))
    for x in range(256):
        base.putpixel((x, 0), (x, 255 - x, (x * 2) % 256))
        base.putpixel((x, 1), ((x + 40) % 256, x, 200))
    return base.resize((w, h), Image.LANCZOS)


def _ruido(w: int, h: int, sigma: float = 90) -> Image.Image:
    return Image.effect_noise((w, h), sigma).convert("RGB")


def _guardar(img: Image.Image, ruta: Path) -> str:
    img.save(ruta, "PNG")
    return str(ruta)


def _args_comprimir(foto, **kw):
    base = dict(foto=foto, peso_max_mb=2.0, max=None, formato_archivo="jpg",
                calidad_min=60, salida=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _args_extender(foto, **kw):
    base = dict(foto=foto, formato="feed", metodo="borde", max_ext=0.25,
                umbral_uniforme=16.0, forzar=False, salida=None)
    base.update(kw)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# comprimir (formato "full")                                                  #
# --------------------------------------------------------------------------- #

def test_comprimir_baja_peso_conservando_tamano(tmp_path):
    foto = _guardar(_gradiente(3000, 2000), tmp_path / "foto.png")
    info = editar.comprimir(_args_comprimir(foto, peso_max_mb=1.0))

    salida = Path(info["salidas"][0]["salida"])
    assert salida.is_file() and salida.suffix == ".jpg"
    assert salida.stat().st_size <= 1.0 * 1024 * 1024  # bajo el objetivo
    assert info["bajo_objetivo"] is True
    assert info["redujo_tamano"] is False  # conserva tamaño original
    with Image.open(salida) as out:
        assert out.size == (3000, 2000)
        assert out.format == "JPEG"


def test_comprimir_con_resize_pequeno(tmp_path):
    foto = _guardar(_gradiente(3000, 2000), tmp_path / "foto.png")
    info = editar.comprimir(_args_comprimir(foto, peso_max_mb=1.0, max=1000))

    with Image.open(info["salidas"][0]["salida"]) as out:
        assert max(out.size) == 1000  # lado largo capado a --max
    assert info["redujo_tamano"] is True
    assert info["bajo_objetivo"] is True


def test_comprimir_objetivo_minusculo_reduce_tamano(tmp_path):
    # Objetivo agresivo: el mecanismo debe activarse (bajar calidad y/o tamaño)
    # y dejar un JPEG válido y más liviano que el PNG de partida.
    foto = _guardar(_gradiente(2400, 1600), tmp_path / "foto.png")
    peso_original = Path(foto).stat().st_size
    info = editar.comprimir(_args_comprimir(foto, peso_max_mb=0.05))

    salida = Path(info["salidas"][0]["salida"])
    assert salida.stat().st_size < peso_original
    assert info["bajo_objetivo"] is True or info["redujo_tamano"] is True
    with Image.open(salida) as out:
        out.verify()  # JPEG íntegro


def test_comprimir_webp(tmp_path):
    foto = _guardar(_gradiente(1600, 1200), tmp_path / "foto.png")
    info = editar.comprimir(_args_comprimir(foto, formato_archivo="webp", peso_max_mb=1.0))
    salida = Path(info["salidas"][0]["salida"])
    assert salida.suffix == ".webp"
    with Image.open(salida) as out:
        assert out.format == "WEBP"


# --------------------------------------------------------------------------- #
# extender (encaje a formato extendiendo fondo uniforme)                      #
# --------------------------------------------------------------------------- #

def test_extender_anade_cielo_arriba(tmp_path):
    # Cuadrada (r0=1.0 > 0.8): hace falta ALTO. Cielo arriba (uniforme), sujeto abajo.
    img = Image.new("RGB", (1000, 1000), (135, 206, 235))
    img.paste(_ruido(1000, 400), (0, 600))
    foto = _guardar(img, tmp_path / "foto.png")

    info = editar.extender(_args_extender(foto))

    assert info["aplicado"] == "extension"
    assert info["extension_segura"] is True
    assert info["salidas"][0]["tamano"] == "1080x1350"
    lados = {ll["lado"] for ll in info["lados"]}
    assert lados == {"arriba"}  # solo el cielo, no el lado del sujeto
    with Image.open(info["salidas"][0]["salida"]) as out:
        assert out.size == (1080, 1350)


def test_extender_horizontal_ambos_lados(tmp_path):
    # Estrecha (r0=0.6 < 0.8): hace falta ANCHO. Bandas negras uniformes a los lados.
    img = Image.new("RGB", (600, 1000), (0, 0, 0))
    img.paste(_ruido(200, 1000), (200, 0))
    foto = _guardar(img, tmp_path / "foto.png")

    info = editar.extender(_args_extender(foto))

    assert info["aplicado"] == "extension"
    assert info["extension_segura"] is True
    lados = {ll["lado"] for ll in info["lados"]}
    assert lados == {"izquierda", "derecha"}


def test_extender_borde_no_uniforme_cae_a_recorte(tmp_path):
    # Ruido por todas partes: ningún borde uniforme -> NO inventa, recorta y avisa.
    foto = _guardar(_ruido(1000, 1000), tmp_path / "foto.png")

    info = editar.extender(_args_extender(foto))

    assert info["aplicado"] == "recorte"
    assert info["extension_segura"] is False
    assert "uniforme" in info["motivo"]
    assert info["salidas"][0]["tamano"] == "1080x1350"


def test_extender_demasiada_extension_cae_a_recorte(tmp_path):
    # Cielo uniforme pero la imagen es tan ancha que haría falta extender > max_ext.
    img = Image.new("RGB", (2000, 600), (135, 206, 235))
    img.paste(_ruido(2000, 200), (0, 400))
    foto = _guardar(img, tmp_path / "foto.png")

    info = editar.extender(_args_extender(foto, max_ext=0.25))
    assert info["aplicado"] == "recorte"
    assert info["extension_segura"] is False
    assert "%" in info["motivo"]


def test_extender_forzar_extiende_pese_a_no_uniforme(tmp_path):
    foto = _guardar(_ruido(1000, 1000), tmp_path / "foto.png")
    info = editar.extender(_args_extender(foto, forzar=True))
    assert info["aplicado"] == "extension"
    assert info["extension_segura"] is False  # se hizo, pero queda marcado
    assert "forzado" in info["motivo"]


def test_extender_ya_en_proporcion_solo_redimensiona(tmp_path):
    foto = _guardar(Image.new("RGB", (800, 1000), (10, 20, 30)), tmp_path / "foto.png")
    info = editar.extender(_args_extender(foto))
    assert info["aplicado"] == "resize"
    assert info["extension_segura"] is True
    assert info["salidas"][0]["tamano"] == "1080x1350"


# --------------------------------------------------------------------------- #
# Smoke por CLI (argparse + bloque DATOS)                                     #
# --------------------------------------------------------------------------- #

def test_cli_extender_imprime_datos(tmp_path):
    import json
    import subprocess

    img = Image.new("RGB", (1000, 1000), (135, 206, 235))
    img.paste(_ruido(1000, 400), (0, 600))
    foto = _guardar(img, tmp_path / "foto.png")
    salida = tmp_path / "out.png"

    proc = subprocess.run(
        [sys.executable, str(Path(editar.__file__)), "extender",
         "--foto", foto, "--formato", "feed", "--salida", str(salida)],
        capture_output=True, text=True, check=True,
    )
    linea = next(ln for ln in proc.stdout.splitlines() if ln.startswith("DATOS "))
    datos = json.loads(linea[len("DATOS "):])
    assert datos["op"] == "extender"
    assert datos["aplicado"] == "extension"
    assert salida.is_file()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
