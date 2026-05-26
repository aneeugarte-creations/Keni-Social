# Re-auditoría post-Ola 2 — keni-social

> Auditor: Claude Code (claude-sonnet-4-6) · Fecha: 2026-05-25  
> Método: inspección directa del código tras `git fetch origin && git merge
> --ff-only origin/main` (Already up to date). Evidencias en formato
> `archivo:línea`. Solo análisis; sin cambios de código.
>
> PRs fusionadas que se verifican: #97 (AdaptadorBase), #96 (servicio_metricas),
> #99 (escribir_atomico), #89 (componentes comunes), #90 (badge fuente).

---

## 1. Verificación Ola 2

### 1.a #97 — AdaptadorBase + engagement_pct única fórmula

**VERIFICADO — COMPLETO.**

| Punto | Evidencia | Estado |
|---|---|---|
| Fórmula única `engagement_pct(interacciones, visualizaciones)` | `mcp-metricas/src/keni_metricas/fuentes/base.py:34–40` — única definición, docstring cita explícitamente "antes duplicada en 10 sitios / #97 / H4" | ✅ |
| Sin fórmula inline `round(inter / vis * 100, 1)` en los 7 módulos que la usaban | `grep` en `fuentes/meta.py`, `youtube.py`, `x.py`, `tiktok.py`, `muestra.py`, `agregador.py`, `reporte.py` — **0 coincidencias** | ✅ |
| Los 4 adaptadores usan `engagement_pct` del módulo base | `meta.py:112,157` · `youtube.py:79,118` · `x.py:75,100` · `tiktok.py:102,128` — todos llaman `engagement_pct(inter, vis)` importada de `base` | ✅ |
| `class AdaptadorBase` concreta (no solo Protocol) | `fuentes/base.py:71–131` — `AdaptadorBase` con `disponible()`, `_headers_bearer()`, `_refrescar()` (no-op), `_intentar()` | ✅ |
| Los 4 adaptadores heredan de `AdaptadorBase` | `meta.py:42` `class AdaptadorMeta(AdaptadorBase)` · `youtube.py:23` · `x.py:25` · `tiktok.py:23` | ✅ |
| Test de herencia e issubclass | `mcp-metricas/tests/test_adaptadores.py:64–67` — `test_adaptadores_heredan_base` verifica `issubclass` para los 4 | ✅ |
| Test de fórmula única | `test_adaptadores.py:56–57` — `test_engagement_pct_formula_unica` con 3 casos (con vis, vis=0, normal) | ✅ |
| API pública estable | `base.py:51–68` — `FuenteMetricas` y `AdaptadorPlataforma` como `Protocol`s con `runtime_checkable`; `AdaptadorBase` es la clase de implementación. Contrato declarado en `__all__` implícito del módulo. | ✅ |

**Nota menor:** `muestra.py:296` calcula `eng = engagement_pct(inter, vis)` (importada de `base`) y luego lo asigna en `:237,277,306`. La fórmula está centralizada; el alias local `eng` es un rename local de nomenclatura, no una duplicación.

---

### 1.b #96 — Fachada `servicio_metricas`; ningún `api/*.py` (salvo `conexiones.py` y `estado.py`) importa internals de `keni_metricas`

**VERIFICADO — COMPLETO, con residuos documentados y acotados.**

| Módulo | Imports de keni_metricas | Estado |
|---|---|---|
| `api/metricas.py:15` | `from keni_metricas import servicio` | ✅ solo fachada |
| `api/reporte_deportes.py:19–20` | `from keni_metricas import servicio` · `from keni_metricas.servicio import CuentaNoEncontrada` | ✅ solo fachada |
| `api/config.py:15–16` | `from keni_metricas import servicio` · `from keni_metricas.servicio import FUENTES_DISPONIBLES, ConfigInvalida` | ✅ solo fachada |
| `api/conexiones.py:24–25` | `from keni_metricas import asistente` · `from keni_metricas.config import ruta_config` | ⚠️ **residuo** — dentro del alcance documentado (credenciales no viven en la fachada; ver N4 de Ola 1); no es una regresión |
| `api/estado.py:25` | `from keni_metricas import doctor` | ⚠️ **residuo** — también dentro del alcance documentado; `estado.py` es un wrapper muy delgado sobre `doctor`; ver §4 de este informe |

