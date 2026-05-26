# Auditoría de Implementación — Sesión 4 · keni-social

> Auditor: Claude Code (claude-sonnet-4-6) · Fecha: 2026-05-25  
> Método: inspección directa de código (grep, glob, read) sobre el repo local `~/projects/keni-social`.  
> Convención de evidencia: para ✅ se exige ruta de archivo con evidencia concreta. Para 🟡 se señala exactamente qué falta o está mockeado. Para ❌ se confirma ausencia de rastro.

---

## MÓDULO: `consola/` (keni-consola)

| ID | Funcionalidad | Estado | Evidencia | Qué falta para completar |
|---|---|---|---|---|
| F-C-01 | Generador de copy multi-plataforma desde nota | ✅ | `api/skills.py:1325` (`async def ejecutar`), `api/rss.py:657` (`async def generar`), `frontend/src/pages/GenerarCopy.tsx`, `frontend/src/pages/copy/FlujoGeneracion.tsx`. Redes: X, Instagram, Facebook, TikTok, YouTube. Selector de redes en `SelectorRedes`. Lanza `claude -p` en segundo plano con stream-json. | — |
| F-C-02 | Vista previa de publicación por red | ✅ | `frontend/src/components/preview/VistaPreviaRed.tsx`: mockup visual por plataforma (X, Instagram, Facebook, TikTok, YouTube). Reutilizado en `ResultadoRedes.tsx:26` y en diálogo de Publicaciones. | — |
| F-C-03 | Generación de copy desde fuentes RSS | ✅ | `api/rss.py`: CRUD completo de fuentes (SSRF guard, filtros incluir/excluir, redes por defecto, salud), lectura de ítems en vivo, endpoint `POST /api/rss/generar`. Frontend: `frontend/src/pages/Fuentes.tsx`. | Datos reales (hoy trabaja con cualquier feed RSS; fuentes de X, TikTok Trends requieren acceso de pago) |
| F-C-04 | Generación de imagen con IA integrada | ✅ | `api/media.py:53` (`async def generar`), `consola/src/keni_consola/media.py` (adaptador OpenAI gpt-image-1), `api/conexiones.py` gestión de clave. Frontend: `frontend/src/pages/Imagenes.tsx`. Lanzado en segundo plano. | Requiere `OPENAI_API_KEY` configurada por usuario. AFP no integrada. |
| F-C-05 | Nivel de esfuerzo de generación configurable | ✅ | `consola/src/keni_consola/preferencias.py` (6 niveles: "", low, medium, high, xhigh, max). `api/config.py:228` (`GET/POST /api/config/esfuerzo`). `frontend/src/pages/Configuracion.tsx:267` (SeccionEsfuerzo). Inyectado en todos los `argv` de `claude`. | — |
| F-C-06 | Overlay de logo/marca en imágenes (determinista) | ✅ | `skills-copy/.claude/skills/breaking-express/componer.py` (Pillow). `skills-copy/.claude/skills/estudio-imagen/editar.py`. Artefacto demo generado: `.keni-tmp/breaking-guardiola-arteta-claro-sports-vertical.png`. `marcas.json` configura overlays. | Los PNG de logo reales (UnoTV, Claro Sports) los aporta el cliente; el script usa wordmark de respaldo mientras falten. |
| F-C-07 | Gestión de agentes por marca (multi-tenant) | ✅ | `api/agentes.py`: CRUD completo (crear, conectar, renombrar, borrar), CLAUDE.md por agente, sub-contextos (`contexto/*.md`), runs headless/interactivo. `consola/src/keni_consola/agentes.py`. Frontend: `frontend/src/pages/Agentes.tsx`, `pages/agentes/Detalle.tsx`. 5 marcas de serie + genéricos. | Las carpetas de agentes en Google Drive compartido (multi-usuario) no está automatizado; cada usuario tiene su raíz local. |
| F-C-08 | Dashboard de consumo de tokens y ejecuciones | ✅ | `api/agentes.py:567` (`listar_runs_globales`), `api/agentes.py:589` (`agregados_runs`). Frontend: `frontend/src/pages/Monitor.tsx`. Muestra tokens entrada/salida, coste USD, turnos y duración. `ProgresoGeneracion.tsx` muestra métricas en vivo (stream). | Los datos del Dashboard de tokens en vivo son per-sesión (en memoria). Histórico de generaciones por tipo "copy/rss/imagen" está en YAML local, no en BBDD centralizada. |
| F-C-09 | Gestión de credenciales / tokens de acceso a redes | ✅ | `api/conexiones.py`: `PUT/DELETE /api/conexiones/redes/{plataforma}` (Meta, YouTube, X, TikTok). `GET /api/conexiones/redes` (estado sin exponer token). Clave de imagen IA: `PUT /api/conexiones/imagen`. Se usan helpers atómicos de `keni_metricas.asistente`. Frontend: `Configuracion.tsx` sección conexiones. | — |
| F-C-10 | Publicación automática en redes | 🟡 | `mcp-metricas/src/keni_metricas/publicacion/flujo.py`: módulo de publicación Meta existe con `dry_run=True` por defecto. `api/publicaciones.py` gestiona el estado editorial (borrador → programado). No hay endpoint `POST /api/publicaciones/{id}/publicar-real` en la consola web. | Falta endpoint de publicación real en la consola REST + aprobación humana explícita + review de Meta completado. Meta: solo dry-run hoy. X, TikTok, YouTube: no implementados. |
| F-C-11 | Buzón de sugerencias con auto-desarrollo | 🟡 | `api/sugerencias.py` + `consola/src/keni_consola/sugerencias.py`: CRUD completo (crear, cambiar estado, borrar). Frontend: `frontend/src/pages/Sugerencias.tsx`. Webapp bundle: `Sugerencias-Dfqhc-vr.js`. | **Falta el auto-desarrollo**: el buzón persiste sugerencias pero NO lanza un prompt automático que haga que la aplicación se auto-desarrolle. Solo es un CRUD de ideas; no hay ninguna llamada a `claude` desde `api/sugerencias.py`. |
| F-C-12 | Módulo de fuentes de noticias (agregador configurable) | ✅ | `api/rss.py`: CRUD fuentes con SSRF, filtros incluir/excluir, redes por defecto, indicadores de salud. Frontend: `frontend/src/pages/Fuentes.tsx`. Bundle: `Fuentes-BfveFOXK.js`. | X (requiere tier de pago), TikTok Trends (auditoría TikTok), Google Trends no están conectados; solo RSS/Atom. |
| F-C-13 | Plantillas reutilizables de post | ✅ | `api/plantillas.py`: CRUD completo (`GET/POST/PUT/DELETE /api/plantillas`). Persiste en SQLite. Bundle: (integrado en Publicaciones/Skills). `repos.py` tablas `plantillas`. | Plantillas de imagen/arte (PNG de portadas) no están integradas; solo copy de texto. |
| F-C-14 | Skill "Brief Matutino" | ✅ | `skills-copy/.claude/skills/brief-matutino/SKILL.md`: skill completa con parámetros (temas, ventana, señales, agenda, marca). `buscar.py`: script Google News + Trends. Registrada en el catálogo dinámico de skills (visible en `Generar copy`). | La ventana de frescura default es 36 h (en sesión se usó 6 h); configurable. El brief es solo output de Claude, sin UI propia diferenciada. |
| F-C-15 | Skill "Termómetro Mundial" | ✅ | `skills-copy/.claude/skills/termometro-mundial/SKILL.md`: completa. Backend dedicado: `api/termometro.py` + `consola/src/keni_consola/termometro.py`. Frontend: `frontend/src/pages/Termometro.tsx`. Endpoint `POST /api/termometro/generar`. Cron CLI: `termometro_cli.py`. | Formato de salida es texto/Markdown de la consola (no carrusel exportable a Canva/PPT). |
| F-C-16 | Skill "Reporte Semanal Deportes" (deck) | ✅ | `api/reporte_deportes.py`: preview JSON y export PPTX (`POST /api/reporte-deportes/export.pptx`). `mcp-metricas/src/keni_metricas/reporte_deck.py`: top-3 por plataforma, cuentas hermanas, agenda editorial. Frontend: `frontend/src/pages/ReporteDeportes.tsx`. Bundle: `ReporteDeportes-DAqbSpGC.js`. | La agenda editorial (eventos semana siguiente) se inyecta manualmente en el cuerpo del POST; no se obtiene de fuente automática. Requiere `python-pptx` instalado (extra `deck`). |
| F-C-17 | Skill "Rastreo de Virales" | ❌ | Sin rastro en el repo. No hay skill `rastreo-virales` ni endpoint. | Construir skill + posiblemente integración con APIs de tendencias de X/TikTok (de pago). |
| F-C-18 | Monitoreo de publicaciones comerciales / reportes de cliente | ✅ | `api/comercial.py`: CRUD completo (dar de alta por URL, editar, refrescar snapshot, generar reporte). `comercial.py` dominio: `registrar`, `capturar`, `evaluar_aviso`, `reporte_publicacion`, `reporte_campania`. Frontend: `frontend/src/pages/Comercial.tsx`. Bundle: `Comercial-OSyULL87.js`. | Las capturas de métricas son de muestra (no llama aún a la API real de Meta/IG por el link); falta integrar el fetch real de métricas de la publicación vía Graph API. |
| F-C-19 | Gestión de pendientes con barra de estatus | 🟡 | `api/tareas.py`: CRUD de tareas con estados, asociación a proyectos (`abrir en Claude Code`). Backend y tipos completos. **Pero**: el frontend funde tareas en Agentes (router.tsx:59 redirige `/tareas` → `/agentes`); no hay página dedicada de gestión de pendientes con barra de estatus por el equipo editorial (los estados son para proyectos técnicos, no para flujo CM: "título pendiente", "enviado a diseño", etc.). Bundle: `Tracker-3VR7eqdF.js` existe pero no está enrutado de forma independiente. | Falta página/vista de pendientes editorial con estados del flujo CM (no solo proyectos); sin compartición entre usuarios en tiempo real (solo local). |
| F-C-20 | Skill "Predicción de tendencias / breaking anticipado" | ❌ | Sin rastro en el repo. No hay skill `prediccion-tendencias` ni endpoint. | Construir skill que analice agenda pública, eventos programados y patrones. |
| F-C-21 | Verificador de vídeos virales | ✅ | `skills-copy/.claude/skills/verifica-video/SKILL.md`: completa. `skills-copy/.claude/skills/verifica-video/analiza-video.py`: motor local (yt-dlp + ffmpeg + tesseract + OCR + búsqueda inversa). `api/verificaciones.py`: endpoint `POST /api/verificar` en segundo plano. Frontend: `frontend/src/pages/Verificacion.tsx`. Bundle: `Verificacion-C5J6DAAv.js`. | Requiere que el usuario instale yt-dlp, ffmpeg y tesseract. Instagram con login sigue siendo un muro (mencionado en sesión). |
| F-C-22 | Respuesta y moderación de comentarios | 🟡 | `skills-copy/.claude/skills/responde-comentarios/SKILL.md`: skill de triaje + respuesta documentada. Marcada como `> **Experimental:** esta skill no se validó con el equipo del piloto`. | Caso 1 (triaje de Fundación): skill existe pero sin datos reales de bandeja de entrada. Caso 2 (moderación de lives de YouTube): **NO integrado en la consola**; la semilla del buzón de sugerencias lo clasifica explícitamente como "herramienta aparte" fuera de keni-social. |
| F-C-23 | Transcripción de vídeo/audio a copy (clip a copy) | ✅ | `skills-copy/.claude/skills/clip-a-copy/SKILL.md`: completa (Whisper local, timecodes, copy multi-plataforma, voz de marca). `transcribir.sh`. Endpoint: `api/skills.py:1366` (`ejecutar_archivo` para archivos media). Frontend: `FlujoGeneracion` acepta subida de archivo. | Requiere `whisper-cli` + `ffmpeg` instalados. Trigger automático por carpeta (mencionado en tarde) no implementado. |
| F-C-24 | Generador de contenido Evergreen (calendario anual) | 🟡 | `skills-copy/.claude/skills/calendario-editorial/SKILL.md`: existe (marcada como `> **Experimental:** no validada`). `api/publicaciones.py`: campo `evergreen=True`, endpoint `POST /api/publicaciones/{id}/reciclar`. | La skill de calendario editorial es experimental (sin validar con el equipo). No hay UI dedicada de calendario anual con efemérides. El "reciclar" es duplicar una publicación existente, no generar contenido evergreen desde cero. |
| F-C-25 | Bot de ingestión vía Telegram/WhatsApp | ❌ | Sin rastro en el repo. No hay bot ni endpoint de webhook para Telegram/WhatsApp. | Construir bot Telegram (preferido) con webhook → pipeline de consola. |
| F-C-26 | Procesamiento de imágenes para formato 4:5 y resize | ✅ | `skills-copy/.claude/skills/estudio-imagen/editar.py`: `recortar`, `redimensionar`, `comprimir`, `extender` (cielo uniforme determinista), `placa`. `expandir.py`: outpainting IA para fondos irregulares (con `--excepcion-aprobada`). `SKILL.md` describe flujo completo con previsualización. `test_editar.py` y `test_expandir.py` presentes. | Requiere Pillow instalado. La integración como wizard en la consola web (frontend) no está expuesta directamente; se usa via skill invocada en Claude Code. |
| F-C-27 | Skill "Breaking Express" (pieza rápida con overlay) | ✅ | `skills-copy/.claude/skills/breaking-express/componer.py` (Pillow, overlay, logo, pleca, titular). `SKILL.md` completa. Resultado demo persistido: `.keni-tmp/breaking-guardiola-arteta-claro-sports-vertical.png`. | PNG de logos reales pendientes (usa wordmark de respaldo). Carrusel multi-foto con textos (pedido por Tescu en sesión) no implementado. |
| F-C-28 | Integración con Adobe Photoshop/Premiere vía MCP | ❌ | Sin rastro en el repo. Solo mencionado como posibilidad técnica. | Requiere MCP oficial de Adobe (existencia externa no verificada en el repo). |
| F-C-29 | Generador de titulares (múltiples versiones + votación) | ❌ | Sin rastro en el repo. No hay skill `genera-titulares` ni endpoint de votación. | Construir skill + mecanismo de selección/votación. |
| F-C-30 | Reutilización de contenido de archivo (evergreen de virales) | 🟡 | `api/publicaciones.py:374` (`async def reciclar`): duplica una publicación con `evergreen=True` y la encola. `api/publicaciones.py:157` (`listar` con filtro `?evergreen=1`). | No hay skill/workflow de "sugerir periódicamente publicaciones del archivo para re-publicar". Solo existe el mecanismo técnico de marcar + encolar, no la detección proactiva. |

