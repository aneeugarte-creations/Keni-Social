"""Presupuesto de rate-limit por plataforma.

Limita cuántas operaciones se piden a cada red en una ejecución, para no pasarse
de cuota (YouTube ~10k unidades/día, X de pago, etc.). El agregador consume una
unidad antes de consultar cada plataforma de cada cuenta; si se agota, esa
plataforma se omite con aviso (degradación elegante) en vez de seguir pegándole.

Caps configurables por entorno: KENI_PRESUPUESTO_YOUTUBE=50, etc.
"""

from __future__ import annotations

import os

from .schema import Plataforma


class PresupuestoExcedido(Exception):
    """Se agotó el presupuesto de llamadas de una plataforma en esta ejecución."""


_CAPS_DEFAULT: dict[Plataforma, int] = {
    Plataforma.facebook: 100,
    Plataforma.instagram: 100,
    Plataforma.youtube: 100,
    Plataforma.x: 50,
    Plataforma.tiktok: 100,
}


def _aplicar_env(caps: dict[Plataforma, int]) -> dict[Plataforma, int]:
    for p in list(caps):
        if (v := os.environ.get(f"KENI_PRESUPUESTO_{p.value.upper()}")):
            try:
                caps[p] = int(v)
            except ValueError:
                pass
    return caps


class Presupuesto:
    def __init__(self, caps: dict[Plataforma, int] | None = None):
        self._caps = dict(_CAPS_DEFAULT)
        if caps:
            self._caps.update(caps)
        self._caps = _aplicar_env(self._caps)
        self._uso: dict[Plataforma, int] = {}

    def consumir(self, plataforma: Plataforma, n: int = 1) -> None:
        cap = self._caps.get(plataforma)
        usado = self._uso.get(plataforma, 0) + n
        if cap is not None and usado > cap:
            raise PresupuestoExcedido(
                f"Presupuesto de {plataforma.value} agotado ({cap} operaciones/ejecución)."
            )
        self._uso[plataforma] = usado

    def restantes(self, plataforma: Plataforma) -> int | None:
        cap = self._caps.get(plataforma)
        return None if cap is None else max(0, cap - self._uso.get(plataforma, 0))

    def uso(self) -> dict[str, int]:
        return {p.value: n for p, n in self._uso.items()}

    def reiniciar(self) -> None:
        self._uso.clear()