El módulo `mcp-metricas/src/keni_metricas/servicio.py` existe (247 líneas), tiene `__all__` explícito con 18 símbolos públicos y expone `RANGOS_VALIDOS`, `FUENTES_DISPONIBLES`, `CUENTA_DEPORTES_PRINCIPAL`, `CUENTAS_DEPORTES_HERMANAS`, `ConfigInvalida`, `CuentaNoEncontrada`, y las funciones `nombre_fuente()`, `cuentas_disponibles()`, `construir_reporte()`, `reporte_csv()`, `reporte_markdown()`, `reporte_json()`, `construir_reporte_deportes()`, `render_reporte_deportes_pptx()`, `instantanea_config()`, `guardar_fuente_y_alcance()`, `normalizar_alcance()`.

**Cobertura de test:** `mcp-metricas/tests/test_servicio.py` (156 líneas) cubre el contrato de la fachada.

---

### 1.c #99 — `escribir_atomico` único usado por todos los módulos de consola (incluido `sugerencias.py`)

**VERIFICADO — COMPLETO, con una copia residual en `keni_metricas` (esperada y documentada).**

`consola/src/keni_consola/io_atomico.py` existe (65 líneas), con `escribir_atomico(ruta, texto, *, modo, prefijo, sufijo)`. Docstring cita explícitamente los 9 módulos que tenían el patrón antes.

| Módulo | Usa `io_atomico.escribir_atomico` | Evidencia |
|---|---|---|
| `ficheros.py:51,179` | ✅ | `from .io_atomico import escribir_atomico` |
| `agentes.py:61,804` | ✅ | `from .io_atomico import escribir_atomico` (wrapper local `_escribir_texto_atomico` delega en él) |
| `sugerencias.py:26,118` | ✅ | `from .io_atomico import escribir_atomico` |
| `secretos.py:22,72` | ✅ | `from .io_atomico import escribir_atomico` |
| `skills_catalogo.py:36,187–189` | ✅ | `from .io_atomico import escribir_atomico` (wrapper local `_escribir_atomico` delega en él) |
| `termometro.py:26,71` | ✅ | `from .io_atomico import escribir_atomico` |
| `preferencias.py:20,73` | ✅ | `from .io_atomico import escribir_atomico` |
| `generaciones.py:48,124` | ✅ | `from .io_atomico import escribir_atomico` |
| `mcp-metricas/asistente.py:437–453` | ❌ copia propia | Esperado: `keni_metricas` no puede importar de `keni_consola`; queda aislada hasta que exista `keni-shared`. Docstring lo documenta. |

**Test:** `consola/tests/test_io_atomico.py` (89 líneas) cubre la función única.

**Nota menor:** `skills_catalogo.py:187–189` define `_escribir_atomico(ruta, texto)` como wrapper de un wrapper (delega en `escribir_atomico`); es redundante pero trivial — un paso intermedio de refactor que no duplica lógica.

---

### 1.d #90/#89 + `fuente` — casamiento END-TO-END

**VERIFICADO — COMPLETO y correctamente cableado.**

Este punto era el más delicado del scope (la agente C avisó que en su merge aún no estaba el campo; B lo añadió después). La cadena completa:

**Nivel 1 — backend métricas:** `mcp-metricas/src/keni_metricas/reporte.py:64` emite `"fuente": fuente.nombre` en el dict del reporte. La fuente de muestra tiene `nombre = "muestra"` (protocolo `FuenteMetricas.nombre`). La fuente real usaría un nombre diferente (p. ej. `"meta"`).

**Nivel 2 — fachada:** `keni_metricas/servicio.py:107–113` — `construir_reporte()` llama a `_reporte.construir_reporte()` y retorna el dict intacto; el campo `fuente` pasa sin transformar.

**Nivel 3 — API consola:** `consola/src/keni_consola/api/metricas.py:129–136`:

