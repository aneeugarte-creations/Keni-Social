# Reporte semanal de deportes (deck PPTX)

Automatiza el reporte que el equipo de redes de **Claro Sports** (piloto AMX) arma a
mano cada semana en Canva. Lo genera desde las métricas y lo entrega como una
**presentación `.pptx`** con la línea visual de la marca. Es **solo lectura**: lee
métricas y escribe un archivo local; nunca publica.

Origen: sesión con Elias (equipo de redes), 2026-05-25. Ver la nota de contexto en
`docs/contexto/2026-05-25-elias-reporte-semanal-deportes.md`.

## Qué rango cubre (el reporte del lunes)

Por defecto el deck cubre la **semana natural cerrada**: **lunes → domingo** de la
semana inmediatamente anterior, **domingo incluido**. Es el rango `semana_cerrada` y
**no depende del día** en que se corra: el lunes a las 10:00 da exactamente la semana
que acaba de cerrar (issue #141). El deck muestra el periodo concreto (p. ej. "18 may
— 24 may 2026") en la portada y la previsualización. Quedan disponibles los rangos
rodantes (`semana`/`7d`/`mes`/`30d`, que terminan **hoy**) por si se quiere otra ventana.

## Qué lleva el reporte

1. **Mejores piezas de la semana**, una lámina por plataforma:
   - Top 3 de **Instagram**, top 3 de **TikTok**, top 3 de **Facebook**.
   - Criterio de orden: **visualizaciones + interacciones**.
   - Por cada pieza: visualizaciones, interacciones y el **link**.
2. **Promoción de cuentas hermanas**: posteos de la semana de **Claro Sports TV** y
   **Csport Golf**, para seguir dándoles difusión. Cada cuenta se **rotula** por
   procedencia: `muestra` (datos sintéticos), `real`, o **`sin datos reales`** si la
   fuente real no tiene esa cuenta todavía (faltan permisos Meta/TikTok) — en ese caso
   **no se inventan cifras** (honestidad, regla de producto).
3. **Agenda editorial de la próxima semana**:
   - **Eventos principales** (externos que cubrimos): qué son y qué vamos a hacer.
   - **Transmisiones propias**: qué vamos a tener y cómo lo vamos a hacer.

## Cómo se usa

Requiere el extra `deck` (trae `python-pptx` para el `.pptx` y `reportlab` para el PDF):

```bash
pip install "keni-metricas[deck]"

# deck del lunes (semana cerrada lun->dom por defecto), con la agenda curada a mano
keni-reporte-deck --agenda agenda-editorial.toml --salida reporte-semana.pptx

# datos estructurados (sin render), p. ej. para depurar o integrar
keni-reporte-deck --formato json

# PDF NATIVO (reportlab, sin LibreOffice)
keni-reporte-deck --formato pdf --salida reporte-semana.pdf

# pptx + PDF nativo de una vez
keni-reporte-deck --agenda agenda-editorial.toml --pdf
```

Opciones: `--rango` (`semana_cerrada` def. | `semana` | `mes` | `7d` | `30d`), `--top`
(piezas por plataforma, def. 3), `--agenda`, `--salida`, `--formato` (`pptx` | `pdf` |
`json`), `--pdf` (genera además el PDF nativo junto al `.pptx`).

## La agenda (curaduría manual)

Las fuentes editoriales son manuales, según los gustos del público: los recurrentes
(fútbol, tenis, básquetbol, béisbol y transmisiones propias) más ocasionales como UFC.
Se escriben en un TOML, una tabla `[[evento]]` por evento:

```toml
[[evento]]
nombre = "Champions League — Semifinal (ida)"
plan = "Cobertura en vivo, clips de goles y reel de previa."
tipo = "principal"   # evento externo que cubrimos

[[evento]]
nombre = "Claro Sports presenta: Camino al Mundial 2026"
plan = "Promo del especial + cápsulas diarias."
tipo = "propio"      # transmisión propia
```

Plantilla lista para copiar: `mcp-metricas/agenda-editorial.ejemplo.toml`. Si no se
pasa `--agenda`, el deck se genera igual con la sección de agenda como pendiente.

## De dónde salen los datos

- Métricas y piezas: el MCP `keni-metricas`. Las piezas ya traen plataforma,
  visualizaciones, interacciones y URL.
- Con la fuente `muestra` (por defecto, offline) el deck funciona desde el día 1 con
  datos representativos. Con credenciales reales (`fuente = "real"`) usa los datos de
  cada plataforma. Claro Sports TV y Csport Golf están dadas de alta como cuentas.
- Top-3 **por plataforma** (no global): `FuenteMuestra.mejores_por_plataforma`
  garantiza n por plataforma; para otras fuentes hay un camino portable que agrupa el
  pool de `mejores_piezas`.

## Diseño

- El núcleo vive en `mcp-metricas/src/keni_metricas/reporte_deck.py`. `python-pptx` y
  `reportlab` son dependencias **opcionales** (`[deck]`) e importadas de forma
  **perezosa** en el MCP.
- `construir_reporte_deportes(...)` arma un dict JSON-serializable (con `periodo` y la
  procedencia de cada cuenta hermana); `render_pptx(...)` produce la presentación y
  `render_pdf(...)` el **PDF nativo** (reportlab, Python puro, sin binarios externos),
  ambos con la misma estructura de láminas y la línea visual roja de Claro Sports.
- El rango `semana_cerrada` se resuelve en `schema.semana_cerrada(...)`: lunes→domingo
  de la última semana natural cerrada, anclado al calendario (no relativo a hoy).
- **Integrado en la Consola** (página "Reporte deportes"): backend
  `consola/src/keni_consola/api/reporte_deportes.py` (`GET /opciones`, `POST /preview`,
  `POST /export.pptx`, `POST /export.pdf`) + frontend `frontend/src/pages/ReporteDeportes.tsx`
  (selector de rango, editor de agenda, previsualización por plataforma y descarga del
  `.pptx` o `.pdf`). El equipo no necesita la CLI.

## Pendiente / siguientes pasos

- Plantilla(s) de imagen para la línea visual de Claro Sports (ver `estudio-imagen.md`).