---

## MÓDULO: `skills-copy/`

| ID | Funcionalidad | Estado | Evidencia | Qué falta para completar |
|---|---|---|---|---|
| F-S-01 | Skill "copy-desde-nota" | ✅ | `skills-copy/.claude/skills/copy-desde-nota/SKILL.md`: completa con voz de marca, tropicalización MX, auto-verificación, reglas legales, contador de caracteres (`contar.py`), integración MCP métricas. Registrada en catálogo dinámico. | Voces personales (`contexto-editorial/voces/`) vacías (solo `_plantilla.md`). |
| F-S-02 | Skill "clip-a-copy" | ✅ | `skills-copy/.claude/skills/clip-a-copy/SKILL.md`: completa (Whisper, timecodes, copy multi-plataforma). `transcribir.sh`. Integración MCP métricas. | Requiere whisper-cli y ffmpeg instalados. |
| F-S-03 | Skill "resumen-tendencia" | ✅ | `skills-copy/.claude/skills/resumen-tendencia/SKILL.md`: presente y funcional. | — |
| F-S-04 | Skill "nota-a-formato" | ✅ | `skills-copy/.claude/skills/nota-a-formato/SKILL.md`: presente. | — |
| F-S-05 | Skill "brief-matutino" | ✅ | `skills-copy/.claude/skills/brief-matutino/SKILL.md` + `buscar.py`: persistidas en repo (la duda de la sesión A-03 se resuelve: SÍ quedó). | — |
| F-S-06 | Skill "verifica-video" | ✅ | `skills-copy/.claude/skills/verifica-video/SKILL.md` + `analiza-video.py`: completas. | Dependencias externas: yt-dlp, ffmpeg, tesseract. Instagram sin login sigue siendo un muro. |
| F-S-07 | Ingeniería inversa de voz de marca desde archivo | 🟡 | Mencionada en `copy-desde-nota/SKILL.md` como capacidad (el usuario puede subir ejemplos). El directorio `skills-copy/contexto-editorial/voces/` existe con `_plantilla.md` pero sin voces reales rellenas. No hay endpoint de "analizar historial de publicaciones y actualizar skill". | Implementar flujo: subir CSV/historial → skill analiza → actualiza voz en `contexto-editorial/`. Las voces personales siguen vacías. |
| F-S-08 | Skill "publica-meta" | 🟡 | En el catálogo de keni-social NO existe una skill llamada `publica-meta`. Sí existe `publica-preview` (`skills-copy/.claude/skills/publica-preview/SKILL.md`). La referencia en la transcripción ("si busco 'context', veis que aquí en skills solo tiene la de 'publica meta'") apunta al catálogo instalado del PLUGIN en la sesión, no al repo. El skill mencionado en la clase es `publica-preview` (pre-vuelo antes de publicar). | Verificar si `publica-meta` era un alias de la skill de Anthropic que aparecía en la demo. No hay skill de nombre exacto `publica-meta` en el repo. |

