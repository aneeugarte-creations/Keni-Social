# ADR 0012 — Integridad referencial y tipos del esquema (apéndice de 0004)

Con Postgres como backend operacional único ([ADR 0004](0004-persistencia-operacional-postgres-unico.md)),
el esquema usa las garantías de integridad y los tipos ricos de Postgres donde aportan, de
forma selectiva. La portabilidad ya no impone "TEXT-para-todo, sin FKs".

## Principio

- **Integridad referencial en la BD.** Las relaciones obligatorias de alto valor del hub
  `contenido` llevan FOREIGN KEY real con `ON DELETE CASCADE`: la hija es dependiente, el
  borrado del padre propaga y una referencia rota se rechaza en escritura, no se descubre
  como fila colgada al leer.

- **Estados acotados por la BD.** Los campos de estado llevan CHECK contra la allowlist
  canónica del código (`keni_shared`/`keni_consola.estados`), de modo que la misma fuente
  valida la app y la BD. Un estado fuera de catálogo se caza al escribir.

- **Concurrencia optimista en el hub.** `contenido` y sus piezas por plataforma llevan una
  columna `version` que sube en cada escritura. Una actualización con versión obsoleta levanta
  `ConflictoVersion` (→ HTTP 409) en vez de pisar una decisión humana o el avance del pipeline.

- **Tipos ricos donde se consultan.** Las columnas JSON que se leen enteras o se querrían
  consultar son `jsonb`, no `TEXT`.

- **Endurecimiento seguro sobre datos vivos.** Cada constraint nuevo va precedido de una
  limpieza/normalización idempotente de las filas que lo violarían, vía migraciones versionadas
  ([ADR 0008](0008-migraciones-esquema-versionadas.md)) re-ejecutables. El detalle de qué tablas
  y columnas lo lleva vive en el código del esquema, no aquí.