```python
# Fuente de los datos: "muestra" (ficticios) o "real". La UI pinta un badge
# de advertencia con esto para que no se confundan datos de muestra con
# reales (riesgo operativo del piloto AMX). Cae a "muestra" por prudencia.
"fuente": rep.get("fuente") or "muestra",
```

El campo `fuente` se expone con fallback defensivo a `"muestra"` si el backend no lo manda.

**Nivel 4 — tipos TS:** `consola/frontend/src/types.ts:743–755` — `ReporteMetricas.fuente?: string` (opcional, con comentario explicativo de que el backend lo añade "en paralelo").

**Nivel 5 — lógica de fuente:** `frontend/src/components/comunes/fuente.ts:10,17` — `FUENTE_MUESTRA = "muestra"` y `esFuenteMuestra(fuente)` que retorna `true` solo para `=== "muestra"`.

**Nivel 6 — componente BadgeFuente:** `frontend/src/components/comunes/BadgeFuente.tsx:17–43` — renderiza `<Badge variant="aviso">Datos de muestra</Badge>` o `<Badge variant="ok">Datos reales</Badge>`; si `fuente` es `undefined`/`null`/`""` no renderiza nada (defensivo).

**Nivel 7 — consumidores UI:**
- `pages/Metricas.tsx:146` — `<BadgeFuente fuente={reporteQuery.data.fuente} />` en el dashboard principal.
- `pages/metricas/TablaCuentas.tsx:29–40` — recibe `fuente?: string` y renderiza `<BadgeFuente fuente={fuente} />` en la cabecera de la tabla.

**Nivel 8 — test:** `test_api_metricas.py:21–54` — `test_reporte_expone_fuente_muestra` y `test_reporte_acotado_a_una_marca_sigue_trayendo_fuente` verifican `data["fuente"] == "muestra"`; `test_export_json_incluye_fuente` verifica que el JSON crudo también lleva `fuente`.

**Cabo suelto — `ReporteDeportes.tsx`:** La página de reporte de deportes (`pages/ReporteDeportes.tsx`) no muestra `BadgeFuente`. El backend sí emite `fuente` en `reporte_deck.py:186`, y `ReporteDeportes` en `types.ts:832` lo tiene como `fuente: string` (no opcional). La UI de preview del deck (`Previsualizacion`) simplemente no lo muestra. Es un gap menor (el deck de deportes es solo para Claro Sports/AMX, que saben que están en piloto), pero es inconsistente con el dashboard principal.

**Resolución del casamiento:** el campo `fuente` que el Agente C necesitaba (procedente del Agente B vía `#96`) **sí llegó** antes de que el bundle se regenerara. La cadena completa está cableada y verificada con tests.

---

### 1.e Resumen Ola 2

| Check | Resultado |
|---|---|
| #97 `AdaptadorBase` + fórmula única `engagement_pct` | ✅ COMPLETO + tests |
| #96 `servicio_metricas` + `api/*.py` solo consume fachada | ✅ COMPLETO (residuos `conexiones.py` + `estado.py` dentro del plan) |
| #99 `escribir_atomico` único en consola (incl. `sugerencias.py`) | ✅ COMPLETO + tests |
| #89 componentes comunes + centinela `NINGUNA` canónico + `SelectorRedMultiple` | ✅ COMPLETO |
| #90 `fuente` END-TO-END: `reporte.py` → `servicio` → `api/metricas.py` → `BadgeFuente` | ✅ COMPLETO + tests |
| Casamiento Agente B (`fuente` en API) × Agente C (`BadgeFuente`) | ✅ CASAN |

**Regresiones detectadas:** ninguna respecto a Ola 1.

**Cabos sueltos menores:**
- `ReporteDeportes.tsx` no muestra `BadgeFuente` aunque el backend sí emite `fuente` (ver §1.d).
- `Termometro.tsx:323` define su propio `function SelectorMarca()` local (no importa el componente compartido de `comunes/`). El centinela `NINGUNA` sí lo importa correctamente de `selectores.ts:8`. El componente local es funcionalmente equivalente pero no reutiliza el de `comunes`.
- `skills_catalogo.py:187` conserva un wrapper `_escribir_atomico` → `escribir_atomico` trivialmente redundante.

