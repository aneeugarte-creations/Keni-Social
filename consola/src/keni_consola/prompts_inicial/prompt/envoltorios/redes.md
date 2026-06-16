---
titulo: "Envoltorio: piezas por red"
descripcion: "Instrucción aditiva del copy POR RED (Texto manual y flujos que piden una pieza por red): limita las redes pedidas, ancla sus límites técnicos y fija el bloque json de piezas. El código rellena {{ETIQUETAS}}, {{LIMITES}} e {{IDS_JSON}} desde el catálogo de redes y sus límites."
tipo: prompt
carpeta: "envoltorios"
creado: 2026-06-11T00:00:00+00:00
actualizado: 2026-06-11T00:00:00+00:00
---

Genera el copy SOLO para estas redes: {{ETIQUETAS}}. Límites técnicos de caracteres (no los excedas): {{LIMITES}}. Mantén tu formato y tu auto-verificación habituales. Además, al FINAL de toda tu respuesta, añade un único bloque de código cercado ```json con esta forma exacta: {"piezas": [{"red": "<id>", "texto": "<copy de esa red>", "copy_in": "<texto que va DENTRO de la imagen>"}, ...]}, usando como <id> únicamente estos valores: {{IDS_JSON}}. Incluye exactamente UNA pieza por cada red pedida (nunca dos de la misma red). Si la pieza de una red es un HILO o un CARRUSEL, va numerada DENTRO de su "texto": en un hilo, un tuit por párrafo con prefijo "1/n ", "2/n "… y cada tuit dentro del límite de la red; en un carrusel, las slides separadas por una línea con solo "---". El `copy_in` es el texto que va SOBRE la imagen (titular/claim corto), distinto del `texto` que la acompaña; respeta la línea editorial de texto-en-imagen de la marca adjunta, sale siempre sin emojis y deja "" si la pieza no lleva imagen.
