---
description: Genera y explica en lenguaje claro el reporte consolidado de métricas multi-marca (con picos/anomalías). Solo lectura.
argument-hint: "[rango: semana|mes|7d|30d] [top N]"
allowed-tools: Bash(uvx *) Bash(uv *) Bash(python -m keni_metricas.reporte *) Bash(keni-reporte *)
---

# Reporte consolidado de métricas

Genera el reporte consolidado de redes (todas las marcas) y, sobre él, una sección
de **picos/anomalías**, y luego explícalo en lenguaje claro para una persona no técnica.

Esto es **solo lectura**: nunca publica ni modifica datos.

## Argumentos

El usuario puede pasar: `$ARGUMENTS` (p. ej. el rango `semana` / `mes` / `7d` / `30d`
y cuántas piezas top por marca). Si no indica nada, usa `--rango mes --top 3 --picos`.

## Qué hacer

1. Corre el reporte consolidado con picos. Usa la CLI del paquete de métricas (la que
   funcione en este entorno):

   ```
   keni-reporte --rango mes --top 3 --picos
   ```

   o, equivalente, desde el repo del MCP de métricas:

   ```
   python -m keni_metricas.reporte --rango mes --top 3 --picos
   ```

   Ajusta `--rango` y `--top` a lo que el usuario haya pedido en `$ARGUMENTS`.
   Si el comando falla porque falta `uv`/`uvx` o el entorno, dilo en una frase y
   sugiere `/keni-social:keni-doctor`.

2. Lee la salida (Markdown) y explícala así, en español, sin jerga:
   - **Titular**: cómo va el conjunto de marcas en el rango.
   - **Por marca**: 1-2 frases por marca (total + sus mejores piezas).
   - **Alertas (picos)**: qué destaca por encima de la media y qué cuentas se
     desvían de su baseline; cuándo merece atención.
   - **Cobertura**: si los datos son parciales (fuente de muestra vs. real), avísalo
     para que nadie tome decisiones sobre datos incompletos.

3. Cierra con 2-3 acciones concretas sugeridas (no las ejecutes).

El equivalente conversacional son las tools MCP `reporte_consolidado` y `picos`; si
el usuario prefiere, puedes pedirlas por ahí en vez de la CLI.
