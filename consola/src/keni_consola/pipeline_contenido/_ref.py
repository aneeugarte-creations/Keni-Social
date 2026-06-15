"""Proxy perezoso al paquete, para honrar el monkeypatch de seams sobre el barrel.

Los tests parchean `pipeline_contenido.<seam>` (el atributo del paquete) y esperan que
las llamadas INTERNAS entre submódulos vean el parche, igual que cuando todo vivía en un
único módulo. Con el split, una llamada directa `_FETCH_OG_IMAGE(...)` resuelve el
nombre LOCAL del submódulo, ajeno al parche del barrel. Enrutando la llamada por
`_ref._FETCH_OG_IMAGE(...)` se lee el atributo VIGENTE del paquete en tiempo de
llamada, preservando el seam sin cambiar el contrato de los tests.
"""

from __future__ import annotations

import importlib
from typing import Any


def __getattr__(name: str) -> Any:
    return getattr(importlib.import_module("keni_consola.pipeline_contenido"), name)
