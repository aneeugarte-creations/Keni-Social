"""Smoke del renderer Node de la plantilla (componer.mjs + @napi-rs/canvas).

Gateado: se SALTA si no hay `node` o el `node_modules` del renderer no está instalado (entornos
de CI Python puros). Donde corre, valida que el PNG sale del tamaño exacto del formato, en modo
placeholder y con foto. Usa Pillow solo para leer el tamaño del PNG (importorskip).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2] / "src" / "keni_consola"
_RENDER = _RAIZ / "motores" / "estudio_imagen" / "render_node"
sys.path.insert(0, str(_RAIZ.parent))

_NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(
    _NODE is None or not (_RENDER / "node_modules" / "@napi-rs" / "canvas").exists(),
    reason="Requiere node + node_modules del renderer (@napi-rs/canvas).",
)


def _spec_unotv():
    from keni_consola import plantillas_marca as pm
    from keni_consola.motores.estudio_imagen import spec_plantilla as sp
    return sp.spec_por_defecto("unotv", pm.DEFECTOS("unotv"))


def _render(payload, out: Path):
    proc = subprocess.run(
        [_NODE, str(_RENDER / "componer.mjs"), "--salida", str(out)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0 and out.is_file(), proc.stderr
    return proc


def test_render_node_placeholder(tmp_path):
    out = tmp_path / "ph.png"
    _render({"spec": _spec_unotv(), "formato": "feed", "placeholder": True,
             "bindings": {"copy_in": "Titular de prueba", "etiqueta_default": "ÚLTIMA HORA"}}, out)
    with Image.open(out) as im:
        assert im.size == (1080, 1350)


def test_render_node_con_foto(tmp_path):
    foto = tmp_path / "foto.jpg"
    Image.new("RGB", (1400, 1000), (20, 80, 140)).save(foto)
    out = tmp_path / "f.png"
    _render({"spec": _spec_unotv(), "formato": "vertical", "placeholder": False, "foto": str(foto),
             "bindings": {"copy_in": "Gol en el 90", "etiqueta_default": ""}}, out)
    with Image.open(out) as im:
        assert im.size == (1080, 1920)
