# keni-metricas

Servidor **MCP** que lee métricas de redes sociales (Meta FB/IG, YouTube, X, TikTok), multi-marca, y las expone a Claude por conversación. Corre **local por persona** con tus propias credenciales — las llaves nunca salen de tu máquina.

## Tools

| Tool | Qué hace |
|---|---|
| `listar_cuentas()` | Marcas y plataformas disponibles. Úsala primero. |
| `metricas_resumen(cuenta, rango)` | Visualizaciones, alcance, engagement y variación, con desglose por plataforma. `rango`: `semana`, `mes`, `7d`, `30d`. |
| `mejores_piezas(cuenta, rango, n)` | Las N piezas con mejor engagement. |
| `comparar_periodos(cuenta, rango_a, rango_b)` | Compara dos rangos. |
| `tendencia_historica(cuenta, rango, n)` | Evolución de las últimas n lecturas guardadas. |
| `reporte_consolidado(rango, top)` | Informe de TODAS las marcas en un rango (total + desglose + mejores piezas). |
| `picos(rango, umbral_pct)` | Alerta proactiva: piezas que despuntan sobre la media y cuentas que se desvían de su baseline. |

## Histórico

Cada lectura de `metricas_resumen` se guarda en un SQLite local (`~/.local/share/keni-metricas/historico.db`, o `KENI_METRICAS_DB`). Con dos o más lecturas de periodos distintos, `variacion_vs_anterior` pasa a ser **real** y `tendencia_historica` muestra la evolución. Desactivable con `KENI_METRICAS_HISTORICO=0`. Es local por persona, como las credenciales.

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

## Reporte consolidado (CLI / cron)

El comando `keni-reporte` arma el informe de todas las marcas y lo escribe en Markdown o JSON — pensado para correr headless o por cron (resuelve la consolidación manual de métricas):

```bash
keni-reporte --rango mes --formato md --salida reporte-mayo.md
keni-reporte --rango semana --formato json        # a stdout
```

La misma información está disponible como tool MCP `reporte_consolidado` para pedirla por conversación. Con `--picos` añade una sección de **alertas** (anomalías).

### Por cron (entrega automática, con red de seguridad)

`scripts/cron-reporte.sh` corre el reporte+picos por launchd/cron: usa un lock para no solaparse, registra en log, escribe a un archivo fechado y **solo lee** (nunca publica). Configurable por entorno:

```bash
KENI_REPORTE_RANGO=semana KENI_REPORTE_DIR="$HOME/keni-reportes" scripts/cron-reporte.sh
```

## Desarrollo

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
