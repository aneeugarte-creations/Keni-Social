# Despliegue local por persona

El MCP corre en la máquina/entorno de cada persona (no hay hosting central). Aquí están las formas de instalarlo, pensadas para **máquinas corporativas bloqueadas** (sin permisos de admin).

## Opción 1 — `uv` (recomendada, sin admin)

`uv`/`uvx` se instala en espacio de usuario (no requiere admin):

```bash
# instalar uv una vez (espacio de usuario)
curl -LsSf https://astral.sh/uv/install.sh | sh

# correr el MCP directamente desde el repo
uvx --from /ruta/a/keni-social/mcp-metricas keni-metricas

# registrarlo en Claude Code
claude mcp add keni-metricas -- uvx --from /ruta/a/keni-social/mcp-metricas keni-metricas
```

## Opción 2 — entorno virtual

```bash
cd /ruta/a/keni-social/mcp-metricas
python3 -m venv .venv && .venv/bin/pip install -e .
claude mcp add keni-metricas -- /ruta/a/keni-social/mcp-metricas/.venv/bin/keni-metricas
```

O en `.mcp.json` del proyecto:

```json
{
  "mcpServers": {
    "keni-metricas": {
      "command": "/ruta/a/keni-social/mcp-metricas/.venv/bin/keni-metricas",
      "env": { "KENI_METRICAS_FUENTE": "muestra" }
    }
  }
}
```

## Opción 3 — Claude Code en la nube de Keni (máquina muy bloqueada)

Quien no pueda instalar nada localmente usa el Claude Code en la nube de Keni desde el navegador, con el MCP corriendo **dentro de su propio entorno** en ese servidor (mismo comando que la opción 1/2). Las credenciales siguen siendo **por persona** dentro de su entorno.

## Configuración

- Por defecto (`fuente = "muestra"`) no hace falta configurar nada.
- Para datos reales: `~/.config/keni-metricas/config.toml` (ver `docs/credenciales.md`). Variables útiles:
  - `KENI_METRICAS_FUENTE=muestra|real`
  - `KENI_METRICAS_CONFIG=/ruta/al/config.toml`

## Comprobar que funciona

```bash
claude mcp list                      # debe aparecer keni-metricas
# en una sesión de Claude:
> usa listar_cuentas
> usa metricas_resumen con cuenta claro_sports y rango semana
```
