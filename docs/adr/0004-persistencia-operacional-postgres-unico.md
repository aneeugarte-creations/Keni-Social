# ADR 0004 — Persistencia operacional: Postgres como backend único

- **Estado:** Aceptado
- **Fecha:** 2026-05-27
- **Decisores:** equipo keni-social
- **Issues:** #130 (auth multiusuario / persistencia hosted) · supersede parcial de [ADR 0002](0002-descomposicion-monolito-modular-catalogo-apps.md)
- **Componente:** persistencia operacional de `keni-consola` (`consola/src/keni_consola/db.py`, `motor_db.py`, `auth/`)
- **Relación:** **supersede la parte de DUAL backend** (SQLite local / Postgres hosted) introducida por #130 y descrita en ADR 0002 § "Persistencia". Mantiene el resto de decisiones de 0001/0002 intactas.

> Nota posterior: el compose de dev `deploy/dev/docker-compose.yml` (mencionado más abajo) se retiró; en desarrollo no se usa Postgres local —la ejecución/validación se hace en el server/CI— y quien necesite correr en local provee su propio `DATABASE_URL`.

---

## Contexto

[ADR 0001](0001-runtime-servicio-compartido.md) decidió el servicio compartido. #130 cableó
la persistencia operacional hosted en Postgres (tareas, comercial, rota, usuarios, sesiones,
cola de jobs) y la fachada `motor_db.py` quedó como punto de extensión: SIN `DATABASE_URL`
arrancaba en **SQLite local**, CON ella en **Postgres**. La idea era preservar el modo local
"cero-config, offline, datos en la máquina" del perfil privado.

En la práctica, mantener **dos backends operacionales** ha generado fricción real:

- **Drift SQLite ↔ Postgres**: el último incidente fue el 500 del calendario en hosted porque
  `rota_eventos` se había creado en Postgres ANTES de añadir las columnas de la ola B; el
  `CREATE TABLE IF NOT EXISTS` no añade columnas y la migración `_migrar_columnas_eventos_rota`
  estaba gateada a SQLite. La portabilidad del DDL fue suficiente para crear tablas nuevas,
  pero no para mantener tablas existentes alineadas entre los dos backends.
- **Concurrencia y semántica de claim**: la cola de jobs requiere `FOR UPDATE SKIP LOCKED` en
  Postgres; en SQLite había que reimplementarla con un UPDATE guardado + WAL + busy_timeout
  por separado, multiplicando los caminos a mantener.
- **Detección de columnas portable** (`PRAGMA table_info` vs `information_schema.columns`),
  `INSERT OR IGNORE` vs `ON CONFLICT`, traducción `?`→`%s`, guardia anti-orfanamiento al
  arrancar hosted con SQLite local poblado: cada uno es un riesgo añadido para una sola línea
  de negocio (un solo cliente, piloto en validación).
- El **hosted ya corre en Postgres** desde hace semanas y es el único entorno donde se sirve
  a usuarios reales; el SQLite local solo se usa para desarrollo, donde la fricción de
  arrancar un Postgres local con Docker es muy baja (un único comando).

El coste de mantener dos backends excede al beneficio de "cero-config local".

## Decisión

**La persistencia operacional de `keni-consola` se servirá EXCLUSIVAMENTE sobre Postgres.**
Se retira el backend SQLite operacional. `DATABASE_URL` (o su derivación desde `POSTGRES_*`)
pasa a ser **OBLIGATORIA** para arrancar la Consola, tanto en local como en hosted.

Consecuencias inmediatas:

- `motor_db.conectar_cruda()` siempre abre Postgres con `psycopg`. Si falta `DATABASE_URL`,
  lanza `RuntimeError` con un mensaje accionable (incluye el comando para levantar un
  Postgres local con Docker). No hay fallback silencioso a SQLite.
- Se eliminan: `_conectar_sqlite`, `ruta_db` (`db.py`/`motor_db.py`), `ENV_DB`/`ENV_TAREAS`,
  la migración best-effort `tareas.json → SQLite`, el guardia anti-orfanamiento
  `_sqlite_local_tiene_datos` y la rama SQLite del claim de la cola.
- Se MANTIENE el wrapper `_ConexionPg`/`_CursorPg` y la traducción de dialecto (`?` → `%s`,
  `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`): los cientos de call sites siguen usando
  `?` y `fila["col"]` sin cambios. La fachada `repos.py`/`db.py`/`auth/` no rompe firmas.
