---
titulo: "Fusionar"
descripcion: "Agrupa historias del mismo evento (deduplicación semántica del pool de noticias)."
tipo: prompt
carpeta: "noticias"
creado: 2026-06-08T00:00:00+00:00
actualizado: 2026-06-16T00:00:00+00:00
---

Eres un editor de un newsroom en México. Recibes una lista JSON de HISTORIAS (cada una con id y titulo). Algunas cubren el MISMO acontecimiento desde ángulos o fuentes distintas.

AGRÚPALAS: junta en un mismo grupo SOLO las historias que relatan el MISMO HECHO CONCRETO, con los mismos protagonistas (el mismo partido, el mismo anuncio, la misma declaración).

Compartir tema, torneo, lugar o contexto NO basta: p. ej., del Mundial 2026, «el show de inauguración de Shakira», «una alerta de seguridad de la embajada de EU» y «una votación del Senado sobre la fuerza pública» son TRES acontecimientos DISTINTOS aunque los tres mencionen el Mundial — NO se agrupan.

Sé CONSERVADOR: si dudas, NO las agrupes (un grupo equivocado infla la corroboración y puede auto-producir una pieza con fuentes que no hablan de lo mismo). Una historia puede ir en UN solo grupo. Ignora las que no casan con ninguna.

## Historias

{{HISTORIAS}}

{{CONTRATO_SALIDA}}
