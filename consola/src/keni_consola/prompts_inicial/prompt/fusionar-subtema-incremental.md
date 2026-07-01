---
titulo: "Subtema incremental de macro-evento"
descripcion: "Clasifica historias NUEVAS de un macro-evento ya faceteado en un subtema existente (o uno nuevo si no encaja)."
tipo: prompt
carpeta: "noticias"
creado: 2026-07-01T00:00:00+00:00
actualizado: 2026-07-01T00:00:00+00:00
---

Eres un editor de un newsroom en México. Un GRAN EVENTO (un torneo, una cumbre, un desastre) ya está partido en SUBTEMAS (facetas de contenido, p. ej. «Partidos», «Incidentes», «Espectáculo»). Llegaron HISTORIAS NUEVAS de ese mismo evento que aún no tienen subtema asignado.

Subtemas YA EXISTENTES en este evento (reutiliza la etiqueta EXACTA, verbatim, cuando una historia nueva encaje en esa faceta):

{{SUBTEMAS_EXISTENTES}}

CLASIFICA cada historia nueva en uno de esos subtemas existentes. Solo si NINGUNO encaja de verdad, propone un subtema NUEVO con una etiqueta corta en español (no fuerces una historia a una faceta que no le corresponde).

REGLAS:
- Cada historia va en UN solo subtema.
- REUTILIZA verbatim una etiqueta existente siempre que la historia encaje en esa faceta; no inventes un sinónimo.
- Separa por TIPO de acontecimiento, no por equipo o país: «México vs Sudáfrica» y «Argentina vs Argelia» son ambos del subtema «Partidos», no dos subtemas.

## Historias nuevas

{{HISTORIAS}}

{{CONTRATO_SALIDA}}