- Las migraciones de columna idempotentes (`_migrar_columnas_tareas`,
  `_migrar_columnas_eventos_rota`) siguen ejecutándose en cada arranque sobre Postgres,
  porque el Postgres hosted persiste entre despliegues y una tabla legada puede no tener
  columnas nuevas (era el origen del 500 del calendario).
- `python -m keni_consola.migracion --solo-db` queda como **no-op idempotente** que
  garantiza el esquema (`asegurar_esquema`), por compatibilidad con `deploy/deploy.sh` (que
  lo invoca como paso 4/5). La migración de media disco → S3 sigue activa.

Lo que **NO cambia** y debe quedar claro:

- El "**histórico en SQLite local**" del **MCP keni-métricas** (`mcp-metricas/`,
  `KENI_METRICAS_HISTORICO`) es otro almacén distinto y NO se ve afectado por esta ADR.
- El **almacén YAML del contenido editorial** (`ficheros.py`) y su **índice SQLite
  regenerable** (`indice.py`) tampoco: siguen siendo el backend único del contenido.
- La privacidad del perfil local se preserva apuntando `DATABASE_URL` a un **Postgres
  local** (`deploy/dev/docker-compose.yml`): ningún dato sale de la máquina. Lo que se pierde
  es el "cero-config, offline por defecto" del primer arranque.

## Consecuencias

**Positivas**

- Una única superficie de persistencia operacional → desaparece el drift SQLite/Postgres y
  el riesgo de regresiones de columna como el 500 del calendario.
- Menos código a mantener (`db.py` adelgaza ≈170 líneas; `motor_db.py` se simplifica), menos
  ramas condicionales (`if motor_db.es_postgres(): ... else: ...`) en el dominio.
- El claim de jobs es siempre `FOR UPDATE SKIP LOCKED`: misma semántica en dev y prod,
  cubierta por los tests concurrentes existentes en Postgres.
- Los tests operacionales ahora se ejecutan sobre el mismo motor que producción: lo que se
  prueba en CI es lo que se sirve.

**Negativas / coste a asumir**

- El desarrollo local exige un Postgres corriendo. Se añade `deploy/dev/docker-compose.yml`
  con un Postgres de un comando, y el mensaje de error de `conectar_cruda` apunta a ese
  comando. Coste: ~30 segundos la primera vez (`docker compose up -d`).
- El "perfil offline puro" deja de existir como tal; sigue siendo posible (Postgres local =
  ningún dato sale), pero no es zero-config.
- CI necesita un service `postgres` para correr los tests operacionales (ya lo tenía: ver
  `.woodpecker/`); los tests sin Postgres se SALTAN con un mensaje claro (no fallan), de
  modo que un dev sin Postgres recibe una señal explícita en vez de un traceback.

## Alternativas consideradas

- **Mantener el dual backend** (el de #130/ADR 0002). Descartada: la fricción supera al
  beneficio, los incidentes acumulan, y el hosted ya es Postgres.
- **Migrar a un ORM (SQLAlchemy)**. Descartada por ahora: el wrapper actual ya da paridad de
  superficie sin reescribir los call sites, que es lo único que aportaría el ORM. Si en el
  futuro se quiere SQLAlchemy, esta ADR no lo impide.
- **Postgres embebido (pglite/duckdb-compat)**. Descartada: no resuelve el problema de drift
  con el Postgres hosted real y añade un tercer backend a la matriz.

## Plan de migración

- El hosted ya estaba en Postgres: no hay cutover que hacer. El paso `--solo-db` del
  `deploy.sh` se convierte en "asegurar esquema" (idempotente) en lugar de "copiar SQLite a
  Postgres".
- Devs locales con un `consola.db` antiguo: nada que migrar a Postgres (era un piloto sin
  datos críticos). Si alguien quiere conservar las tareas locales, el script archivado
  `consola/scripts/migrar_a_ficheros.py` sigue ahí (lee el SQLite por su cuenta).
- Los tests operacionales pasan a depender de un Postgres de pruebas
  (`KENI_TEST_DATABASE_URL`); sin él, los tests que tocan la operacional se SALTAN con un
  mensaje claro.
