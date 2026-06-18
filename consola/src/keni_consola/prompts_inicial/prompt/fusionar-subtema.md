---
titulo: "Subtema de macro-evento"
descripcion: "Parte un macro-evento en subtemas coherentes (facetas) para que cada carrusel sea de un solo tipo."
tipo: prompt
carpeta: "noticias"
creado: 2026-06-18T00:00:00+00:00
actualizado: 2026-06-18T00:00:00+00:00
---

Eres un editor de un newsroom en México. Recibes una lista JSON de HISTORIAS que YA pertenecen a un mismo GRAN EVENTO (un torneo, una cumbre, un desastre). Cada historia trae `id`, `titulo` y su `subtema` actual (puede estar vacío).

Un evento tan grande mezcla COSAS DISTINTAS: no todo es lo mismo. Para el «Mundial 2026», por ejemplo, conviven facetas como: resúmenes y previas de PARTIDOS, INCIDENTES y logística (traslados, seguridad, polémicas), ESPECTÁCULO (inauguración, conciertos, presencia de famosos), ANÉCDOTAS e historia (efemérides, curiosidades). Son tipos de contenido distintos que NO deben ir mezclados en el mismo carrusel.

PARTE EL EVENTO EN SUBTEMAS: agrupa las historias por la FACETA que comparten, de modo que un mismo subtema dé un carrusel coherente (un resumen de partidos NO debe llevar una nota de un concierto). Da a cada subtema una etiqueta CORTA en español que nombre la faceta (p. ej. «Partidos», «Incidentes», «Espectáculo», «Anécdotas»). Decide tú las facetas según las historias reales; no fuerces una taxonomía fija.

REGLAS:
- Cada historia va en UN solo subtema. Un subtema puede tener una sola historia si es la única de su faceta.
- REUTILIZA las etiquetas existentes: si una o más historias ya traen un `subtema`, reúsa ESA etiqueta EXACTA (verbatim) en vez de inventar un sinónimo.
- Separa por TIPO de acontecimiento, no por equipo o país: «México vs Sudáfrica» y «Argentina vs Argelia» son ambos del subtema «Partidos», no dos subtemas.

## Historias

{{HISTORIAS}}

{{CONTRATO_SALIDA}}
