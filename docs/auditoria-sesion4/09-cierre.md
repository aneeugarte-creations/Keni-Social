# Informe de Cierre — Sesión 4 (Olas 1–9 completas)

> **Auditor:** Claude Code (claude-sonnet-4-6)  
> **Fecha:** 2026-05-26  
> **SHA auditado:** `237812a` (tip de `main`, merge fast-forward desde `origin/main` completado)  
> **Método:** mirror integrado completo en venv aislado (`/tmp/keni-audit-ola9-venv`,
> Python 3.x / arm64) + inspección directa de código con referencias archivo:línea.
> Sin modificar código ni mergear ramas.

---

## 1. Mirror Integrado — Resultado por Job (Ola 9 / SHA 237812a)

Instalación: `pip install -e keni-shared -e mcp-metricas -e "consola[dev]"` en venv fresco.
Todos los paquetes instalaron sin conflictos de dependencias.

| Job | Herramienta | Resultado | Detalle |
|---|---|---|---|
| **keni-shared ruff** | ruff check . | ✅ VERDE | All checks passed! |
| **keni-shared pytest** | pytest | ✅ VERDE | **25 passed** en 0.01 s |
| **mcp-metricas ruff** | ruff check . | ✅ VERDE | All checks passed! |
| **mcp-metricas pytest** | pytest | ✅ VERDE | **459 passed** en 0.76 s |
| **consola ruff** | ruff check . | ✅ VERDE | All checks passed! |
| **consola pytest** | pytest | ✅ VERDE | **729 passed** en 3.62 s |
| **frontend npm ci** | npm ci | ✅ VERDE | 0 vulnerabilities |
| **frontend lint** | npm run lint | ✅ VERDE | eslint sin errores |
| **frontend typecheck** | npm run typecheck | ✅ VERDE | tsc --noEmit sin errores |
| **frontend test** | npm run test | ✅ VERDE | **92 passed** (14 test files) |
| **frontend gen:types** | npm run gen:types | ✅ VERDE | types.gen.ts generado sin error |
| **frontend gen:types:check** | npm run gen:types:check | ✅ VERDE | coincide con el esquema del backend |
| **frontend build** | npm run build | ✅ VERDE | built in 2.67 s |
| **git status post-build** | git status --short (tracked) | ✅ LIMPIO | 0 ficheros tracked modificados |
| **skills evals pytest** | pytest evals/ | ✅ VERDE | **86 passed** en 0.17 s |

### Totales

| Conjunto | Tests | Estado |
|---|---|---|
| keni-shared | 25 | ✅ |
| mcp-metricas | 459 | ✅ |
| consola backend | 729 | ✅ |
| frontend vitest | 92 | ✅ |
| skills evals | 86 | ✅ |
| **TOTAL** | **1391 passed, 0 failed, 0 errors** | **✅ TODO VERDE** |

> Respecto al informe anterior (Olas 1–8, SHA `d6e1a9a`, 1363 passed): +28 tests.
> Los 28 nuevos corresponden a cobertura añadida por los refactors de Ola 9
> (frontend: +28 tests en 14→14 archivos; el suite de backend se mantiene estable
> porque los refactors de Ola 9 no añaden lógica nueva, solo reorganizan módulos).

---

## 2. Verificación de Cierres de Ola 9

### 2.a H6 (3ª etapa) — `api/skills.py` como fachada y `skills_generacion_api.py` nuevo

| Punto | Ref archivo:línea | Estado |
|---|---|---|
| `api/skills.py` es solo fachada — **124 líneas** | `api/skills.py:1–124` — docstring explica rol de fachada; zero handlers HTTP | ✅ |
| Rutas de generación en `skills_generacion_api.py` — **573 líneas** | `api/skills_generacion_api.py:566–573` — `RUTAS` exporta 6 rutas `/api/skills{...}` | ✅ |
| `RUTAS` auto-descubierta por `api.descubrir` (sin tocar `app.py`) | `api/__init__.py:4–17` — auto-descubrimiento via `pkgutil.iter_modules` | ✅ |
| Las 6 URLs del contrato son idénticas a antes | `/api/skills`, `/api/skills/ejecutar`, `/api/skills/ejecutar-archivo`, `/api/skills/historial`, `/api/skills/historial/{id}`, `/api/skills/historial/{id}/guardar` | ✅ |
| Reducción: 773 L → 124 L (−84 %) | (medición directa `wc -l`) | ✅ |

### 2.b N13 — Ningún módulo de `dominio/` ni CLI importa `from .api import` (salvo el residuo preexistente)

