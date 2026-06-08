# ADR 0002 — Descomposición: monolito modular + catálogo de apps, no microservicios

- **Estado:** Aceptado (Fases A y B implementadas)
- **Fecha:** 2026-05-27
- **Decisores:** equipo keni-social (auditoría de arquitectura, épica #140)
- **Issues:** #140 (épica) · #130 (ADR 0001, runtime) · #137 · #9 · #135 · #133
- **Componente:** arquitectura interna del servicio (`consola/` + generación sandboxeada + MCP)
- **Relación:** **complementa** a [ADR 0001](0001-runtime-servicio-compartido.md); no lo supersede.
  El **agrupamiento concreto del catálogo por unidad de producto** (qué apps existen y por qué)
  lo fija [ADR 0005](0005-agrupamiento-catalogo-por-unidad-de-producto.md); este ADR define el
  **mecanismo** (catálogo data-driven + fronteras), 0005 define **el contenido** (las 3 apps).

---

## Contexto

[ADR 0001](0001-runtime-servicio-compartido.md) decidió el **runtime y el modelo de despliegue**:
de "app local single-user + `claude -p` por subproceso" a un **servicio compartido multiusuario**
(un backend, auth, estado compartido; la generación corre por `claude -p` en **sandbox por usuario**).
Eso resuelve el *dónde corre* y el *para quién*.

Lo que ADR 0001 deja **abierto** es la pregunta de este ADR: **cómo se descompone por dentro ese
servicio**. Las opciones sobre la mesa eran tres:

1. **Monolito único** (todo en una app, como hoy pero crecido).
2. **Microservicios dockerizados** (un servicio por feature/dominio).
3. **Catálogo de apps tipo router** (estilo Office 365): un shell/launcher con apps independientes.

El riesgo declarado a evitar es un "mastodonte de spaghetti code". Pero hay un riesgo simétrico y
menos obvio: **microservicios prematuros producen el mismo spaghetti, solo que distribuido** —
peor de depurar y de desenredar.

### Restricciones del producto que condicionan la decisión

- **Escala pequeña.** Un cliente piloto (AMX), equipo de ~16 personas, un solo equipo de desarrollo.
  Reutilizable a futuros clientes y multi-tenant (#135), pero **no** es un escenario de muchos
  equipos/servicios con cadencias de despliegue independientes.
- **Modo híbrido** (ADR 0001 y `docs/despliegue-*.md`): local por privacidad / hosted por equipo.
  La **transcripción whisper se queda local** en la máquina del usuario (el audio no sale: es moat).
- **El moat es editorial, no la infra.** `estado-producto.md` §3: "Claude + MCP + whisper.cpp es
  plomería replicable". Invertir en una plataforma de microservicios es invertir en la plomería.
- **Las features nuevas son ligeras.** Las de la convergencia de Elías
  (rota, radar, QA editorial, pendientes) son en el fondo CRUD + una llamada a Claude; no son
  dominios pesados que justifiquen un servicio cada uno.

---

## Estado actual (lo que hay hoy)

El servicio **ya es de facto un monolito modular**; lo que falta es formalizar sus fronteras y
hacer el catálogo explícito. Evidencia en el repo:

- **Backend ya partido por feature.** `consola/src/keni_consola/api/` tiene ~30 routers
  autónomos: `agentes.py`, `comercial.py`, `metricas.py`, `publicaciones.py`, `tareas.py`,
  `reporte_deportes.py`, `termometro.py`, `verificaciones.py`, etc. Cada feature ya vive en su módulo.
- **El sidebar ya es el "launcher" del catálogo.**
  `consola/frontend/src/components/layout/navegacion.ts` agrupa las apps en *Trabajo* y *Ajustes*
  con ruta + icono + descripción por entrada — pero está **hardcodeado**, no es data-driven.
- **Base común ya existe.** `keni-shared/` (marcas, cuentas, esquema YAML, normalización) es la
  dependencia compartida; `FuenteMetricas` es un contrato limpio y el **MCP de métricas ya es un
  proceso aparte** (stdio/HTTP).

Lo que **falta** y deja la puerta al spaghetti:

- **Fronteras no enforced.** Nada impide hoy que un módulo de `api/` importe las tripas de otro;
  el acoplamiento app↔app no está prohibido por ninguna prueba ni lint.
- **Catálogo no data-driven.** Añadir una app exige tocar la navegación a mano; no hay manifest.
- **El runner de generación se EXTRAJO a un worker** (#130 Fase 2 / Fase B de abajo): el back
  **ENCOLA** un job (tabla `jobs` en Postgres) y un **worker** corre `claude -p` (`worker.py`,
  reusando `dominio/runner.py` + `generaciones.lanzar_job_claude` con todo el #137). En local
  el worker corre **en proceso** (un hilo); en hosted es el servicio `worker` de compose. La
  generación ya **no** está acoplada al proceso del gateway: reiniciar el back no mata los jobs.

---

## Decisión

Adoptar un **monolito modular organizado como un catálogo de apps**, y extraer a servicio
**solo en las costuras reales**. Propiedades de primera clase:

1. **Catálogo de apps como principio de organización.** Un shell/launcher (el actual sidebar) +
   apps registradas por **manifest** (ruta, icono, permisos, módulo backend). El catálogo se
   genera desde los manifests, no se mantiene a mano. Es la lectura correcta de la idea
   "tipo Office 365": **un router de apps, no N despliegues**.

2. **Cada app = módulo autocontenido.** Ruta frontend + router backend (`api/<app>.py`) + su
   dominio/almacenamiento. Depende **solo** de `keni-shared` y del contrato del gateway.
   **Regla de oro: nunca `app → app`.** Una necesidad cruzada se resuelve por una API/evento
   interno explícito del gateway, jamás importando las tripas de otra app.

3. **Tres deployables, no N microservicios:**

   | Deployable | Razón de ser separado | Estado |
   |---|---|---|
   | **Gateway + módulos de feature** (Starlette + SPA React; el catálogo) | El grueso; modular por dentro | Existe; falta formalizar fronteras |
   | **Generación en sandbox por usuario** (`claude -p` en `code.kenitech.io`, despachada por el gateway) | Única costura nueva fuerte: trabajo largo, streaming, aislamiento por persona | [ADR 0001](0001-runtime-servicio-compartido.md) |
   | **MCP de métricas** (stdio/HTTP; un adaptador por red) | Ya es proceso aparte con contrato propio | Existe ✓ |

   Más infra compartida: **Postgres** (estado compartido; resuelve la tensión YAML-vs-SQLite local),
   **object storage** (media), y **whisper** (transcripción en el sandbox del usuario en hosted, o en
   su máquina en local; nunca a una API de terceros — ver [ADR 0001](0001-runtime-servicio-compartido.md)).
   La persistencia operacional del gateway ya **consume Postgres** (`DATABASE_URL`) y la media
   **object storage S3/Garage** (`S3_*`) en hosted, cayendo a SQLite+disco en local (#130)
   _(superseded por [ADR 0004](0004-persistencia-operacional-postgres-unico.md): Postgres-only, SQLite eliminado)_; el
   contenido editorial YAML por marca sigue en el volumen (migrarlo es trabajo futuro).

4. **Docker/compose con dos perfiles**, no un enjambre: perfil **local/privacidad** (un contenedor
   o la app local, sin exponer red) y perfil **hosted/equipo** (gateway + sandboxes + MCP + Postgres).

5. **Contrato anti-spaghetti explícito y verificado en CI** (ver Consecuencias): la disciplina de
   fronteras es lo que evita el mastodonte, no la topología.

---

## Consecuencias

### Lo que se conserva (no se toca)

- La **IP de dominio** que ADR 0001 ya blinda (skills, contexto editorial, `FuenteMetricas`,
  `keni-shared`).
- El **backend por feature** ya existente (`api/*.py`) y el **sidebar como catálogo**
  (`navegacion.ts`): son el punto de partida, no algo a reescribir.
- El **MCP de métricas** como proceso aparte con su contrato.

### Lo que se añade / formaliza

- **Manifest/registry de apps**: cada app declara ruta, icono, permisos y módulo; el catálogo
  (navegación) se genera de ahí (data-driven).
- **Regla de dependencia unidireccional** `app → keni-shared/gateway`, **nunca `app → app`**,
  verificada por un **test/lint de fronteras en CI** (si un módulo importa las tripas de otro, CI
  falla). Sin este chequeo, la decisión degenera en la alternativa A.
- **Estado compartido por la capa de datos del gateway** (Postgres), no una app leyendo las tablas
  de otra.

### Lo que se extrae

- La **generación** sale del proceso del gateway: corre por `claude -p` en el **sandbox por usuario**
  de `code.kenitech.io`, despachada por el gateway (ver [ADR 0001](0001-runtime-servicio-compartido.md)).

### Costura de extracción futura

- Cada módulo es ya la **unidad de extracción**: si una app crece a dominio pesado (p. ej. el radar
  de tendencias evoluciona a una pipeline de ingestión), su frontera de módulo es la línea por la
  que se separa a servicio, sin reescritura.

### Riesgos

- **Depende de disciplina.** El valor anti-spaghetti vive en el chequeo de fronteras de CI; si no
  se implementa o se silencia, se vuelve un monolito enmarañado (alternativa A). *Mitigación:* el
  test de fronteras es parte de la Fase A, no opcional.
- **Multi-tenant (#135).** El catálogo y los módulos **no** deben hardcodear marcas; cada app
  respeta el modelo cliente/marca de `keni-shared`. Se coordina con #135.

---

## Plan de migración por fases

Incremental y sin parar el piloto. No mueve la IP de dominio; reordena y formaliza la estructura.

### Fase A — Formalizar fronteras (sin mover nada de sitio)

- Definir el **contrato de módulo** (qué expone, de qué depende) y un **test/lint de fronteras** que
  prohíba `app → app`.
- Convertir la navegación en **catálogo data-driven** desde manifests por app.
- **Criterios de aceptación:**
  - CI **falla** si un módulo de `api/` importa los internos de otro módulo de `api/`.
  - El sidebar/catálogo se genera a partir de los manifests de las apps (añadir una app no exige
    editar la navegación a mano).

### Fase B — Sacar la generación del gateway al worker (#130 Fase 2) — **HECHO**

- El gateway **ENCOLA** la generación (tabla `jobs` en Postgres; spec serializable con prompt +
  post-procesado) y responde al instante; un **worker** la clava y corre `claude -p`, escribiendo
  el stream-json y el resultado en el registro de generación (la SPA sigue **sondeando** ese
  registro, sin cambiar la UX). El gateway **no** ejecuta `claude -p` en su propio proceso. El
  runner de subprocesos se **endurece como permanente** (#137: cola con tope, grupo de procesos
  propio, kill del árbol) y se **reutiliza tal cual** en el worker.
  - **Local / un solo proceso:** el back arranca el worker **en proceso** (un hilo de fondo): la
    UX de una sola máquina no cambia (sin servicio aparte, `claude` en el mismo entorno).
  - **Hosted:** un servicio **`worker`** de compose consume la misma cola; la imagen del back
    **pierde Node + la CLI `claude`** (se mueven a la imagen del worker).
- **Criterios de aceptación (cumplidos):**
  - La generación corre **fuera del proceso del gateway** (en el worker); reiniciar el gateway
    **no mata** los jobs en curso (en hosted el worker es otro contenedor).
  - Un timeout/cancelación **no deja procesos huérfanos** (kill del árbol del grupo de procesos);
    la cancelación funciona **cross-proceso** (flag en la cola que el worker sondea).
  - "Actividad IA" registra **tokens/coste/duración por job y usuario** (ya lo hacía el runner; el
    worker lo conserva al reusar `lanzar_job_claude`).
- **Pendiente (más profundo):** el **aislamiento por usuario** del sandbox en `code.kenitech.io`
  (un sandbox por persona) es infra aparte; hoy el worker es un servicio compartido del stack.

### Fase C — Dockerizar con dos perfiles

- `docker compose` con `gateway` + `sandboxes` + `mcp` + `postgres`.
- **Criterios de aceptación:**
  - `docker compose up` levanta el **modo equipo** completo.
  - El **modo local** conserva la privacidad: whisper transcribe en local y nada se expone a la red.

### Fase D — Nuevas apps de Elías como módulos del catálogo

- F4 (rota), F7 (radar), F3 (QA), F5 (pendientes)… entran **como módulos** que cumplen el contrato.
- **Criterios de aceptación:**
  - Cada feature nueva se añade como módulo con su manifest, **sin tocar otras apps**.
  - Ninguna app nueva introduce un import `app → app` (lo bloquea el test de la Fase A).

---

## Enlaces

- Épica #140 — Auditoría de arquitectura: ¿sirve la arquitectura al objetivo del producto?
- [ADR 0001](0001-runtime-servicio-compartido.md) — Runtime: servicio compartido multiusuario (este ADR lo complementa)
- #137 — Robustez del runner (se mantiene `claude -p`; el runner se endurece como **permanente**, ver [ADR 0001](0001-runtime-servicio-compartido.md))
- #9 — Fase 3: scheduling + cola de aprobación + dashboard (apps del catálogo sobre estado compartido)
- #135 — Multi-cliente sin hardcodear marcas (coordina con el contrato de módulo)
- #133 — Distribución rota (el servicio compartido del catálogo la resuelve de fondo)
