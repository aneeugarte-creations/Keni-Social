# Ola 4 — Fuentes externas + idiomas

Objetivo: conectar tantas fuentes fiables como sea posible (gratis y robustas
primero), de cualquier idioma, y traducir/tropicalizar a MX lo extranjero.
Reusa la infra RSS existente (`fuentes_rss` + `dominio/http_feed.py` con guard
SSRF + el Radar que consolida). NO romper el Radar (cambios aditivos y best-effort).

## A. Catálogo de presets (la mayor parte de "más fuentes")

Casi toda fuente nueva se modela como un feed RSS (URL) que el Radar ya sabe
consumir. Entregamos un **catálogo curado** que el equipo activa con un clic.

`dominio/fuentes_presets.py` (NUEVO): lista estática de presets fiables, p.ej.:
- Noticias MX: Reforma, El Universal, Milenio, Animal Político (RSS).
- Internacional multi-idioma: Reuters, AP, AFP, BBC, El País, DW, Le Monde,
  vía RSS propio o Google News RSS.
- Google News RSS por consulta/tema: plantilla
  `https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}`.
- Reddit: `https://www.reddit.com/r/{sub}/top/.rss?t=day`.
- GDELT (mundial, multi-idioma): `https://api.gdeltproject.org/api/v2/doc/doc?query={q}&format=rss&sort=datedesc`.
- YouTube canal: `https://www.youtube.com/feeds/videos.xml?channel_id={id}`.
- Deportes: ESPN, Marca, AS, FIFA, Liga MX (RSS). Ciencia/Tech: NASA, MIT TR,
  Xataka. Gaming: IGN, Polygon, Eurogamer (para Nación Gamer).

Forma de un preset:
```
{ "id": "reuters-world", "nombre": "Reuters — World",
  "url": "https://...", "categoria": "internacional",
  "marca_sugerida": "unotv", "linea_sugerida": "Internacional",
  "idioma": "en", "region": "GLOBAL", "descripcion": "..." }
```
Categorías (vocabulario por marca; `breaking`/`evergreen` son transversales): UnoTV usa
`mx`, `internacional`, `entretenimiento`; Claro Sports `futbol`, `motor`, `otros-deportes`, `mx`;
Nación Gamer `gaming`. El conjunto canónico vive en `fuentes_presets.CATEGORIAS_VALIDAS`.

### API (api/fuentes.py — añadir, no romper lo existente)
- `GET /api/fuentes/presets?categoria=` → `{ "presets": [Preset...], "categorias": ["mx",...] }`.
  Marca cada preset con `activa: bool` si ya existe una `fuentes_rss` con esa URL.
- `POST /api/fuentes/presets/activar` body `{ "ids": ["reuters-world",...], "marca": ""? }`
  → crea `fuentes_rss` para los presets elegidos (reusa `repos.crear_fuente_rss`,
  aplica `marca_sugerida`/`linea_sugerida` si no se pasa marca). Idempotente por URL.
  → `{ "creadas": n, "fuentes": [ ... ] }`.

## B. Traducir + tropicalización MX

`dominio/traduccion.py` (NUEVO): traducción **síncrona por lotes** con Haiku,
mismo patrón que `importador_calendario._ejecutar_claude_json` (claude -p
--output-format json --model haiku). Una sola llamada para una lista de items.
```
def traducir_items(items: list[dict], *, ejecutor=None) -> list[dict]
# items: [{ "id", "titulo", "resumen" }] en idioma extranjero
# returns: [{ "id", "titulo_es", "resumen_es" }] traducido + tropicalizado MX
```
Ejecutor inyectable (tests). Best-effort: si falla, devuelve los originales.

### Integración en el Radar (radar.py / api/radar.py) — ADITIVA y acotada
- Detectar idioma del item/preset (usa el `idioma` del preset; heurística simple
  si no se sabe). Marcar `idioma` en cada tema.
- Traducir corre **SIEMPRE** (no tiene toggle propio: va dentro de la etapa
  «Crear noticias», gateada por `KENI_PIPELINE_RECOLECTAR` + `KENI_MAQUINA`). Tras consolidar,
  toma los temas extranjeros del **top N** (cap, p.ej. `KENI_TRADUCCION_MAX=15`),
  llama UNA vez a `traducir_items`, y sustituye `titulo`/`por_que` por la versión ES,
  guardando `titulo_original`. Con timeout y fallback al original (no degradar el
  Radar si Haiku tarda/falla).
- Tema del Radar gana campos opcionales: `idioma?: str`, `traducido?: bool`,
  `titulo_original?: str`. Sin tocar el resto del scoring.

## C. Frontend

- `types.ts`: `Preset` + `RespuestaPresets`; `TemaRadar` gana
  `idioma?: string; traducido?: boolean; titulo_original?: string`.
- `lib/api.ts`: `fuentes.presets(categoria?, signal?)`,
  `fuentes.activarPresets({ ids, marca? })`.
- Página Fuentes (`pages/Fuentes.tsx`): nueva sección/tab **Catálogo** que lista
  presets por categoría con badges (idioma, región, marca sugerida), checkboxes y
  botón "Activar seleccionadas". Refresca la lista de RSS al activar.
- Radar/Plan (`pages/Radar.tsx`, `ParrillaDia.tsx`): para temas `traducido`,
  muestra el título ES y un badge pequeño "traducido de {idioma}" (con tooltip del
  `titulo_original`). No romper el render actual.

## Reglas
- Worktree `~/projects/keni-social-maquina`. No pytest/Postgres local; valida con
  ruff + ast + (frontend) tsc -b + vite build + vitest. SSRF: toda URL pasa por el
  guard existente. SQLite-dialect `?`. snake_case en JSON. No tocar `webapp/`.