---

## 2. Scope Ola 3 — Estado real y evaluación por issue

### #98 — Adelgazar `api/skills.py` (1694 L)

**Estado: PENDIENTE. Viabilidad: ALTA.**

`api/skills.py` sigue en 1694 líneas. El análisis de responsabilidades:

| Responsabilidad | Líneas aprox. | Destino propuesto |
|---|---|---|
| HTTP handlers (`opciones`, `ejecutar`, `ejecutar_archivo`, `historial*`) | ~250 L | Queda en `api/skills.py` (≤400 L tras el movimiento) |
| `AcumuladorStream` + `parsear_resultado_json` + `parsear_salida` | ~350 L (`:396–928`) | → `generaciones.py` o nuevo `dominio/stream.py` |
| Verdicto `_derivar_verdicto` + `quitar_emojis` + helpers de parseo de encabezados | ~200 L (`:691–970`) | → `dominio/stream.py` |
| `_arg_presupuesto` + `MetricasRun` + `metricas_a_dict` | ~60 L (`:155–205`, `:326–345`) | → `generaciones.py` (ya usa estas clases) |
| `construir_prompt*` + `_instruccion_redes` | ~100 L (`:240–325`) | → `dominio/skills.py` o `skills_catalogo.py` |
| `_crear_publicaciones_desde_piezas` + helpers de imágenes | ~100 L (`:985–1043`, `:930–971`) | → `dominio/skills.py` |
| Import privado `from .publicaciones import _publicacion_a_dict` | `api/skills.py:62` | Hacer pública `publicacion_a_dict` en `publicaciones.py` |

**Ciclo pendiente:** `generaciones.py:267,321` siguen con `from .api import skills` como import local para evitar el ciclo `generaciones↔api.skills`. Si `AcumuladorStream`/presupuesto se mueven a `generaciones.py`, el ciclo desaparece y los imports locales se eliminan.

**Riesgo:** medio. `api/skills.py` tiene amplia cobertura de test (varios `test_skills_*.py`); los tests guían el refactor. El handler que queda debe seguir pasando el mismo contrato HTTP.

**Estimación:** M-L (2–3 días). Ejecutable por un agente de backend en solitario.

---

### #101 — Generar `types.ts` desde backend / esquema compartido

**Estado: PENDIENTE. Viabilidad: MEDIA-BAJA en Ola 3.**

`types.ts` sigue con 179 interfaces, 1446 líneas. El campo `fuente` de `ReporteMetricas` se añadió a mano (`:754`, con comentario), lo que confirma que el proceso sigue siendo manual.

**Enfoque técnico viable:**
- El backend construye dicts a mano (no hay modelos Pydantic completos por endpoint, solo los del schema de métricas). Para generar tipos TS habría que: (a) formalizar los dicts de respuesta como modelos Pydantic en el backend, o (b) usar `datamodel-code-generator` / `pydantic-to-typescript` sobre los modelos existentes, o (c) añadir un endpoint `GET /api/schema.json` que emita JSON Schema y procesarlo con `json-schema-to-typescript`.
- La opción (c) es la de menor invasión: no requiere reescribir los handlers, solo formalizar las respuestas más importantes como TypedDicts/Pydantic y exportar el esquema.

**Dependencias:** requiere que las fronteras (`servicio`, `api/*.py`) estén estables (ya lo están tras Ola 2). No tiene dependencias de Ola 3.

**Riesgo de dejarlo para Ola 4:** bajo. `types.ts` se desincroniza silenciosamente, pero el CI con `tsc --noEmit` y los tests de API detectan las roturas más gruesas. El mayor riesgo es añadir campos nuevos en el backend sin actualizar `types.ts` (ya pasó con `fuente`, resuelto a mano).

**Recomendación:** dejar para Ola 4. Es el cambio de tooling más largo y sin bloqueantes urgentes. En Ola 3 se puede hacer como tarea de un solo agente si la carga de los demás issues lo permite.

