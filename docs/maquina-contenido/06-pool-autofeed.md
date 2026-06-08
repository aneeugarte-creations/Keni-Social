# Ola E — Pool único → dedup → auto-feed (sin botones manuales)

Visión del owner: TODAS las notas entran a un **pool**, se **deduplican**, y un
**pipeline automático** lleva las **historias relevantes** al **feed** como
borradores con copy+QA hechos, listos para imagen + aprobación. Sin "Enviar al
feed" manual (queda solo un override discreto "empujar ya"). Todo gateado por el
kill-switch `KENI_MAQUINA`.

Decisiones: auto-fluyen **solo historias relevantes** (umbral por marca); **tope
por marca/día configurable**; **automático + override**.

## Piezas que ya existen (reusar, no reinventar)
- Pool = `noticias_items` (Ola A). Dedup = clustering → `noticias_clusters`
  (historias, Ola B). Copy+QA en 1 agente = `copy-desde-nota` vía
  `dominio.generar.lanzar_copy` (parsea veredicto → `qa_veredicto`, badge IA en el
  feed). Feed = tablero de piezas. Frescura/TTL por línea = `dominio/frescura`.

## 1. Unificar el pool (todas las notas dentro de `noticias_items`)
Cuando se parsea/crea una nota de CUALQUIER origen, además de su tabla propia,
**insertar también en `noticias_items`** para que entre al dedup + pipeline:
- Cajones (worker `procesar` de insumos): cada `insumos_item` → `noticias_items`
  con `fuente_id='cajon-<cajon>'`, `fuente_nombre`=cajón, `origen` propio, marca,
  titulo, resumen, fecha, idioma, y **`senal` alta** (curado por el equipo = alta
  prioridad, así supera el umbral fácilmente). `clave` de dedup por url/título.
- Investigación (worker `procesar`): cada `inv_candidato` → `noticias_items`
  (`fuente_id='investigacion'`, enlace, marca, fecha).
- Eventos NO entran (son agenda de cobertura, no notas de copy).
Idempotente por `UNIQUE(fuente_id, clave)`. El clustering los agrupa con el resto.

## 2. Daemon auto-feed (`autofeed_daemon.py`)
Gateado por `config.maquina_activa() and config.autofeed_activo()`
(`KENI_AUTOFEED`, def **OFF**). Patrón `daemon_util.bucle_gateado`, como
`pipeline_contenido`. Cada barrido, **por marca activa**:
1. Selecciona historias (`noticias_clusters`) recientes, `estado='nuevo'`, NO
   draftadas, con `score >= KENI_AUTOFEED_UMBRAL` (def 0.5), ordenadas por score.
2. **Frescura**: descarta historias caducas para líneas no-green de esa marca
   (reusa `dominio/frescura` con la línea/categoría). Green no caduca.
3. **Tope diario por marca**: `cap = cap_marca(marca)` (config, con override por
   marca como `_ETAPAS_MARCA`); resta lo ya draftado hoy (contenido
   `origen='autofeed'`, fecha hoy). Toma hasta el cupo restante.
4. Para cada historia elegida: crea la pieza del feed
   (`repos.crear_contenido(flujo='importante', origen='autofeed', ...)` +
   `contenido_plataforma` por las redes por defecto de la marca, `falta_copy=1`,
   `falta_imagen=1`) y **lanza copy+QA** (`autogen_copy.lanzar_para_topic` /
   `dominio.generar.lanzar_copy`, 1 agente → veredicto IA). Marca el cluster
   `estado='usado'` + `contenido_id` (dedup: no re-draftar). Best-effort.

Config (config.py + ajustes_catalogo, todo gateado por el maestro):
- `KENI_AUTOFEED` (bool, def False) — "Auto-feed: pool → feed automático".
- `KENI_AUTOFEED_UMBRAL` (float, def 0.5) — umbral de relevancia.
- `KENI_AUTOFEED_CAP` (int, def 20) — tope diario por marca (con overrides por
  marca, patrón `_ETAPAS_MARCA`/`marca_apagada`).
- `KENI_AUTOFEED_INTERVALO_MIN` (def 10) — cadencia del barrido.
Registrar `daemons.iniciar_autofeed()`.

## 3. Override manual ("empujar ya")
Los endpoints actuales de "usar/aceptar/preparar" (insumos, noticias, historias,
investigación) SE QUEDAN como el override manual. No se borran. El frontend solo
los re-etiqueta a "Empujar ya" (Ola E frontend).

## Frontend (otra tanda)
- Quitar el botón prominente "Enviar al feed"; dejar un **"Empujar ya"** discreto
  (mismo endpoint) para forzar una nota/historia concreta.
- Las páginas de fuentes pasan a ser de **visibilidad/curación del pool** (ver qué
  hay, qué ya está en el feed, qué se descartó). Mostrar estado por item: en pool /
  en cola / en el feed / descartado.
- Panel: el toggle `KENI_AUTOFEED` + cap por marca + umbral (auto desde catálogo).

## Reglas
- Worktree. ruff (`datetime.UTC`) + ast + (frontend) tsc -b + vite build + vitest.
  PYTHONPATH=src para pytest local. Idempotente. Gateado por `KENI_MAQUINA`. Nada
  autopublica (todo cae en el feed para imagen + aprobación humana). snake_case. No `webapp/`.
