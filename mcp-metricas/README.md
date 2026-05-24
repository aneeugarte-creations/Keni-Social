# keni-metricas

Servidor **MCP** que lee métricas de redes sociales (Meta FB/IG, YouTube, X, TikTok), multi-marca, y las expone a Claude por conversación. Corre **local por persona** con tus propias credenciales — las llaves nunca salen de tu máquina.

## Tools

| Tool | Qué hace |
|---|---|
| `listar_cuentas()` | Marcas y plataformas disponibles. Úsala primero. |
| `metricas_resumen(cuenta, rango)` | Visualizaciones, alcance, engagement y variación, con desglose por plataforma. `rango`: `semana`, `mes`, `7d`, `30d`. |
| `mejores_piezas(cuenta, rango, n)` | Las N piezas con mejor engagement. |
| `comparar_periodos(cuenta, rango_a, rango_b)` | Compara dos rangos. |

## Fuentes de datos

- **`muestra`** (por defecto): datos representativos y deterministas. El MCP funciona sin configurar nada — sirve para tests y para usar mientras llegan los permisos reales de cada plataforma.
- **`real`**: combina los adaptadores por plataforma con tus credenciales. Cada plataforma se activa cuando hay credenciales y permisos (Meta App Review, auditoría de TikTok, tier de pago de X). Ver [`../docs/credenciales.md`](../docs/credenciales.md).

## Instalación y uso (local por persona)

Sin permisos de admin, vía `uv` (recomendado):

```bash
uvx --from /ruta/a/keni-social/mcp-metricas keni-metricas   # ejecuta el servidor
```

O con un entorno virtual:

```bash
cd mcp-metricas
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/keni-metricas
```

Registrarlo en Claude Code:

```bash
claude mcp add keni-metricas -- uvx --from /ruta/a/keni-social/mcp-metricas keni-metricas
```

Configuración (opcional, para datos reales): copia `credenciales.ejemplo.toml` a `~/.config/keni-metricas/config.toml`. Ver [`../docs/despliegue-local.md`](../docs/despliegue-local.md).

## Desarrollo

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
