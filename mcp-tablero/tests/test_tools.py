"""Tests de las tools del MCP de tablero, ejercitadas EN PROCESO (sin servidor ni red).

Mismo patron que mcp-metricas/tests/test_tools.py: se replica el registro de
`server.crear_servidor` (`registrar(mcp, cliente)`) sobre una `FastMCP` de prueba y se
invocan via `mcp.call_tool` (la misma superficie que usa un cliente MCP real). El
`ClienteConsola` se sustituye por un doble en memoria: las VALIDACIONES deben cortar
ANTES de tocar la red (el doble registra cada llamada) y los `ErrorConsola` deben salir
como `{"error": ...}` (nunca traceback).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from keni_tablero.cliente import ErrorConsola
from keni_tablero.tools import CLASES, ESTADOS_PUBLICACION, ESTADOS_PLATAFORMA, FLUJOS, registrar

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class ClienteFalso:
    """Doble del `ClienteConsola`: registra llamadas y devuelve respuestas canned."""

    def __init__(self, respuestas: dict[str, Any] | None = None, error: str | None = None):
        self.llamadas: list[tuple[str, tuple, dict]] = []
        self._respuestas = respuestas or {}
        self._error = error

    def _resolver(self, metodo: str, *args, **kwargs) -> dict:
        self.llamadas.append((metodo, args, kwargs))
        if self._error:
            raise ErrorConsola(self._error)
        return self._respuestas.get(metodo, {})

    def listar_publicacion(self, params=None):
        return self._resolver("listar_publicacion", params)

    def crear_publicacion(self, cuerpo):
        return self._resolver("crear_publicacion", cuerpo)

    def actualizar_publicacion(self, publicacion_id, cuerpo):
        return self._resolver("actualizar_publicacion", publicacion_id, cuerpo)

    def actualizar_plataforma(self, publicacion_id, pieza_id, cuerpo):
        return self._resolver("actualizar_plataforma", publicacion_id, pieza_id, cuerpo)

    def agregar_plataforma(self, publicacion_id, red):
        return self._resolver("agregar_plataforma", publicacion_id, red)


def _mcp(cliente: ClienteFalso) -> FastMCP:
    mcp = FastMCP("keni-tablero-test")
    registrar(mcp, cliente)  # type: ignore[arg-type] — duck typing, mismo contrato
    return mcp


def _payload(resultado) -> dict:
    assert resultado, "la tool no devolvio contenido"
    return json.loads(resultado[0].text)


async def _llamar(cliente: ClienteFalso, nombre: str, **args) -> dict:
    return _payload(await _mcp(cliente).call_tool(nombre, args))


# --- allowlists: una sola fuente (keni-shared) ------------------------------- #


def test_allowlists_vienen_de_keni_shared():
    """Las tuplas son las mismas de keni-shared (y por tanto las que re-exporta
    `keni_consola.estados`)."""
    from keni_shared import estados as compartidos

    assert ESTADOS_PLATAFORMA is compartidos.ESTADOS_PIEZA
    assert ESTADOS_PUBLICACION is compartidos.ESTADOS_PUBLICACION
    assert FLUJOS is compartidos.FLUJOS_CONTENIDO
    assert CLASES is compartidos.CLASES_PUBLICACION


# --- validaciones: cortan ANTES de tocar la red -------------------------------- #


async def test_crear_contenido_sin_titulo_no_toca_la_red():
    cliente = ClienteFalso()
    out = await _llamar(cliente, "crear_publicacion", titulo="   ")
    assert "titulo" in out["error"]
    assert cliente.llamadas == []


async def test_crear_contenido_flujo_invalido():
    cliente = ClienteFalso()
    out = await _llamar(cliente, "crear_publicacion", titulo="Pieza", flujo="virales")
    assert "Flujo invalido" in out["error"]
    assert cliente.llamadas == []


async def test_crear_contenido_clase_invalida():
    cliente = ClienteFalso()
    out = await _llamar(cliente, "crear_publicacion", titulo="Pieza", clase="epica")
    assert "Clase invalida" in out["error"]
    assert cliente.llamadas == []


async def test_mover_pieza_estado_invalido():
    cliente = ClienteFalso()
    out = await _llamar(cliente, "mover_pieza", publicacion_id="c1", pieza_id="p1", estado="listo")
    assert "Estado invalido" in out["error"]
    assert cliente.llamadas == []


async def test_actualizar_contenido_sin_campos():
    cliente = ClienteFalso()
    out = await _llamar(cliente, "actualizar_publicacion", publicacion_id="c1")
    assert "error" in out
    assert cliente.llamadas == []


async def test_actualizar_contenido_estado_invalido():
    cliente = ClienteFalso()
    out = await _llamar(cliente, "actualizar_publicacion", publicacion_id="c1", estado="terminada")
    assert "Estado invalido" in out["error"]
    assert cliente.llamadas == []


# --- caminos felices ------------------------------------------------------------ #


_ITEM = {
    "id": "c1",
    "titulo": "Final Liga MX",
    "clase": "contenido",
    "flujo": "evento",
    "marca": "claro_sports",
    "estado": "pendiente",
    "plataformas": [{"id": "p1", "red": "instagram", "red_nombre": "Instagram", "estado": "pendiente"}],
    "interno_no_expuesto": "secreto",
}


async def test_listar_tablero_resume_items_y_catalogos():
    cliente = ClienteFalso(
        respuestas={"listar_publicacion": {"contenidos": [_ITEM], "catalogos": {"marcas": [{"id": "m"}]}}}
    )
    out = await _llamar(cliente, "listar_tablero", flujo="evento")
    assert out["total"] == 1
    assert out["items"][0]["id"] == "c1"
    assert "interno_no_expuesto" not in out["items"][0]  # vista compacta, no el dict crudo
    # catalogos ausentes degradan a las allowlists compartidas
    assert out["catalogos"]["flujos"] == list(FLUJOS)
    assert out["catalogos"]["estados_plataforma"] == list(ESTADOS_PLATAFORMA)
    # los filtros viajan al cliente tal cual (el encoding es cosa del cliente HTTP)
    (metodo, args, _kw) = cliente.llamadas[0]
    assert metodo == "listar_publicacion"
    assert args[0]["flujo"] == "evento"


async def test_crear_contenido_arma_el_cuerpo():
    cliente = ClienteFalso(respuestas={"crear_publicacion": {"contenido": _ITEM}})
    out = await _llamar(
        cliente,
        "crear_publicacion",
        titulo="  Final Liga MX  ",
        flujo="evento",
        marca="claro_sports",
        redes=["instagram", "x"],
    )
    assert out["contenido"]["id"] == "c1"
    cuerpo = cliente.llamadas[0][1][0]
    assert cuerpo["titulo"] == "Final Liga MX"
    assert cuerpo["redes"] == ["instagram", "x"]
    assert cuerpo["marca"] == "claro_sports"


async def test_mover_pieza_devuelve_la_plataforma():
    cliente = ClienteFalso(
        respuestas={"actualizar_plataforma": {"plataforma": {"id": "p1", "red": "x", "estado": "en_revision"}}}
    )
    out = await _llamar(cliente, "mover_pieza", publicacion_id="c1", pieza_id="p1", estado="en_revision")
    assert out["plataforma"]["estado"] == "en_revision"
    assert cliente.llamadas[0] == ("actualizar_plataforma", ("c1", "p1", {"estado": "en_revision"}), {})


async def test_error_consola_sale_como_dict_error():
    cliente = ClienteFalso(error="La Consola rechazo la credencial (401). Revisa KENI_CONSOLA_TOKEN.")
    out = await _llamar(cliente, "listar_tablero")
    assert out["error"].startswith("La Consola rechazo la credencial")


async def test_agregar_plataforma_feliz():
    cliente = ClienteFalso(
        respuestas={"agregar_plataforma": {"plataforma": {"id": "p2", "red": "tiktok", "estado": "pendiente"}}}
    )
    out = await _llamar(cliente, "agregar_plataforma", publicacion_id="c1", red="tiktok")
    assert out["plataforma"]["red"] == "tiktok"