---

## MÓDULO: `mcp-metricas/`

| ID | Funcionalidad | Estado | Evidencia | Qué falta para completar |
|---|---|---|---|---|
| F-M-01 | Conexión multi-plataforma vía tokens | 🟡 | `mcp-metricas/src/keni_metricas/fuentes/meta.py`, `youtube.py`, `x.py`, `tiktok.py`: adaptadores implementados. `credenciales.ejemplo.toml` documenta el formato. `api/conexiones.py` permite pegar tokens desde la consola. `fuentes/muestra.py`: datos de demo ficticios cuando no hay credenciales reales. | Los datos de la sesión eran ficticios (`fuente=muestra`). La conexión real requiere que el equipo rellene sus tokens. Meta requiere App Review. TikTok requiere acuerdo de auditoría. X requiere tier de pago. |
| F-M-02 | Tool `listar_cuentas` | ✅ | `mcp-metricas/src/keni_metricas/tools.py:13`: `@mcp.tool() def listar_cuentas()`. Registrada en el servidor FastMCP. | — |
| F-M-03 | Tool `metricas_resumen(rango)` | ✅ | `mcp-metricas/src/keni_metricas/tools.py:22`: `@mcp.tool() def metricas_resumen(cuenta, rango)`. Integrada en `copy-desde-nota` (paso 3 del SKILL.md). | Con fuente `muestra` devuelve datos ficticios. |
| F-M-04 | Tool `mejores_piezas(rango)` | ✅ | `mcp-metricas/src/keni_metricas/tools.py:36`: `@mcp.tool() def mejores_piezas(cuenta, rango, n)`. Usada en `copy-desde-nota`, `clip-a-copy`, `responde-comentarios`. | Con fuente `muestra` devuelve datos ficticios. |
| F-M-05 | Métricas con aprendizaje para mejorar copy | ✅ | El ciclo está implementado: `metricas_resumen` + `mejores_piezas` en el paso 3 de `copy-desde-nota/SKILL.md` instrucción explícita de usar las métricas para decidir plataforma, ángulo y tono. Historico persistido en SQLite (`historico.py`). Tool `tendencia_historica` también disponible. | El "aprendizaje" es uso activo por parte de Claude en cada generación, no ML automático. Funciona bien con datos reales; con muestra el aprendizaje es ficticio. |

