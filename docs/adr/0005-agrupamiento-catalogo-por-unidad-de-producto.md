# ADR 0005 — Agrupamiento del catálogo por unidad de producto (A/B/C) + shell

El catálogo de la consola se organiza por **unidad de producto**, no por número de módulos:
tres apps de producto activables de forma independiente, más un shell de servicios
transversales. El criterio de agrupación es tener usuarios, datos y gating distintos.

## Las tres apps + shell

- **A · Producción** (`produccion`). El motor que convierte input crudo (nota, clip, URL,
  tendencia) en contenido publicable y verificado. Es el moat.
- **B · Métricas** (`metricas`). Lectura multi-marca / multi-plataforma, consolidación,
  reportes y narrativa de insight.
- **C · Operación** (`operacion`). Coordinación del equipo: rota, pendientes, parrilla,
  programación, aprobación y publicación.
- **Shell** (no es una app de catálogo). Servicios comunes a las tres apps —auth, usuarios,
  config, conexiones/secretos, media, panel, catálogo— que viven en ajustes/home, no en el
  sidebar.

Cada app de producto tiene su **flag de activación** propio (`KENI_APP_*`), porque su gating
y su comprador difieren. El sidebar se genera desde el **manifest** de cada app, no se
hardcodea: activar o añadir una app no exige tocar la navegación.

La fuente de verdad del inventario de módulos de cada app son los **manifests**
(`consola/src/keni_consola/apps/*.toml`, clave `modulos_backend`) y el registro que los
parsea (`apps/registro.py`), no este documento. El conjunto de apps de producto de hoy es
`APPS_PRODUCTO = {"produccion", "metricas", "operacion"}` (en el lint); es la división por
defecto de esta fase, revisable (ver «Estado» / «Revisar cuando» al final), no una ley fija.

## Seams permitidos

La regla por defecto de hoy es: **`app → app` está prohibido**. Un cruce entre apps se
resuelve por API/fachada del gateway o por `keni-shared`, nunca importando las tripas de otra
app. Todo puede depender de `keni-shared` (marcas, límites, normalización), de la **infra
transversal** (capa de datos del gateway, cola de jobs `generaciones`, servicios del shell) y
de la fachada de solo lectura de Métricas; eso siempre es legítimo (`app → shell` / infra
compartida nunca cuenta como cruce).

Existe un conjunto cerrado de cruces directos legítimos, codificado como **allowlist
explícita** en el lint de fronteras (`SEAMS_PERMITIDOS` en
`consola/tests/test_fronteras.py`) y verificado en CI por contrato. La allowlist es la fuente
de verdad de los cruces vigentes; cualquier import entre apps que no esté en ella hace caer el
lint (que resuelve tanto los imports relativos como los absolutos del paquete, incluida la
forma `importlib.import_module("keni_consola…")` con string literal). Hoy se reduce a cuatro
seams legítimos, todos patrones estables:

- **Handoff A → C** (`historial → piezas`): una generación de copy deposita un *borrador* de
  pieza vía el contrato de C (`dominio.piezas.crear_borrador`), no importando su interior.
- **Lectura de la agenda de C** (`produccion → piezas`): el panel «Producción del día» calcula
  el próximo hueco por red con la MISMA función del encolado/auto-programación. Solo lectura.
- **Doctor de salud transversal** (`estado → actividad`): el health-check del shell lee el
  snapshot de la cola de operación. Solo lectura, le importa a todo el equipo.
- **Efecto de config de marca sobre la cadena de aprobación** (`marcas → colaboracion`,
  shell → C): bajar el umbral de likes de una marca resetea a `pendiente` los OK humanos de
  sus piezas en revisión, usando las primitivas de `dominio.colaboracion`. Es el efecto
  intrínseco de cambiar el umbral, acotado a ese único disparo.

La **cola de jobs `generaciones` NO es un seam**: es infra transversal y vive en el shell
(`shell.toml`), así que sus consumidores (media, parrilla_import, publicaciones, sugerencias)
la importan como `app → shell` —siempre permitido— sin entrada en la allowlist. Antes estaba
clasificada como módulo de A y generaba cuatro entradas al mismo destino; eso era el síntoma de
una frontera mal cortada, no un caso para ampliar la allowlist (ver «Revisar cuando»).

Para el detalle exacto y vigente leer la allowlist en el lint. **Si necesitas un cruce nuevo,
pregúntate primero si la frontera sigue bien cortada**: ¿el destino es realmente infra
transversal (→ reclasifícalo a shell/`keni-shared`)? ¿el cruce puede ir por un contrato del
gateway o una fachada de solo lectura? Ampliar `SEAMS_PERMITIDOS` es el último recurso, con
justificación, no el primer reflejo.

## Métricas complementa, no reemplaza

**B es CONSUMIDOR de métricas, no motor de ingesta.** Lee dato real vía la API de Metricool
como **un adapter más detrás del contrato `FuenteMetricas`** (`FuenteMetricool`), intercambiable
con la fuente de muestra/demo (`FuenteMuestra`) que sirve de fallback. No construimos
adaptadores propios por plataforma (Meta/TikTok/X/YouTube): eso duplicaría lo que Metricool ya
consolida y arrastra los trámites por red sin aportar moat —la ingesta es plomería replicable—.
El valor de B es la capa de **insight, narrativa y reporte** encima, no la ingesta. Añadir un
origen nuevo es implementar una `FuenteMetricas` más.

La publicación real a redes es una **sub-capacidad de Operación** que se habilita también vía
Metricool con una sola integración (FB/IG/X/TikTok/YouTube), sin bloquear el resto de la app;
por defecto queda en dry-run.

## Arquitectura por tipo de app

Cada app tiene una naturaleza distinta y, por tanto, una arquitectura distinta. Mapean a los
tres deployables de ADR 0002 (gateway+módulos · worker de generación · MCP de métricas), no a
N microservicios:

- **A · Producción — asíncrono.** El gateway **encola** la generación y un **worker** aparte
  corre `claude -p`; la transcripción corre en su propio servicio o en local. Los módulos del gateway no llevan estado pesado;
  el trabajo largo vive en el worker. Tolerante a latencia.
- **B · Métricas — consumidor read-through con caché.** Adapter detrás de `FuenteMetricas`, con
  refresco programado, caché e histórico propio, en proceso aparte (MCP). I/O-bound de solo
  lectura: ni worker pesado ni ingesta propia por plataforma.
- **C · Operación — CRUD transaccional multiusuario.** Estado compartido en Postgres (ADR 0004),
  identidad por usuario, cola de aprobación / rota / pendientes; consistencia transaccional y
  near-real-time por sondeo.
- **Shell — infra transversal.** Auth/sesión, catálogo, secretos, media, settings. Sin lógica de
  negocio de app; ofrece servicios a A/B/C.

## Test scoping

Como el lint de fronteras garantiza que **las apps no se importan entre sí**, es seguro correr
**solo los tests de la app tocada + el contrato de fronteras + `keni-shared`** en vez de la suite
completa. El CI ejecuta jobs por app en paralelo, marcando los tests por app; `keni-shared` y el
contrato de fronteras (barato: AST + manifests, sin Postgres) corren siempre como base común. El
aislamiento de apps no es solo claridad de producto: es lo que habilita esta mejora directa del
tiempo de feedback.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- Dos o más seams apunten al mismo módulo destino → señal de frontera mal cortada: re-clasificar el módulo (como acabamos de hacer con `generaciones`), no ampliar la allowlist.
- Se cierre el piloto AMX → reevaluar el conjunto `APPS_PRODUCTO` y si la división en apps sigue siendo la correcta.
