# ADR 0006 — Contenido editorial estructurado en Postgres

Extiende [ADR 0004](0004-persistencia-operacional-postgres-unico.md): el contenido editorial
estructurado vive en Postgres, no en YAML por marca con índice de rutas paralelo.

Cubre las fuentes RSS (con sus items vistos), las etiquetas con sus hashtags y las franjas
editoriales (`dia_semana` + `hora` por marca/red). Estas entidades viven en las tablas
`fuentes_rss`, `rss_items_vistos`, `etiquetas` (campaña/vertical/origen, con sus `hashtags`)
y `franjas_editoriales`, sin índice de rutas que pueda desincronizarse al recrear contenedores.

Lo único que sigue file-backed es la prosa editorial por marca (`marca.yaml`, `CLAUDE.md`,
voces) y el historial de prompts: ficheros versionados, editables a mano, sin estado
operacional. `ficheros.py` ya no es backend de las entidades estructuradas.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- Una entidad editorial estructurada necesite edición a mano fuera de la app (volvería a tener sentido un fichero versionado).
- Cambie el modelo de persistencia operacional (ver ADR 0004).
