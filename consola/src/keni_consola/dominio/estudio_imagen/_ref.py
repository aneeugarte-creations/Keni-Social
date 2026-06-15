"""Indirección al BARREL para preservar el contrato de monkeypatch.

Este proxy resuelve PEREZOSAMENTE el paquete (`estudio_imagen.__init__`) en cada acceso, de modo
que `_ref.NOMBRE(...)` siempre lee el atributo ACTUAL del barrel. Los submódulos usan `_ref.X`
SOLO en los puntos que los tests parchean (la red / los renders / las funciones de composición
compuestas), no en todo.
"""

from __future__ import annotations

import importlib
from typing import Any

_PAQUETE = __name__.rsplit(".", 1)[0]  # 'keni_consola.dominio.estudio_imagen'


def __getattr__(nombre: str) -> Any:
    # Resuelve el barrel ya inicializado (no hay ciclo: solo se invoca en tiempo de llamada,
    # nunca durante la importación de los submódulos) y devuelve su atributo vigente.
    return getattr(importlib.import_module(_PAQUETE), nombre)