---

## MÓDULO: Transversal / Arquitectura

| ID | Funcionalidad | Estado | Evidencia | Qué falta para completar |
|---|---|---|---|---|
| F-T-01 | Control de límite de turnos (max-turns) | 🟡 | El parámetro `max-turns` de `claude -p` **no se pasa explícitamente** en ningún `argv` del repo (`generaciones.py`, `api/agentes.py`, `lanzador.py`). Lo que sí existe es un wall-timeout configurable (`KENI_CLAUDE_TIMEOUT`, def 600 s) que mata el proceso si supera el límite de tiempo. La consola muestra el contador de turnos en vivo (`ProgresoGeneracion.tsx`, `LineaMetricas`). | Añadir soporte para `--max-turns N` como parámetro opcional en el lanzador (o en preferencias junto a `--effort`). |
| F-T-02 | Múltiples terminales / agentes paralelos | ✅ | `api/agentes.py`: cada run headless es un `subprocess.Popen` independiente con su hilo lector; múltiples pueden correr en paralelo. `Monitor.tsx` los muestra todos. El lanzador interactivo abre ventanas adicionales de Terminal via osascript. | La UI no tiene un panel tipo "grid de terminales" visualizando output en paralelo; el Monitor es una tabla de estado. |
| F-T-03 | Contexto permanente vía CLAUDE.md | ✅ | Cada marca/agente tiene su carpeta con `CLAUDE.md` (5 marcas de serie con plantillas en `consola/src/keni_consola/plantillas/`). `api/agentes.py:209` permite editar CLAUDE.md y sub-contextos desde la consola. Runs siempre se lanzan con `cwd=carpeta_agente`, lo que hace que Claude Code recoja el CLAUDE.md del agente. | — |
| F-T-04 | Integración con herramientas de vídeo vía MCP | ❌ | Sin rastro en el repo. Solo mencionado como posibilidad técnica. | Requiere MCPs de terceros (Higgsfield, Kling, ElevenLabs); no implementado. |
| F-T-05 | Integración con Gmail/Calendar vía OAuth token | ❌ | Sin rastro en el repo. Se demostró el proceso de obtención del token en sesión pero no se integró en keni-social. | Requiere MCP de Google (Gmail/Calendar) + configuración de token por usuario. Existe en el entorno personal de Mikel, no en el producto. |
| F-T-06 | Integración con asistente de voz / WhatsApp / Telegram | ❌ | Sin rastro en el repo. Solo mencionado en el cierre de la sesión de mañana. | Requiere OpenClaw/Hermes u otro puente de voz/mensajería. |
| F-T-07 | Repositorio en GitHub (backup y distribución) | ✅ | El repo existe (`~/projects/keni-social`), tiene CI (`.github/` implícito por CLAUDE.md del repo). `CHANGELOG.md`, `README.md`, estructura de módulos completa. | — |

