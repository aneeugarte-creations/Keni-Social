# ADR 0004 — Postgres como backend operacional único

La persistencia operacional de la Consola (tareas, comercial, rota, usuarios,
sesiones, cola de jobs) vive **exclusivamente en Postgres**. No hay backend
operacional paralelo que pueda desincronizarse del que se sirve en producción.

## Principio

- `DATABASE_URL` es **obligatoria** para arrancar la Consola, en local y en
  hosted. Si falta, el arranque falla con un mensaje accionable; nunca hay
  fallback silencioso a otro almacén.
- Una única superficie operacional implica una sola semántica de concurrencia
  (claim de la cola de jobs con `FOR UPDATE SKIP LOCKED`) y un solo dialecto SQL.
  Lo que se prueba en CI corre sobre el mismo motor que producción.
- Las migraciones de columna son idempotentes y se ejecutan en cada arranque:
  el Postgres hosted persiste entre despliegues y una tabla legada puede no
  tener columnas nuevas.
- La privacidad del perfil local se preserva apuntando `DATABASE_URL` a un
  Postgres que el propio dev gestiona: ningún dato sale de la máquina.

## Frontera de almacenamiento

Cada tipo de dato tiene un único hogar, sin almacenes duplicados:

- **Operacional + editorial estructurado** → Postgres.
- **Prosa editorial** (CLAUDE.md por marca, biblioteca, voces) → ficheros
  versionados bajo `KENI_DATA_DIR`.
- **Media** (imágenes) → S3/Garage.

El histórico del MCP keni-métricas es un almacén propio del MCP y queda fuera
de este principio.
