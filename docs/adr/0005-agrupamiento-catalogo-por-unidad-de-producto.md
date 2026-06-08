# ADR 0005 — Agrupamiento del catálogo por unidad de producto (A/B/C) + shell

- **Estado:** Aceptado e implementado (2026-05-29) — manifests + catálogo data-driven + lint de fronteras + seams saneados + `FuenteMetricol` en `main`.
- **Fecha:** 2026-05-29
- **Decisores:** equipo keni-social / innovación
- **Componente:** organización del catálogo de apps (`consola/`)
- **Relación:** **complementa** a [ADR 0002](0002-descomposicion-monolito-modular-catalogo-apps.md).
  0002 fija el **mecanismo** (monolito modular + catálogo data-driven + fronteras enforced); este
  ADR fija **el contenido**: qué apps existen, qué módulos contiene cada una y por qué.

> **[Nota de estado]** La **decisión de fronteras A/B/C + shell sigue vigente**. El inventario de
> módulos de abajo refleja el estado del 2026-05-29: el **sistema de skills** (`skills`,
> `skills_catalogo_api`, `skills_generacion_api`, ruta `/skills`) de la app **A · Producción** se
> **retiró** después y se reemplazó por la **Texto de prompts** (`texto.py`, `/texto`) +
> lanzador neutro (`dominio/generar.py`) y el **Estudio** de imagen (`/estudio`). El agrupamiento por
> unidad de producto no cambia.

---

## Contexto

La consola creció hasta cargar cinco propuestas de valor en una sola superficie (~30 routers en
`consola/src/keni_consola/api/`, sidebar de 9 entradas en `navegacion.ts`, más la spec F1–F9 de la
convergencia de Elías). El problema no es el número de módulos sino que **el agrupamiento no mapea a
unidades de producto** con usuarios, datos y gating distintos. ADR 0002 decidió que la solución es
un catálogo de apps con fronteras enforced; faltaba decidir **cuáles son esas apps**.

## Decisión

El catálogo se organiza en **tres apps de producto** + un **shell** de servicios transversales.
Cada app es activable de forma independiente (flag), porque tienen gating y comprador distintos.

### A · Producción (el moat)

Motor que convierte input crudo (nota, clip, URL, tendencia) en contenido publicable y verificado.
Usuario: community managers + Elías como revisor. Gating: ninguno (Fase 0, vendible hoy).

Módulos backend: `agentes`, `generaciones`, `hashtags`, `plantillas`, `skills`,
`skills_catalogo_api`, `skills_generacion_api`, `qa_editorial`, `verificaciones`, `reciclaje`,
`rss`, `termometro`, `radar`.
Rutas frontend: `/generacion`, `/investigacion/{fuentes,termometro,radar}`,
`/revision/{editorial,verificacion}`, `/skills`, `/agentes`, `/agentes/actividad`, `/agentes/:id`.

### B · Métricas e inteligencia

Lectura multi-marca / multi-plataforma, consolidación y reportes (Monday deck, comercial, análisis
diario). Usuario: Mariana, Elías, Bernardo→Joe.

