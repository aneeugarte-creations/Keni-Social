# ADR 0008 — Migraciones de esquema versionadas

El esquema operacional de la Consola se asegura on-demand en cada arranque de cada
proceso, bajo un advisory lock cross-proceso que serializa los arranques simultáneos. Sobre
ese flujo conviven varias superficies, no una sola. Conviene nombrarlas con fidelidad:

- **DDL declarativo idempotente** (`_DDL_ESQUEMA`): la fuente de verdad de la FORMA del
  esquema. Corre SIEMPRE (es barato) y es lo que recibe una BD virgen.
- **ALTERs/UPDATEs inline dentro del DDL**: unas pocas sentencias `ALTER TABLE … ADD COLUMN
  IF NOT EXISTS` y backfills puntuales (`UPDATE … WHERE … IS NULL`) viven junto al DDL y
  corren siempre, también idempotentes. Son columnas añadidas después del `CREATE` original
  que se prefirió no encadenar al journal.
- **Journal de migraciones versionadas** (`schema_migraciones`): el registro ordenado de
  transformaciones sobre BDs ya creadas (PRE-DDL y POST-DDL).
- **Reglas always-on fuera del journal** (`_crear_indices_unicos_idempotencia`,
  `_dedup_turnos_rota`): redes de seguridad que deben reintentarse en cada arranque y por
  eso NO se anotan (anotarlas congelaría su fallo).

## DDL declarativo idempotente

El DDL declarativo (`CREATE ... IF NOT EXISTS`) es la **fuente de verdad de la forma del
esquema** y lo que recibe una BD virgen. Se ejecuta siempre (una vez por proceso) y actúa
como red de seguridad. Sus ALTERs/UPDATEs inline siguen el mismo principio: idempotentes,
siempre.

## Journal de migraciones versionadas

Las transformaciones sobre BDs ya creadas (ALTER, backfills, renombres) se anotan en un
journal en la propia BD (`schema_migraciones`). El registro ordenado vive en código como
entradas con un nombre estable; el runner, bajo el advisory lock de esquema, ejecuta solo
las entradas cuyo id aún no está en el journal y las anota al completar.

Hay dos clases de entrada, y la diferencia es real, no cosmética:

- **Migraciones nuevas** (`re_aplicar_si_cambia=False`): se aplican **una sola vez por BD**.
  Su id de journal es su nombre tal cual; una vez registrado, no se vuelve a tocar.
- **Migraciones legadas** (`re_aplicar_si_cambia=True`): nacieron re-ejecutables y muchas se
  EXTIENDEN editando su tupla directora (`_COLUMNAS_*_AMPLIADAS`, `_FKS`, `_COLUMNAS_TS_CANON`…)
  o su propio cuerpo. Su id de journal incluye una **huella** (hash blake2b del fuente de la
  fn + `repr` de sus datos directores), así que **editar el contenido las RE-APLICA una vez**
  bajo un id nuevo (`nombre@hash`), dejando el id viejo como fila inerte. Son idempotentes,
  de modo que re-aplicar es seguro.

Principios:

- **Aplicar una vez rige para las migraciones NUEVAS.** Las legadas se re-evalúan POR
  CONTENIDO: mientras su huella no cambie no se re-pagan, pero editar la fn o su tupla las
  re-aplica. No es un journal de "una vez para todo".
- **Idempotencia como defensa.** Trabajo y registro entran en la misma transacción cuando es
  posible; cuando la migración commitea internamente, su idempotencia cubre una caída entre
  el trabajo y su registro.
- **Fallar visible.** Una migración pendiente que falla aborta el arranque sin registrarse:
  mejor caerse que servir con un esquema a medias. Se reintenta en el próximo arranque.

## Sobre el número de cada migración

El prefijo numérico (`00NN-`) ordena la lectura del registro, pero **no es un orden global
asignable sin coordinación**: con varios agentes añadiendo entradas en paralelo, los números
se han repetido. Hoy mismo colisionan entre las tuplas PRE y POST (ids `0039`, `0041`, `0042`
aparecen en ambas). La **unicidad la da el slug completo** (el `nombre`, que es la PK del
journal), no el número. Así que el número es una pista de orden, no una identidad: tratarlo
como un contador global inviolable es un mito.

Por eso NO se establece como ley el "nunca renumerar". Lo que sí se mantiene mientras el
journal esté vivo es: no reescribir el slug de una entrada ya publicada (el journal la
referencia por ese id) ni reordenar entradas de forma que cambie su efecto.

## Squash / baseline (operación legítima en piloto)

Renumerar/colapsar el historial es una operación VÁLIDA, no un tabú. En el contexto del
piloto AMX —una sola BD, datos descartables— un **baseline (squash)** es legítimo y barato:

1. El DDL declarativo ya produce la FORMA correcta sobre una BD virgen.
2. Se vacía el journal (`schema_migraciones`).
3. Se re-stampa: o bien partiendo de una BD recreada por DDL (journal vacío, todo se aplica
   limpio una vez), o anotando como aplicadas las entradas colapsadas.

Esto colapsa la maraña de `_migrar_*` legadas en un punto de partida limpio. No se hace por
deporte, pero tampoco está prohibido: este ADR lo **bendice explícitamente** como salida de
limpieza cuando el ruido del historial supere su valor.

## Reglas que se quedan fuera del journal a propósito

Las redes de seguridad que deben **reintentarse en cada arranque** hasta que una limpieza
manual lo permita (p. ej. la creación de índices únicos sobre tablas que pueden tener
duplicados preexistentes, o el dedup previo de turnos) corren siempre y no se anotan en el
journal: anotarlas congelaría su fallo.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- El número de migraciones crezca demasiado (~50+), entre una segunda BD/tenant, o se salga del piloto con datos reales → evaluar un baseline (squash) o adoptar Alembic.
