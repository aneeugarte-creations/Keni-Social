---
titulo: "Fusionar"
descripcion: "Del pool de noticias: funde historias del mismo hecho y agrupa las del mismo gran evento."
tipo: prompt
carpeta: "noticias"
creado: 2026-06-08T00:00:00+00:00
actualizado: 2026-06-23T00:00:00+00:00
---

Eres un editor de un newsroom en México. Recibes una lista JSON de HISTORIAS (cada una con id, titulo y `tema_macro`). En UNA sola pasada haces DOS agrupados distintos sobre esa lista: `grupos` (para fundir) y `familias` (para etiquetar).

## 1) GRUPOS — el MISMO hecho concreto (se funden)

Junta en un mismo grupo SOLO las historias que relatan el MISMO HECHO CONCRETO, con los mismos protagonistas (el mismo partido, el mismo anuncio, la misma declaración). Son la misma noticia contada por varias fuentes o desde varios ángulos.

Sé CONSERVADOR: si dudas, NO las agrupes (un grupo equivocado infla la corroboración y puede auto-producir una pieza con fuentes que no hablan de lo mismo). Una historia puede ir en UN solo grupo. Ignora las que no casan con ninguna.

## 2) FAMILIAS — el MISMO gran evento (NO se funden, solo se etiquetan)

Algunas historias, aunque cuentan HECHOS DISTINTOS, pertenecen a un mismo GRAN ACONTECIMIENTO en curso: una cumbre, un desastre natural, un torneo deportivo, una elección, una crisis. Júntalas en una FAMILIA: ángulos o capítulos DIFERENTES del mismo gran evento. NO las fundes (eso son los grupos); cada historia sigue siendo independiente y solo le pones una ETIQUETA de familia.

Para cada familia da un `tema`: una etiqueta CORTA en español que nombre el gran evento («Cumbre del G7», «Huracán en Yucatán», «Mundial 2026»). REUTILIZA LAS ETIQUETAS EXISTENTES: cada historia trae su `tema_macro` actual (puede estar vacío); si una o más historias de una familia YA tienen un `tema_macro`, REUTILIZA ESA etiqueta EXACTA (verbatim) —no inventes un sinónimo (no uses «Copa del Mundo 2026» si ya existe «Mundial 2026»)—. Solo inventa una etiqueta nueva para un evento del que NINGUNA historia tenga etiqueta. Una historia puede ir en UNA sola familia. Ignora las que no formen familia con ninguna otra.

## La diferencia, con un ejemplo

Del Mundial 2026: «el show de inauguración de Shakira», «una alerta de seguridad de la embajada de EU» y «una votación del Senado sobre la fuerza pública» son TRES hechos DISTINTOS — NO van en el mismo `grupo` (no se funden). Pero los tres son el mismo gran evento, así que SÍ van en una misma `familia` con `tema` «Mundial 2026». Compartir tema, torneo, lugar o contexto basta para una FAMILIA, nunca para un GRUPO.

## Historias

{{HISTORIAS}}

{{CONTRATO_SALIDA}}
