---
description: Guía la comprobación previa (dry-run) de una publicación con la skill publica-meta. Muestra qué se publicaría; NO publica.
argument-hint: "[copy aprobado] [plataformas] [media]"
---

# Preview de publicación (dry-run)

Acompaña al usuario en la **comprobación final** de una publicación: mostrar EXACTO qué
se enviaría por cada plataforma (texto final, conteo de caracteres, hashtags,
hilo/carrusel, media referenciada) más avisos y una checklist humana.

Esto es **dry-run puro**: NO publica, NO toca la red. Solo enseña lo que se enviaría.

## Argumentos

`$ARGUMENTS` puede traer el copy ya aprobado, las plataformas destino y la media.

## Qué hacer

1. Usa la skill **`/keni-social:publica-meta`** como motor del preview: pásale el
   copy aprobado, las plataformas (X, Instagram, Facebook, …) y la media indicada en
   `$ARGUMENTS`. Si falta algo (copy, plataforma o media), pídelo antes de continuar.

2. Presenta el resultado del dry-run de forma legible: por plataforma, el texto final,
   el conteo de caracteres, los hashtags, si es hilo/carrusel y qué media se
   referencia, junto con cualquier aviso.

3. Termina con una checklist humana corta (qué revisar antes de publicar de verdad) y
   recuerda explícitamente que **no se ha publicado nada**. La publicación real vive
   fuera de este flujo y exige token; aquí jamás se ejecuta.
