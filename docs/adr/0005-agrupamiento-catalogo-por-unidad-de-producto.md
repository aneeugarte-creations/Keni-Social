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
parsea (`apps/registro.py`), no este documento. El conjunto de apps de producto está fijado
en código (`APPS_PRODUCTO = {"produccion", "metricas", "operacion"}`).

## Seams permitidos

La regla invariante es: **`app → app` está prohibido**. Un cruce entre apps se resuelve por
API/fachada del gateway o por `keni-shared`, nunca importando las tripas de otra app. Todo
puede depender de `keni-shared` (marcas, límites, normalización) y de la fachada de solo
lectura de Métricas; eso siempre es legítimo.

Existe un conjunto cerrado de cruces directos legítimos, codificado como **allowlist
explícita** en el lint de fronteras (`SEAMS_PERMITIDOS` en
`consola/tests/test_fronteras.py`) y verificado en CI por contrato. Esa allowlist es la
fuente de verdad: cualquier import entre apps que no esté en ella hace caer el lint. Los
cruces que admite responden a patrones estables:

- **Handoff A → C:** una generación o un import de operación crea un *borrador* de pieza vía
  el contrato de C, no importando su interior.
- **Infraestructura de jobs como servicio del shell:** módulos del shell y de operación que
  encolan trabajo (generación de media, import por Claude, auto-desarrollo) reutilizan la
  cola de jobs de Producción.
- **Lecturas read-only transversales:** el panel/estado del shell agrega snapshots de
  operación y métricas por fachadas de solo lectura.

Para el detalle exacto y vigente de qué pares están permitidos y por qué, leer la allowlist
en el lint. Cambiar un cruce es cambiar `SEAMS_PERMITIDOS` con justificación, no introducir
un import nuevo.

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