**Sin gating: B es CONSUMIDOR de Metricool, no motor de ingesta.** Lee dato real vía la **API REST
de Metricool** (AMX está en plan **Advanced** → API token disponible) como **un adapter más detrás
del contrato `FuenteMetricas`** (`FuenteMetricol`). **No** construimos adaptadores propios por
plataforma (Meta/TikTok/X/YouTube): eso duplicaría lo que Metricool ya consolidó y arrastraría los
trámites por red (permisos, auditorías, tiers) sin aportar moat (la ingesta es "plomería
replicable"). El valor de B es la capa de
**insight/narrativa/reporte** encima (deck del lunes F1, "por qué" diario F6, consultas
conversacionales), no la ingesta. La fuente `muestra` queda como fallback/demo. Encaja con la
estrategia ya escrita de **complementar, no reemplazar Metricool**.

Ya tiene contrato propio (`FuenteMetricas`) y proceso aparte (MCP), así que añadir Metricool es
implementar una `FuenteMetricas` más — menos trabajo que los adaptadores por red.

Módulos backend: `metricas`, `comercial`, `reporte_deportes`.
Rutas frontend: `/analiticas/{metricas,comercial,reporte-deportes}`.

### C · Operación de equipo

Coordinación del trabajo del equipo: rota, pendientes compartidos, parrilla, programación y
aprobación. Usuario: Elías/Diana + el equipo. Gating: multiusuario (#130); la publicación real
se habilita vía Metricool (flag `KENI_PUBLICAR_REAL`).

**Decisión (D-publicación):** rota / pendientes / parrilla / programación entran **ya** (con
multiusuario #130). La **publicación real** a redes es una **sub-capacidad** de C que **se habilita
vía Metricool** (flag `KENI_PUBLICAR_REAL`; una integración cubre FB/IG/X/TikTok/YouTube, sin App
Review), sin bloquear el resto de la app (hoy queda en dry-run por defecto).

Módulos backend: `publicaciones`, `aprobacion`, `franjas`, `rota`, `tareas`.
Rutas frontend: `/publicaciones`, `/parrilla/{pendientes,calendario}`.

### Shell (transversal, no es una app)

Servicios comunes que el shell ofrece a todas las apps; viven en el dropdown de ajustes / la home,
no como app de catálogo. Módulos: `auth`, `usuarios`, `config`, `estado`, `conexiones`, `limites`,
`media`, `panel`, `sugerencias`, `carpetas`, `proyectos`.
Rutas frontend: `/panel`, `/mi-cuenta`, `/configuracion`, `/sugerencias`, `/usuarios`.

## Seams permitidos (cruces explícitos, NO imports internos)

La regla de ADR 0002 es `app → app` prohibido. Estos cruces son legítimos y se resuelven por
**API/fachada del gateway o `keni-shared`**, nunca importando las tripas de otra app. El lint de
fronteras los codifica como allowlist explícita:

1. **A → C (handoff de contenido):** una generación de copy puede crear un *borrador* en
   `publicaciones`. Va por endpoint/evento del gateway, no import.
2. **`reciclaje` (A) lee `publicaciones` (C):** consume la API de lectura de C; hoy importa de C
   y hay que sanearlo (T1.1 del plan).
3. **`panel` (shell) lee métricas (B) + cola de aprobación (C):** el shell agrega por las fachadas
   de solo-lectura (`keni_metricas.servicio` y la cola de C). Cruce shell→app permitido.
4. **`media` (shell)** la consumen A (generar/adjuntar) y C (adjuntar): media es shell.
5. **`conexiones` (shell)** guarda secretos que consumen B (tokens métricas) y C (tokens
   publicación): shell.
6. **Todo → `keni-shared`** (marcas, límites, normalización) y **→ `keni_metricas.servicio`**
   (fachada de B): siempre permitido.

## Consecuencias

- El sidebar/`navegacion.ts` deja de estar hardcodeado: se genera desde el **manifest** de cada app
  (ADR 0002 Fase A). Añadir/activar una app no exige editar la navegación.
- Cada app gana un **flag de activación**: Producción y **Métricas** on (Métricas con **dato real
  vía Metricool desde ya**, sin gating); **Operación** enciende con multiusuario (#130) y la
  publicación real vía Metricool (flag `KENI_PUBLICAR_REAL`).
- Los seams pasan de imports implícitos a **contratos explícitos** verificados en CI.
- La costura de extracción de ADR 0002 sigue válida: si Métricas se vende standalone, su frontera
  de app es la línea de separación a deployable, sin reescritura.

## Arquitectura por tipo de app

Cada app tiene una naturaleza distinta y, por tanto, una arquitectura distinta. Mapean a los **tres
deployables** de ADR 0002 (gateway+módulos · worker de generación · MCP de métricas), no a N
microservicios:

- **A · Producción — asíncrono + sandbox.** El gateway **encola** la generación (tabla `jobs`) y un
  **worker** corre `claude -p` (ADR 0001 / 0002 Fase B); whisper transcribe **local**. Los módulos
  del gateway no llevan estado pesado; el trabajo largo vive en el worker. Tolerante a latencia.
- **B · Métricas — consumidor read-through con caché.** Adapter `FuenteMetricol` (REST de Metricool)
  detrás de `FuenteMetricas`; **refresco programado + caché + histórico propio**; el MCP ya es
  proceso aparte. Es I/O-bound de solo lectura: ni worker pesado ni ingesta propia por plataforma.
- **C · Operación — CRUD transaccional multiusuario.** Estado compartido en **Postgres** (ADR 0004),
  identidad por usuario, cola de aprobación / rota / pendientes; consistencia transaccional y
  near-real-time por sondeo.
- **Shell — infra transversal.** Auth/sesión, catálogo (`/api/catalogo`), secretos, media, settings.
  Sin lógica de negocio de app; ofrece servicios a A/B/C.

## Test scoping (resuelve la lentitud del pytest global)

Hoy cada cambio corre la **suite completa**, y eso lastra el ciclo. Como el lint de fronteras
garantiza que **las apps no se importan entre sí**, es seguro correr **solo los tests de la app
tocada + el contrato + `keni-shared`**:

- CI con **jobs por paquete/app en paralelo**, disparados por **filtro de rutas**: cambiar
  `api/metricas.py` corre solo los tests de B; cambiar `keni-shared` corre la **suite completa**
  (es la base común, su contrato afecta a todas).
- Local: selección por ruta + `pytest-xdist` (paralelo) y, opcional, `pytest-testmon` (incremental).
- Implicación: la separación no es solo claridad de producto, es una **mejora directa del tiempo de
  CI/feedback**. El aislamiento de apps es lo que lo habilita.

## Riesgos

- **Disciplina de fronteras.** Sin el lint que codifica estos seams, la decisión degenera en
  monolito enmarañado. El lint es parte de la Fase 0 del plan, no opcional.
- **Clasificación de `reciclaje` y `panel`.** Son los dos módulos con cruce real hoy; el plan los
  trata como tareas de saneo explícitas (T1.1, T1.2) antes de declarar las fronteras "limpias".

## Enlaces

- [ADR 0002](0002-descomposicion-monolito-modular-catalogo-apps.md) — mecanismo del catálogo.
