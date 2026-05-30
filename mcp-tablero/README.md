# keni-tablero (MCP)

Servidor MCP para **controlar el tablero de contenido de la Consola Keni** desde Claude
Code. Es el lado de ESCRITURA, hermano de `keni-metricas` (solo lectura de métricas):
crear, mover y listar contenido del tablero hablando con la API HTTP de la Consola
(`/api/contenido`). La Consola sigue siendo la única fuente de verdad; este MCP no
persiste nada por su cuenta.

## Tools

- `listar_tablero(flujo, marca, estado, clase, desde, hasta)` — items del tablero + catálogos.
- `crear_contenido(titulo, flujo, marca, prioridad, descripcion, fechas, redes, clase)` — alta.
- `mover_pieza(contenido_id, plataforma_id, estado)` — cambia el estado de una fila por
  plataforma (arrastrar la tarjeta). `aprobado`/`publicado` disparan los eventos/webhooks.
- `actualizar_contenido(contenido_id, ...)` — edita el padre (estado, prioridad, responsable…).
- `agregar_plataforma(contenido_id, red)` — añade una red a un contenido existente.

## Configuración (entorno)

- `KENI_CONSOLA_URL` — base de la Consola (def `http://127.0.0.1:8765`; hosted
  `https://social.kenitech.io`).
- `KENI_CONSOLA_TOKEN` — token de la Consola (credencial de la API). Sin él, la Consola
  responde 401.
- `KENI_MCP_TRANSPORT` — `stdio` (def) | `http`. En `http`: `KENI_MCP_HOST`/`KENI_MCP_PORT`
  (def `127.0.0.1:8001`).

## Uso local

```bash
uvx --from ./mcp-tablero keni-tablero
```

Se distribuye también como parte del plugin `keni-social` (ver `.claude-plugin/plugin.json`):
Claude Code lo arranca con `uvx --from ${CLAUDE_PLUGIN_ROOT}/mcp-tablero keni-tablero`.
