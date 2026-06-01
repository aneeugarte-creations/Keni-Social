#!/usr/bin/env python3
"""Tests del compositor determinista (componer.py), centrados en `logo_posicion`.

Usa Pillow de verdad (sin red, sin IA). `importorskip("PIL")` lo salta limpio si faltara.
Comprueba que el motor honra la esquina del logo y produce una salida valida para las 4
posiciones, ademas de un smoke por CLI (`--config` temporal con un logo PNG real).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

# El motor vive en `keni_consola/motores/estudio_imagen/` (mismo patron que test_editar.py).
_MOTOR = (
    Path(__file__).resolve().parents[2]
    / "src" / "keni_consola" / "motores" / "estudio_imagen"
)
sys.path.insert(0, str(_MOTOR))
import componer  # noqa: E402


def _guardar(img: Image.Image, ruta: Path) -> str:
    img.save(ruta, "PNG")
    return str(ruta)


def _cfg_con_logo(logo_path: str, posicion: str) -> dict:
    """Catalogo minimo (una marca de prueba) con el logo y la posicion dados."""
    return {
        "formatos": {
            "feed": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
        },
        "marcas": {
            "prueba": {
                "nombre": "Prueba", "id_metricas": "prueba",
                "rojo": "#E30613", "tinta": "#111315", "blanco": "#FFFFFF",
                "etiqueta_default": "", "titular_mayusculas": False, "titular_condensada": False,
                "logo": logo_path, "marca_agua": "", "overlay_breaking": "",
                "logo_posicion": posicion, "wordmark": "Prueba", "verificar": "",
            }
        },
    }


def _args(foto, salida, config):
    return SimpleNamespace(
        foto=foto, marca="prueba", titular="", formato="feed", etiqueta="",
        logo=None, overlay=None, marca_agua=None, salida=str(salida), config=str(config),
    )


def _logo_png(ruta: Path) -> str:
    """Logo PNG pequeno y reconocible (cuadro magenta opaco sobre transparente)."""
    logo = Image.new("RGBA", (120, 120), (255, 0, 255, 255))
    logo.save(ruta, "PNG")
    return str(ruta)


@pytest.mark.parametrize(
    "posicion",
    ["superior-izquierda", "superior-derecha", "inferior-izquierda", "inferior-derecha"],
)
def test_componer_honra_logo_posicion(tmp_path, posicion):
    foto = _guardar(Image.new("RGB", (1200, 1200), (40, 40, 40)), tmp_path / "foto.png")
    logo = _logo_png(tmp_path / "logo.png")
    cfg = tmp_path / "marcas.json"
    cfg.write_text(json.dumps(_cfg_con_logo(logo, posicion)), encoding="utf-8")
    salida = tmp_path / "out.png"

    info = componer.componer(_args(foto, salida, cfg))

    assert salida.is_file()
    assert info["logo_real"] is True  # se uso el PNG real, no el wordmark
    with Image.open(salida) as out:
        assert out.size == (1080, 1350)


def test_esquina_logo_distingue_las_cuatro():
    """`_esquina_logo` coloca cada posicion en un cuadrante distinto del lienzo."""
    w, h, margin, st, sb = 1080, 1350, 56, 60, 96
    ancho = alto = 96
    si = componer._esquina_logo("superior-izquierda", ancho, alto, w, h, margin, st, sb)
    sd = componer._esquina_logo("superior-derecha", ancho, alto, w, h, margin, st, sb)
    ii = componer._esquina_logo("inferior-izquierda", ancho, alto, w, h, margin, st, sb)
    id_ = componer._esquina_logo("inferior-derecha", ancho, alto, w, h, margin, st, sb)
    assert si[0] < sd[0] and ii[0] < id_[0]  # izquierda a la izquierda de derecha
    assert si[1] < ii[1] and sd[1] < id_[1]  # superior por encima de inferior
    assert si == (margin, st + 24)  # retrocompat: superior-izquierda == comportamiento previo


def test_componer_placeholder_sin_foto(tmp_path):
    """Sin foto (placeholder): compone la plantilla del tamaño del formato y marca el flag."""
    logo = _logo_png(tmp_path / "logo.png")
    cfg = tmp_path / "marcas.json"
    cfg.write_text(json.dumps(_cfg_con_logo(logo, "superior-izquierda")), encoding="utf-8")
    salida = tmp_path / "placa.png"
    args = SimpleNamespace(
        foto=None, placeholder=True, marca="prueba", titular="Titular de prueba",
        formato="feed", etiqueta="", logo=None, overlay=None, marca_agua=None,
        salida=str(salida), config=str(cfg),
    )

    info = componer.componer(args)

    assert info["placeholder"] is True
    assert salida.is_file()
    with Image.open(salida) as out:
        assert out.size == (1080, 1350)


def test_cli_componer_con_logo_posicion(tmp_path):
    foto = _guardar(Image.new("RGB", (1000, 1000), (10, 20, 30)), tmp_path / "foto.png")
    logo = _logo_png(tmp_path / "logo.png")
    cfg = tmp_path / "marcas.json"
    cfg.write_text(json.dumps(_cfg_con_logo(logo, "inferior-derecha")), encoding="utf-8")
    salida = tmp_path / "out.png"

    proc = subprocess.run(
        [sys.executable, str(Path(componer.__file__)),
         "--foto", foto, "--marca", "prueba", "--formato", "feed",
         "--salida", str(salida), "--config", str(cfg)],
        capture_output=True, text=True, check=True,
    )
    linea = next(ln for ln in proc.stdout.splitlines() if ln.startswith("DATOS "))
    datos = json.loads(linea[len("DATOS "):])
    assert datos["logo_real"] is True
    assert salida.is_file()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
