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
| `serie_seguidores(rango)` | Crecimiento de seguidores por día y por red (stock diario + neto del periodo). |
| `desglose_interacciones(rango)` | Likes, comentarios, compartidos, guardados y video_views por marca×red, con totales. |
| `crosstab(rango)` | Rendimiento cruzado marca×red×formato (piezas, visualizaciones, engagement, rendimiento relativo). |
| `correlacion_seguidores(rango)` | Seguidores ganados ↔ piezas publicadas por marca×red×día (correlación, no causalidad). |
| `analisis_diario(rango, marca)` | Narrativa accionable del periodo: qué subió/bajó, la pieza que lo explica y el siguiente paso. |

## Histórico

Cada lectura de `metricas_resumen` se guarda en un SQLite local (`~/.local/share/keni-metricas/historico.db`, o `KENI_METRICAS_DB`). Con dos o más lecturas de periodos distintos, `variacion_vs_anterior` pasa a ser **real** y `tendencia_historica` muestra la evolución. Desactivable con `KENI_METRICAS_HISTORICO=0`. Es local por persona, como las credenciales.

## Fuentes de datos

- **`muestra`** (por defecto): datos representativos y deterministas. El MCP funciona sin configurar nada — sirve para tests y como respaldo cuando no hay credenciales reales configuradas.
- **`real`**: las métricas reales llegan vía **Metricool** (un token por marca, plan Advanced), que ya consolida Facebook, Instagram, X, TikTok y YouTube. Ver [`../docs/credenciales.md`](../docs/credenciales.md).

## Instalación y uso (local por persona)

`keni-metricas` **depende de `keni-shared`** (la capa más baja del monorepo:
catálogo de marca, límites de plataforma, `io_atomico`, `engagement_pct`). Como
`keni-shared` no está publicado, instálalo antes desde la ruta del monorepo.

Sin permisos de admin, vía `uv` (recomendado):

```bash
uvx --with /ruta/a/keni-social/keni-shared --from /ruta/a/keni-social/mcp-metricas keni-metricas
```

O con un entorno virtual (instala primero la dependencia local):

```bash
python3 -m venv .venv
.venv/bin/pip install -e ./keni-shared    # ruta del monorepo
.venv/bin/pip install -e ./mcp-metricas
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
