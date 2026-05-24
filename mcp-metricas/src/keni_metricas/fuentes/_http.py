"""Cliente HTTP compartido por los adaptadores: timeouts + reintentos con backoff."""

from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

log = logging.getLogger("keni_metricas")


def cliente_http(timeout: float = 15.0) -> httpx.Client:
    return httpx.Client(timeout=timeout)


def _es_transitorio(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception(_es_transitorio),
)
def get_json(
    cliente: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
) -> dict:
    """GET con reintentos en errores transitorios (red / 5xx). Lanza en 4xx."""
    r = cliente.get(url, params=params, headers=headers)
    r.raise_for_status()
    return r.json()


def post_json(
    cliente: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    data: dict | None = None,
    json: dict | None = None,
    headers: dict | None = None,
) -> dict:
    """POST simple (para endpoints de token / TikTok). Sin reintentos."""
    r = cliente.post(url, params=params, data=data, json=json, headers=headers)
    r.raise_for_status()
    return r.json()


def con_refresh(hacer, refrescar):
    """Ejecuta hacer(); si da 401 y refrescar() consigue un token nuevo, reintenta 1 vez.

    `hacer` debe leer el token actual del adaptador (que `refrescar` actualiza),
    y `refrescar` devuelve True si obtuvo un token nuevo.
    """
    try:
        return hacer()
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 401 or not refrescar():
            raise
        return hacer()


# Tope de seguridad para los bucles de paginación.
MAX_PAGINAS = 10
