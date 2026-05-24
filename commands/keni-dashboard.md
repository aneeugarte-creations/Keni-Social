---
description: Genera el dashboard HTML autocontenido (reporte + picos) y resume qué contiene. Solo lectura, no publica.
argument-hint: "[rango: semana|mes|7d|30d] [salida.html]"
allowed-tools: Bash(uvx *) Bash(uv *) Bash(python -m keni_metricas.dashboard *)
---

# Dashboard HTML de métricas

Genera el **dashboard HTML** autocontenido (un solo archivo, CSS embebido) que reúne
el reporte consolidado y las alertas de picos, y luego di al usuario dónde quedó y
qué encontrará dentro.

Esto es **solo lectura**: lee métricas y escribe un único archivo HTML local. No publica nada.

## Argumentos

`$ARGUMENTS` puede traer el rango (`semana` / `mes` / `7d` / `30d`) y/o la ruta de
salida. Por defecto: `--salida dashboard.html --rango mes --top 3`.

## Qué hacer

1. Genera el dashboard:

   ```
   python -m keni_metricas.dashboard --salida dashboard.html --rango mes --top 3
   ```

   Ajusta `--salida` y `--rango` a lo que pida `$ARGUMENTS`. Si falta `uv`/`uvx` o el
   entorno no está listo, dilo en una frase y sugiere `/keni-social:keni-doctor`.

2. Confirma la ruta del archivo HTML generado (no lo abras tú; indícale al usuario
   que lo abra en su navegador).

3. En 3-4 viñetas, describe qué incluye el dashboard: resumen por marca, mejores
   piezas (top), alertas de picos/anomalías y la cobertura de los datos. Si la
   cobertura es parcial (datos de muestra), avísalo.