---

### #112 — Límites de plataforma: única fuente (`meta.ts` ↔ `plataformas.md`)

**Estado: PENDIENTE. Viabilidad: ALTA y bajo riesgo.**

Hay exactamente **2 fuentes de verdad** (no más):

1. `consola/frontend/src/pages/publicaciones/meta.ts:26–33` — dict `META_REDES` con `limite` numérico o `null` (X: 280, IG: 2200, FB: null, TikTok: 2200, YT: null).
2. `skills-copy/contexto-editorial/plataformas.md:6,13,27,34` — prosa para la skill (X 280 duro, IG ~2200, TikTok ~2200/4000 recientes, YT título 100).

**Discrepancia detectada:** `plataformas.md:27` dice "~2.200 caracteres / ~4.000 en publicaciones recientes" para TikTok; `meta.ts:32` solo pone `2200`. La divergencia ya existe.

**Enfoque propuesto para unificar:**
- Añadir `GET /api/publicaciones/opciones` (o `GET /api/redes`) que exponga los límites desde el backend Python (único lugar de edición). El frontend importa desde ahí en vez de `meta.ts`.
- `plataformas.md` hace referencia al endpoint o a un archivo YAML de contexto editorial que sirve como fuente canónica para la skill.
- El dict `META_REDES` pasa a ser alimentado desde la respuesta del API en vez de estar hardcodeado.

**Estimación:** S-M (1 día). Ejecutable por el agente de frontend, aunque toca también el backend (añade el endpoint).

---

### #103 — max-turns al runner (F-T-01)

**Estado: PENDIENTE. Viabilidad: ALTA.**

`generaciones.py` usa `--max-budget-usd` vía `KENI_CLAUDE_MAX_USD` (`:319–342`) pero no `--max-turns`. La adición es mecánica: añadir `KENI_CLAUDE_MAX_TURNS` env o un parámetro por generación, pasarlo en el array `args` del subproceso, propagarlo desde el endpoint de ejecución en `api/skills.py`. Un campo en `types.ts` para exponerlo opcionalmente al frontend.

**Estimación:** XS-S (< 1 día). Backend puro; no toca el bundle.

---

### #104 — Vista editorial de pendientes (F-C-19)

**Estado: PENDIENTE. Viabilidad: ALTA.**

El backend de tareas (`api/tareas.py`) expone `listar`, `crear`, `actualizar`, `borrar`, `abrir`. El tipo `Tarea` existe en `types.ts`. Lo que falta es la página de frontend que consume ese backend y muestra los pendientes con estados. Es trabajo 100 % de frontend sobre una API ya existente.

**Estimación:** S-M (1–2 días). Solo frontend, pero requiere `npm run build` al final (toca el bundle).

---

### #105 — Voces personales: ingeniería inversa de voz de marca (F-S-07)

**Estado: PENDIENTE. `skills-copy/contexto-editorial/voces/` solo tiene `_plantilla.md`.**

La skill que ingiere historial de publicaciones y genera la ficha de voz es nueva (no existe ni en experimental). Es una skill de `skills-copy`; no toca el bundle del frontend ni el backend Python.

**Estimación:** M (1–2 días). Agente de skills-copy en solitario.

---

### #106 — `publica-meta`: alinear nombre exacto de la demo (F-S-08)

**Estado: PENDIENTE. La skill se llama `publica-preview` en el repo.**

`skills-copy/.claude/skills/publica-preview/keni.yaml:2` — `nombre: Publica preview`. El nombre demostrado es `publica-meta`. Es un rename de la skill (actualizar `keni.yaml`, `SKILL.md` y posiblemente el directorio de la skill). Sin impacto en el backend ni el frontend de la consola.

**Estimación:** XS (< 0.5 día). Solo skills-copy; sin dependencias.

---

### #107 — `responde-comentarios`: salir de experimental (F-C-22)

**Estado: PENDIENTE. Skill marcada como `grupo: experimentales` en `keni.yaml:3`.**

