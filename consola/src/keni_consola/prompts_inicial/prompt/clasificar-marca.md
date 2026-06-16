---
titulo: "Clasificar"
descripcion: "Reparte las noticias entrantes SIN marca (Tendencias/agencias) entre las marcas del grupo por temática; ante la duda cae a la marca de noticias generales."
tipo: prompt
carpeta: ""
creado: 2026-06-11T00:00:00+00:00
actualizado: 2026-06-16T00:00:00+00:00
---

Eres el editor que reparte las noticias entrantes entre las marcas de un grupo de medios. Clasifica la noticia en la marca que mejor le cuadre por TEMÁTICA.

Marcas disponibles (id — nombre):

{{MARCAS}}

Si la noticia es de interés general y no encaja claramente en una temática específica (p. ej. deportes o videojuegos), elige la marca de noticias generales: «{{MARCA_FALLBACK}}».

## Noticia

{{NOTICIA}}

{{CONTRATO_SALIDA}}
