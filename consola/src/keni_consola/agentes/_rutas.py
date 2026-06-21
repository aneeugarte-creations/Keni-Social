"""Validacion anti-escape del SLUG de un agente.

El nombre de carpeta de un agente generico se deriva de un nombre humano y SOLO
puede vivir DENTRO de la raiz de agentes. Aqui se valida que el slug no escape:
rechaza rutas absolutas, `..`, separadores de ruta, comodines y caracteres de
control, y exige que la ruta resuelta caiga estrictamente dentro de la raiz. Sin
shell. Mensajes en espanol.
"""

from __future__ import annotations

from pathlib import Path

# Caracteres prohibidos en el slug (separadores, comodines, etc.).
_CARACTERES_PROHIBIDOS = set('/\\:*?"<>|')


class NombreAgenteInvalido(ValueError):
    """El nombre/slug pedido no es valido o escaparia de la raiz de agentes."""


def resolver_slug_agente(slug: str, raiz: Path) -> Path:
    """Resuelve `<raiz>/<slug>/` garantizando que cae ESTRICTAMENTE dentro de la raiz.

    Valida el slug y garantiza que la ruta final no sale de `raiz`. Lanza
    `NombreAgenteInvalido` (en espanol) ante cualquier intento de escape.
    """
    crudo = (slug or "").strip()
    if not crudo:
        raise NombreAgenteInvalido("El nombre del agente no puede estar vacío.")

    # Rutas absolutas: prohibidas.
    if crudo.startswith(("/", "~")) or (len(crudo) >= 2 and crudo[1] == ":"):
        raise NombreAgenteInvalido("Usa solo un nombre, no una ruta absoluta.")

    # `..` o `.` como componentes: intento de salir de la raiz. Se valida ANTES que
    # los caracteres prohibidos para dar el mensaje claro de escape.
    if crudo in (".", "..") or ".." in crudo:
        raise NombreAgenteInvalido(
            "El nombre no puede contener '..': no se permite salir de la carpeta base."
        )

    # Caracteres peligrosos: separadores de ruta, control, comodines.
    if any(c in _CARACTERES_PROHIBIDOS for c in crudo):
        raise NombreAgenteInvalido(
            "El nombre tiene caracteres no permitidos (no uses / \\ : * ? etc.)."
        )
    if any(ord(c) < 32 for c in crudo):
        raise NombreAgenteInvalido("El nombre tiene caracteres de control no permitidos.")

    base = raiz.resolve()
    destino = (base / crudo).resolve()

    # Defensa en profundidad: la ruta resuelta debe quedar DENTRO de la base y no ser
    # la base misma. `is_relative_to` cubre cualquier escape por symlink/`..`.
    if destino == base or not destino.is_relative_to(base):
        raise NombreAgenteInvalido("El agente quedaría fuera de la carpeta base permitida.")

    return destino
