# Plan de separación en apps — runbook de agentes

- **Fecha:** 2026-05-29 · **Estado:** ejecutado (2026-05-29) — T0 + seams (T1.1–1.3) + T2.B + manifests A/C/S + verificación integral, todo en `main` local (pendiente push a origin).
- **Decisión que ejecuta:** [ADR 0005](adr/0005-agrupamiento-catalogo-por-unidad-de-producto.md)
  (apps A/B/C + shell) sobre el mecanismo de [ADR 0002](adr/0002-descomposicion-monolito-modular-catalogo-apps.md)
  (catálogo data-driven + fronteras enforced).
- **Objetivo:** separar la consola en **3 apps de producto + shell** sin reescribir dominio, con
  fronteras verificadas en CI, de forma que varios agentes trabajen **en paralelo sin colisionar**.

> **Reglas del repo (de `CLAUDE.md`):** cada agente trabaja en **su propio worktree + rama**,
> nunca sobre el checkout de `main`. `git fetch` antes de tocar nada. A `main` solo entran merges
> limpios (`git push <rama>:main`, sin PR). Tests también en el worktree propio.

---

## 0. Mapeo de referencia (router → unidad)

| Unidad | Módulos backend (`consola/src/keni_consola/api/`) | Rutas frontend |
|---|---|---|
| **A · Producción** | `agentes`, `generaciones`, `hashtags`, `plantillas`, `skills`, `skills_catalogo_api`, `skills_generacion_api`, `qa_editorial`, `verificaciones`, `reciclaje`, `rss`, `termometro`, `radar` | `/generacion`, `/investigacion/*`, `/revision/*`, `/skills`, `/agentes`, `/agentes/actividad`, `/agentes/:id` |
| **B · Métricas** | `metricas`, `comercial`, `reporte_deportes` | `/analiticas/*` |
| **C · Operación** | `publicaciones`, `aprobacion`, `franjas`, `rota`, `tareas` | `/publicaciones`, `/parrilla/*` |
| **Shell** (no app) | `auth`, `usuarios`, `config`, `estado`, `conexiones`, `limites`, `media`, `panel`, `sugerencias`, `carpetas`, `proyectos` | `/panel`, `/mi-cuenta`, `/configuracion`, `/sugerencias`, `/usuarios` |

**Seams permitidos** (allowlist del lint; ver ADR 0005 §Seams): A→C handoff de borrador ·
`reciclaje`→`publicaciones` (vía API) · `panel`→métricas+cola · `media`/`conexiones` shell ·
todo→`keni-shared`/`keni_metricas.servicio`.

---

## 1. Artefactos que introduce la separación

1. **Manifest por app** — un archivo declarativo por app (un fichero independiente cada uno, para
   no colisionar): `id`, `etiqueta`, `icono`, `grupo_nav`, `modulos_backend` (lista de módulos
   `api/*` que posee), `rutas_frontend`, `flag_activacion` (env), `permisos`. Ubicación propuesta:
   `consola/src/keni_consola/apps/<app>.toml` (+ un cargador `apps/registro.py`).
2. **Endpoint de catálogo** — `GET /api/catalogo`: devuelve las apps **activas** (según flags) con
   sus entradas de navegación. El shell sirve este endpoint.
3. **Navegación data-driven** — `navegacion.ts` deja de hardcodear: el sidebar se hidrata de
   `/api/catalogo`. `router.tsx` valida que sus paths existen en el catálogo (lazy components).
4. **Lint de fronteras en CI** — test que parsea imports de cada `api/<router>.py`, mapea cada
   router a su app vía manifest y **falla si un router de la app X importa internals de la app Y**,
   salvo los seams de la allowlist. Se añade a `.github/workflows/ci.yml` y `.woodpecker/`.
5. **Test scoping por app** — los tests dejan de correr en bloque: jobs de CI por app/paquete
   disparados por **filtro de rutas** (cambio en una app → solo sus tests + contrato + `keni-shared`;
   cambio en `keni-shared` → suite completa). Lo habilita el lint de fronteras (apps aisladas).
   Resuelve la lentitud del pytest global. Detalle en [ADR 0005](adr/0005-agrupamiento-catalogo-por-unidad-de-producto.md) §Test scoping.

---

## 2. Fases y dependencias

```
Fase 0 (FUNDACIÓN, 1 agente, GATING)  ──►  Fase 1 (SEAMS, 3 agentes ∥)
                                      └─►  Fase 2 (APPS, 4 agentes ∥)   ──►  Fase 3 (VERIF, 1 agente)
```

- **Fase 0 bloquea todo.** Crea el manifest, el catálogo data-driven y el lint con la allowlist de
  seams actuales (para que CI quede verde con el estado de hoy).
- **Fase 1 y Fase 2 corren en paralelo tras Fase 0**, con **ownership de ficheros disjunto**
  (detallado por tarea) → sin colisiones entre worktrees.
