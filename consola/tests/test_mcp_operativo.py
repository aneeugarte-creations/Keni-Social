"""Tests del servidor MCP operativo (`mcp_operativo` + montaje en `app.crear_app`).

Cubre lo NOVEDOSO y arriesgado de esta capa, sin pasar por el protocolo MCP en cable:

  - Montaje condicional: sin `KENI_MCP_BEARER` no se monta `/mcp` (despliegue intacto);
    con bearer, el endpoint existe y EXIGE el bearer (401 sin/!= bearer).
  - `ClienteConsola`: llama a la API en proceso con una SESIÓN del dueño, de modo que
    las acciones quedan ATRIBUIDAS a ese usuario (no "sin autor" como el token).
  - Renovación de sesión: ante un 401 (sesión caducada) re-mintea y reintenta.
  - Registro de tools: las tools esperadas están registradas en el FastMCP.

Todo OFFLINE: la API se sirve EN PROCESO (httpx ASGITransport); nunca se abre un socket
ni se llama a `claude`. Requiere Postgres de pruebas (fixture `entorno`), como el resto.
"""

from __future__ import annotations

import anyio
import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, mcp_operativo

BEARER = "bearer-mcp-de-prueba-0123456789"
OWNER = "duena"
OWNER_PASS = "contraseña-larga-de-prueba"


def _crear_owner_admin() -> str:
    """Crea (idempotente) un admin sin `debe_cambiar_password` y devuelve su nombre."""
    if auth.autenticar(OWNER, OWNER_PASS) is None:
        auth.crear_usuario(OWNER, OWNER_PASS, rol="admin", debe_cambiar_password=False)
    return OWNER


# --------------------------------------------------------------------------- #
# Montaje condicional + guard del bearer                                       #
# --------------------------------------------------------------------------- #


def test_sin_bearer_no_se_monta_mcp(entorno, monkeypatch):
    """Sin `KENI_MCP_BEARER`, `/mcp` no se monta: cae al catch-all del SPA (no 401)."""
    monkeypatch.delenv("KENI_MCP_BEARER", raising=False)
    with TestClient(app_modulo.crear_app(token="t", bootstrap=False)) as cliente:
        r = cliente.get("/mcp")
    # No hay guard ni endpoint MCP: la ruta cae al SPA (200 HTML), nunca 401 del MCP.
    assert r.status_code != 401


def test_con_bearer_exige_autorizacion(entorno, monkeypatch):
    """Con bearer configurado, `/mcp` responde 401 sin bearer o con uno incorrecto."""
    monkeypatch.setenv("KENI_MCP_BEARER", BEARER)
    monkeypatch.setenv("KENI_MCP_USUARIO", OWNER)
    with TestClient(app_modulo.crear_app(token="t", bootstrap=False)) as cliente:
        sin = cliente.get("/mcp")
        malo = cliente.get("/mcp", headers={"Authorization": "Bearer no-es"})
        # Con el bearer correcto se PASA el guard; el MCP responde su propio status (un GET
        # sin las cabeceras de streamable-HTTP da 4xx del MCP, p.ej. 405/406, pero NO 401).
        bueno = cliente.get("/mcp", headers={"Authorization": f"Bearer {BEARER}"})
    assert sin.status_code == 401
    assert malo.status_code == 401
    assert bueno.status_code != 401


# --------------------------------------------------------------------------- #
# ClienteConsola: sesión del dueño + atribución + renovación                   #
# --------------------------------------------------------------------------- #


def test_cliente_opera_como_dueno_y_atribuye(entorno):
    """Crear contenido vía el cliente in-proceso lo atribuye al usuario del MCP."""
    _crear_owner_admin()
    app = app_modulo.crear_app(token="t", bootstrap=False)
    cli = mcp_operativo.ClienteConsola(app, OWNER)

    async def flujo():
        creado = await cli.post("/api/contenido", {"titulo": "Pieza MCP", "prioridad": "alta"})
        assert "error" not in creado, creado
        pieza = creado["contenido"]
        assert pieza["titulo"] == "Pieza MCP"
        # ATRIBUCIÓN: el autor es el usuario del MCP (no "sin autor" como el token).
        assert pieza["autor_nombre"] == OWNER
        # Aparece al listar.
        listado = await cli.get("/api/contenido")
        ids = [c["id"] for c in listado["contenidos"]]
        assert pieza["id"] in ids
        await cli.aclose()

    anyio.run(flujo)


