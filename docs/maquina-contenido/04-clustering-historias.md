# Ola B — Clustering de historias + scoring (sobre el store persistente)

El archivo `noticias_items` (Ola A) tiene miles de artículos crudos. Esta ola los
agrupa en **historias** (misma noticia contada por varias fuentes, multi-fuente y
en el tiempo), las puntúa y las expone como el "newsroom story view". Sin tope
artificial: top-N solo para mostrar.

## Modelo

### Tabla `noticias_clusters` (una historia) — NUEVA
```
id            TEXT PRIMARY KEY
titulo        TEXT NOT NULL DEFAULT ''     -- título representativo (el de mayor señal/idioma es)
resumen       TEXT NOT NULL DEFAULT ''
marca         TEXT NOT NULL DEFAULT ''     -- marca dominante de sus items ('' = sin marca)
categoria     TEXT NOT NULL DEFAULT ''
geo           TEXT NOT NULL DEFAULT ''
clave         TEXT NOT NULL DEFAULT ''     -- clave normalizada del título representativo
n_items       INTEGER NOT NULL DEFAULT 0
n_fuentes     INTEGER NOT NULL DEFAULT 0   -- fuentes distintas (corroboración)
idiomas       TEXT NOT NULL DEFAULT '[]'   -- JSON lista
senal         INTEGER NOT NULL DEFAULT 0   -- agregado (suma/máx de señales de items)
score         REAL NOT NULL DEFAULT 0      -- ranking
breaking      INTEGER NOT NULL DEFAULT 0   -- aceleración / muchas fuentes en poco tiempo
primer_visto  TEXT NOT NULL DEFAULT ''
ultimo_visto  TEXT NOT NULL DEFAULT ''
estado        TEXT NOT NULL DEFAULT 'nuevo'-- nuevo|usado|descartado
contenido_id  TEXT NOT NULL DEFAULT ''
creado        TEXT NOT NULL DEFAULT ''
actualizado   TEXT NOT NULL DEFAULT ''
```
Índices: `(marca, score)`, `(categoria)`, `(ultimo_visto)`, `(estado)`, `(clave)`.
`noticias_items.cluster_id` (ya existe en Ola A) apunta aquí.

## Clustering (dominio/clustering.py — PURO/testeable)

Incremental, dentro de una **ventana reciente** (config `KENI_CLUSTER_VENTANA_H`,
def 72h):
- `clave_cluster(item)`: por `url_canonica` (host+path sin query) si existe; si no,
  clave normalizada del título (`dominio/dedup`).
- `asignar(item, clusters_recientes) -> cluster_id|None`: une el item a un cluster
  reciente si (a) misma `url_canonica` normalizada, o (b) fuzzy del título normalizado
  ≥ `KENI_CLUSTER_UMBRAL` (def 0.82) con el `titulo` del cluster (reusa la lógica
  fuzzy/sinónimos de `radar.py`). Si no, crea cluster nuevo.
- `recalcular(cluster, items) -> dict`: recomputa `n_items`, `n_fuentes` (distinct
  fuente_id), `idiomas`, `senal` (máx/sum), `titulo`/`resumen` representativos
  (preferir idioma es y mayor señal), `marca` dominante, `primer/ultimo_visto`,
  `breaking` (≥N fuentes en <M horas), y `score`.
- `puntuar(cluster, *, palabras_marca) -> (score, razon)`: combina corroboración
  (n_fuentes), frescura (recencia de `ultimo_visto`), viralidad (`senal`),
  relevancia de marca (reusa `relevancia_marca`/`parrilla`). Documentar la fórmula.

## Integración en el daemon de ingesta

Tras insertar items nuevos en cada barrido, ejecutar un paso de clustering:
para los items recién insertados (sin `cluster_id`), cargar clusters de la ventana,
asignar/crear, fijar `noticias_items.cluster_id`, y `upsert` del cluster recalculado.
Best-effort; acotado por la ventana. (Si es más limpio, un `iniciar_clustering()`
aparte gateado por `KENI_INGESTA`, con su propio tick corto.)

## API (api/noticias.py — añadir)
- `GET /api/noticias/historias?marca=&categoria=&desde=&estado=&limit=&offset=`
  → `{ "historias": [Historia...], "total": n }`. Orden: `score` desc. marca-aware.
- `GET /api/noticias/historias/{id}` → `{ "historia": Historia, "items": [NoticiaItem...] }`
- `POST /api/noticias/historias/{id}/usar` `{redes?,generar?}` → tablero
  (`origen='historia'`), marca cluster + sus items `usado`, guarda `contenido_id`.
- `POST /api/noticias/historias/{id}/descartar` → `estado=descartado`.

Forma `Historia` (snake_case): `{ id, titulo, resumen, marca, marca_nombre, categoria,
geo, n_items, n_fuentes, idiomas:[], senal, score, breaking, primer_visto,
ultimo_visto, estado, contenido_id, enlaces:[{titulo,url,fuente}] }` (enlaces =
hasta ~8 items del cluster como fuentes corroborantes).

## Frontend
- `types.ts`: `Historia`, `RespuestaHistorias`.
- `lib/api.ts`: `noticias.historias(params)`, `historia(id)`, `usarHistoria(id,body)`,
  `descartarHistoria(id)`.
- En `pages/Cobertura.tsx`: añadir un toggle/sub-pestaña **"Historias"** vs "Artículos".
  Historias muestra cada cluster con título, nº de fuentes (corroboración), badges
  (categoría, idiomas, breaking), lista expandible de enlaces corroborantes, y
  acciones Usar/Descartar. marca-aware + refetchInterval. (Reusa el patrón de la página.)

## Reglas
- Worktree `~/projects/keni-social-ing`. ruff + ast + tsc -b + vite build + vitest.
  Lógica de clustering PURA y testeada (fuzzy, ventana, breaking). SQLite `?`.
  snake_case. No tocar `webapp/`.