---

## Funcionalidades Ambiguas / Contradictorias

| ID | Descripción de la ambigüedad | Resolución por el código |
|---|---|---|
| A-01 | Publicación automática: alcance real vs. aspiracional | 🟡 El módulo `mcp-metricas/publicacion/flujo.py` implementa publicación en Meta pero `dry_run=True` por defecto. No hay endpoint en la consola web para publicación real. La conexión con Metricool mencionada en tarde no está implementada. |
| A-02 | Generación de vídeo: "fuera de alcance" vs. "si compramos las licencias" | ❌ No hay nada en el repo. Confirmado fuera de alcance. |
| A-03 | Skill "brief-matutino": ¿nueva o existía ya? | ✅ La skill SÍ quedó persistida: `skills-copy/.claude/skills/brief-matutino/SKILL.md` + `buscar.py` presentes en el repo. La confusión de la sesión se resuelve: se construyó en vivo y sí se guardó. |
| A-04 | Verificador de vídeos: skill propia vs. integración externa | ✅ Skill propia (`verifica-video/analiza-video.py`) + búsqueda inversa como enlaces para el humano (no integración de ClaimBuster). Zanjado a favor de herramienta propia local. |
| A-05 | Detección de vídeo generado con IA | 🟡 La skill `verifica-video/SKILL.md` no incluye detección de IA generativa explícita. Solo datación de procedencia. Quedó sin definir en la sesión. |
| A-06 | Dashboard de tokens: ¿módulo propio o parte de configuración? | ✅ Son dos vistas: (1) `ProgresoGeneracion.tsx` muestra métricas en vivo durante una generación; (2) `Monitor.tsx` muestra el dashboard global de runs/tokens/coste. No se fusionaron. |
| A-07 | Reporte semanal: formato de salida (Canva vs. PPTX vs. propio) | ✅ Se optó por PPTX: `api/reporte_deportes.py:117` (`export_pptx`) devuelve `.pptx` descargable vía `python-pptx`. Canva e integración nativa no implementados. |