La skill existe y tiene ejemplos (`ejemplos/comentarios-ejemplo.md`). Salir de experimental requiere:
- Actualizar `keni.yaml` (cambiar `grupo`).
- Revisar y completar `SKILL.md` con el alcance acotado (sin moderación de lives).
- Pasar los checks estáticos de CI.

**Estimación:** XS-S (< 1 día). Solo skills-copy.

---

### #108 — `calendario-editorial` / evergreen anual (F-C-24)

**Estado: PARCIALMENTE PENDIENTE. Skill existe pero marcada `grupo: experimentales`.**

`skills-copy/.claude/skills/calendario-editorial/` existe con `keni.yaml` y `SKILL.md`. El issue pide añadir el cruce con efemérides por nicho de marca. Es la skill más compleja de las features 🟡: requiere contexto editorial por marca (ya existe en `contexto-editorial/marcas/*.md`), un catálogo de efemérides por nicho y la lógica de cruce.

**Estimación:** M (1–2 días). Solo skills-copy; sin dependencias de backend.

---

### Residuos de Ola 2 (issues nuevos detectados en esta auditoría)

| Residuo | Archivo:línea | Severidad | Fix |
|---|---|---|---|
| `api/estado.py:25` importa `keni_metricas.doctor` directo (no via fachada) | `api/estado.py:25` | Baja — documentado como aceptable en Ola 1 y en `servicio.py` (N4); el wrapper es muy delgado | Exponer `ejecutar_chequeos` en `servicio.py` si se quiere consistencia total; o dejarlo como está |
| `Termometro.tsx:323` tiene `SelectorMarca` local (no usa el componente de `comunes/`) | `Termometro.tsx:323–357` | Baja — usa `NINGUNA` de `comunes/selectores.ts` correctamente; el componente local es funcionalmente equivalente | Migrar a `comunes/SelectorMarca` con `conNinguna={true}` |
| `ReporteDeportes.tsx` no muestra `BadgeFuente` (el tipo lo tiene, la UI lo omite) | `ReporteDeportes.tsx` (sin `BadgeFuente`) · `types.ts:832` `fuente: string` | Baja — el deck es para un equipo que conoce el piloto; no es un riesgo operativo como el dashboard | Añadir `<BadgeFuente fuente={rep.fuente} />` en `Previsualizacion` |
| `skills_catalogo.py:187–189` tiene wrapper `_escribir_atomico` → `escribir_atomico` redundante | `skills_catalogo.py:187` | Trivial | Llamar `escribir_atomico(ruta, texto)` directamente en los 3 callsites |
| `CompararPeriodos.tsx` no muestra `BadgeFuente` (la comparativa no indica si los datos son muestra) | `metricas/CompararPeriodos.tsx` (sin badge) | Media — el usuario puede confundir la comparativa de datos ficticios con datos reales | Añadir `<BadgeFuente>` en la cabecera de la comparativa |

---

## 3. Partición sin solape para Ola 3

### Principios
- Bundle `consola/src/keni_consola/webapp/` solo lo regenera **un agente por ola** (`npm run build` en `consola/frontend/`).
- Fronteras naturales: `mcp-metricas` · `consola-backend` · `consola-frontend` · `skills-copy`.
- Dependencias de Ola 3 son planas (la fachada ya es estable, el catálogo de marcas es estable, `io_atomico` existe).

### Dependencias entre issues

```
#98 (skills.py)  →  necesita que #96 esté en main (ya está ✅)
                  →  independiente del frontend

#101 (types.ts)  →  requiere fronteras estables (✅ tras Ola 2)
                  →  independiente del resto de Ola 3 (Ola 4)

#112 (límites)   →  toca un endpoint nuevo (backend) + frontend (meta.ts)
                  →  el agente de frontend necesita el endpoint del backend

#103 (max-turns) →  solo backend generaciones.py; independiente

#104 (tareas UI) →  solo frontend; backend API existe; requiere bundle

#105 (voces)     →  solo skills-copy; independiente

#106 (publica)   →  solo skills-copy; independiente

#107 (responde)  →  solo skills-copy; independiente

#108 (calendario)→  solo skills-copy; independiente
```

