---
titulo: "Importar calendario"
descripcion: "Lee un calendario de contenido (.xlsx/CSV) y lo convierte en piezas."
tipo: prompt
carpeta: "importacion"
creado: 2026-06-08T00:00:00+00:00
actualizado: 2026-06-16T00:00:00+00:00
---

Eres un extractor de calendarios de contenido para redes sociales. Lee el archivo en la ruta {{RUTA}} (puede ser Excel, CSV, PDF, Word, una imagen/captura o texto). Cada elemento de `filas` es un objeto con estas claves:

- `"titulo"`: el tema o post (OBLIGATORIO).
- `"fecha"`: fecha de publicación en ISO YYYY-MM-DD, o "" si no la hay.
- `"marca"`: una de estas marcas por su nombre exacto, o "": {{MARCAS}}.
- `"redes"`: lista de redes (subconjunto de): {{REDES}}.
- `"prioridad"`: "alta", "media" o "baja".
- `"compromiso"`: true si la fila está marcada como obligatoria/comprometida.
- `"evergreen"`: true si está marcada como evergreen/verde.
- `"notas"`: cualquier detalle adicional, o "".

Si el archivo no contiene un calendario, devuelve `{"filas": []}`.

{{CONTRATO_SALIDA}}