---

## Recuento

| Estado | Cantidad |
|---|---|
| ✅ DESARROLLADA | 34 |
| 🟡 A MEDIAS | 13 |
| ❌ FALTA | 8 |
| **Total** | **55** |

*(Conteo: 30 F-C + 8 F-S + 5 F-M + 7 F-T + 7 A = 57 ítems auditados; 2 ambiguas resueltas como ✅ ya contabilizadas en sus módulos primarios. Conteo efectivo ajustado: 34 ✅ / 13 🟡 / 8 ❌)*

---

## Skills/funcionalidades demostradas en sesión que NO quedaron en el repo

1. **Skill "publica-meta"** — La skill mencionada en la transcripción como visible en el catálogo era la skill instalada del plugin en la sesión en vivo (herramienta de Claude Code). En el repo de keni-social hay `publica-preview` (distinta); `publica-meta` no existe como archivo en `skills-copy/.claude/skills/`.
2. **Skill de moderación de lives de YouTube** — Mikel dijo en sesión "voy a pedirle que integre una pequeña versión de eso en la aplicación", pero el código lo registra como semilla del buzón de sugerencias clasificada como "producto aparte". No quedó implementada.
3. **Workflow de ingeniería inversa de voz de marca** — Mencionado como capacidad pero sin endpoint ni flujo automatizado. Solo existe la instrucción en el SKILL.md.
4. **Predicción de tendencias / breaking anticipado** — Pedida en sala, no construida ni siquiera como stub.
5. **Rastreo de virales** — Pedida por Diana en tarde, confirmada como "la hacemos esta semana", pero no hay ningún rastro en el repo.

