# Reporte semanal de deportes (deck PPTX)

Automatiza el reporte que el equipo de redes de **Claro Sports** (piloto AMX) arma a
mano cada semana en Canva. Lo genera desde las métricas y lo entrega como una
**presentación `.pptx`** con la línea visual de la marca. Es **solo lectura**: lee
métricas y escribe un archivo local; nunca publica.

Origen: sesión con Elias (equipo de redes), 2026-05-25. Ver la nota de contexto en
`docs/contexto/2026-05-25-elias-reporte-semanal-deportes.md`.

## Qué lleva el reporte

1. **Mejores piezas de la semana**, una lámina por plataforma:
   - Top 3 de **Instagram**, top 3 de **TikTok**, top 3 de **Facebook**.
   - Criterio de orden: **visualizaciones + interacciones**.
   - Por cada pieza: visualizaciones, interacciones y el **link**.
2. **Promoción de cuentas hermanas**: algunos posteos de la semana de **Claro Sports
   TV** y **Csport Golf**, para seguir dándoles difusión.
3. **Agenda editorial de la próxima semana**:
   - **Eventos principales** (externos que cubrimos): qué son y qué vamos a hacer.
   - **Transmisiones propias**: qué vamos a tener y cómo lo vamos a hacer.

## Cómo se usa

Requiere el extra `deck` (trae `python-pptx`):

```bash
pip install "keni-metricas[deck]"

# deck completo de la semana, con la agenda curada a mano
keni-reporte-deck --rango semana --agenda agenda-editorial.toml --salida reporte-semana.pptx

# datos estructurados (sin render), p. ej. para depurar o integrar
keni-reporte-deck --formato json --rango semana

# además del pptx, intenta exportar PDF (si hay LibreOffice instalado)
keni-reporte-deck --rango semana --agenda agenda-editorial.toml --pdf
```

Opciones: `--rango` (`semana`|`mes`|`7d`|`30d`, def. `semana`), `--top` (piezas por
plataforma, def. 3), `--agenda`, `--salida`, `--formato` (`pptx`|`json`), `--pdf`.

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

- Vive en `mcp-metricas/src/keni_metricas/reporte_deck.py`. `python-pptx` es una
  dependencia **opcional** (`[deck]`) e importada de forma **perezosa**: el servidor
  MCP y la consola no la cargan.
- `construir_reporte_deportes(...)` arma un dict JSON-serializable (sirve para JSON o
  para alimentar otro render); `render_pptx(...)` produce la presentación.

## Pendiente / siguientes pasos

- Integración en la consola (botón "generar reporte semanal").
- Exportación PDF nativa sin depender de LibreOffice.
- Plantilla(s) de imagen para la línea visual de Claro Sports (ver `estudio-imagen.md`).
