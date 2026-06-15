# Ola D — Monitor de cobertura + Traducir todo + auto-verificación

Cierra el motor para que la cobertura sea de medio serio: salud a escala,
detección de huecos, traducción de todo lo relevante, y verificación por
corroboración. Aditivo sobre Olas A–C.

## 1. Monitor de cobertura / salud de fuentes

### Auto-desactivado de feeds muertos (daemon de ingesta)
- Config `KENI_INGESTA_MAX_ERRORES` (def 8). Cuando `errores_seguidos >= max`,
  el daemon marca el feed como auto-desactivado: `activo=0` + nueva columna
  `desactivado_auto INTEGER DEFAULT 0` (+ migración idempotente en `fuentes_rss`).
  Deja de sondearlo; queda visible para reactivar. En éxito se resetea.

### API
- `GET /api/noticias/salud` →
```
{ "resumen": { "feeds_total", "activos", "auto_desactivados", "fallando",
               "stale", "items_24h", "por_categoria": {cat:n}, "por_idioma": {lang:n},
               "huecos": [ "categoria/region sin items frescos" ],
               "frescura_global_min": n },
  "feeds": [ { "id","nombre","categoria","marca","marca_nombre","activo",
               "desactivado_auto","ultima_actualizacion","ultimo_error",
               "errores_seguidos","items_24h","frescura_min" } ] }
```
  marca-aware (`?marca=`). "Hueco" = categoría/región esperada sin items en 24h.
  "stale" = feed activo sin items nuevos en `KENI_FEED_SLA_MIN` (def 180 min).
- `POST /api/fuentes/{id}/reactivar` → `activo=1`, `desactivado_auto=0`,
  `errores_seguidos=0`, `proximo_sondeo=''` (reintentar ya).

## 2. Traducir todo (no solo top-15)

Hoy Traducir en el Radar está topado a 15. Para el motor:
- Los **clusters** (historias) en idioma extranjero se traducen+tropicalizan a MX
  en el daemon (paso tras Agrupar), por LOTES con Haiku
  (`dominio/traduccion.traducir_items`), guardando en `noticias_clusters`:
  `titulo_es`, `resumen_es`, `traducido` (migración idempotente, columnas nuevas).
- Sin tope artificial: traduce todos los clusters extranjeros recientes con
  `score`/relevancia por encima de un umbral (config `KENI_TRAD_MIN_SCORE`, def 0)
  en lotes acotados por barrido (`KENI_TRAD_LOTE`, def 40) para no saturar; los que
  falten se cogen en el siguiente barrido. Best-effort (si Haiku falla, original).
- `Historia` expone `titulo`/`resumen` ya en ES cuando `traducido`, con
  `titulo_original`/`idioma`.

## 3. Auto-verificación (por corroboración)

Verificación a nivel de cobertura (no fact-check por afirmación): se basa en
corroboración multi-fuente independiente, barata y robusta.
- En `recalcular`/Agrupar, fija `verificacion` en el cluster:
  - `corroborada` si `n_fuentes >= 2` con dominios/outlets distintos,
  - `unica_fuente` si solo 1 fuente,
  - `dudosa` si la única fuente es de baja confianza (lista `FUENTES_BAJA_CONFIANZA`
    configurable, p.ej. agregadores/foros) o señales de clickbait.
  Columna `verificacion TEXT DEFAULT 'unica_fuente'` en `noticias_clusters`
  (migración idempotente). Exponer en `Historia`.
- (Opcional, enchufable) endpoint `POST /api/noticias/historias/{id}/verificar`
  que lanza una revisión Haiku de afirmaciones del cluster y devuelve un veredicto;
  déjalo gateado/best-effort, no en el camino caliente.

## Frontend
- `types.ts`: `SaludCobertura` (resumen+feeds), extender `Historia` con
  `verificacion`, `titulo_original?`, `idioma?`, `traducido?`.
- `lib/api.ts`: `noticias.salud(marca?)`, `fuentes.reactivar(id)`.
- En `pages/Cobertura.tsx` (o sub-pestaña **"Salud"**): tabla de feeds con estado
  (activo/auto-desactivado/stale), items 24h, frescura, último error, y botón
  **Reactivar**; tarjetas-resumen (activos/fallando/stale/items 24h) y lista de
  **huecos de cobertura**. En las tarjetas de Historia: badge de `verificacion`
  (Corroborada N fuentes / Única fuente / Dudosa) y badge "traducido de {idioma}".

## Reglas
- Worktree `~/projects/keni-social-ing`. ruff (`datetime.UTC`) + ast + tsc -b +
  vite build + vitest. Migraciones idempotentes. Traducción/verificación
  best-effort, nunca rompen el daemon ni la API. SQLite `?`. snake_case. No `webapp/`.
