# Mapa del código — `consola/src/keni_consola`

Índice de navegación de los **78 módulos planos** del top-level de `keni_consola`.
Son la **capa de servicio/dominio compartida**: los routers de `api/` y el
orquestador `daemons.py` los importan. NO están en el catálogo de apps
(`apps/*.toml` mapea solo los routers `api/<X>.py`).

No se han movido a subpaquetes **a propósito**: renombrar = reescribir imports en
todo el repo, y con ~7 agentes empujando a `main` sin PR eso es una bomba de
rebase (además rompería el resolver del lint de fronteras, `tests/test_fronteras.py`).
Este doc es el sustituto barato: agrupa por concern **sin tocar un solo import**.
Las descripciones salen del docstring real de cada módulo.

> Registro canónico de daemons: **`daemons.py`** (lista de `iniciar_*`).
> Subpaquetes con su propia estructura: `api/`, `dominio/`, `motores/`, `auth/`,
> `apps/`, `esquema_api/` — ver su `__init__.py`.

## Daemons (hilos de fondo) — registrados en `daemons.py`
Cada uno exporta un `iniciar_*`; casi todos GATEADOS por env var (OFF por defecto).
- `daemons.py` — arranca SOLO los hilos demonio de fondo (sin servidor web). La lista canónica.
- `daemon_util.py` — bucle de demonio GATEADO y RESPONSIVO en caliente (toggle on/off sin reiniciar).
- `programador.py` — programador de publicaciones (#9, Fase 3): prepara/publica las piezas vencidas.
- `auto_programar.py` — una pieza APROBADA pasa SOLA a `programado` en su próximo hueco.
- `auto_responsable.py` — auto-asignación de responsable desde la rota.
- `pipeline_contenido.py` — MÁQUINA DE CONTENIDO: espinazo CI→QA→Redactar→Ilustrar (etapas «Generar copy»/«Generar arte»).
- `autogen_copy.py` — lanzador reutilizable de COPY de un tema (`lanzar_para_topic`); usado por la etapa de Redactar del pipeline y por endpoints manuales.
- `autogen_arte.py` — selección + lanzador de ARTE (`topics_sin_arte`/`lanzar_para_topic`); los usa la etapa de Ilustrar del pipeline.
- `ingesta_daemon.py` — motor de ingesta persistente (Ola A), etapa «Crear noticias».
- `trends_daemon.py` — vuelca Google Trends (con sus noticias) al pool de Noticias.
- `eventos_scanner.py` — barrido de vencimientos del tablero: emite `contenido.vencido`.
- `alertas_rendimiento.py` — barrido de alertas de rendimiento / reciclaje proactivo.
- `media_gc_daemon.py` — GC periódica de media suelta (gateado en vivo).
- `limpiador_generaciones.py` — cierra generaciones atascada (`ejecutando` sueltas).
- `sugerencias_algoritmo.py` — job diario: noticias de algoritmo → sugerencias editoriales. *(nombre engañoso: produce sugerencias EDITORIALES)*
- `metricas_refresco.py` — refresco de la cache de métricas (espejo de `programador.py`).
- `metricas_piezas_refresco.py` — refresco PROACTIVO de la cache de métricas POR PIEZA.
- `algoritmos_refresco.py` — ingiere los feeds de inteligencia de plataforma cada N horas.
- `patrones_refresco.py` — re-deriva de Metricool los perfiles de patrones por marca cada N días (gateado, ADR 0009).

## Métricas y analítica (lado lectura)
- `metricas_cache.py` — cache de métricas: lectura instantánea + refresco en fondo.
- `metricas_linea.py` — rendimiento real del periodo AGRUPADO por LÍNEA de contenido y por ORIGEN.
- `metricas_pieza.py` — rendimiento real por PIEZA del tablero, leído de Metricool.
- `comercial.py` — seguimiento de UN post real de Metricool + captura + reporte.
- `algoritmos.py` — inteligencia de PLATAFORMA (cambios de algoritmo + tendencias por red).
- `priorizacion.py` — score de prioridad dinámico para la "lista viva" del día (H3).
- `relevancia_marca.py` — relevancia por marca para la investigación (Plan del día).
- `patrones_marca.py` — perfil de PATRONES por marca (top vs fondo medido) + verificador de voz del copy (ADR 0009).
- `patrones_derivar.py` — CLI de derivación: Metricool/JSONL → perfil JSON + doc editorial `patrones`.

## Media y assets
- `media.py` — almacenamiento de media (imágenes) + generación por IA.
- `almacen_media.py` — almacén de OBJETOS: disco (local) o S3/Garage (hosted), un solo código.
- `marca_assets.py` — logo / marca de agua / pleca por marca (mocks sustituibles).
- `formatos_red.py` — matriz `red -> formatos de imagen`: fuente única de los lienzos por red.
- `transcripcion.py` — transcripción local de video/audio (whisper.cpp), capa SHELL.

## Pipeline de contenido (automatización, Flujo C)
- `pipeline_contenido.py` — pipeline CI→CD→QA por marca (la "pipeline").
- `pipeline_estado.py` — observabilidad: en qué ETAPA está cada tema.

## Persistencia / repos
- `repos.py` — capa REPOSITORIO: fachada ÚNICA de persistencia (lo que llama `api/`). *[el más grande aún sin partir]*
- `db.py` — BARREL: reexporta todos los `db_<dominio>`; `db.<algo>` sigue funcionando igual.
- `db_<dominio>.py` — CRUD por dominio (el cuerpo de la antigua db.py de 9571 líneas): `db_rota`, `db_contenido`, `db_publicaciones`, `db_noticias`, `db_editor`, `db_parrilla`, `db_colaboracion`, `db_comercial`, `db_metricas`, `db_hashtags_franjas`, `db_webhooks`, `db_green`, `db_jobs`, `db_notificaciones`.
- `_db_comun.py` — plumbing compartido de los `db_<dominio>`: imports, logger y re-export de `_db_core`.
- `_db_core.py` — cimientos: conexión, locks y esquema/migraciones.
- `motor_db.py` — motor de persistencia operacional: Postgres, un solo backend.
- `migracion.py` — migración one-shot del cutover hosted: media disco → S3/Garage.
- `migrar_contenido.py` — migración de datos legados al tablero de CONTENIDO unificado.
- `versionado.py` — versionado de la Texto con git (historial · diff · rollback).

> Capas de DB: `api/` → `repos.py` (fachada) → `db.py` (barrel) → `db_<dominio>.py` (CRUD) → `_db_core.py` (cimientos) ← `motor_db.py` (conexión Postgres). El plumbing común de los `db_<dominio>` está en `_db_comun.py`.

## Ficheros-como-verdad (prosa editorial en disco)
- `ficheros.py` — backend de FICHEROS YAML: el historial de prompts vive en disco.
- `indice.py` — índice REGENERABLE del backend de ficheros (NO es la fuente de verdad).
- `texto.py` — almacén ÚNICO: PROMPTS + LÍNEA EDITORIAL (files-as-truth).
- `plantillas_marca.py` — store EDITABLE de la "Plantilla de marca" del Estudio.
- `io_atomico.py` — escritura atómica de texto (REEXPORTA `keni_shared.io_atomico`).

## Catálogo / datos de referencia
- `marcas.py` — catálogo de marca (REEXPORTA `keni_shared.marcas`).
- `redes.py` — fuente ÚNICA de las redes destino de copy.
- `estados.py` — constantes neutras de DOMINIO (allowlists de estados/métricas).
- `limites_plataforma.py` — límites de caracteres (REEXPORTA `keni_shared.limites_plataforma`).
- `agentes.py` — dominio AGENTES: el conjunto ABIERTO de agentes.
- `agencias.py` — adaptadores de agencias de noticias (Reuters/AFP) como fuentes.
- `bootstrap_lineas.py` — inicial idempotente de LÍNEAS de contenido y orígenes.

## Cola de jobs y worker (generación IA)
- `cola.py` — cola de jobs: el back ENCOLA, un WORKER clava y ejecuta (#130 Fase 2).
- `worker.py` — clava jobs de la cola y corre `claude -p` (ADR 0002 Fase 2).
- `generaciones.py` — dominio GENERACIONES: trabajos de IA seguibles en vivo.
- `lanzador.py` — lanza Claude Code en una carpeta del proyecto.

## Operación del equipo
- `rota.py` — lógica de DOMINIO de la parrilla y rota de horarios (#144).
- `sugerencias.py` — buzón de sugerencias LOCAL (ideas de producto del equipo).
- `proyectos.py` — config local de "carpetas de proyecto" para la pestaña Proyectos.
- `importador_calendario.py` — importa calendario editorial (Excel/CSV) al tablero.
- `actividad.py` — vista UNIFICADA de la actividad de IA de la consola.

## Ajustes / secretos / config
- `config.py` — fuente ÚNICA de las env vars `KENI_*`.
- `ajustes.py` — almacén EDITABLE de flags + tuning de funcionalidad.
- `ajustes_catalogo.py` — catálogo DECLARATIVO de ajustes editables (verdad para la API admin).
- `preferencias.py` — preferencias locales no secretas del equipo.
- `secretos.py` — almacén LOCAL de secretos (clave del proveedor de imagen IA).
- `rutas.py` — raíz de estado ÚNICA (un solo volumen en contenedor, #130).
- `permisos.py` — permisos por ROL: helper "¿es admin?" (#153).
- `seguridad.py` — autenticación + protección CSRF (#134).

## Plataforma / arranque / infra transversal
- `app.py` — App Starlette: API JSON + sirve el SPA React.
- `__main__.py` — arranca la Consola (servidor Starlette/uvicorn).
- `observabilidad.py` — logging, middleware de peticiones y errores.
- `_http_json.py` — helper para leer el body JSON de una petición.
- `mcp_operativo.py` — servidor MCP operativo montado en `/mcp` de la propia Consola.

---

## Convención de nombres (para no perpetuar el desorden)

El layout es plano, así que el **nombre del fichero es el único índice**. Reglas:

1. **Idioma**: dominio en español; términos de infra establecidos en inglés (`worker`, `bootstrap`, `db`, `config`).
2. **Automatización**: preferir `auto_<concern>` (hoy conviven `auto_*`, `autogen_*`, `autofeed_*` — inconsistente).
3. **Daemons**: el sufijo `_daemon` está solo en 5 de ~20; la pertenencia se define por `daemons.py`, no por el nombre. No añadir `_daemon` a ciegas.
4. **`_` inicial** = helper privado, no se importa entre concern-groups (`_db_core`, `_http_json`).
5. **Familias por prefijo** (`metricas_*`): cuidado con singular/plural (`metricas_pieza` vs `metricas_piezas_refresco`).

Renombrar módulos `.py` reescribe imports en todo el repo → es trabajo de **ventana
coordinada** (freeze), no de un commit suelto. Hasta entonces, este mapa es la guía.
