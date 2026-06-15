# ADR 0012 — Integridad referencial y tipos del esquema (apéndice de 0004)

- **Estado:** Aceptado
- **Fecha:** 2026-06-13
- **Decisores:** equipo keni-social
- **Componente:** esquema operacional de `keni-consola` (`consola/src/keni_consola/_db_core/`, `db_contenido/`, `db_publicaciones.py`)
- **Relación:** **apéndice de [ADR 0004](0004-persistencia-operacional-postgres-unico.md)** (Postgres como backend único) y de [ADR 0008](0008-migraciones-esquema-versionadas.md) (migraciones versionadas). No supersede nada.

---

## Contexto

El esquema operacional nació en la era de **doble backend** (SQLite local / Postgres hosted) y
heredó una postura de "máxima portabilidad": **casi todo `TEXT`** (ids, fechas ISO, JSON
serializado), `NOT NULL DEFAULT ''` con `''` como sentinel de "sin valor", y **solo 2 FKs
formales** en 55 tablas. Esa postura tenía sentido cuando el DDL debía valer para SQLite y
Postgres a la vez.

[ADR 0004](0004-persistencia-operacional-postgres-unico.md) retiró SQLite: **el único backend
real es Postgres**; `motor_db.py` solo IMITA la API de `sqlite3` sobre Postgres para no tocar
los cientos de call-sites. La consecuencia es que **la paridad SQLite ya no impone nada**: el
esquema puede usar las garantías de integridad y los tipos ricos de Postgres.

Una crítica de arquitectura señaló los riesgos de seguir con "TEXT-para-todo, sin FKs":
- borrados que dejan **filas sueltas** (sin FK, nada propaga ni impide referencias rotas);
- columnas de **estado** que aceptan cualquier string (un bug escribe un estado inválido y se
  detecta tarde, en lectura);
- **last-write-wins** en las ediciones del hub `contenido`: el avance del pipeline puede pisar
  una decisión humana (y viceversa) sin que nadie lo note;
- JSON y fechas como `TEXT`: no consultables, sin validación de forma ni de orden temporal.

## Decisión

Endurecer el esquema de forma **incremental y segura sobre datos reales** (despliega a
producción), con migraciones versionadas idempotentes (ADR 0008) que **limpian/normalizan antes
de cada constraint** para que el deploy no falle contra datos heredados sucios.

1. **FOREIGN KEYS** en las relaciones OBLIGATORIAS de alto valor del hub `contenido` y afines,
   todas `ON DELETE CASCADE` (la hija es dependiente), precedidas de limpieza de sueltos
   (incluido el sentinel `''`): `contenido_plataforma`, `contenido_comentarios`,
   `contenido_copy_versiones`, `contenido_aprobaciones`, `documento_versiones`,
   `video_subtitulos`, `insumos_item`, `comercial_snapshots` → su padre.
   (Migración `0028`.)

2. **CHECK de allowlist** en los campos de estado, reutilizando las allowlists canónicas del
   código (`keni_shared`/`keni_consola.estados`), con normalización previa de valores inválidos:
   `contenido.estado`, `contenido_plataforma.estado`, `contenido_aprobaciones.decision`,
   `usuarios.rol`, `contenido.qa_veredicto`. (Migración `0029`.)

3. **Concurrencia optimista**: columna `version INTEGER NOT NULL DEFAULT 0` en `contenido` y
   `contenido_plataforma`, que sube en CADA escritura del repo. Las funciones de actualización
   aceptan un `version_esperada` opcional; si llega obsoleta, levantan `ConflictoVersion`
   (→ HTTP 409) en vez de pisar. El avance de estado del pipeline
   (`transicionar_estado_publicacion`) también la sube. (Migración `0030`.)

4. **Tipos `jsonb`** en las dos columnas TEXT-JSON que se leen enteras y se querrían consultar:
   `jobs.spec` y `metricas_cache.payload`. Los call-sites de lectura aceptan dict-o-str; la
   escritura no cambia (se sigue pasando el JSON serializado y Postgres lo castea). (Migración
   `0031`.)

## Alcance deliberadamente limitado (lo que NO se hizo y por qué)

- **FKs en referencias OPCIONALES** (`contenido.evento_id`, `noticias_items.contenido_id`,
  `noticias_items.cluster_id`): el esquema usa `''` (no `NULL`) como "sin referencia". Una FK de
  Postgres exige que cada valor no-nulo exista en el padre, e `''` no es `NULL` → exigiría un
  padre con `id=''`. Convertir `''`→`NULL` implica volver nullable la columna y tocar los muchos
  call-sites que comparan/filtran por `''` (riesgo alto sobre datos vivos). **Diferido.**

- **FK `metricas_pieza_snapshots.pieza_id` → `contenido_plataforma.id`**: NO procede. `pieza_id`
  guarda el **`id_post_metricool`** (id del post en Metricool), no un `contenido_plataforma.id`
  (ver `metricas_pieza._registrar_historico`). Una FK borraría/limpiaría todo el histórico de
  métricas. **No se aplica** (constatación de modelo, no omisión).

- **`noticias_clusters.qa_veredicto`**: su conjunto de valores aún no está centralizado en una
  allowlist. **Diferido** a la siguiente ola (mismo patrón que `contenido.qa_veredicto`).

- **Migración de TIMESTAMP TEXT a `timestamptz`** (`metricas_pieza_snapshots.ts`,
  `comercial_snapshots.ts`, `jobs.creado/claimed_at`, `gasto_ia.dia`, `contenido.creado/
  actualizado`, etc.): **diferida**. Con `dict_row`, una columna `timestamptz` vuelve como
  `datetime`, y (a) varias de estas columnas usan el sentinel `''` (incompatible con
  `timestamptz`), (b) hay `substr(creado,1,10)` sobre el texto, y (c) `contenido.creado/
  actualizado` y las series se serializan como **string ISO** en muchas respuestas de API, donde
  un `datetime` no es JSON-serializable. Convertir con seguridad exigiría castear a texto en cada
  lectura (sin beneficio real) o un refactor amplio de serialización. Además, el texto ya está en
  **canon UTC sin offset** (`tiempo.ahora_iso` + migración `0024`), así que el **orden léxico ==
  cronológico**: las consultas de rango/orden ya son correctas. Prioridad: correctitud sobre
  cobertura.

## Consecuencias

- **Integridad real**: los borrados propagan, las referencias rotas se rechazan, los estados
  fuera de catálogo se cazan en escritura (antes, en lectura o nunca).
- **Carrera pipeline↔humano** detectable y controlada (409) sin romper el last-write-wins de los
  call-sites que no pasan `version`.
- **Despliegue seguro**: cada constraint va precedido de limpieza/normalización idempotente; las
  migraciones corren una vez por BD (journal `schema_migraciones`) y son re-ejecutables.
- La postura "**TEXT-para-todo por paridad SQLite**" queda **superada**: el esquema usa ya las
  garantías de Postgres donde aportan, de forma selectiva y medida.