- **Fase 3 cierra** tras el merge de todas.

---

## 3. Tareas (cada una = un agente, un worktree, una rama)

### Fase 0 — Fundación · rama `sep/fundacion`

**T0 — Manifest + catálogo data-driven + lint de fronteras.**
- Crear `apps/registro.py` + un manifest por app (`apps/produccion.toml`, `apps/metricas.toml`,
  `apps/operacion.toml`, `apps/shell.toml`) con el mapeo de §0.
- Añadir `GET /api/catalogo` (módulo shell) que lee el registro y filtra por flag de activación.
- Hidratar `navegacion.ts` desde `/api/catalogo` (sidebar deja de hardcodear; los grupos y entradas
  salen del manifest). `router.tsx` referencia paths declarados.
- Añadir el **lint de fronteras** como test (`consola/tests/test_fronteras.py`) + paso en
  `.github/workflows/ci.yml` y `.woodpecker/`. Codificar la **allowlist de seams** de ADR 0005 §Seams.
- **Ficheros propios:** `apps/*`, `api/catalogo.py` (nuevo), `frontend/.../navegacion.ts`,
  `frontend/.../router.tsx`, `tests/test_fronteras.py`, `.github/workflows/ci.yml`, `.woodpecker/*`.
- **Aceptación:**
  - [ ] CI **verde con el repo actual** (los seams existentes están en la allowlist).
  - [ ] El sidebar se genera de los manifests: añadir/activar una app **no** edita `navegacion.ts` a mano.
  - [ ] Un import nuevo `api/<appX>` → internals de `api/<appY>` (fuera de allowlist) **rompe CI**.
  - [ ] Desactivar el flag de una app la **oculta del catálogo** sin romper el arranque.
  - [ ] CI corre **solo los tests de la app tocada** (+ contrato + `keni-shared`) por filtro de
    rutas; cambio en `keni-shared` corre la suite completa. (Test scoping, artefacto 5.)

### Fase 1 — Saneo de seams (tras Fase 0; paralelas entre sí)

**T1.1 — `reciclaje` (A) deja de importar `publicaciones` (C) · rama `sep/seam-reciclaje`.**
- Sustituir el import interno por consumo de la **API/contrato de lectura** de `publicaciones`.
- **Ficheros propios:** `api/reciclaje.py` (+ contrato de lectura que exponga C si hace falta, sin
  tocar la lógica de `publicaciones`).
- **Aceptación:** [ ] el lint de T0 pasa sin `reciclaje` en la allowlist de excepciones internas;
  [ ] reciclaje sigue listando candidatas y disparando el reciclado existente.

**T1.2 — `panel` (shell) formaliza lectura de B + cola de C · rama `sep/seam-panel`.**
- Asegurar que `panel` lee métricas por `keni_metricas.servicio` y la cola por la fachada de C, no
  por internals.
- **Ficheros propios:** `api/panel.py`.
- **Aceptación:** [ ] panel rinde resumen de métricas + cola sin importar internals de B/C.

**T1.3 — Handoff A→C (generación → borrador) como contrato explícito · rama `sep/seam-handoff`.**
- Formalizar el camino "una generación de copy crea un borrador en `publicaciones`" como
  endpoint/evento del gateway (no import directo de C desde generación).
- **Ficheros propios:** punto de creación de borrador (en `generaciones`/`skills_generacion_api`) +
  el endpoint de ingreso de C.
- **Aceptación:** [ ] crear copy → borrador sigue funcionando vía contrato; [ ] lint en verde.

### Fase 2 — Declaración por app (tras Fase 0; paralelas entre sí y con Fase 1)

> Cada agente solo edita **su** manifest (fichero propio) + ajustes acotados de **sus** módulos.
> No tocan `navegacion.ts` ni `router.tsx` (ya data-driven tras T0).

**T2.A — App Producción · rama `sep/app-produccion`.**
- Completar/validar `apps/produccion.toml` con sus 13 módulos y rutas; verificar que ningún módulo
  de A importa internals de B/C (salvo seams ya saneados en Fase 1).
- **Aceptación:** [ ] A se activa/desactiva por flag; [ ] lint en verde para todos los módulos de A.

**T2.B — App Métricas · rama `sep/app-metricas`.**
- `apps/metricas.toml` (3 módulos) + flag de activación propio.
- **Camino de dato real: adapter `FuenteMetricol`** (API REST de Metricool; AMX en plan Advanced →
  API token) como **una `FuenteMetricas` más**, **sin App Review**. B es **consumidor** de Metricool,
  no ingesta propia (ver ADR 0005 §B). La fuente `muestra` queda como fallback/demo.
- **Aceptación:** [ ] B aparece/desaparece del catálogo por flag; [ ] no importa internals de A/C;
  [ ] el adapter Metricool entrega métricas reales por marca tras configurar el API token (degrada
  con honestidad si no hay token); [ ] **no** se añaden adaptadores propios por plataforma.

