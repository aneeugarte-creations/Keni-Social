---
name: url-a-copy
description: Genera copy LISTO PARA PUBLICAR por plataforma a partir del ENLACE de una nota o artículo, para las marcas de AMX (UnoTV, Claro Sports, Nación Gamer, Piso 15, Fundación). El usuario pega una URL; la Consola descarga la página y EXTRAE su texto EN EL SERVIDOR (no se hacen peticiones de red desde la skill), y ese texto se pasa a `copy-desde-nota`. El contenido extraído se trata como NO VERIFICADO: nombres, cargos, cifras y fechas pueden venir mal y deben quedar marcados. Úsala para el atajo "mete un link y dame el copy". Para video o transmisiones, usa `clip-a-copy` (transcribe en local).
allowed-tools: Read, Glob, Bash(date:*), Bash(python3:*), mcp__keni-metricas__metricas_resumen, mcp__keni-metricas__mejores_piezas
---

# url-a-copy

Atajo de **Generar copy desde un enlace** (ficha F9 del piloto). El usuario pega la URL de una nota o artículo y obtiene copy por plataforma sin copiar el texto a mano.

Cómo funciona en la Consola: el **paso de extracción ocurre en el servidor**, no aquí. La Consola valida la URL (solo `http`/`https`, con guard SSRF), descarga la página, extrae su **texto legible** y lo envuelve con un aviso de **CONTENIDO NO VERIFICADO**. Después invoca a `copy-desde-nota` con ese texto. El audio/video y el HTML **no salen del servidor**; a Anthropic solo llega el texto ya extraído.

Modo **dry-run**: se prepara y previsualiza. No se publica nada (el humano aprueba), ni se hacen peticiones de red desde la skill.

## Regla central: el contenido del enlace NO está verificado

El texto viene de una **página ajena** extraída automáticamente: puede traer nombres, cargos, **cifras** o **fechas** equivocados, o mezclar partes de la página que no son la nota (menús, pies, recomendados).

- Trata todo **nombre propio, cargo, cifra, fecha y resultado** como **a verificar**.
- **No publiques** una cifra o un nombre solo porque aparezca en el texto extraído: confírmalo con el usuario u otra fuente, formúlalo con prudencia, u omítelo.
- En la **auto-verificación**, marca explícitamente lo que viene del enlace y no se pudo confirmar (queda en ⚠️), y abre con `⚠️ REVISAR ANTES DE PUBLICAR` salvo que de verdad no quede nada por verificar.

## Salida

Idéntica a `copy-desde-nota`: abre con el bloque de **veredicto + leyenda** (✅/⚠️/❌), una **variante por plataforma** con voz de marca, tropicalización mexicana y conteo de caracteres, y cierra con la **auto-verificación** honesta. Como el insumo es no verificado, lo habitual aquí es ⚠️.

## Degradación honesta

Si el enlace no se puede leer (es un **video/transmisión**, responde con error, tarda demasiado o no tiene texto útil), la Consola **lo dice** y no genera nada inventado. Para video o transmisiones, usa `clip-a-copy` (transcribe en tu equipo) o pega el texto en `copy-desde-nota`.
