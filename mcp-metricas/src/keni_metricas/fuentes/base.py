"""Interfaces comunes: una fuente de metricas y un adaptador por plataforma.

`FuenteMetricas` es lo que consumen las tools del MCP. Hay dos implementaciones:
- `FuenteMuestra` (datos offline, para tests y para usar mientras llegan los permisos
  reales de cada plataforma).
- `FuenteCompuesta` (en `agregador.py`), que combina varios `AdaptadorPlataforma`
  reales por marca.

`engagement_pct()` es la fórmula única de engagement; toda métrica/pieza (real, de
muestra, agregada o de reporte) la usa. La definición vive AHORA en
`keni_shared.metricas` (H3/E1), la capa más baja del monorepo, para que la consola
también la importe de la misma fuente; aquí se reexporta para no tocar los ~10
sitios de keni-metricas que ya la importan de `.fuentes.base` (antes #97 / H4).

`AdaptadorBase` centraliza el boilerplate que los 4 adaptadores reales
(meta/youtube/x/tiktok) repetían: el guard `disponible()`, el header `Bearer`,
el punto de refresh de token y el wrapper `try/except + log.warning` que degrada
a un valor por defecto sin romper. Cada adaptador hereda y solo implementa lo
específico de su plataforma (endpoints, parseo de campos, refresh propio).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Protocol, TypeVar, runtime_checkable

import httpx
from keni_shared.metricas import engagement_pct  # noqa: F401  (reexport: la fuente es keni_shared)

from ..schema import Cuenta, MetricaPlataforma, Pieza, Plataforma, ResumenMetricas
from ._http import cliente_http, con_refresh, log

T = TypeVar("T")


@runtime_checkable
class FuenteMetricas(Protocol):
    """Origen de metricas que las tools del MCP consultan."""

    nombre: str

    def cuentas(self) -> list[Cuenta]: ...

    def resumen(self, cuenta_id: str, rango: str) -> ResumenMetricas: ...

    def mejores_piezas(self, cuenta_id: str, rango: str, n: int) -> list[Pieza]: ...


@runtime_checkable
class AdaptadorPlataforma(Protocol):
    """Lee metricas de UNA plataforma para un handle/id de cuenta concreto."""

    plataforma: Plataforma

    def disponible(self) -> bool:
        """True si hay credenciales suficientes para operar (si no, se omite)."""
        ...

    def metricas(self, handle: str, desde: date, hasta: date) -> MetricaPlataforma | None: ...

    def piezas(self, handle: str, desde: date, hasta: date, n: int) -> list[Pieza]: ...


class AdaptadorBase:
    """Base concreta de los adaptadores reales por plataforma (H4).

    Aporta el comportamiento común y deja a cada subclase solo lo específico:

    - `__init__`: guarda credenciales, token y cliente httpx (compartible en tests).
      El nombre de la clave del token es configurable vía `claves_token` para X,
      que admite `bearer_token` o `access_token`.
    - `disponible()`: hay credenciales suficientes si hay token.
    - `_headers_bearer()`: header `Authorization: Bearer <token>`.
    - `_refrescar()`: punto de extensión para renovar el token ante un 401.
      Por defecto es no-op (el bearer de app de X no caduca).
    - `_intentar()`: ejecuta una operación con `con_refresh` (reintenta 1 vez tras
      un 401 si el refresh consigue token nuevo) envuelta en `try/except` que
      registra un `log.warning` y degrada al `defecto` indicado, sin romper.

    `plataforma` es de instancia (Meta sirve facebook e instagram con la misma
    clase) o de clase (las demás la fijan), por lo que NO se declara aquí como
    anotación de clase para no pisar el atributo de instancia.
    """

    # Claves de credencial donde buscar el token de acceso, en orden de preferencia.
    claves_token: tuple[str, ...] = ("access_token",)

    def __init__(self, creds: dict, cliente: httpx.Client | None = None):
        self._creds = creds
        self._token = self._leer_token(creds)
        self._cli = cliente or cliente_http()

    def _leer_token(self, creds: dict) -> str | None:
        for clave in self.claves_token:
            if (valor := creds.get(clave)):
                return valor
        return None

    def disponible(self) -> bool:
        """True si hay credenciales suficientes para operar (si no, se omite)."""
        return bool(self._token)

    def _headers_bearer(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _refrescar(self) -> bool:
        """Renueva el token ante un 401. Por defecto no-op (devuelve False)."""
        return False

    def _intentar(self, accion: Callable[[], T], *, defecto: T, contexto: str) -> T:
        """Ejecuta `accion` con refresh + degradación.

        Antepone el guard `disponible()`: si no hay credenciales, devuelve `defecto`
        sin tocar la red. Envuelve la llamada en `con_refresh` (reintento único tras
        401) y atrapa cualquier excepción dejando un `log.warning` con `contexto`.
        """
        if not self.disponible():
            return defecto
        try:
            return con_refresh(accion, self._refrescar)
        except Exception as e:  # noqa: BLE001
            log.warning("%s falló: %s", contexto, e)
            return defecto


class CuentaNoEncontrada(Exception):
    """La cuenta solicitada no existe en la fuente activa."""
