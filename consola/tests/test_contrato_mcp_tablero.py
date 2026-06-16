"""Contrato: las rutas de `/api/publicaciones` de las que depende `mcp-tablero`.

`mcp-tablero` (paquete aparte, distribuido por el plugin via uvx) escribe en el
tablero de la Consola por HTTP a traves de `keni_tablero.cliente.ClienteConsola`.
NO comparte codigo con la Consola: la unica cosa que los une es la FORMA de estos
endpoints. Si alguien renombra/borra una de estas rutas en `api/publicaciones.py`, el
MCP se rompe en silencio (sus propios tests —`mcp-tablero/tests`, que SI corren en
CI via `.woodpecker/tests-python.yml`— mockean el HTTP, asi que no detectan un
endpoint renombrado en la Consola).

Este test es el guardarrail barato: falla AQUI, en la suite de la Consola, en el
mismo commit que toca la ruta, recordando que hay un consumidor externo. Es puro
(solo inspecciona la tabla `RUTAS`, sin red ni BD).

Si una ruta cambia a proposito: actualiza tambien `mcp-tablero/src/keni_tablero/
cliente.py` y este contrato EN EL MISMO commit.
"""

from __future__ import annotations

from keni_consola.api import publicaciones


def _pares_ruta_metodo() -> set[tuple[str, str]]:
    pares: set[tuple[str, str]] = set()
    for ruta in publicaciones.RUTAS:
        for metodo in ruta.methods or []:
            pares.add((ruta.path, metodo))
    return pares


# (path, metodo) que consume keni_tablero.cliente.ClienteConsola. Espejo 1:1 de los
# `self._peticion(...)` de cliente.py.
RUTAS_QUE_USA_MCP_TABLERO = {
    ("/api/publicaciones", "GET"),  # listar_publicacion
    ("/api/publicaciones", "POST"),  # crear_publicacion
    ("/api/publicaciones/{publicacion_id}", "PATCH"),  # actualizar_publicacion
    ("/api/publicaciones/{publicacion_id}/plataformas", "POST"),  # agregar_plataforma
    ("/api/publicaciones/{publicacion_id}/plataformas/{pieza_id}", "PATCH"),  # actualizar_plataforma
}


def test_rutas_de_mcp_tablero_existen():
    disponibles = _pares_ruta_metodo()
    faltan = RUTAS_QUE_USA_MCP_TABLERO - disponibles
    assert not faltan, (
        "mcp-tablero depende de rutas de /api/publicaciones que ya no existen: "
        f"{sorted(faltan)}. Si el cambio es a proposito, actualiza "
        "mcp-tablero/src/keni_tablero/cliente.py y este contrato en el mismo commit."
    )
