---
titulo: "Priorizar"
descripcion: "Extrae las keywords y temas de la línea editorial de una marca para priorizar el pool."
tipo: prompt
carpeta: "noticias"
creado: 2026-06-08T00:00:00+00:00
actualizado: 2026-06-08T00:00:00+00:00
---

Eres un analista editorial del equipo de redes de una empresa de medios en México. Lee la LÍNEA EDITORIAL de la marca «{{MARCA}}» y extrae su PERFIL de cobertura: las palabras y frases clave (temas, secciones, entidades, coberturas típicas) que definen QUÉ publica esta marca, para poder puntuar qué noticias le encajan. Devuelve entre 10 y {{MAX_KEYWORDS}} términos, en minúsculas, sin acentos, concretos (p. ej. 'liga mx', 'seleccion mexicana', 'box'), no genéricos ('noticia', 'contenido'). Devuelve EXCLUSIVAMENTE un objeto JSON con la forma {"keywords": ["...", "..."]} sin ningún texto adicional ni ```json.

Línea editorial de «{{MARCA}}»:
{{EDITORIAL}}
