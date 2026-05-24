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
