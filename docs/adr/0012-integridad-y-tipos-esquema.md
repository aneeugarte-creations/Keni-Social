# ADR 0012 — Integridad referencial y tipos del esquema (apéndice de 0004)

Con Postgres como backend operacional único ([ADR 0004](0004-persistencia-operacional-postgres-unico.md)),
el esquema usa las garantías de integridad y los tipos ricos de Postgres donde aportan, de
forma selectiva. La portabilidad ya no impone "TEXT-para-todo, sin FKs".

## Decisión (revisable)

En esta fase de endurecimiento del esquema elegimos:

- **Integridad referencial en la BD.** Para las relaciones obligatorias de alto valor del hub
  `contenido` optamos hoy por FOREIGN KEY real con `ON DELETE CASCADE`: la hija se trata como
  dependiente, el borrado del padre propaga y, mientras esa relación se modele así, una
  referencia rota se rechaza en escritura en vez de descubrirse como fila colgada al leer.

- **Estados acotados por la BD.** Mientras los catálogos de estado sean estables, los campos de
  estado llevan CHECK contra la allowlist canónica del código (`keni_shared`/`keni_consola.estados`),
  de modo que la misma fuente valida la app y la BD. Con ese CHECK activo un estado fuera de
  catálogo se rechaza al escribir; aflojarlo para iterar es una edición trivial de la allowlist.

- **Concurrencia optimista en el hub.** `contenido` y sus piezas por plataforma llevan una
  columna `version` que sube en cada escritura. Una actualización con versión obsoleta levanta
  `ConflictoVersion` (→ HTTP 409) en vez de pisar una decisión humana o el avance del pipeline.

- **Tipos ricos donde se consultan.** Las columnas JSON que se leen enteras o se querrían
  consultar son `jsonb`, no `TEXT`.

- **Endurecimiento seguro sobre datos vivos.** Cada constraint nuevo va precedido de una
  limpieza/normalización idempotente de las filas que lo violarían, vía migraciones versionadas
  ([ADR 0008](0008-migraciones-esquema-versionadas.md)) re-ejecutables. El detalle de qué tablas
  y columnas lo lleva vive en el código del esquema, no aquí.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- Se necesiten estados experimentales/libres para iterar una feature (aflojar un CHECK es legítimo y trivial: editar la tupla de allowlist).
- Cambie el backend de persistencia.
- El volumen invalide la concurrencia optimista opt-in (version→409).
