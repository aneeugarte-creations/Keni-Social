"""Estudio de imagen — motor determinista por subproceso (patrón `api/verificaciones`).

Submódulo de área del paquete `dominio.estudio_imagen`:
  - EDITAR (determinista) -> motor `motores/estudio_imagen/editar.py` (Pillow, sin coste ni red:
    recortar/redimensionar/comprimir/extender/placa). Adapta la foto de una pieza a su formato.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from . import _ref
from ._comun import (
    _TIMEOUT_EDITAR_S,
    OPS_EDITAR,
    EstudioError,
    _importar_salidas,
    _materializar,
    _resultado,
    _ruta_motor,
)

__all__ = ["_argv_editar", "editar"]


def _argv_editar(op: str, foto: Path | None, out: Path, params: dict[str, Any]) -> list[str]:
    """Construye el argv de `editar.py <op> ...` segun la operacion (valores ya validados)."""
    motor = _ruta_motor("editar.py")
    cmd = [sys.executable, str(motor), op]
    if foto is not None:
        cmd += ["--foto", str(foto)]
    cmd += ["--salida", str(out)]
    if op == "recortar":
        cmd += ["--formato", params["formato"]]
    elif op == "redimensionar":
        cmd += ["--max", str(params["max"])]
    elif op == "comprimir":
        cmd += ["--peso-max-mb", str(params["peso_max_mb"]), "--formato-archivo", params["formato_archivo"]]
    elif op == "extender":
        cmd += ["--formato", params["formato"], "--metodo", params["metodo"]]
        if params.get("forzar"):
            cmd += ["--forzar"]
    elif op == "placa":
        cmd += ["--texto", params["texto"], "--marca", params["marca"], "--formato", params["formato"]]
        if params.get("fuente_cita"):
            cmd += ["--fuente-cita", params["fuente_cita"]]
    return cmd


def editar(imagen: str, op: str, params: dict[str, Any]) -> dict[str, Any]:
    """Operacion DETERMINISTA (Pillow) sobre un objeto de media -> resultado uniforme.

    `placa` puede no llevar foto de fondo; el resto requiere `imagen`. Sin coste, sin red.
    """
    if op not in OPS_EDITAR:
        raise EstudioError(f"Operacion de edicion no soportada: {op}.")
    ext = ".jpg" if op == "comprimir" and params.get("formato_archivo") == "jpg" else ".png"
    if op == "comprimir" and params.get("formato_archivo") == "webp":
        ext = ".webp"
    with tempfile.TemporaryDirectory(prefix="keni-estudio-") as tmp:
        carpeta = Path(tmp)
        foto: Path | None = None
        if imagen:
            foto = _materializar(imagen, carpeta)
        elif op != "placa":
            raise EstudioError("Falta la imagen de entrada para esta operacion.")
        out = carpeta / f"salida{ext}"
        cmd = _argv_editar(op, foto, out, params)
        info = _ref._correr_motor(cmd, timeout=_TIMEOUT_EDITAR_S)
        return _resultado(_importar_salidas(info), info)
