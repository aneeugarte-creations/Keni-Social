# ADR 0008 — Migraciones de esquema versionadas (journal `schema_migraciones`)

- **Estado:** Aceptado
- **Fecha:** 2026-06-09
- **Decisores:** equipo keni-social
- **Componente:** persistencia operacional de `keni-consola` (`consola/src/keni_consola/_db_core.py`, `migracion.py`, `tests/_postgres.py`)
- **Relación:** se apoya en [ADR 0004](0004-persistencia-operacional-postgres-unico.md) (Postgres único). No sustituye el DDL declarativo idempotente: lo complementa.

---

## Contexto

`_db_core._crear_esquema` "asegura" el esquema on-demand en cada arranque de cada proceso
(back/worker/daemons/mcp): ~89 sentencias DDL idempotentes (`CREATE ... IF NOT EXISTS`)
más una lista de migraciones ad-hoc (`_migrar_*`, pre-DDL y post-DDL) que corrían **siempre**
y por tanto debían ser **idempotentes y re-ejecutables** para toda la vida del producto.
Todo ello corre bajo un `pg_advisory_lock` cross-proceso (los arranques simultáneos de un
deploy se serializan).

Problemas del modelo "todo re-ejecutable":

- Cada migración nueva carga con el coste perpetuo de la idempotencia (guards de
  `information_schema`, renombres condicionados, backfills con `WHERE` defensivos), aunque
  su trabajo real sea one-shot.
- No hay registro de QUÉ se aplicó ni cuándo: depurar una BD hosted es leer el código.
- Migraciones de datos costosas (backfills, normalizaciones) se re-ejecutan en cada arranque
  de cada proceso, pagando su coste una y otra vez.

## Decisión

**Journal de migraciones en la propia BD** (`schema_migraciones (id TEXT PK, aplicado_en
TEXT)`) **+ registro ordenado en código** (`_db_core.MIGRACIONES_PRE_DDL` /
`MIGRACIONES_POST_DDL`, entradas `Migracion("00NN-nombre", fn, ...)`). El runner
(`_aplicar_migraciones`), **bajo el advisory lock de esquema ya existente**, ejecuta SOLO
las entradas no registradas y las registra al completar. Si la fn no commitea internamente,
trabajo + registro entran en la misma transacción; si commitea (DDL multi-paso), el registro
va después y la idempotencia de la fn cubre una caída entre medias.

Sin big-bang, conservador:

- El **DDL declarativo idempotente se queda como está**: red de seguridad y fuente de verdad
  de la forma del esquema; se ejecuta siempre (una vez por proceso/URL, es barato).
- Los índices únicos defensivos (`_crear_indices_unicos_idempotencia`) y su dedup previo
  quedan **fuera del journal a propósito**: deben reintentarse cada arranque hasta que la
  limpieza manual de duplicados permita crearlos.
- **Compatibilidad pre-journal**: en la primera ejecución sobre una BD existente el journal
  nace vacío aunque las migraciones legadas ya se aplicaran de facto; como todas son
  idempotentes, corren una última vez y quedan registradas.
- **Migraciones legadas extensibles**: las `_migrar_columnas_*` históricas se extienden
  editando su tupla directora (`_COLUMNAS_*_AMPLIADAS`, `_COLUMNAS_TS_CANON`) o su cuerpo.
  Sus entradas llevan `re_aplicar_si_cambia=True`: el id del journal incluye una **huella**
  (hash del fuente de la fn + `repr` de sus datos), de modo que editar la tupla re-aplica la
  migración una vez sin tocar el journal a mano. Los ids viejos quedan como filas inertes.
- **Errores**: una migración pendiente que falla se loguea con su id y **aborta el arranque
  sin registrarse** (mejor caerse visible que servir con esquema a medias; mismo
  comportamiento que tenían las `_migrar_*` cuando lanzaban). Las best-effort
  (`_normalizar_timestamps_texto`) conservan su tolerancia interna por columna.

## Regla para cambiar el esquema (a partir de ahora)

1. Ajustar `_DDL_ESQUEMA` (lo que recibe una BD virgen).
2. Añadir una entrada **al final** de `MIGRACIONES_POST_DDL` (PRE_DDL solo si el DDL chocaría
   con la forma vieja) con nombre secuencial estable y la fn de ALTER/backfill para BDs ya
   creadas. Las migraciones nuevas corren **una sola vez por BD**: ya no necesitan ser
   re-ejecutables en cada arranque (la idempotencia sigue siendo deseable como defensa).
3. Nunca renumerar ni reordenar entradas publicadas.

## Consecuencias

- `migracion.py --solo-db` (deploy) sigue funcionando igual: asegura DDL + aplica pendientes.
- Arranques posteriores al primero: 1 `SELECT` al journal + DDL idempotente (sin re-pagar
  backfills).
- En la suite, `tests/_postgres.py` trunca `schema_migraciones` entre tests a propósito:
  cada test parte de journal vacío y se preserva la auto-curación "BD vieja" que ejercitan
  los tests de migraciones.
- El journal acumula filas inertes cuando una migración con huella cambia de contenido:
  aceptado (trazabilidad barata; nunca se borra automáticamente).
