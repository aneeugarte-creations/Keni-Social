# ADR 0004 — Postgres como backend operacional único

La persistencia operacional de la Consola (tareas, comercial, rota, usuarios,
sesiones, cola de jobs) tiene a Postgres como **única fuente de verdad**. Hoy,
a la escala del piloto, Postgres es además el único motor que la sirve.

## Principio

El principio es **una sola fuente de verdad por dato**: cada dato operacional
vive en un solo almacén autoritativo. No se duplica la verdad operacional en dos
almacenes que puedan desincronizarse entre sí o respecto al que se sirve en
producción. Esto NO veta un almacén especializado de apoyo (p. ej. una cache o
un broker de mensajería) mientras no sea fuente de verdad de un dato operacional.

- `DATABASE_URL` es **obligatoria** para arrancar la Consola, en local y en
  hosted. Si falta, el arranque falla con un mensaje accionable; nunca hay
  fallback silencioso a otro almacén.
- Una única fuente de verdad operacional implica una sola semántica de
  concurrencia y un solo dialecto SQL para esos datos. Lo que se prueba en CI
  corre sobre el mismo motor que producción.
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

## Implementación actual (no es principio)

- **Un solo motor para todo**: que Postgres sea hoy el único almacén operacional
  es la elección de la escala del piloto, no un principio. El principio es la
  fuente de verdad única por dato; el motor que la sirva puede cambiar.
- **Cola de jobs sobre Postgres** (polling + `FOR UPDATE SKIP LOCKED`): es una
  implementación adecuada a la carga del piloto, no un principio. Un broker
  dedicado sería legítimo si la escala lo justifica.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- El polling de la cola presione a Postgres o crezca el número de workers → reconsiderar un broker dedicado.
- Aparezca un caso legítimo para un almacén especializado (cache, broker); este ADR prohíbe duplicar la verdad operacional, no usar la herramienta adecuada.