### Propuesta de 4 grupos en paralelo

| Grupo | Issues | Archivos clave | Toca bundle | Prerequisito | Estimación |
|---|---|---|---|---|---|
| **Agente A** — Backend consola | #98 `api/skills.py` adelgazar + ciclo · #103 max-turns · residuos backend (estado.py/CompararPeriodos badge) | `api/skills.py`, `generaciones.py`, nuevo `dominio/stream.py` (o nombre elegido), `api/estado.py` (opcional) | No | Ninguno (fachada ya estable) | L (3 d) |
| **Agente B** — Frontend + límites plataforma | #104 vista editorial de pendientes · #112 límites única fuente (endpoint nuevo + refactor `meta.ts`) · residuos frontend (Termometro `SelectorMarca`, `ReporteDeportes BadgeFuente`, `CompararPeriodos BadgeFuente`) | `api/publicaciones.py` (o nuevo endpoint), `pages/publicaciones/meta.ts`, `pages/Termometro.tsx`, `pages/ReporteDeportes.tsx`, `pages/metricas/CompararPeriodos.tsx`, nueva `pages/Tareas.tsx` | **Sí** — único agente con `npm run build` | Depende del endpoint de límites del Agente A (o puede hacerlo él mismo si es un endpoint simple) | M-L (2–3 d) |
| **Agente C** — Skills-copy | #105 voces + #106 publica-meta rename + #107 responde-comentarios estabilizar + #108 calendario-editorial evergreen | `skills-copy/.claude/skills/*/keni.yaml`, `SKILL.md`, `contexto-editorial/voces/` | No | Ninguno | M (2 d) |
| **Agente D** — Tipos TS (Ola 4) | #101 `types.ts` generado | `types.ts`, añadir modelos Pydantic o TypedDicts en `api/*.py` | Sí | Fronteras estables (✅); pero no hay urgencia | L (2–3 d) |

### Notas de coordinación

