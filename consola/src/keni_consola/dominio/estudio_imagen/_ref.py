"""Indirección al BARREL para preservar el contrato de monkeypatch del módulo original.

El módulo `dominio/estudio_imagen.py` era un único fichero: cuando una función llamaba a otra
(p. ej. `componer_desde_plantilla` -> `renderizar_documento`, o `editar` -> `_correr_motor`), la
llamada se resolvía como atributo del MISMO módulo. Por eso los tests pueden
`monkeypatch.setattr(estudio_imagen, "renderizar_documento", ...)` y la función interna ve el
parche. Al partir el módulo en submódulos, una llamada directa entre submódulos dejaría de pasar
por el atributo del paquete y el parche no se vería.

Este proxy resuelve PEREZOSAMENTE el paquete (`estudio_imagen.__init__`) en cada acceso, de modo
que `_ref.NOMBRE(...)` siempre lee el atributo ACTUAL del barrel — exactamente lo que el módulo
original hacía. Los submódulos usan `_ref.X` SOLO en los puntos que los tests parchean (la red /
los renders / las funciones de composición compuestas), no en todo.
"""

from __future__ import annotations

import importlib
from typing import Any

_PAQUETE = __name__.rsplit(".", 1)[0]  # 'keni_consola.dominio.estudio_imagen'


def __getattr__(nombre: str) -> Any:
    # Resuelve el barrel ya inicializado (no hay ciclo: solo se invoca en tiempo de llamada,
    # nunca durante la importación de los submódulos) y devuelve su atributo vigente.
    return getattr(importlib.import_module(_PAQUETE), nombre)
