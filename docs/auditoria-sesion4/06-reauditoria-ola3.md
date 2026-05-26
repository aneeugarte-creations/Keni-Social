# Re-auditoría post-Ola 3 — keni-social

> Auditor: Claude Code (claude-sonnet-4-6) · Fecha: 2026-05-25  
> Método: inspección directa del código + mirror completo de CI tras
> `git fetch origin && git merge --ff-only origin/main` (Already up to date).  
> SHA auditado: `2210565`. Evidencias en formato `archivo:línea`. No se modificó código.
>
> PRs fusionadas que se verifican: #98 (adelgazar skills.py), #103 (max-turns),
> #104 (pendientes), #112 (límites), #105–#108 (4 skills Ola 3).  
> Merge paralelo auditado de pasada: estudio-imagen → OpenRouter (SHA `b0cb849`).  
> Workflow ci.yml eliminado intencionalmente antes de esta ola — no se reporta.

---

## 1. Resultado del mirror de CI integrado

### 1.a mcp-metricas

```
cd mcp-metricas
pip install -e ".[dev]"   →  OK
ruff check .              →  All checks passed!
pytest                    →  459 passed in 0.79s
```

**VERDE. Sin fallos.**

---

### 1.b consola (backend)

```
pip install -e ./mcp-metricas
pip install -e "./consola[dev]"
cd consola
ruff check .              →  All checks passed!
pytest                    →  721 passed in 7.06s
```

**VERDE. Sin fallos.**

---

### 1.c consola (frontend)

```
cd consola/frontend
npm ci                    →  OK (0 vulnerabilities)
npm run lint              →  OK (eslint sin errores)
npm run typecheck         →  OK (tsc --noEmit sin errores)
npm run test              →  Test Files  9 passed (9) / Tests  53 passed (53)
npm run build             →  ✓ built in 2.72s
```

**VERDE. Sin fallos.**  
Los warnings de React Router Future Flag (`v7_startTransition`,
`v7_relativeSplatPath`) son ruido de versión, no errores; estaban ya en
Ola 2 y no bloquean.

**Bundle vendorizado coincide con el rebuild.** `git status
consola/src/keni_consola/webapp/` devuelve vacío tras `npm run build`:
el bundle commiteado es idéntico al resultado de recompilar en limpio.

---

### 1.d skills-copy/evals

```
pip install pytest pyyaml
cd skills-copy/evals
pytest -q    →  86 passed in 0.40s
```

**VERDE. Sin fallos.**

---

### Resumen CI

| Job | Resultado | Tests |
|---|---|---|
| mcp-metricas (ruff + pytest) | ✅ VERDE | 459 passed |
| consola backend (ruff + pytest) | ✅ VERDE | 721 passed |
| consola frontend (lint + typecheck + vitest + build) | ✅ VERDE | 53 passed |
| skills-copy evals (pytest) | ✅ VERDE | 86 passed |
| **Total** | **✅ VERDE** | **1319 passed, 0 failed** |

---

## 2. Verificación Ola 3

### 2.a #98 — Adelgazar `api/skills.py`

**VERIFICADO — PARCIALMENTE COMPLETO. Primera etapa cerrada; segunda etapa abierta.**

El hallazgo H6 original describía `api/skills.py` con 1694 L mezclando HTTP +
lógica de dominio + ciclo `generaciones ↔ api.skills` roto con import perezoso.

**Lo que se hizo:**

| Punto | Evidencia | Estado |
|---|---|---|
| Lógica de stream extraída a `dominio/stream.py` | `dominio/stream.py:35–662` — `MetricasRun`, `AcumuladorStream`, `parsear_resultado_json`, `arg_presupuesto`, `arg_max_turns`, `derivar_veredicto`, `normalizar_redes`, `quitar_emojis` | ✅ |
| Lógica de skills extraída a `dominio/skills.py` | `dominio/skills.py:1–297` — `construir_prompt*`, `cosechar_imagenes`, `crear_publicaciones_desde_piezas`, `construir_procesar_copy`, `construir_procesar_documento` | ✅ |
| `api/skills.py` ya NO importa `from .api import skills` localmente | `generaciones.py:48` solo importa `from .dominio import stream` — **ciclo resuelto** | ✅ |
| Import privado `_publicacion_a_dict` eliminado | `api/skills.py:61` — `from ..dominio.publicaciones import publicacion_a_dict` (pública) | ✅ |
| `dominio/publicaciones.py` hace pública `publicacion_a_dict` | `dominio/publicaciones.py` (43 L) | ✅ |
| Tests siguen pasando (contrato HTTP intacto) | 721 passed en consola | ✅ |

