"""Paso de AGENCIAS (Fase 2): ingiere las agencias configuradas (Reuters/AFP) al pool."""

from __future__ import annotations

from typing import Any

from ... import agencias, repos
from ...dominio import ingesta
from .._comun import _log

# Agencias CONFIGURADAS a sondear en cada barrido. Lista fija para el piloto (no hay config
# per-marca ni env de "qué agencias"); `agencias.traer_items` degrada honesto a `[]` sin
# credencial, así que sondear una agencia no configurada es un no-op sin red ni coste.
_AGENCIAS = ("reuters", "afp")


def paso_agencias() -> dict[str, Any]:
    """Ingiere las AGENCIAS configuradas (Reuters/AFP) al pool `noticias_items`. Best-effort.

    Para cada agencia: `agencias.traer_items()` (que devuelve `[]` honesto sin credencial, sin
    tocar la red), se construye la fila de pool con `ingesta.noticia_item_de_agencia` y se
    persiste por el MISMO sumidero que el RSS (`repos.crear_noticias_items`, idempotente por
    UNIQUE(fuente_id, clave)). Una agencia que falla (red/auth/forma) se loguea y NO aborta el
    barrido ni las demás agencias. Sin credenciales vivas (AFP usa un token placeholder) el
    paso es un no-op honesto. Devuelve `{items}` con cuántas filas nuevas se insertaron.
    """
    nuevos = 0
    for ag in _AGENCIAS:
        try:
            crudos = agencias.traer_items(ag)
            pool = [
                fila
                for it in crudos
                if (fila := ingesta.noticia_item_de_agencia(it, agencia=ag)) is not None
            ]
            if pool:
                nuevos += repos.crear_noticias_items(pool)
        except Exception:  # noqa: BLE001 -- una agencia no debe tumbar el barrido
            _log.exception("recolectar_daemon: fallo ingiriendo la agencia %s.", ag)
    return {"items": nuevos}
