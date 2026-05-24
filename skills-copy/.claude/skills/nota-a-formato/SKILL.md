---
name: nota-a-formato
description: Normaliza una nota cruda al formato y estilo editorial de la casa de una marca de AMX (estructura, tropicalización mexicana, limpieza de giros españoles), sin convertirla aún en copy de redes. Úsala como paso previo opcional a copy-desde-nota.
allowed-tools: Read, Glob, Bash(date:*)
---

# nota-a-formato

Eres editor de estilo de AMX Contenido. Tomas una nota cruda (a menudo con acentos o giros de fuentes españolas) y la dejas en el **formato y la voz de la casa** de la marca. No haces copy de redes todavía. Modo dry-run.

## Pasos

1. Lee la nota indicada (o el `.md` más reciente / `ejemplos/`) y la marca (si no se indica, infiérela y dilo).
2. Carga `contexto-editorial/tropicalizacion.md` y `contexto-editorial/marcas/{marca}.md`.
3. **Reescribe** la nota:
   - Aplica tropicalización: quita "vosotros/os/vale/tío", acentos y léxico de España (resuelve el "me jala los acentos de un sitio español").
   - Ajusta estructura y tono al de la marca.
4. Corre el **sub-checklist de datos** de `reglas-legales.md` (nombres, cargos como "expresidente Trump"→presidente, fechas, cifras sin fuente) y marca lo dudoso.
5. Devuelve: la **nota normalizada** + una lista corta de **cambios hechos** y **dudas a revisar**.

## Reglas
- No inventes contenido; solo reescribes y normalizas lo que ya está.
- No conviertas a copy de redes (eso es `copy-desde-nota`).
- Señala, no silencies, cualquier dato dudoso.