def test_cliente_token_token_vacio_sin_usuario(entorno):
    """Si no hay usuario al que atribuir, el cliente degrada con un error claro (no rompe)."""
    app = app_modulo.crear_app(token="t", bootstrap=False)
    cli = mcp_operativo.ClienteConsola(app, "no-existe-nadie")

    async def flujo():
        # Sin usuarios en la BD, `_mintar_sesion` no resuelve id -> error explicativo.
        r = await cli.get("/api/contenido")
        assert "error" in r
        await cli.aclose()

    anyio.run(flujo)


def test_cliente_renueva_sesion_tras_401(entorno):
    """Si la sesión se invalida (401), el cliente re-mintea y reintenta una vez."""
    _crear_owner_admin()
    app = app_modulo.crear_app(token="t", bootstrap=False)
    cli = mcp_operativo.ClienteConsola(app, OWNER)

    async def flujo():
        primera = await cli.get("/api/contenido")
        assert "error" not in primera, primera
        # Invalida la sesión vigente: el siguiente request debe re-mintear y volver a pasar.
        auth.borrar_sesion(cli._cookie)
        segunda = await cli.get("/api/contenido")
        assert "error" not in segunda, segunda
        await cli.aclose()

    anyio.run(flujo)


# --------------------------------------------------------------------------- #
# Registro de tools                                                            #
# --------------------------------------------------------------------------- #


def test_tools_registradas(entorno):
    """El servidor MCP registra el set de tools esperado (creación/gestión/aprobación/datos)."""
    servidor = mcp_operativo.crear_servidor(OWNER)

    async def nombres():
        return {t.name for t in await servidor._mcp.list_tools()}

    tools = anyio.run(nombres)
    esperadas = {
        "keni_contexto", "keni_metricas_opciones",
        "keni_listar_contenido", "keni_crear_contenido", "keni_actualizar_contenido",
        "keni_generar_copy", "keni_estado_generacion", "keni_listar_generaciones",
        "keni_listar_publicaciones", "keni_detalle_publicacion",
        "keni_cola_aprobacion", "keni_enviar_a_revision", "keni_aprobar", "keni_rechazar",
        "keni_panel", "keni_tuberia", "keni_resumen_dia",
        "keni_metricas_reporte", "keni_metricas_analisis", "keni_metricas_piezas",
    }
    faltan = esperadas - tools
    assert not faltan, f"faltan tools: {faltan}"
    # Techo de seguridad: NO debe haber tool de publicar/programar real.
    assert not {n for n in tools if "publicar" in n or "programar" in n or "metricool" in n}


@pytest.mark.parametrize("tool", ["keni_crear_contenido", "keni_aprobar", "keni_panel"])
def test_tools_invocables_via_call_tool(entorno, tool):
    """`call_tool` invoca las tools en proceso (humo del registro + holder del cliente)."""
    _crear_owner_admin()
    api_app = app_modulo.crear_app(token="t", bootstrap=False)
    servidor = mcp_operativo.crear_servidor(OWNER)
    servidor.holder.cliente = mcp_operativo.ClienteConsola(api_app, OWNER)

    args = {
        "keni_crear_contenido": {"titulo": "Desde call_tool", "prioridad": "media"},
        "keni_aprobar": {"publicacion_id": "no-existe"},
        "keni_panel": {},
    }[tool]

    async def invocar():
        res = await servidor._mcp.call_tool(tool, args)
        await servidor.holder.cliente.aclose()
        return res

    res = anyio.run(invocar)
    # call_tool no debe lanzar; devuelve contenido (dict estructurado o bloques).
    assert res is not None