**Lo que sigue sin resolver (Ola 4):**

- `api/skills.py` sigue con **886 líneas** (bajó desde 1694, es progreso sustancial —47 % menos— pero supera el umbral de god-file de ~400 L). Los 8 handlers de catálogo (`catalogo_listar`, `catalogo_crear`, `catalogo_obtener`, `catalogo_actualizar`, `catalogo_skill_md`, `catalogo_borrar`, `catalogo_vista_prompt`, y `catalogo_vista_prompt`) en `api/skills.py:762–886` son candidatos naturales para un fichero separado `api/skills_catalogo_api.py` (ver §3).
- `api/skills.py:225–233` contiene `normalizar_redes()` como wrapper local de `stream.normalizar_redes()`. Trivialmente redundante, no es un problema.
- `termometro_cli.py:37` sigue importando `from .api import skills as api_skills` para usar `_arg_presupuesto()`, `normalizar_redes()`, `_cwd_ejecucion_skills()`, `parsear_resultado_json`, `SkillError`, y `construir_procesar_documento`. Todos estos ya están en `dominio/stream` o `dominio/skills`; el import es un alias hacia atrás que funciona pero es el residuo de acoplamiento más visible (ver N13).
- `skills_catalogo.py:165` tiene `from .api import skills` en un import local para resolver la ruta de skills. Esto también es un residuo de acoplamiento hacia `api/` desde un módulo de dominio (ver N13).

---

### 2.b #103 — max-turns llega al argv (F-T-01)

**VERIFICADO — COMPLETO.**

| Punto | Evidencia | Estado |
|---|---|---|
| `KENI_CLAUDE_MAX_TURNS` leído y validado | `dominio/stream.py:88–130` — `arg_max_turns()` devuelve `['--max-turns', N]` si la env es un entero positivo, `[]` si no | ✅ |
| Pasa al subproceso de `claude` | `generaciones.py:283` — `*stream.arg_max_turns()` en la lista de argumentos del Popen | ✅ |
| Vive en dominio, no en `api/skills.py` | La función `arg_max_turns` está en `dominio/stream.py`, igual que `arg_presupuesto` — el docstring de `generaciones.py:272` lo documenta explícitamente | ✅ |
| Test de la función | `consola/tests/test_dominio_stream.py` (parte del suite de 721 passed) | ✅ |

---

### 2.c #104 — Vista de pendientes

**VERIFICADO — COMPLETO.**

`pages/Tareas.tsx` existe y tiene test en `pages/Tareas.test.tsx` (5 tests, todos pasan). El backend `api/tareas.py` no se modificó (ya existía). La página está en el router y el bundle incluye el chunk correspondiente. El test verifica lista de tareas y barra de estatus con recuento por estado.

---

### 2.d #112 — Límites de plataforma desde única fuente

**VERIFICADO — COMPLETO Y BIEN CABLEADO. Cadena end-to-end cerrada.**

