"""Lanza Claude Code en una carpeta del proyecto (capa de control sobre el motor).

En macOS le decimos a Terminal.app, via `osascript`, que abra una ventana y
ejecute `cd <ruta> && claude`. SEGURIDAD:
  - NUNCA `shell=True`. Se invoca `subprocess.run(["osascript", "-e", script])`.
  - La `ruta` ya viene validada contra la allowlist (consola.toml) por el llamante.
  - DOBLE escape de la ruta: primero para el SHELL que teclea Terminal (con
    `shlex.quote`, asi una ruta con apostrofo como `/Users/o'brien` no rompe el
    `cd`), y despues para el literal AppleScript (comillas dobles -> `\\"`,
    backslash -> `\\\\`).

En sistemas que no son macOS no lanzamos nada: devolvemos un aviso claro de
"solo macOS por ahora" sin crashear.

`abrir_en_claude_code` es una funcion modulo-nivel para que los tests la parcheen
(mockeen) y NO lancen nada real.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def _escapar_applescript(texto: str) -> str:
    """Escapa una cadena para incrustarla dentro de un literal AppleScript ("...")."""
    return texto.replace("\\", "\\\\").replace('"', '\\"')


def abrir_en_claude_code(ruta: Path, prompt: str | None = None) -> str:
    """Abre Terminal en `ruta` y ejecuta `claude` (macOS). Devuelve un mensaje legible.

    Si se pasa `prompt`, se lanza `claude '<prompt>'` para que el asistente arranque
    con ese texto inicial (p.ej. el detalle de una tarea). El `prompt` se entrecomilla
    con `shlex.quote` igual que la ruta, asi que un apostrofo dentro del texto no rompe
    el comando ni permite inyeccion. Sin `prompt` (caso de Proyectos) se abre `claude`
    a secas; por eso el parametro es opcional con default `None`.

    Lanza `RuntimeError` (mensaje en espanol) si `osascript` falla. En no-macOS
    devuelve un aviso de plataforma sin intentar lanzar nada.
    """
    if sys.platform != "darwin":
        return "Por ahora 'Abrir en Claude Code' solo funciona en macOS."

    ruta_str = str(Path(ruta))
    # DOS niveles de escape, en orden:
    #   1) shell: la ruta (y el prompt opcional) se incrustan en un comando que
    #      Terminal teclea en /bin/sh. `shlex.quote` los entrecomilla de forma segura
    #      (una ruta o prompt con apostrofo como /Users/o'brien rompe un `cd '<ruta>'`
    #      ingenuo; shlex lo resuelve cerrando/escapando la comilla: 'o'\''brien').
    #   2) AppleScript: el comando completo va como literal "..." dentro del script,
    #      asi que escapamos comillas dobles y backslashes para no romperlo.
    # Sin shell=True por aqui: osascript recibe el script como argumento -e.
    comando_shell = f"cd {shlex.quote(ruta_str)} && claude"
    prompt_limpio = (prompt or "").strip()
    if prompt_limpio:
        comando_shell += f" {shlex.quote(prompt_limpio)}"
    comando_esc = _escapar_applescript(comando_shell)
    script = f'tell application "Terminal" to do script "{comando_esc}"\n' 'tell application "Terminal" to activate'

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
