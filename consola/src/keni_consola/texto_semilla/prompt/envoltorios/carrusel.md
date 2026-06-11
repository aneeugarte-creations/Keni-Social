---
titulo: "Envoltorio: decisión de carrusel"
descripcion: "Bloque que se añade al copy unificado cuando la historia agrupa 2+ notas: el modelo decide entre post y carrusel editorial. El código rellena {{N_NOTAS}}, {{MAX_SLIDES}} y {{CATALOGO_FOTOS}} (catálogo numerado de fotos propias)."
tipo: prompt
carpeta: "envoltorios"
creado: 2026-06-11T00:00:00+00:00
actualizado: 2026-06-11T00:00:00+00:00
---

DECIDE además el `tipo` de salida y decláralo en el json: esta HISTORIA agrupa {{N_NOTAS}} notas relacionadas. Elige "carrusel" SOLO si gana contándose como PANEL (una tarjeta por sub-historia: agenda de conciertos, partidos del día, lista de medidas…): la PORTADA lleva el titular paraguas (ese es el `copy_in`) y añades "slides": [{"titular": "<titular corto de ESA sub-historia, sin emojis, misma línea editorial de texto-en-imagen>", "foto": <número del catálogo o 0 si ninguna>}, …] con una entrada por sub-historia (2 a {{MAX_SLIDES}}). Si la historia es UNA sola noticia contada por varios medios, elige "post" y NO incluyas "slides". Ante la duda, "post". {{CATALOGO_FOTOS}}