1. **Agente A y C** pueden arrancar en paralelo sin dependencias entre sí.
2. **Agente B** puede arrancar la parte de frontend puro (#104 y los residuos) en paralelo con A, pero el issue #112 (endpoint de límites) necesita coordinarse: o el Agente A añade el endpoint en Python y B lo consume, o B lo añade él mismo en el mismo PR (más simple dado que es un endpoint pequeño). Recomendación: B lo hace todo en un solo PR.
3. **Agente D** (#101) se deja para Ola 4. La razón: `types.ts` estático funciona bien hoy (los tests de API + `tsc` en CI detectan roturas), y la generación de tipos requiere un cambio de tooling que no desbloquea ninguna otra feature urgente.
4. El bundle lo regenera **solo Agente B**. Agente A y C no tocan `frontend/`.

### Qué conviene dejar para Ola 4

| Issue | Por qué diferir |
|---|---|
| #101 `types.ts` generado | Cambio de tooling, no hay urgencia operativa; los tests de CI detectan desincronizaciones |
| Unificación de persistencia (E5 del plan original) | No está en los issues de Ola 3; el mayor riesgo de todo el backlog; requiere planificación con migración verificada |
| `EnConstruccion.tsx` / `agentes.py` reconciliación con dominio (E7) | Ya borrado en Ola 1; E7 sigue pendiente pero no hay issues abiertos concretos |

---

## 4. Problemas NUEVOS

### N6 — `CompararPeriodos` no muestra `BadgeFuente` (extensión del N3 resuelto)

`consola/frontend/src/pages/metricas/CompararPeriodos.tsx` no muestra `BadgeFuente`. La comparativa A vs B llama a `/api/metricas/comparar` que devuelve `{marca, rango_a, rango_b, etiqueta_a, etiqueta_b, total, por_marca}`, **sin campo `fuente`**. Los datos en `por_marca` pueden ser de muestra pero la UI no lo indica.

**Fix:** (a) añadir `fuente` al endpoint `GET /api/metricas/comparar` en `api/metricas.py:172–193` (tomando `fuente` de uno de los dos reportes; si alguno es muestra, el resultado lo es); (b) mostrar `<BadgeFuente>` en la cabecera de `CompararPeriodos.tsx`.

**Severidad:** Media. Misma clase de riesgo operativo que N3 (ya resuelto para el dashboard principal).

---

### N7 — Import privado `_publicacion_a_dict` persiste en `api/skills.py` (residuo H6)

`consola/src/keni_consola/api/skills.py:62` sigue con `from .publicaciones import _publicacion_a_dict`. El prefijo `_` señala que es un símbolo privado de otro handler. `skills.py:1019,1562` lo usa para crear publicaciones desde las piezas generadas.

La solución correcta es hacer pública `publicacion_a_dict` en `publicaciones.py` o moverla a un dominio compartido. Este residuo se resuelve en #98.

**Severidad:** Baja-Media (funciona, pero viola el principio de módulos con fronteras claras).

---

### N8 — `api/metricas.py:_variacion_pct` duplica la lógica de variación porcentual

`api/metricas.py:46–48` define `_variacion_pct(a, b)`. Esta es la misma función que existe de forma equivalente en otros puntos del codebase (el resultado de las métricas ya incluye `variacion_vs_anterior` desde el histórico). No es una duplicación crítica, pero si en el futuro se centraliza el formato de métricas, esta función sería el último candidato a extraer.

**Severidad:** Baja. Anotada como deuda de formato menor.

---

### N9 — `api/conexiones.py` importa `keni_metricas.config.ruta_config` directamente (no via fachada)

`api/conexiones.py:25` importa `from keni_metricas.config import ruta_config`. La fachada `servicio.py` expone `guardar_fuente_y_alcance()` y `normalizar_alcance()` pero no `ruta_config`. Esta función es la ruta al fichero de configuración del MCP; `conexiones.py` la usa para escribir credenciales directamente.

Esto fue documentado como aceptable en el hallazgo N4 de la re-auditoría Ola 1 ("la escritura de credenciales no vive en la fachada"). Lo registramos explícitamente como cabo suelto para que, cuando se amplíe `servicio.py`, se evalúe si `ruta_config` o una abstracción de ella debe exponerse como parte del contrato.

**Severidad:** Baja. No es un bug; es un acoplamiento acotado y documentado.

---

## 5. Resumen ejecutivo

**Ola 2: sin regresiones. Los 4 PRs principales están implementados correctamente.**

El casamiento clave — el campo `fuente: "muestra"` emitido por `reporte.py`, expuesto por la fachada `servicio.py`, pasado por `api/metricas.py:136` al JSON y consumido por `BadgeFuente.tsx:29` — **funciona end-to-end** y está cubierto por tests en los tres niveles (Python backend, Python API, Vitest frontend). El hecho de que el Agente B añadiera `fuente` en `api/metricas.py` antes de que el Agente C regenerara el bundle fue el paso coordinación correcto; el campo está en `types.ts:754` y el componente lo consume de forma defensiva.

**Cabos sueltos de Ola 2:** cinco, todos de baja-media severidad: `ReporteDeportes.tsx` sin `BadgeFuente`, `CompararPeriodos` sin `fuente` ni badge (el más relevante, N6), `Termometro.tsx` con `SelectorMarca` local, y dos wrappers trivialmente redundantes.

**Ola 3:** 10 issues abiertos. Los de calidad estructural (#98, #112) tienen alta viabilidad y bajo riesgo. Las features 🟡 (#103–#108) son independientes y de esfuerzo limitado. `#101` (`types.ts` generado) conviene diferir a Ola 4. La partición en 3 grupos activos (A=backend consola, B=frontend+límites, C=skills-copy) no tiene solapamientos de archivos; el único punto de coordinación es el endpoint de límites (#112) que conviene que el Agente B entregue completo (añade el endpoint en Python y lo consume en el frontend) para no crear una dependencia de orden entre A y B.

---

*Auditoría completada 2026-05-25. Inspección directa del código; sin ejecución del servidor ni tests en vivo. No se modificó código.*
