"""Lanza Claude Code en una carpeta del proyecto (capa de control sobre el motor).

En macOS le decimos a Terminal.app, via `osascript`, que abra una ventana y
ejecute `cd <ruta> && claude`. SEGURIDAD:
  - NUNCA `shell=True`. Se invoca `subprocess.run(["osascript", "-e", script])`.
  - La `ruta` ya viene validada contra la allowlist (consola.toml) por el llamante.
  - La ruta se escapa para AppleScript (comillas dobles -> `\\"`, backslash -> `\\\\`).

En sistemas que no son macOS no lanzamos nada: devolvemos un aviso claro de
"solo macOS por ahora" sin crashear.

`abrir_en_claude_code` es una funcion modulo-nivel para que los tests la parcheen
(mockeen) y NO lancen nada real.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _escapar_applescript(texto: str) -> str:
    """Escapa una cadena para incrustarla dentro de un literal AppleScript ("...")."""
    return texto.replace("\\", "\\\\").replace('"', '\\"')


def abrir_en_claude_code(ruta: Path) -> str:
    """Abre Terminal en `ruta` y ejecuta `claude` (macOS). Devuelve un mensaje legible.

    Lanza `RuntimeError` (mensaje en espanol) si `osascript` falla. En no-macOS
    devuelve un aviso de plataforma sin intentar lanzar nada.
    """
    if sys.platform != "darwin":
        return "Por ahora 'Abrir en Claude Code' solo funciona en macOS."

    ruta_str = str(Path(ruta))
    ruta_esc = _escapar_applescript(ruta_str)
    # Construimos el comando que se teclea en Terminal. La ruta va entre comillas
    # SIMPLES dentro del comando de shell (cd '<ruta>') y todo el comando va como
    # literal AppleScript con comillas dobles escapadas. Sin shell=True por aqui:
    # osascript recibe el script como argumento -e, no pasa por /bin/sh nuestro.
    comando_shell = f"cd '{ruta_esc}' && claude"
    script = f'tell application "Terminal" to do script "{comando_shell}"\n' 'tell application "Terminal" to activate'

    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as e:  # osascript no disponible (raro en macOS)
        raise RuntimeError("No se encontro 'osascript'; no se pudo abrir Terminal.") from e
    except subprocess.CalledProcessError as e:
        detalle = (e.stderr or "").strip() or "error desconocido de osascript"
        raise RuntimeError(f"No se pudo abrir Claude Code: {detalle}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Tiempo agotado al pedirle a Terminal que abriera Claude Code.") from e

    return f"Claude Code se esta abriendo en una nueva ventana de Terminal ({ruta_str})."


def claude_disponible() -> bool:
    """True si el binario `claude` esta en el PATH (best-effort, informativo)."""
    return shutil.which("claude") is not None
