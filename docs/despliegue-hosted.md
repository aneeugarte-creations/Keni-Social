# Despliegue hosted (MCP sobre HTTP)

Esta es la **mitad *hosted* de la arquitectura híbrida** de `keni-metricas`:

- **Local por persona (stdio).** El MCP corre en la máquina de cada quien con sus propias credenciales, que nunca salen del equipo. Ver `docs/despliegue-local.md` y `docs/credenciales.md`. Es el modo por defecto.
- **Hosted por Keni (HTTP).** Keni hospeda el MCP de métricas de forma central y lo expone sobre **streamable-HTTP**, usando **tokens de Meta de System User** (que **no caducan**). Así no hay renovación manual del token cada ~60 días, como sí ocurre con los tokens de usuario.

Ambos modos son el mismo servidor: solo cambia el **transporte**.

## Cómo se elige el transporte

El transporte se selecciona por variable de entorno:

| Variable | Valores | Por defecto | Qué hace |
|---|---|---|---|
| `KENI_MCP_TRANSPORT` | `stdio` \| `http` | `stdio` | `http` activa streamable-HTTP. |
| `KENI_MCP_HOST` | host/IP | `127.0.0.1` | Interfaz de escucha (solo en `http`). |
| `KENI_MCP_PORT` | puerto | `8000` | Puerto de escucha (solo en `http`). |

El valor se normaliza (mayúsculas/espacios son indiferentes). Un `KENI_MCP_PORT` no numérico cae al `8000` por defecto.

## Correrlo en HTTP

```bash
cd /ruta/a/keni-social
python3 -m venv .venv
.venv/bin/pip install -e ./keni-shared   # dependencia local (no está en PyPI)
.venv/bin/pip install -e ./mcp-metricas

KENI_MCP_TRANSPORT=http \
KENI_MCP_HOST=0.0.0.0 \
KENI_MCP_PORT=8000 \
KENI_METRICAS_FUENTE=real \
KENI_METRICAS_CONFIG=/ruta/al/config.toml \
  .venv/bin/keni-metricas
```

El endpoint MCP queda en **`/mcp`** (p. ej. `http://HOST:PORT/mcp`). No hay que instalar nada extra para el transporte: la pila ASGI (uvicorn + starlette) viene **incluida con el SDK `mcp`**.

### API de transporte usada

Internamente, `server.py`:

1. Construye `FastMCP("keni-metricas", host=KENI_MCP_HOST, port=KENI_MCP_PORT)` — host/puerto se fijan en la **construcción** (FastMCP los lee de sus `Settings`, no del `.run()`).
2. Arranca con `mcp.run(transport="streamable-http")`.

(SDK `mcp` 1.27.x. En `stdio` se invoca `mcp.run()` sin argumentos.)

## Autenticación (bearer)

El endpoint HTTP **no** lleva auth por sí solo: hay que ponerla delante. Dos opciones:

- **Reverse proxy (recomendado para el piloto).** Un proxy (nginx/Caddy/Cloudflare) por delante valida un header `Authorization: Bearer <token>` y reenvía solo el tráfico autorizado al `127.0.0.1:8000` del MCP. Mantén `KENI_MCP_HOST=127.0.0.1` para que el puerto del MCP no quede expuesto directamente.
- **Auth nativa de FastMCP.** El `FastMCP` admite `token_verifier`/`auth` (verificación de bearer tokens / OAuth resource server) si se quiere validar dentro del propio servidor en lugar del proxy.

En cualquier caso: **TLS obligatorio** (el bearer va en claro en el header) y **nunca** se exponen las credenciales de plataforma — viven en el `config.toml` del entorno hosted, no se envían al cliente.

## Credenciales en hosted

El despliegue hosted usa **tokens de System User de Meta** (`tipo_token = "system_user"` en `config.toml`), que no caducan, así que el MCP no intenta renovarlos. Cómo obtenerlos: ver `docs/credenciales.md` (sección "Meta: token de System User").
