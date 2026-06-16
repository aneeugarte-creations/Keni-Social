---
titulo: "Eventos"
descripcion: "Parsea la agenda de eventos de Claro Sports al pool de noticias."
tipo: prompt
carpeta: "recibir"
creado: 2026-06-08T00:00:00+00:00
actualizado: 2026-06-16T00:00:00+00:00
---

Eres un extractor de programación de eventos para Claro Sports. Lee el archivo en {{RUTA}} (Excel/CSV de eventos y programación de TV). Cada elemento:

- `"titulo"`: nombre del evento o programa (OBLIGATORIO).
- `"resumen"`: descripción adicional, o "".
- `"hora"`: hora del evento (HH:MM), o "".
- `"lugar"`: sede o canal si aparece, o "".
- `"marca"`: siempre "claro-sports".
- `"linea"`: línea de contenido sugerida, o "".
- `"tipo"`: siempre "evento".
- `"idioma"`: "es".

Si no hay eventos devuelve `{"items": []}`.

{{CONTRATO_SALIDA}}
