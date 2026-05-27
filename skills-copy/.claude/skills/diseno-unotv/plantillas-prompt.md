# Plantillas de prompt — UnoTV

Puntos de partida que el Skill personaliza con el material y la guía. Los `{…}` se rellenan; los textos visibles van en español tal cual deben aparecer. Sustituye los valores `[VERIFICAR]` por los de `guia-diseno.md` cuando se confirmen. **Recuerda: en noticia, la foto real es el material; evita generar escenas falsas.**

---

## A) Portada de vídeo vertical 9:16 (Reels / TikTok / Shorts)

### A.1 — Editar el frame real de la nota (recomendado · Nano Banana / Gemini)
```
Sobre esta imagen (foto real de la nota), crea una portada vertical 9:16 para Reels con la identidad de UnoTV:
- Aplica un degradado oscuro de abajo hacia arriba para legibilidad, sin dramatizar la imagen.
- Titular claro y directo (el hecho), sans seria peso bold, color blanco: "{TITULAR = EL HECHO}". Colócalo en el tercio inferior, SIN bajar de los 420 px inferiores (zona segura).
- Si es urgente: etiqueta pequeña "ÚLTIMA HORA" en bloque rojo {#E30613 [VERIFICAR]} arriba; si no, etiqueta de categoría.
- Deja libres los 220 px superiores para el logo (esquina superior {lado}).
- Sobriedad: sin adornos, sin estética deportiva. No alteres el contenido de la foto.
- No cambies datos ni añadas elementos que no estén en la imagen.
```

### A.2 — Titular bien renderizado (Ideogram)
```
Vertical 9:16 news cover, UnoTV style: sober, credible, high contrast, clean.
Background: {describe la foto real de la nota}. Dark gradient at the bottom for legibility.
Clear bold serious sans headline (normal case, not condensed) reading exactly: "{TITULAR}".
Small red {#E30613} category/breaking tag at top. Leave top and bottom safe margins clear. Newsroom look, not sporty.
```

### A.3 — Instrucciones Canva (ejecución manual)
```
Plantilla 9:16. Foto real de la nota a sangre. Capa: degradado oscuro inferior.
Titular sans seria bold, caja normal, blanco, "{TITULAR}", por encima de los 420 px inferiores.
Etiqueta roja {#E30613 [VERIFICAR]} "ÚLTIMA HORA"/categoría arriba. Logo UnoTV esquina superior {lado}, discreto.
Revisar: dato sin errata, texto fuera de zonas inseguras, contraste alto, sobriedad.
```

---

## B) Post / portada IG-Facebook 4:5 (1080×1350)

### B.1 — Nano Banana / Gemini (editar)
```
Convierte esta foto de la nota en un post 4:5 de UnoTV:
- Foco claro en {sujeto/escena}. Degradado oscuro para legibilidad.
- Titular = el hecho, una o dos líneas, blanco, legible (>64 px equivalentes): "{TITULAR}".
- Etiqueta roja {#E30613 [VERIFICAR]} de categoría/última hora pequeña. Logo arriba {lado}.
- Sobrio, creíble, alto contraste. No dramatices ni alteres la imagen.
```

### B.2 — DALL·E / GPT-Image (solo gráfico ilustrativo, no hecho real)
```
4:5 clean news graphic, UnoTV look: sober, red {#E30613} accent, high contrast, lots of clarity.
Use ONLY for clearly illustrative/conceptual graphics (e.g., infografía), never to fabricate a real event.
Scene/concept: {describe}. Leave clean space for a headline.
```

---

## C) Carrusel IG (varias 4:5)

```
Slide 1 (portada/gancho): foto real + titular-gancho "{EL HECHO}". Decide el clic — aquí se gana el engagement.
Slides 2-N: desarrollo del hecho, un punto por slide (qué / dónde / cuándo / por qué), misma rejilla y tipografía sobria.
Slide final: cierre + fuente atribuida + CTA suave ("síguenos", "lee la nota").
En todas: logo arriba {lado}, etiqueta roja {#E30613 [VERIFICAR]} puntual, alto contraste, cero erratas.
```

---

## D) Gráficos sobre vídeo IG / Facebook

### D.1 — Portada (primer frame)
Aplica A o B según orientación.

### D.2 — Lower-third / rótulo
```
Sobre este frame, añade un lower-third de UnoTV: barra sobria inferior, nombre en blanco "{NOMBRE}" y
cargo más pequeño "{CARGO}", acento rojo fino {#E30613 [VERIFICAR]} opcional. En zona segura, sin tapar la imagen.
```

### D.3 — Cintillo "última hora"
```
Añade un cintillo de última hora: banda roja {#E30613 [VERIFICAR]} con texto blanco breve "{TITULAR BREVE}".
Sobrio, sin tapar la imagen, dentro de zona segura. (Usa el dato real; no inventes.)
```

---

## Recordatorio
Todo prompt debe respetar: **zonas seguras**, **un solo titular claro = el hecho**, **cero erratas en datos visibles**, **sobriedad** (sin estética deportiva), **contraste/legibilidad móvil**, **logo bien puesto**, **sensibilidad** en notas delicadas, y los **antipatrones** de la guía (bandera con escudo, sensacionalismo, menores). Verifica el resultado en el Paso 3 del Skill.