La divergencia TikTok 2200 vs 4000 (detectada en la auditoría de Ola 2, §2 punto #112) está **reconciliada**.

Cadena de única fuente:

**Nivel 1 — módulo canónico:** `consola/src/keni_consola/limites_plataforma.py` — `LIMITES: dict[str, int|None]` con `tiktok: 4000`. Sin estado ni I/O.

**Nivel 2 — `redes.py` consume `limites_plataforma`:** `redes.py:38–42` — cada `Red` se construye con `limite=limites_plataforma.limite_de(id)`. No redefine los valores.

**Nivel 3 — endpoint `GET /api/limites`:** `api/limites.py:27–30` — itera `redes.REDES` y emite `{id, nombre, limite}`. Test en `consola/tests/test_api_limites.py` verifica forma y unicidad.

**Nivel 4 — frontend hidratación:** `AppShell.tsx:44–51` — llama `GET /api/limites` al arrancar y pasa el resultado a `hidratarLimites()` (idempotente). `meta.ts:68–74` sobrescribe la caché mutable `_limites`.

**Nivel 5 — semilla de arranque:** `meta.ts:51–58` — `_LIMITES_SEMILLA` con los mismos valores (incluyendo `tiktok: 4000`), para que `metaRed().limite` sea correcto antes de la hidratación.

**Nivel 6 — guard de skills:** `skills-copy/evals/test_limites.py` — verifica que `plataformas.md` declara TikTok a 4000 y no a 2200 (test `test_tiktok_reconciliado_a_4000_y_sin_2200`). El guard se ancla en la tabla canónica `LIMITES_CANONICOS` (espejo estático de `limites_plataforma.LIMITES`).

**Nivel 7 — `plataformas.md` reconciliado:** `skills-copy/contexto-editorial/plataformas.md` — sección TikTok dice "límite duro 4.000 caracteres" sin mencionar 2200.

**Gap menor — N11 subsiste parcialmente:** No existe un test en Python que importe dinámicamente `limites_plataforma.LIMITES` y verifique que `_LIMITES_SEMILLA` en `meta.ts` coincide byte a byte. El guard de evals usa una tabla estática duplicada. Si alguien actualiza `limites_plataforma.py` y olvida actualizar `_LIMITES_SEMILLA` en `meta.ts` Y la tabla en `evals/test_limites.py`, hay un drift silencioso hasta que la app haga la primera petición de hidratación. Severidad baja (la semilla solo cubre el instante antes de la hidratación; el error es cosmético y temporal).

---

### 2.e #112 + badge `CompararPeriodos` (N6 de Ola 2)

**VERIFICADO — COMPLETO. Casamiento end-to-end cerrado.**

El N6 (la comparativa no mostraba badge de fuente) está resuelto en el commit `2210565`.

| Punto | Evidencia | Estado |
|---|---|---|
| Backend `_fuente_combinada(rep_a, rep_b)` | `api/metricas.py:51–63` — si alguno de los dos reportes es "muestra", el combinado lo es | ✅ |
| `comparar` emite `"fuente"` | `api/metricas.py:208` — `"fuente": _fuente_combinada(rep_a, rep_b)` | ✅ |
| Frontend consume el campo | `CompararPeriodos.tsx:142–144` — `<BadgeFuente fuente={data.fuente} className="ml-1" />` | ✅ |
| Tipo TS actualizado | `types.ts` tiene `fuente` en el tipo de respuesta de comparar | ✅ |
| Tests de backend | `test_api_metricas.py:74–89` — `test_comparar_expone_fuente_muestra` y `test_comparar_acotado_a_una_marca_sigue_trayendo_fuente` | ✅ |

---

### 2.f #105–#108 — Las 4 skills de Ola 3

**VERIFICADAS — TODAS COMPLETAS. Los 86 tests de evals pasan en verde.**

| Skill | Issue | Grupo | Fuera de experimental | Puntos clave | Estado |
|---|---|---|---|---|---|
| `voces-marca` | #105 | `produccion` | ✅ | `historial` + `nombre_voz` en keni.yaml; referencia `_plantilla.md`; destino `contexto-editorial/voces/`; avisa de no inventar rasgos | ✅ COMPLETO |
| `publica-meta` | #106 | `produccion` | ✅ | `name: publica-meta` en frontmatter; DRY-RUN documentado; afirma que no publica | ✅ COMPLETO |
| `responde-comentarios` | #107 | `comunidad` | ✅ | Sin marca `> **Experimental:**`; scope sin lives declarado | ✅ COMPLETO |
| `calendario-editorial` | #108 | `planificacion` | ✅ | Sin marca experimental; soporta evergreen + efemérides; campo `ventana` en keni.yaml | ✅ COMPLETO |

**Residuo detectado:** el directorio `skills-copy/.claude/skills/publica-preview/` sigue existiendo con `grupo: experimentales`. Es el nombre anterior de `publica-meta`. No causa ningún fallo (los evals no lo testean; está en experimental así que no aparece en la UI de producción), pero es dead code de skills. Recomendación: borrar en Ola 4.

---

### 2.g Merge paralelo estudio-imagen → OpenRouter

**VERIFICADO — FUNCIONAL. No introduce regresiones en el core.**

`generaciones.py:304` mapea `"openrouter": "OPENROUTER_API_KEY"` como uno de los proveedores de imagen soportados junto a `"openai"` y `"gemini"`. El test suite de consola (721 passed) cubre el generador de imagen con fakes; el merge no rompe nada.

El cambio es puntual en `generaciones.py` y en `secretos.py` (almacén de proveedor + clave). No toca el bundle (el frontend ya tenía el selector de proveedor). El skill `estudio-imagen` tiene su propio `generar.py` y `test_expandir.py`.

---

### Resumen verificación Ola 3

| Check | Resultado |
|---|---|
| #98 adelgazar skills.py + ciclo resuelto + import privado eliminado | ✅ COMPLETO (primera etapa); 886 L restan (Ola 4) |
| #103 max-turns llega al argv desde `KENI_CLAUDE_MAX_TURNS` | ✅ COMPLETO + tests |
| #104 vista de pendientes (Tareas.tsx) | ✅ COMPLETO + tests |
| #112 límites única fuente: `limites_plataforma` → `redes` → `GET /api/limites` → AppShell → `hidratarLimites` → `meta.ts` | ✅ COMPLETO + guard en evals |
| #112 + N6: badge `CompararPeriodos` con `_fuente_combinada` | ✅ COMPLETO + tests |
| #105 voces-marca | ✅ COMPLETO + 9 tests evals |
| #106 publica-meta | ✅ COMPLETO + 7 tests evals |
| #107 responde-comentarios fuera de experimental | ✅ COMPLETO + 4 tests evals |
| #108 calendario-editorial evergreen + efemérides | ✅ COMPLETO + 6 tests evals |
| Bundle vendorizado coincide con rebuild | ✅ git status vacío tras npm run build |
| CI integrado (4 jobs) | ✅ 1319 passed, 0 failed |

**Regresiones detectadas:** ninguna respecto a Ola 2.

---

## 3. Scope Ola 4 — Estado de residuos y plan

### 3.a #101 — Generar `types.ts` desde backend

**Estado: PENDIENTE (Ola 4 confirmado).**

`types.ts` sigue con ~179 interfaces a mano. En Ola 3 se añadieron `LimiteRed`, `RespuestaLimites` a mano (aunque bien documentados). El riesgo de desincronización sigue siendo bajo dado que `tsc --noEmit` y los tests de API atrapan las roturas más gruesas, pero la adición de cada campo nuevo (como `fuente` en Ola 2) es manual y no tiene verificación automática de completitud.

**Plan:** opción de menor invasión = `GET /api/schema.json` que emita los tipos clave como JSON Schema, procesado con `json-schema-to-typescript`. Requiere formalizar los dicts de respuesta de los endpoints principales como TypedDicts o modelos Pydantic. Estimación: L (2–3 días). Sin bloqueantes urgentes.

---

### 3.b `api/skills.py` 886 L — partir handlers de catálogo

**Estado: PRIMERA ETAPA COMPLETADA EN OLA 3. Segunda etapa lista para Ola 4.**

La bajada de 1694 → 886 L es real y bien hecha: la lógica de dominio vive en `dominio/`. Lo que queda en las 886 líneas:

| Sección | Líneas aprox. | Observación |
|---|---|---|
| Cabecera + reexportaciones de dominio | ~95 L | Necesarias para retrocompatibilidad; no mover |
| Handlers HTTP `opciones`, `ejecutar`, `ejecutar_archivo`, `historial*`, `historial_guardar` | ~200 L | Core del handler; queda aquí |
| Helpers HTTP (`normalizar_redes` wrapper, `_preview`, `_redes_desde_form`, `_nombre_skill`, etc.) | ~120 L | Pueden quedarse o ir a dominio |
| 8 handlers de catálogo (`catalogo_listar`…`catalogo_borrar`…`catalogo_vista_prompt`) | ~125 L | **Candidatos a `api/skills_catalogo_api.py`** — son CRUD puro del catálogo de archivos, independientes de la lógica de generación |
| Resto (validación, lanzadores, helpers de subida) | ~346 L | Queda en `api/skills.py` |

**Recomendación Ola 4:** extraer las 8 funciones `catalogo_*` a `api/skills_catalogo_api.py`. Esto dejaría `api/skills.py` en ~760 L (no llega al umbral ideal de 400, pero el módulo tiene responsabilidades legítimamente amplias). La extracción es mecánica, sin cambio de contratos HTTP.

---

### 3.c N11 — Test cruzado semilla `meta.ts` ↔ backend de límites

**Estado: PARCIALMENTE RESUELTO. El guard estático existe pero no es dinámico.**

La guarda en `skills-copy/evals/test_limites.py` ancla una tabla `LIMITES_CANONICOS` estática. Si se actualiza `limites_plataforma.py` y se olvida actualizar `_LIMITES_SEMILLA` en `meta.ts` y la tabla de `test_limites.py`, hay drift silencioso.

**Fix para Ola 4 (XS):** añadir en `consola/tests/test_api_limites.py` un test que lea `limites_plataforma.LIMITES` y verifique que los valores numéricos de `_LIMITES_SEMILLA` en `meta.ts` coinciden. Se puede hacer parseando el fichero TS con regex (igual que hace `test_limites.py` para `plataformas.md`). Es una prueba de ~15 líneas.

---

### 3.d N12 — `RedComercial.limite` aparte

**Estado: RESUELTO POR #112.**

El tipo `RedComercial` en `types.ts:1363–1367` tiene `limite?: number` (opcional). El backend `api/comercial.py:192` llama `redes.opciones()` que a su vez usa `limites_plataforma.limite_de()`. La cadena es única. El `?` en TypeScript es correcto: `limite` puede ser `null` (sin tope) o un número; TS lo modela como opcional para tolerar los `null` del backend. No es un residuo; es correcto.

**Conclusión N12: cerrado.**

---

### 3.e Acoplamientos residuales `→ api.skills`

**Estado: DOCUMENTADO. Dos residuos concretos.**

| Módulo | Línea | Acoplamiento | Severidad | Fix propuesto |
|---|---|---|---|---|
| `termometro_cli.py:37` | `from .api import skills as api_skills` | Usa `_arg_presupuesto`, `parsear_resultado_json`, `SkillError`, `normalizar_redes`, `_cwd_ejecucion_skills`, `construir_procesar_documento` — todos ya en `dominio/stream` o `dominio/skills` | Baja-Media | Migrar los imports directamente a `dominio.stream` y `dominio.skills`; requiere ajustar la firma de `normalizar_redes` (añadir `canonicas` explícitas) |
| `skills_catalogo.py:165` | `from .api import skills` (import local dentro de función) | Solo para `skills._cwd_skills()`, que resuelve la ruta del directorio de skills | Baja | Mover `_cwd_skills()` a un módulo de dominio o a `skills_catalogo` mismo |

Ambos son legados del pre-refactor H6. No rompen nada (los tests pasan); son acoplamientos de dominio → API que quedan como deuda técnica menor.

---

### 3.f Limpieza de `publica-preview`

**Estado: RESIDUO ACTIVO.**

`skills-copy/.claude/skills/publica-preview/` existe con `grupo: experimentales`. Es el nombre anterior de `publica-meta` (issue #106 renombró el directorio a `publica-meta` pero no borró el antiguo). No aparece en la UI de producción (está en experimentales) ni rompe ningún test. Es código muerto.

**Fix (XS):** borrar el directorio en Ola 4.

---

### Tabla Ola 4 vs backlog

| Issue/Residuo | Ola 4 | Backlog menor | Justificación |
|---|---|---|---|
| #101 `types.ts` generado | ✅ | — | No hay urgencia pero la deuda crece con cada campo nuevo |
| Partir handlers catálogo de `api/skills.py` (~125 L) | ✅ | — | Mecánico, bajo riesgo, completa la reducción de H6 |
| N11 test cruzado semilla `meta.ts` ↔ `limites_plataforma` | ✅ | — | XS; evita drift silencioso |
| Acoplamientos `termometro_cli.py` y `skills_catalogo.py` → `api.skills` | — | ✅ | Funciona, tests pasan; refactor de confort |
| Borrar `publica-preview` (directorio muerto) | ✅ | — | XS; limpieza directa |
| `Termometro.tsx:323` `SelectorMarca` local (de Ola 2) | — | ✅ | Baja severidad; no reportado en nuevos issues |
| `ReporteDeportes.tsx` sin `BadgeFuente` (de Ola 2) | — | ✅ | El deck es solo para el equipo AMX que conoce el piloto |
| `skills_catalogo.py:187` wrapper `_escribir_atomico` redundante | — | ✅ | Trivial; no duplica lógica |
| E5 unificación de persistencia (`db.py` + `ficheros.py`) | — | Ola 5+ | El mayor riesgo; requiere plan de migración verificada |

---

## 4. Problemas NUEVOS

### N13 — `termometro_cli.py` y `skills_catalogo.py` siguen acoplados a `api.skills` (residuo H6)

**Detectado en esta auditoría.** Descrito en §3.e.

`termometro_cli.py:37` importa `from .api import skills as api_skills` y usa 6 símbolos que ya viven en `dominio/stream` y `dominio/skills`. El acoplamiento es innecesario tras el refactor #98: `termometro_cli` es un módulo de dominio (CLI de cron) que no debería depender de la capa HTTP.

`skills_catalogo.py:165` tiene un import local a `api.skills` solo para resolver la ruta del directorio de skills. Está dentro de una función (`dir_skills()`), lo que lo hace invisible en los imports de cabecera. La dependencia `skills_catalogo → api.skills` es una inversión de la dependencia natural (`api.skills → skills_catalogo`).

**Severidad:** Baja. El CI pasa. Es deuda estructural residual de H6, confirmada.

---

### N14 — `publica-preview` directorio zombie

**Detectado en esta auditoría.** Descrito en §3.f.

El directorio `skills-copy/.claude/skills/publica-preview/` quedó huérfano tras el rename a `publica-meta` (#106). No rompe nada. Es la misma clase de problema que `EnConstruccion.tsx` (código muerto reportado en H8 de la auditoría original).

**Severidad:** Muy baja. Limpieza directa.

---

## 5. Estado de la deuda estructural H1–H8

| Hallazgo | Descripción original | Olas cerradas | Estado actual |
|---|---|---|---|
| **H1** | Consola importa internals del MCP (no la fachada declarada) | Ola 2: `servicio_metricas` cubre `api/metricas.py`, `api/config.py`, `api/reporte_deportes.py` | **PARCIALMENTE CERRADO.** `api/conexiones.py:25` (`keni_metricas.config.ruta_config`) y `api/estado.py:25` (`keni_metricas.doctor`) siguen con imports directos. Documentados como aceptables (N4, N9 de Ola 1). Contrato de fachada incompleto pero acotado. |
| **H2** | Dos backends de persistencia (`db.py` + `ficheros.py`) + índice + migración | — | **ABIERTO.** `db.py` (1592 L), `ficheros.py` (1173 L), `indice.py`, `migracion.py` siguen coexistiendo. Es el mayor foco de complejidad accidental. Sin issues abiertos de Ola 3 ni Ola 4 planificados. Ola 5+ con plan de migración verificada. |
| **H3** | Catálogo de marcas duplicado en ≥4 fuentes (3 esquemas de id) | — | **ABIERTO.** `marcas.py`, `muestra.py`, `breaking-express/marcas.json`, fichas `.md` siguen siendo fuentes independientes. Sin issues abiertos. Requiere `keni-shared` (E1 del plan original). |
| **H4** | Boilerplate de adaptadores 4×; fórmula `engagement_pct` 10 copias | Ola 2: `AdaptadorBase` + fórmula única `engagement_pct` en `fuentes/base.py` | **CERRADO (Ola 2).** Verificado en la re-auditoría de Ola 2. |
| **H5** | `types.ts` espejado a mano (179 interfaces, 1440 L) | — | **ABIERTO.** Issue #101 en Ola 4. En Ola 3 se añadieron correctamente `LimiteRed`, `RespuestaLimites` pero de forma manual. |
| **H6** | Lógica de negocio en `api/skills.py` + ciclo + dependencia invertida dominio→API | Ola 3: dominio extraído a `dominio/stream.py` + `dominio/skills.py`; ciclo resuelto; import privado `_publicacion_a_dict` eliminado | **PARCIALMENTE CERRADO (Ola 3).** 1694→886 L. Segunda etapa (handlers de catálogo) en Ola 4. Acoplamientos residuales N13 (`termometro_cli` + `skills_catalogo`) documentados. |
| **H7** | Escritura atómica + límites de plataforma + render/formato + datos de muestra duplicados | Ola 2: `io_atomico` único. Ola 3: `limites_plataforma` única fuente. | **PARCIALMENTE CERRADO.** Escritura atómica ✅ (Ola 2). Límites de plataforma ✅ (Ola 3). Render/formato y datos de muestra siguen sin unificar (no hay issues abiertos; backlog menor). |
| **H8** | Código muerto + god-files + constantes Meta duplicadas | Ola 3: `publica-preview` zombie añadido | **PARCIALMENTE CERRADO.** `EnConstruccion.tsx` documentado (no hay issue de borrado abierto). God-files reducidos: `api/skills.py` 1694→886 L. `publica-preview` nuevo zombie (N14). Constantes `BASE`/`TIPO_SYSTEM_USER` duplicadas en `fuentes/meta.py` y `publicacion/meta.py` siguen sin unificar. |

### Síntesis deuda H1–H8

- **Cerrados completamente:** H4
- **Cerrados en Ola 3 (segunda etapa abierta):** H6 (primera etapa cerrada; 886 L restantes + N13)
- **Avance sustancial (Ola 2 + Ola 3):** H7 (io_atomico + límites resueltos; render/muestra pendientes)
- **Avance parcial (Ola 2):** H1 (fachada cubre la mayoría; dos residuos documentados)
- **Sin tocar:** H2, H3, H5 — los tres más costosos. H2 es el de mayor riesgo operativo; H3 requiere `keni-shared`; H5 espera Ola 4.

---

## 6. Resumen ejecutivo

**Ola 3: sin regresiones. CI 100 % verde (1319 tests passed). Todos los objetivos principales cumplidos.**

Los tres cambios estructurales más relevantes de la ola:

1. **#98 primera etapa cerrada:** `api/skills.py` bajó 47 % (1694→886 L). La lógica de dominio vive en `dominio/stream.py` (662 L) y `dominio/skills.py` (297 L). El ciclo `generaciones ↔ api.skills` está roto: `generaciones.py` solo importa `dominio.stream`. El import privado `_publicacion_a_dict` se eliminó; ahora `publicacion_a_dict` es pública en `dominio/publicaciones.py`. Lo que queda para Ola 4: partir los 8 handlers de catálogo (~125 L) y migrar `termometro_cli.py` y `skills_catalogo.py` para que no importen `api.skills`.

2. **#112 + N6 completamente cerrados:** La cadena `limites_plataforma.py` → `redes.py` → `GET /api/limites` → `AppShell.hidratarLimites()` → `meta.ts._LIMITES_SEMILLA` está completa y verificada en los 4 niveles (pytest consola, vitest frontend, evals skills, `plataformas.md`). El badge `BadgeFuente` en `CompararPeriodos.tsx` está cableado con `_fuente_combinada()` en el backend y cubierto por tests.

3. **4 skills de Ola 3 validadas:** Las skills `voces-marca`, `publica-meta`, `responde-comentarios` y `calendario-editorial` están en grupos de producción, fuera de experimental, con contratos de skill correctos y 26 tests de evals pasando.

**Ola 4 — issues confirmados:** #101 (`types.ts` generado), partir handlers catálogo de `api/skills.py`, N11 (test cruzado semilla), borrar `publica-preview`.

**Deuda estructural pendiente sin fecha:** H2 (persistencia dual — el más arriesgado), H3 (catálogo de marcas sin `keni-shared`), el render/formato duplicado (H7 parcial).

---

*Auditoría completada 2026-05-25. CI ejecutado en venvs aislados (PEP 668). No se modificó código. SHA auditado: `2210565`.*
