# ADR 0008 — Migraciones de esquema versionadas

El esquema operacional de la Consola se asegura on-demand en cada arranque de cada
proceso, bajo un advisory lock cross-proceso que serializa los arranques simultáneos. Sobre
ese flujo conviven dos mecanismos complementarios.

## DDL declarativo idempotente

El DDL declarativo (`CREATE ... IF NOT EXISTS`) es la **fuente de verdad de la forma del
esquema** y lo que recibe una BD virgen. Se ejecuta siempre (es barato: una vez por
proceso) y actúa como red de seguridad.

## Journal de migraciones versionadas

Las transformaciones sobre BDs ya creadas (ALTER, backfills, renombres) se aplican **una
sola vez por BD** y se anotan en un journal en la propia BD (`schema_migraciones`). El
registro ordenado vive en código como entradas con nombre secuencial estable; el runner,
bajo el advisory lock de esquema, ejecuta solo las entradas aún no registradas y las anota
al completar.

Principios invariantes:

- **Aplicar una vez, con trazabilidad.** El journal guarda qué migración se aplicó y cuándo;
  los arranques posteriores solo consultan el journal, sin re-pagar backfills.
- **Idempotencia como defensa.** Trabajo y registro entran en la misma transacción cuando es
  posible; cuando la migración commitea internamente, su idempotencia cubre una caída entre
  el trabajo y su registro.
- **Fallar visible.** Una migración pendiente que falla aborta el arranque sin registrarse:
  mejor caerse que servir con un esquema a medias. Se reintenta en el próximo arranque.
- **Nunca renumerar ni reordenar** entradas ya publicadas: el journal las referencia por id.

## Reglas que se quedan fuera del journal a propósito

Las redes de seguridad que deben **reintentarse en cada arranque** hasta que una limpieza
manual lo permita (p. ej. la creación de índices únicos sobre tablas que pueden tener
duplicados preexistentes) corren siempre y no se anotan en el journal: anotarlas congelaría
su fallo.