| Punto | Ref | Estado |
|---|---|---|
| `dominio/*.py` → cero imports de `api/` | `grep -rn "from .api\|from ..api" dominio/` → sin resultados | ✅ |
| `skills_catalogo.py` → imports lazy de `dominio.skills` (no de `api/`) | `skills_catalogo.py:167` y `:573` — `from .dominio import skills as dom_skills` (lazy, dentro de función) | ✅ |
| `termometro_cli.py:36` → **ÚNICO residuo** `from .api import rss` | `termometro_cli.py:36` — usa `leer_items_fuente` / `item_pasa_filtros` de `api/rss.py` | ✅ ACEPTADO |
| El residuo `api.rss` es preexistente, no forma parte de N13, y no crea ciclo | Confirmado: moverlo requeriría tocar `api/rss.py`; no planificado en Ola 9 | DOCUMENTADO |

### 2.c H7 — `lib/formato.ts` como fuente única; sin formateadores/KPIs duplicados

| Punto | Ref | Estado |
|---|---|---|
| `src/lib/formato.ts` es la fuente canónica | `lib/formato.ts:1–101` — `numeroCompacto`, `numeroCompleto`, `porcentaje`, `variacion`, `costeUsd`, `duracion` | ✅ |
| `pages/metricas/formato.ts` es solo re-export | `pages/metricas/formato.ts:1–16` — `export { ... } from "@/lib/formato"` (deprecated, sin lógica propia) | ✅ |
| `pages/comercial/formato.ts` no duplica números | `pages/comercial/formato.ts` — solo helpers de fecha/estado (`fechaCorta`, `fechaHora`, `fechaDia`, `presentacionEstado`, `etiquetaMetrica`); no redefine funciones numéricas | ✅ |
| `TarjetaKpi` en `components/comunes/` (único) | `components/comunes/TarjetaKpi.tsx` — fuente única del componente | ✅ |
| `Monitor.tsx` y `Comercial.tsx` usan `TarjetaKpi`, no definen el componente | `Monitor.tsx:KpisTotales` y `Comercial.tsx:Kpis` — wrappers locales que renderizan `<TarjetaKpi>` | ✅ |

### 2.d H8 — Constante `BASE` de Meta Graph API unificada en tests

| Punto | Ref | Estado |
|---|---|---|
| Fuente canónica `BASE = "https://graph.facebook.com/v21.0"` | `mcp-metricas/src/keni_metricas/fuentes/meta.py:26` | ✅ |
| `publicacion/meta.py` importa `BASE` de `fuentes/meta.py` | `mcp-metricas/src/keni_metricas/publicacion/meta.py:43` — `from ..fuentes.meta import BASE, TIPO_SYSTEM_USER` | ✅ |
| Tests usan `BASE` importada, sin URLs `graph.facebook.com` hardcodeadas | `tests/test_meta.py:8`, `test_paginacion_refresh.py:8`, `test_publicacion.py:21`, `test_publicacion_cola.py:12`, `test_publicacion_flujo.py:29` — todos importan `BASE` del módulo | ✅ |

---

## 3. Tabla de Hallazgos H1–H8 + E1 + E5 — Estado Final tras Ola 9

