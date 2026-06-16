"""Procedencia de las cifras de Campañas: la fuente activa de Métricas (Metricool).

Lo que queda del antiguo apartado "Comercial" (seguimiento por snapshots, retirado): solo
`fuente_actual`, que `campanias.py` y la API usan para etiquetar de dónde salen las cifras.
"""
from __future__ import annotations

from keni_metricas import servicio


def fuente_actual() -> str:
    """Nombre de la fuente activa de las cifras (procedencia, p. ej. "metricool").

    Deriva de la configuracion de metricas (la misma fuente que alimenta el tablero).
    "" si la fuente no se puede resolver (config incompleto): aqui NUNCA se inventan
    cifras, asi que la procedencia desconocida no degrada a datos de demostracion.
    """
    try:
        return servicio.nombre_fuente()
    except Exception:  # noqa: BLE001 -- sin fuente valida, procedencia desconocida
        return ""
