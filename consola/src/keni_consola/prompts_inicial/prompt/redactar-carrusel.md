---
titulo: "Carrusel"
descripcion: "Camino carrusel de Redactar: arma el panel editorial (portada paraguas + un slide por sub-historia). El Decisor ya eligió este camino."
tipo: prompt
carpeta: ""
creado: 2026-06-22T00:00:00+00:00
actualizado: 2026-06-22T00:00:00+00:00
---

PRODUCE un CARRUSEL editorial (el Decisor ya eligió este camino): esta HISTORIA agrupa {{N_NOTAS}} notas relacionadas y se cuenta como PANEL, una tarjeta por SUB-HISTORIA (agenda de conciertos, partidos del día, lista de medidas…). Declara `"tipo": "carrusel"` en el json. La PORTADA lleva el titular paraguas (ese es el `copy_in`) y añades "slides": [{"titular": "<titular corto de ESA sub-historia, sin emojis, misma línea editorial de texto-en-imagen>", "foto": <número del catálogo o 0 si ninguna>}, …] con una entrada por sub-historia (2 a {{MAX_SLIDES}}). {{CATALOGO_FOTOS}}