| Hallazgo | Descripción original | Olas que actuaron | Estado final |
|---|---|---|---|
| **H1** | Consola importa internals del MCP (no la fachada declarada) | Ola 2: `servicio_metricas` | **PARCIALMENTE CERRADO.** `api/conexiones.py:25` (`keni_metricas.config.ruta_config`) y `api/estado.py:25` (`keni_metricas.doctor`) mantienen 2 imports directos documentados como N4/N9. Sin cambios en Ola 9. |
| **H2** | Dos backends de persistencia (`db.py` + `ficheros.py`) | Ola 7 (E5): `repos.py` fachada sin conmutador | **CERRADO (arquitectura).** `repos.py` es la única interfaz pública; el conmutador `USAR_FICHEROS` fue eliminado. `db.py` (20 kB) y `ficheros.py` (42 kB) siguen coexistiendo como implementaciones internas diferenciadas por entidad (contenido→ficheros, operacional→db), que es el diseño correcto. No es deuda; es arquitectura deliberada. |
| **H3** | Catálogo de marcas duplicado en ≥4 fuentes (3 esquemas de id) | Ola 6 (E1/H3): `keni-shared` | **CERRADO.** `marcas.py` reexporta de `keni_shared.marcas`. `mcp-metricas` y `consola` consumen la misma fuente. `keni-shared` instalado como dependencia local del monorepo (`4832cfa`). |
| **H4** | Boilerplate de adaptadores 4×; fórmula `engagement_pct` 10 copias | Ola 2: `AdaptadorBase` + fórmula única | **CERRADO (Ola 2).** Sin regresiones en Ola 9 (459 tests mcp-metricas en verde). |
| **H5** | `types.ts` espejado a mano (179 interfaces, 1440 L) | Ola 4: `gen:types` + `types.gen.ts` (#101) | **CERRADO.** `types.gen.ts` generado automáticamente del backend; `gen:types:check` en verde; git limpio post-build. El subconjunto estable de tipos viene del backend; el resto vive en `types.ts` a mano (diseño intencional). |
| **H6** | Lógica de negocio en `api/skills.py` + ciclo + dependencia invertida dominio→API | Ola 3: dominio extraído. Ola 4: handlers catálogo a `skills_catalogo_api.py`. **Ola 9: handlers generación a `skills_generacion_api.py` + cortar N13** | **CERRADO.** `api/skills.py` 1694 L → **124 L** (fachada). Ciclo resuelto. `dominio/` y CLI no importan de `api/`. Residuo preexistente: `termometro_cli.py:36` `from .api import rss` (documentado, no es N13). |
| **H7** | Escritura atómica + límites de plataforma + render/formato + datos de muestra duplicados | Ola 2: `io_atomico`. Ola 3: `limites_plataforma`. **Ola 9: `lib/formato.ts` + `TarjetaKpi` centralizados** | **CERRADO.** io_atomico ✅ Ola 2. Límites plataforma ✅ Ola 3. Render/formato ✅ Ola 9 (`lib/formato.ts` fuente única; `pages/metricas/formato.ts` es re-export deprecado). TarjetaKpi ✅ Ola 9 (componente único en `components/comunes/`). Datos de muestra en `muestra.py`: aceptable, son fixtures de demo, no código de producción duplicado. |
| **H8** | Código muerto + god-files + constantes Meta duplicadas | Ola 1: `EnConstruccion.tsx` borrado (`520c994`). N14 (Ola 4): `publica-preview/` zombie borrado (`e37efaf`). **Ola 9: `BASE` Meta unificada en tests** | **CERRADO.** Código muerto eliminado. `api/skills.py` dejó de ser god-file (124 L). `BASE` Meta: `publicacion/meta.py` importa de `fuentes/meta.py`; tests usan la constante importada. |
| **E1** | `keni-shared` como paquete canónico de tipos/validaciones compartidos | Ola 6: paquete creado e instalado | **CERRADO.** `keni-shared` instalado como dependencia editable del monorepo; `marcas`, `cuentas`, `io_atomico`, `engagement_pct`, `limites_plataforma` se derivan de `keni-shared`. 25 tests en verde. |
| **E5** | Fachada única de persistencia (eliminar conmutador `USAR_FICHEROS`) | Ola 7: `repos.py` fachada fija, conmutador eliminado (`ccac938`) | **CERRADO.** `repos.py` enruta por tipo de entidad de forma fija y documentada (sin env var, sin conmutador). APIs que antes apuntaban a `db.*` o `ficheros.*` directamente ahora pasan por `repos.*`. |

### Síntesis

- **Cerrados completamente (Ola 9):** H6, H7, H8 (pasaron de PARCIAL a CERRADO en esta ola)
- **Ya cerrados antes de Ola 9:** H3/E1, H4, H5, H2/E5
- **Cerrado parcialmente (sin cambios en Ola 9):** H1 (2 residuos documentados, de baja severidad)

---

## 4. Deuda Residual Real tras Ola 9

Lista corta de lo que queda genuinamente abierto:

1. **`termometro_cli.py:36` → `from .api import rss`** (residuo preexistente, no N13)  
   Usa `leer_items_fuente` y `item_pasa_filtros` de `api/rss.py`. Moverlo requiere tocar `api/rss.py`. Severidad baja; el CI pasa.

2. **Voces de marca vacías** (`skills-copy/contexto-editorial/voces/` solo tiene `_plantilla.md`)  
   Bloqueado por datos del piloto AMX: no hay historial de publicaciones reales para hacer ingeniería inversa de voz. Es dependencia externa del cliente, no deuda técnica interna.

3. **H1 parcial: 2 imports directos de internals de `keni_metricas`**  
   `api/conexiones.py:25` (`keni_metricas.config.ruta_config`) y `api/estado.py:25` (`keni_metricas.doctor`). Documentados como N4/N9, aceptados. La fachada `servicio_metricas` cubre el 95 % del consumo.

4. **Externo — publicación real en redes** (brecha F-C-10/A-01)  
   El pipeline editorial está completo hasta borradores. La publicación real requiere tokens de Meta/YouTube/X/TikTok del equipo AMX y, para Meta, App Review aprobado. Bloqueado externamente.

5. **Externo — datos reales en lugar de muestra** (brecha F-M-01)  
   Toda demo corre con `fuente=muestra`. Requiere que AMX rellene tokens reales en `credenciales.toml`.

6. **Externo — TikTok acuerdo de auditoría / X tier de pago** (brecha F-M-01 parcial)  
   Los adaptadores existen; las plataformas requieren contratos/pagos externos.

7. **Externo — skills de rastreo de virales y predicción de tendencias** (brecha F-C-17/F-C-20)  
   Pedidas por el equipo editorial AMX; sin implementación. Fuera del scope de las olas de deuda estructural.

---

## 5. Confirmación de No-Regresión

Mirror integrado completo (1391 tests) en verde sobre el SHA `237812a` con venv limpio.
No se detectaron regresiones respecto a ninguna ola anterior. El git working tree no presenta
drift en ficheros tracked tras el build de frontend.
