# Ola A — Motor de ingesta persistente (núcleo de cobertura)

Objetivo: pasar de "descarga en vivo por petición, con topes" a una **ingesta
persistente, siempre activa, a nivel de artículo, escalable a cientos de feeds**,
con archivo, salud por feed y cadencia near-real-time configurable. El Radar/Plan
y la UI leen del store; la red se sondea en background.

Decisiones del owner: solo fuentes **gratuitas/robustas** (conectores de pago
enchufables pero inactivos); cadencia **agresiva** (prioritarias ~2-5 min, resto
~10-15 min), **configurable por feed**.

## Modelo de datos

### Tabla `noticias_items` (archivo a nivel de artículo) — NUEVA
```
id            TEXT PRIMARY KEY
fuente_id     TEXT NOT NULL DEFAULT ''      -- fuentes_rss.id
fuente_nombre TEXT NOT NULL DEFAULT ''
categoria     TEXT NOT NULL DEFAULT ''      -- mx|internacional|deportes|ciencia-tech|gaming|tendencias|''
marca         TEXT NOT NULL DEFAULT ''      -- de la fuente (o '' global)
titulo        TEXT NOT NULL DEFAULT ''
resumen       TEXT NOT NULL DEFAULT ''
url           TEXT NOT NULL DEFAULT ''
url_canonica  TEXT NOT NULL DEFAULT ''      -- url normalizada (sin utm, fragmentos)
idioma        TEXT NOT NULL DEFAULT ''
autor         TEXT NOT NULL DEFAULT ''
imagen        TEXT NOT NULL DEFAULT ''
publicado_en  TEXT NOT NULL DEFAULT ''      -- pubDate del feed (ISO) si hay
capturado_en  TEXT NOT NULL DEFAULT ''      -- cuándo lo ingerimos (ISO)
clave         TEXT NOT NULL DEFAULT ''      -- hash dedup (url_canonica o titulo normalizado)
cluster_id    TEXT NOT NULL DEFAULT ''      -- historia (lo llena Ola B)
senal         INTEGER NOT NULL DEFAULT 0
geo           TEXT NOT NULL DEFAULT ''
estado        TEXT NOT NULL DEFAULT 'nuevo' -- nuevo|usado|descartado
contenido_id  TEXT NOT NULL DEFAULT ''
creado        TEXT NOT NULL DEFAULT ''
```
Índices: `(capturado_en)`, `(marca, capturado_en)`, `(categoria)`, `(estado)`,
y **UNIQUE `(fuente_id, clave)`** (dedup por feed; no re-insertar el mismo artículo).

### Columnas de planificación en `fuentes_rss` (migración idempotente ADD COLUMN)
```
intervalo_min   INTEGER NOT NULL DEFAULT 0   -- 0 = usar el default por categoría
categoria       TEXT NOT NULL DEFAULT ''     -- para cadencia/clasificación
prioridad       INTEGER NOT NULL DEFAULT 0   -- mayor = más frecuente
proximo_sondeo  TEXT NOT NULL DEFAULT ''     -- ISO; '' = sondear ya
errores_seguidos INTEGER NOT NULL DEFAULT 0  -- backoff
pausado_hasta   TEXT NOT NULL DEFAULT ''     -- backoff exponencial tras errores
```
Sigue el patrón `_migrar_columnas_*` existente (p.ej. `_migrar_columnas_eventos_rota`).

## Ingesta (dominio/ingesta.py)

PURO/inyectable (tests no tocan red). Reusa `dominio/http_feed`:
- `items_de_feed(feed, *, max_items, fetcher=None) -> tuple[list[dict], dict]`:
  descarga+parsea (reusa `http_feed.leer_items_fuente`; **añade un param `max_items`
  a la ruta de parseo** para superar el tope fijo de 30 en ingesta, p.ej. 100),
  construye dicts de `noticias_items` con `clave` de dedup (`url_canonica` normalizada;
  si no hay url, hash del título normalizado vía `dominio/dedup`), idioma (del feed/
  preset si se conoce; heurística simple si no), `publicado_en`. Devuelve (items, salud).
- `url_canonica(url) -> str`: quita `utm_*`, `#fragmento`, normaliza esquema/host.

## Daemon (ingesta_daemon.py)

