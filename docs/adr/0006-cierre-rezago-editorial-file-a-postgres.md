# ADR 0006 — Cierre del rezago file→Postgres de las 3 entidades editoriales

- **Estado:** Aceptado
- **Fecha:** 2026-06-01
- **Decisores:** equipo keni-social
- **Issues:** cierre del rezago de [ADR 0004](0004-persistencia-operacional-postgres-unico.md) (persistencia operacional Postgres único)
- **Componente:** persistencia de CONTENIDO editorial reutilizable (`consola/src/keni_consola/db.py`, `repos.py`, `migrar_contenido.py`, `migracion.py`)
- **Relación:** completa la migración a Postgres iniciada por ADR 0004; NO supersede nada.

---

## Contexto

[ADR 0004](0004-persistencia-operacional-postgres-unico.md) fijó Postgres como backend
operacional ÚNICO. La mayoría del dominio ya migró: publicaciones, contenido, plantillas,
etiquetas, media-metadata y toda la rota. Quedaron **tres entidades editoriales rezagadas**
todavía file-backed (`ficheros.py`, YAML por marca + un índice SQLite regenerable de rutas
ABSOLUTAS, `indice.sqlite`):

- `fuentes_rss` (+ items vistos + salud),
- `grupos_hashtags`,
- `franjas` (editoriales: `dia_semana` + `hora` por marca/red).

El índice SQLite guardaba **rutas absolutas** a los YAML. Al recrear los contenedores del
deploy, esas rutas quedaban apuntando a ubicaciones viejas y el índice no encontraba los
ficheros: la **página de Fuentes RSS aparecía VACÍA** pese a que los YAML seguían en disco.
Era el mismo tipo de fragilidad que motivó ADR 0004 (drift entre dos almacenes), pero del
lado del índice de rutas.

## Decisión

**Migrar las 3 entidades a Postgres**, cerrando el rezago. Tablas nuevas, dialecto portable
(mismo estilo `?`/`fila["col"]` que el resto del esquema; `motor_db` traduce a Postgres):

- `fuentes_rss` (con `creado` para el orden "recientes primero") + `rss_items_vistos`
  (una fila por `(fuente_id, clave)`, PK compuesta, sin FK ⇒ `marcar_item` no exige fuente
  existente, paridad con el file-backed).
- `grupos_hashtags` (tags como JSON serializado, igual patrón que `biblioteca_media`).
- `franjas_editoriales` — nombre DISTINTO de `rota_franjas`/`rota_config_franjas` (franjas
  horarias del equipo, otra cosa) para no colisionar.

El esquema se asegura idempotente al arrancar el `back` (`_crear_esquema` + hooks
`_migrar_columnas_*` vacíos por coherencia) y en `deploy.sh` paso [4/5]
(`migracion --solo-db`).

`repos.py` reapunta la delegación de estas 3 entidades de `ficheros.*` a `db.*` SIN cambiar
las firmas públicas: `api/rss.py`, `api/hashtags.py`, `api/franjas.py` y el frontend no se
tocan. Los dicts devueltos conservan las mismas claves que la capa de ficheros.

### Migración de datos existentes (no destructiva)

`migrar_contenido.py` gana `migrar_fuentes_rss` / `migrar_grupos_hashtags` / `migrar_franjas`:
leen el origen YAML legado vía `ficheros` e insertan en Postgres lo que FALTE, **preservando
el id** (INSERT … ON CONFLICT (id) DO NOTHING). Son **idempotentes** (re-ejecutar no duplica)
y se ejecutan por dos vías:

1. el hook best-effort del arranque del `back` (`app.crear_app` → `migrar_contenido.migrar()`),
2. el paso DETERMINISTA del deploy: `migracion.migrar_editorial_file_a_pg`, dentro de
   `migracion --solo-db` (deploy.sh [4/5]).

**Los YAML y el código de `ficheros.py` NO se borran** en este cambio: quedan como respaldo
/ origen de la migración. Una limpieza posterior puede retirarlos.

## Consecuencias

- **Positivas:** desaparece el índice de rutas absolutas como punto de fallo; Fuentes RSS deja
  de poder aparecer vacía tras recrear contenedores. Un solo backend para todo el dominio
  editorial reutilizable (coherente con ADR 0004). El dato histórico del piloto (16 fuentes
  RSS, 13 franjas, 8 grupos de hashtags) queda copiado a Postgres preservando ids.
- **Neutras:** `ficheros.py` mantiene las funciones de estas entidades como origen legado; no
  son parte del flujo en caliente. La capa de tests añade cobertura en `test_db_editorial.py`.
- **A futuro:** retirar los YAML y el código file-backed de estas 3 entidades una vez
  verificado en producción que todo lee/escribe desde Postgres.