**T2.C — App Operación · rama `sep/app-operacion`.**
- `apps/operacion.toml` (5 módulos) + flag (multiusuario #130). **Publicación real** queda como
  sub-capacidad que enciende con App Review; rota/pendientes activas antes.
- **Aceptación:** [ ] C por flag; [ ] no importa internals de A/B (cola la lee panel vía fachada).

**T2.S — Shell · rama `sep/shell`.**
- `apps/shell.toml` con los 11 módulos transversales; confirmar que viven en home/ajustes (ya en el
  dropdown del avatar) y no como app de catálogo.
- **Aceptación:** [ ] los módulos shell no aparecen como apps; [ ] `media`/`conexiones`/`limites`
  expuestos como servicios consumibles por A/B/C según la allowlist.

### Fase 3 — Verificación integral · rama `sep/verificacion`

**T3 — Suite completa + matriz de activación.**
- Correr toda la batería: tests de los 3 paquetes Python + evals estáticos de `skills-copy` + build
  del frontend.
- Probar la **matriz de flags**: A / A+B / A+C / A+B+C arrancan y el catálogo refleja solo lo activo.
- Actualizar `docs/arquitectura.md` y `docs/estado-producto.md` para reflejar las 3 apps.
- **Aceptación:** [ ] CI verde; [ ] cada combinación de flags arranca sin error; [ ] docs alineados.

---

## 4. Garantía de no-colisión (ownership de ficheros)

| Rama | Ficheros que edita (exclusivos) |
|---|---|
| `sep/fundacion` | `apps/*`, `api/catalogo.py`, `navegacion.ts`, `router.tsx`, `tests/test_fronteras.py`, CI |
| `sep/seam-reciclaje` | `api/reciclaje.py` (+ contrato lectura C) |
| `sep/seam-panel` | `api/panel.py` |
| `sep/seam-handoff` | punto de borrador en `generaciones`/`skills_generacion_api` + ingreso C |
| `sep/app-produccion` | `apps/produccion.toml` |
| `sep/app-metricas` | `apps/metricas.toml` |
| `sep/app-operacion` | `apps/operacion.toml` |
| `sep/shell` | `apps/shell.toml` |

Como los manifests son **un fichero por app**, las tareas de Fase 2 no se pisan. Las de Fase 1 tocan
routers distintos. `app.py` **no se toca** (auto-descubre `RUTAS`). El único punto compartido
(`navegacion.ts`/`router.tsx`) lo deja cerrado la Fase 0 antes de abrir el paralelo.

---

## 5. Orden de lanzamiento sugerido

1. Lanzar **T0** (Fase 0) en solitario. Merge a `main` cuando CI quede verde.
2. Tras el merge: lanzar **en paralelo** T1.1, T1.2, T1.3, T2.A, T2.B, T2.C, T2.S (7 agentes,
   worktrees disjuntos). Cada uno hace `git fetch` y parte de `main` ya con la Fase 0.
3. Mergear cada rama a `main` conforme pase su CI (sin PR, push de rama a `main`).
4. Lanzar **T3** al final, sobre `main` con todo integrado.

---

## 6. Fuera de alcance (no lo hace esta separación)

- No mueve la **IP de dominio** (skills, contexto editorial, `FuenteMetricas`, `keni-shared`).
- No extrae nada a microservicios ni a repos aparte (ADR 0002: tres deployables, no N servicios).
- No toca **context-agent** (repo aparte, infra de contexto; ver `07-innovacion/context-agent`).
- No implementa features nuevas F1–F9: solo reordena fronteras. Las F# entran luego **como módulos**
  de su app (Fase D de ADR 0002).

---

## 7. Decisiones resueltas (2026-05-29)

Ya no quedan decisiones abiertas para arrancar; quedaban estas y se cierran así:

- **D-Métricas (B):** B es **consumidor de Metricool** vía API REST (AMX en Advanced), adapter
  `FuenteMetricol` detrás de `FuenteMetricas`. **Sin gating** para leer. No se construye ingesta
  propia por plataforma. (Descartada la variante "apuntar Claude al MCP de Metricool directamente":
  perdería la normalización por marca y el dashboard.)
- **D-Publicación (C):** rota / pendientes / parrilla / programación entran ya con multiusuario
  (#130); la **publicación real** es sub-capacidad que enciende con App Review, sin bloquear C.
- **D-Manifest:** formato **TOML por app** (`apps/<app>.toml`) + cargador `apps/registro.py`;
  catálogo y navegación data-driven desde ahí.
- **D-Test scoping:** jobs de CI por app/paquete con filtro de rutas (artefacto 5 / T0). Cierra la
  lentitud del pytest global.
- **D-Topología:** un solo deployable (catálogo), **no** microservicios; arquitectura **por tipo de
  app** según ADR 0005 §Arquitectura por tipo de app (A asíncrono+worker · B consumidor+caché ·
  C CRUD transaccional · Shell infra).