Usa `daemon_util.bucle_gateado` + `toca_ejecutar`. Tick corto (~30-60s).
Cada barrido (`ejecutar_barrido`):
1. Selecciona feeds **vencidos** (`proximo_sondeo` <= ahora o '' , `activo=1`, no
   `pausado_hasta` futuro), hasta un cap por barrido (`KENI_INGESTA_BATCH`, def 40).
2. Sondea en paralelo (bounded; `KENI_INGESTA_WORKERS`, def 12) con
   `http_feed.mapear_en_paralelo`.
3. Inserta items nuevos (UNIQUE evita duplicados), actualiza salud
   (`ultimo_conteo`, `ultimo_error`, `ultima_actualizacion`), y **programa el
   próximo**: `proximo_sondeo = ahora + intervalo`. Intervalo = `intervalo_min` del
   feed si >0, si no el default por categoría (config): breaking/deportes ~180s,
   mx/internacional/tendencias ~600s, ciencia-tech/gaming ~1800s.
4. **Backoff**: en error incrementa `errores_seguidos` y fija `pausado_hasta =
   ahora + min(intervalo * 2^errores, tope)`. En éxito resetea `errores_seguidos`.

Gating: `config.ingesta_activa()` vía `KENI_PIPELINE_SELECCION` (**default False** para CI/test;
se ACTIVA en producción, ver deploy). Config: `KENI_PIPELINE_SELECCION`, `KENI_INGESTA_BATCH`,
`KENI_INGESTA_WORKERS`, `KENI_INGESTA_MAX_ITEMS` (def 100), y los intervalos por
categoría. Registra `daemons.iniciar_ingesta()` como los demás.

## Auto-seed del catálogo (para que el motor no esté vacío)

En el bootstrap, si no hay `fuentes_rss`, **activa los presets** de
`dominio/fuentes_presets` como `fuentes_rss` (idempotente por URL), con su
`marca_sugerida`, `categoria` y `prioridad` por categoría. (La Ola C amplía a
cientos verificados; aquí solo garantizamos cobertura inicial real.)

## API (api/noticias.py — RUTAS auto-descubierta)
- `GET /api/noticias?marca=&categoria=&desde=&q=&estado=&limit=&offset=`
  → `{ "items": [Item...], "total": n }`. Newest first (`capturado_en` desc).
  **marca-aware**: filtra por marca; '' / ausente = todas (admin). Paginado.
- `POST /api/noticias/{id}/usar` `{redes?, generar?}` → lleva al tablero reutilizando
  el camino de aportación (`origen='noticia'`), marca `estado=usado` + `contenido_id`.
- `POST /api/noticias/{id}/descartar` → `estado=descartado`.
- `GET /api/noticias/cobertura` → resumen básico de salud: nº feeds activos,
  feeds con error, items últimas 24h por categoría, último sondeo. (Monitor completo = Ola D.)

## Deploy (que SÍ corra en producción)
Añade al servicio `daemons` en `deploy/` las env: `KENI_PIPELINE_SELECCION=1` (+ batch/workers
si procede). Así el motor está **activo en prod** (no como el Investigador, apagado).
NO lo actives en CI/tests.

## Frontend (vista de cobertura)
- `types.ts`: `NoticiaItem`, `RespuestaNoticias`, `ResumenCobertura`.
- `lib/api.ts`: grupo `noticias` (`listar({marca,categoria,desde,q,estado,limit,offset})`,
  `usar(id, body)`, `descartar(id)`, `cobertura()`).
- Página `pages/Cobertura.tsx` bajo el hub Investigación (`/datos/investigacion/cobertura`,
  tab nuevo): **flujo continuo** del archivo (marca-aware con `useMarcaActiva`),
  filtros por categoría/idioma/búsqueda, badges (fuente, categoría, idioma, hora),
  acciones Usar (→tablero) / Descartar, y una **barra de cobertura** (resumen de
  `/cobertura`: feeds activos/erróneos, items 24h por categoría, frescura). React Query
  con `refetchInterval` para que se vea "vivo".

## Reglas
- Worktree `~/projects/keni-social-ing`. No pytest/Postgres local; ruff + ast +
  (frontend) tsc -b + vite build + vitest. Ejecutor/fetcher inyectable en tests
  (NUNCA red). SQLite-dialect `?`. snake_case JSON. No tocar `webapp/`.
