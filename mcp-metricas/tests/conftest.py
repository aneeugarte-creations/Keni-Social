"""Fixtures compartidas de los tests del MCP de metricas.

BACKOFF CERO EN TESTS: `fuentes/_http.get_json` reintenta errores transitorios (red / 5xx)
con `tenacity` + `wait_exponential` (espera REAL de 1.5-3s por test que ejercita el camino
500). En tests no queremos pagar esa espera de pared: anulamos SOLO el `sleep` del
controlador de reintentos (autouse, toda la sesion). Se conserva el NUMERO de intentos y la
logica de exito/fallo —solo desaparece la espera—, asi que el comportamiento bajo prueba no
cambia, pero la suite deja de dormir segundos enteros.
"""

from __future__ import annotations

import pytest

from keni_metricas.fuentes import _http


@pytest.fixture(autouse=True, scope="session")
def _sin_espera_de_reintentos():
    """Pone a no-op el sleep del `@retry` de tenacity de `get_json` (sin tocar #intentos)."""
    controlador = getattr(_http.get_json, "retry", None)
    if controlador is not None:
        original = controlador.sleep
        controlador.sleep = lambda _segundos: None
        try:
            yield
        finally:
            controlador.sleep = original
    else:  # pragma: no cover -- defensa si tenacity cambia la forma del decorador
        yield
