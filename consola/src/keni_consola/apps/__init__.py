"""Catálogo de apps de la Consola Keni (ADR 0005 + ADR 0002).

Las apps (A·Producción, B·Métricas, C·Operación) y el Shell se declaran en
manifests TOML (`<app>.toml`) que vive junto a este módulo. `registro.py` los
parsea y expone el catálogo + su activación por flag. Ver `registro.py`.
"""

from __future__ import annotations