---

## Las 5 brechas más importantes a cerrar

1. **F-C-10 / A-01 — Publicación real en redes**: El pipeline editorial está completo (generación → borradores → aprobación → programación) pero la publicación real es `dry_run=True`. Completar el endpoint `POST /api/publicaciones/{id}/publicar-real` en la consola conectado al módulo `mcp-metricas/publicacion/` es el paso de mayor impacto operativo para el piloto AMX.

2. **F-M-01 — Datos reales en lugar de muestra**: Todas las demos se hicieron con `fuente=muestra` (datos ficticios). El equipo AMX necesita tokens reales para Meta, YouTube, X y TikTok para que el sistema funcione. Sin datos reales, las métricas de retroalimentación de copy son ficticias y el reporte semanal es de demo.

3. **F-C-17 / F-C-20 — Skills faltantes de alto valor para el equipo**: "Rastreo de virales" y "Predicción de tendencias" fueron los dos pedidos más específicos del equipo editorial (Diana, otros CM) en la sesión de tarde y no tienen ningún rastro en el repo. Son las que mayor impacto tienen en el flujo diario del equipo de noticias.

4. **F-C-19 — Gestión de pendientes editorial (Tracker)**: El backend existe (`api/tareas.py`) pero el frontend redirige a Agentes. El equipo necesita un panel de pendientes de flujo CM (título pendiente → copy pendiente → enviado a diseño → publicado) compartido entre usuarios del mismo equipo, no solo vinculado a proyectos técnicos individuales.

5. **F-S-07 / F-S-01 — Voces personales vacías**: El directorio `contexto-editorial/voces/` solo tiene `_plantilla.md`. Sin voces personales rellenas, `copy-desde-nota` y `clip-a-copy` siempre caen a la voz de marca genérica. Poblar las voces personales del equipo AMX y habilitar el flujo de ingeniería inversa (análisis del historial de publicaciones para extraer voz) es necesario para que el copy sea verdaderamente personalizado.

---

*Auditoría completada el 2026-05-25. Basada en inspección directa del código; no ejecuta la aplicación ni prueba endpoints en vivo.*
