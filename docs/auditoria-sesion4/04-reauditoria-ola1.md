# Re-auditoría post-Ola 1 — keni-social

> Auditor: Claude Code (claude-sonnet-4-6) · Fecha: 2026-05-25  
> Método: inspección directa del código tras `git merge --ff-only origin/main`
> (HEAD `f426b02`). Evidencias en formato `archivo:línea`. Solo análisis; sin
> cambios de código.
>
> PRs fusionadas que se verifican: #82/#83 (catálogo único de marcas),
> #88 (IndicadorEstado en topbar), #100 (borra EnConstruccion + unifica constantes
> Meta), #102 (propaga catálogo a métricas y skills).

---

## 1. Verificación Ola 1

### 1.a Catálogo único de marca — #82/#83/#102

**VERIFICADO — sin divergencias detectadas.**

| Punto de verificación | Evidencia | Estado |
|---|---|---|
| Catálogo canónico en la consola | `consola/src/keni_consola/marcas.py:59–65` — 5 marcas, `id` slug-guion, `id_metricas` guion_bajo, bien documentado | ✅ |
| `muestra.py` anclado al catálogo | `mcp-metricas/src/keni_metricas/fuentes/muestra.py:101–105` exporta `IDS_METRICAS_MARCAS` y `IDS_CUENTAS_HERMANAS`; comentario `:39–46` cita explícitamente `#82/#102` | ✅ |
| Guard de no-divergencia en test consola | `consola/tests/test_marcas.py` — `test_muestra_de_metricas_usa_los_mismos_id_metricas`, `test_marcas_json_de_skills_usa_ids_canonicos`, `test_fichas_editoriales_de_skills_cubren_el_catalogo_canonico` | ✅ |
| Guard en test mcp-metricas | `mcp-metricas/tests/test_muestra.py` — `test_ids_marca_muestra_anclados_al_catalogo_canonico` (no puede importar `keni_consola`, declara el espejo local y la consola verifica la igualdad cruzada) | ✅ |
| `breaking-express/marcas.json` usa ids canónicos | `skills-copy/.claude/skills/breaking-express/marcas.json` — claves `"unotv"`, `"claro-sports"` (slug-guion); campo `"id_metricas"` = `"unotv"`, `"claro_sports"` (guion_bajo) | ✅ |
| Fichas editoriales — 5 archivos, nombres = ids canónicos | `skills-copy/contexto-editorial/marcas/*.md` — `claro-sports.md`, `unotv.md`, `nacion-gamer.md`, `piso-15.md`, `fundacion.md` | ✅ |

**Cabo suelto detectado:** `marcas.json` solo tiene tokens para dos marcas (`unotv`, `claro-sports`). El guard de test lo acepta porque comprueba que las claves presentes son _subconjunto_ del catálogo canónico, no igualdad total. Esto es correcto por diseño (las otras marcas aún no tienen sistema de diseño propio), pero conviene mantenerlo documentado.

### 1.b `repos.py` como única fachada de persistencia

**VERIFICADO — todos los `api/*.py` que necesitan persistencia de contenido usan `repos`.**

- Módulos con `import repos`:  
  `plantillas.py:23`, `comercial.py:25`, `hashtags.py:24`, `rss.py:51`, `franjas.py:27`, `skills.py:60`, `publicaciones.py:28`, `tareas.py:26`.
- Ningún módulo de `api/` importa `db` o `ficheros` directamente.
- Los módulos que no importan `repos` (`metricas.py`, `reporte_deportes.py`, `config.py`, `conexiones.py`, `estado.py`, `agentes.py`, `termometro.py`, `sugerencias.py`) no gestionan contenido YAML/SQLite; tienen su propia persistencia o delegan en dominios no-repos (credenciales, config.toml de métricas, sugerencias JSON plano, procesos de agentes).

**Excepción documentada y aceptable:**  
`sugerencias.py` (dominio) tiene su propia escritura atómica a un fichero JSON plano (`sugerencias.py:114–127`). No es persistencia de _contenido editorial_ sino un buzón simple; no pasa por `repos`. Es coherente pero añade una 10.ª copia del patrón atómico (ver §4, N2).

### 1.c `EnConstruccion.tsx` borrado + constantes Meta unificadas — #100

**VERIFICADO.**

- `consola/frontend/src/components/layout/EnConstruccion.tsx` — **no existe** en el árbol de trabajo (confirmado con `find` y listado de `components/layout/`).
- Ninguna referencia a `EnConstruccion` en el código fuente frontend ni en el bundle vendorizado.
- `publicacion/meta.py:43` importa `BASE` y `TIPO_SYSTEM_USER` desde `fuentes/meta.py:25,28`:  
  ```python
  from ..fuentes.meta import BASE, TIPO_SYSTEM_USER
  ```  
  Las constantes existen en un solo sitio; `publicacion/meta.py` ya no las declara.

### 1.d `IndicadorEstado` montado + `/estado` redirige — #88

**VERIFICADO.**

| Punto | Evidencia | Estado |
|---|---|---|
| Componente `IndicadorEstado.tsx` existe | `consola/frontend/src/components/layout/IndicadorEstado.tsx` — 191 líneas; popover con lista de chequeos, `NivelEstado`, refetch | ✅ |
| Montado en la topbar | `AppShell.tsx:5` importa; `AppShell.tsx:87` `<IndicadorEstado />` dentro del `<header>`, alineado a la derecha con `ml-auto` | ✅ |
| Backend `/api/estado` limpio | `api/estado.py:62–86` — filtra chequeos clip-a-copy (`_NOMBRES_FUERA_DE_DOMINIO`), devuelve `resultados + resumen + siguiente_paso` | ✅ |
| `/estado` redirige a `/configuracion` | `router.tsx:56` — `{ path: "estado", element: <Navigate to="/configuracion" replace /> }` | ✅ |
| `/conexiones` también redirige | `router.tsx:55` — `{ path: "conexiones", element: <Navigate to="/configuracion" replace /> }` | ✅ |
| Tests nuevos | `consola/tests/test_api_estado.py` (46 líneas) cubre el filtro de dominio y mapeo de estados; `IndicadorEstado.test.tsx` (104 líneas) | ✅ |

**Navegación limpia:** `navegacion.ts` no tiene entradas para "Estado" ni "Conexiones"; ambas desaparecieron del sidebar y solo viven como redirects.

### 1.e Verificación Ola 1 — Resumen

| Check | Resultado |
|---|---|
| Catálogo único de marca propagado y verificado cruzado | ✅ COMPLETO |
| `repos.py` única fachada de persistencia en `api/*.py` | ✅ COMPLETO |
| `EnConstruccion.tsx` borrado y constantes Meta unificadas | ✅ COMPLETO |
| `IndicadorEstado` en topbar + `/estado` redirige | ✅ COMPLETO |

**Sin regresiones detectadas.** Los cambios de Ola 1 son limpios, con cobertura de test añadida para cada uno.

---

## 2. Scope Ola 2 — Estado real de cada issue

### #89 Componentes compartidos (SelectorMarca / SelectorRed / BloqueError / EstadoVacio)

**Estado: PARCIAL.**

Los componentes compartidos _existen_, pero la migración no está completa:

**Hecho:**
- `components/comunes/SelectorMarca.tsx` — un único componente de brand selector.
- `components/comunes/SelectorRed.tsx` — selector de red única (dropdown).
- `components/comunes/BloqueError.tsx` — bloque de error centralizado.
- `components/comunes/EstadoVacio.tsx` — estado vacío centralizado.
- `components/comunes/selectores.ts` — un solo módulo con `MARCA_TODAS = "__todas__"`, `RED_TODAS = "__todas__"` y helpers de traducción. El docstring en `:7` confirma que antes había tres centinelas distintos (`"todas"`, `"__todos__"`, `"__ninguna__"`).
- La mayor parte de las páginas ya importa desde `@/components/comunes/`.

**Pendiente — centinelas divergentes:**
- `pages/comercial/DialogoNueva.tsx:37` declara `const NINGUNA = "__ninguna__"` propio (no importa de `selectores.ts`). Tiene su propio `<Select>` inline para marca y red (`DialogoNueva.tsx:172–193`), sin usar `SelectorMarca` ni `SelectorRed`.
- `pages/Termometro.tsx:337` declara `const SIN = "__ninguna__"` propio.
- El centinela `"__ninguna__"` (para "sin marca / sin red") _no está definido_ en `selectores.ts`; no tiene nombre canónico compartido.
- `pages/copy/SelectorRedes.tsx` (chips de selección múltiple) sigue viviendo en `pages/copy/`, no en `components/comunes/`. Fuentes importan de dos rutas distintas: `@/components/comunes/SelectorRed` (dropdown singular, para publicaciones) y `./SelectorRedes` (chips plural, para generación).

**Plan de ataque:**
1. Añadir `NINGUNA = "__ninguna__"` a `selectores.ts` y exportarlo.
2. Migrar `DialogoNueva.tsx` y `Termometro.tsx` a `SelectorMarca`/`SelectorRed` del catálogo compartido, eliminando sus centinelas locales.
3. Mover `SelectorRedes.tsx` (chips) a `components/comunes/` con nombre diferenciador (`SelectorRedesMultiple` o similar) para que el inventario en `comunes/` sea el contrato único.

**Archivos afectados:** `pages/comercial/DialogoNueva.tsx`, `pages/Termometro.tsx`, `pages/copy/SelectorRedes.tsx` (mover), `components/comunes/selectores.ts` (añadir `NINGUNA`).

---

### #87 Fusionar Conexiones en Configuración

**Estado: HECHA.**

- `pages/Configuracion.tsx:1–8` documenta la fusión; incluye `SeccionRedes` (`Configuracion.tsx:485`) y sección de imagen IA.
- `/conexiones` redirige a `/configuracion` (`router.tsx:55`).
- No existe archivo `Conexiones.tsx` en el árbol.

---

### #84 Almacén YAML + índice regenerable

**Estado: HECHA (funcional pero sin endpoint de regeneración explícito).**

- `consola/src/keni_consola/ficheros.py` — backend YAML por marca (fuente de verdad).
- `consola/src/keni_consola/indice.py` — SQLite regenerable; el contrato está documentado: "puede borrarse en cualquier momento: se regenera leyendo los YAML" (`indice.py:15`).
- El índice se re-indexa automáticamente al detectar mtime diferente (`ficheros.py:229–239`).
- `repos.py` conmuta entre backends con `KENI_CONSOLA_BACKEND` (defecto `ficheros`).

**Cabo suelto:** No hay endpoint REST `/api/config/reindexar` o similar para forzar una regeneración manual desde la UI. Si el índice se corrompe, el usuario debe borrarlo a mano o esperar al auto-repair por mtime. Para el piloto actual es aceptable, pero es una operación de mantenimiento sin interfaz.

---

### #90 Coser Métricas (badge fuente, enlaces, herencia de filtros)

**Estado: PARCIALMENTE HECHA.**

| Sub-tarea | Estado | Evidencia |
|---|---|---|
| Enlace "Generar copy" desde TablaCuentas | ✅ Hecho | `metricas/TablaCuentas.tsx:68–75` — `<Link to="/generar-copy" state={{ marca: marcaCanonicaDesdeMetricas(c.marca_id) }}>` |
| Herencia de filtro marca → CompararPeriodos | ✅ Hecho | `Metricas.tsx:150` pasa `marcaActual={marca}`; `CompararPeriodos.tsx:65,70–71` inicializa y sincroniza con el prop |
| Helper de traducción canónica | ✅ Hecho | `selectores.ts:53–63` — `marcaCanonicaDesdeMetricas` + `marcaMetricasDesdeCanonica` |
| Badge fuente (muestra / real) en el dashboard | ❌ Pendiente | El API `metricas.py:_reporte_serializable` no incluye `fuente` en la respuesta JSON. La página `Metricas.tsx` no muestra ningún badge indicando si los datos son de muestra o reales. El usuario no tiene forma visual de saberlo sin ir a Configuración. |

**Plan de ataque para badge fuente:**
1. Añadir `"fuente": fuente.nombre` al JSON de `_reporte_serializable` en `api/metricas.py` (la fachada `construir_fuente` devuelve un objeto con atributo `nombre = "muestra"` o `"real"`).
2. En `Metricas.tsx`, mostrar un `<Badge>` pequeño ("Datos de muestra") cuando `reporte.fuente === "muestra"`.
3. Mismo badge en `ReporteDeportes.tsx` y comparativas de periodos.

---

### #96 Fachada `servicio_metricas` (H1)

**Estado: PENDIENTE.**

La consola sigue importando internals de `keni_metricas` directamente. Lista exacta actual:

| Módulo consola | Imports de keni_metricas | Nivel de acoplamiento |
|---|---|---|
| `api/metricas.py:17–19,48` | `keni_metricas.config.{cargar_config, construir_fuente, FuenteScoped}`, `keni_metricas.reporte.{construir_reporte, render_csv, render_markdown}`, `keni_metricas.schema.RANGOS_DIAS` | Alto — accede a config, reporte y schema internos |
| `api/reporte_deportes.py:18–26` | `keni_metricas.config.{cargar_config, construir_fuente}`, `keni_metricas.fuentes.base.CuentaNoEncontrada`, `keni_metricas.reporte_deck.*`, `keni_metricas.schema.RANGOS_DIAS` | Alto — incluye `reporte_deck` (CLI de PPTX) |
| `api/config.py:16–17` | `keni_metricas.{asistente}`, `keni_metricas.config.{...}` | Medio — gestión de config.toml |
| `api/conexiones.py:24–25` | `keni_metricas.{asistente}`, `keni_metricas.config.ruta_config` | Medio — escritura de tokens |
| `api/estado.py:25` | `keni_metricas.{doctor}` | Bajo — solo lectura de estado |

No existe módulo `keni_metricas.servicio` ni interfaz estable que separe la fachada de los internals. Un refactor de `keni_metricas.config` o `keni_metricas.reporte` rompe la consola en silencio (solo lo atrapa el CI).

**Plan de ataque:**
1. Crear `mcp-metricas/src/keni_metricas/servicio.py` con funciones públicas estables: `cuentas_disponibles()`, `reporte(marca, rango)`, `comparar(marca, rango_a, rango_b)`, `piezas(marca, rango, n)`, `exportar_csv(...)`, `exportar_md(...)`, más los rangos válidos y el nombre de la fuente activa.
2. Migrar `api/metricas.py` y `api/reporte_deportes.py` a consumir solo `servicio.*`.
3. `api/config.py` y `api/conexiones.py` son frontera legítima (escriben credenciales): pueden seguir usando `asistente` y `config`, pero acotar a esos dos módulos como contrato explícito.
4. `api/estado.py` puede seguir con `doctor` directamente (es un wrapper muy delgado).

---

### #97 `AdaptadorBase` + `engagement_pct` (H4)

**Estado: PENDIENTE.**

Conteo exacto de repeticiones hoy:

| Patrón | Ocurrencias | Archivos |
|---|---|---|
| `engagement_pct = round(inter / vis * 100, 1) if vis else 0.0` | 10 | `fuentes/meta.py:118,165` · `youtube.py:93,134` · `x.py:76,100` · `tiktok.py:107,133` · `muestra.py:296` · `agregador.py:133` + `reporte.py:69` |
| `if not self.disponible(): return` | 8 | `meta.py:85,123` · `youtube.py:65,97` · `x.py:65,83` · `tiktok.py:96,114` |
| `{"Authorization": f"Bearer {self._token}"}` | 3 | `youtube.py:36` · `tiktok.py:74` · `x.py:45` |
| `except Exception: log.warning(...); return None/[]` | 12 | 3–4 por adaptador (total 12 entre los 4 archivos) |

`fuentes/base.py:31` sigue siendo solo un `Protocol`; no hay `AdaptadorBase` class.

**Plan de ataque:**
1. Añadir `class AdaptadorBase` en `fuentes/base.py` con: `disponible()` guard via `__init_subclass__` o método plantilla, `_headers_bearer()`, `_try_call()` genérico, y `calcular_engagement(inter, vis)` como `staticmethod` / función de módulo.
2. Migrar los 4 adaptadores a heredar de `AdaptadorBase`, eliminando los 8 guards y los 12 try-except duplicados.
3. Centralizar `engagement_pct` en una sola función; las 10 llamadas inline pasan a `AdaptadorBase.calcular_engagement(inter, vis)`.
4. `reporte.py:69` y `agregador.py:133` también pasan a la función centralizada.

---

### #99 `escribir_atomico` único + límites de plataforma única fuente (H7)

**Estado: PENDIENTE.**

**Escritura atómica — 9 copias (conteo actual, sin cambio respecto a la auditoría anterior):**

| Módulo | Línea | Nota |
|---|---|---|
| `consola/src/keni_consola/ficheros.py` | 165,180–185 | función local |
| `consola/src/keni_consola/agentes.py` | 804,806–811 | función local `_escribir_texto_atomico` |
| `consola/src/keni_consola/sugerencias.py` | 114,120–127 | función local `_escribir` |
| `consola/src/keni_consola/secretos.py` | 67,73–79 | inline |
| `consola/src/keni_consola/skills_catalogo.py` | 186–194 | función privada `_escribir_atomico` |
| `consola/src/keni_consola/termometro.py` | 69,73–78 | función local |
| `consola/src/keni_consola/preferencias.py` | 70,75–82 | función local |
| `consola/src/keni_consola/generaciones.py` | 125 | inline |
| `mcp-metricas/src/keni_metricas/asistente.py` | 438,447–453 | función local |

**Límites de plataforma — 2 fuentes de verdad:**
- `skills-copy/contexto-editorial/plataformas.md` — prosa para la skill (X 280, IG ~2.200).
- `consola/frontend/src/pages/publicaciones/meta.ts:29–33` — código TypeScript (`x:280, instagram:2200, facebook:null, tiktok:2200, youtube:null`). Lo usa `ContadorCaracteres` en el frontend.

**Plan de ataque:**
1. Crear `consola/src/keni_consola/io_atomico.py` con `escribir_atomico(ruta, texto, *, modo=None)` (y variante `escribir_atomico_dict` para YAML/JSON/TOML si se quiere). Migrar los 8 callsites de la consola mecánicamente.
2. Para `mcp-metricas/asistente.py`: o se crea el helper en `keni_metricas` también, o (si se crea `keni-shared`) se comparte. Por ahora, como `keni_metricas` no depende de la consola, la copia en `asistente.py` queda aislada hasta que exista una capa `keni-shared`.
3. Para límites de plataforma: añadir `LIMITES_PLATAFORMA` como dict en `meta.ts` (ya existe) y exportarlo también desde un endpoint `GET /api/publicaciones/opciones` o un módulo Python que valide al guardar publicaciones, para que la skill `plataformas.md` referencie ese único número en vez de repetirlo en prosa.

---

## 3. Partición sin conflictos para Ola 2

### Principios
- El bundle `consola/src/keni_consola/webapp/` solo puede regenerarlo **un agente por ola** (requiere `npm run build` en `consola/frontend/`).
- Las tres fronteras naturales son: **frontend** (React/TS), **backend Python** (consola `api/` + dominio), **métricas Python** (mcp-metricas).
- Los tests del CI validan las fronteras: si el contrato se rompe, el CI lo atrapa.

### Dependencias entre issues

```
#97 AdaptadorBase     ──┐
                        ├──► (opcional) keni-shared: io_atomico, engagement
#99 escribir_atomico  ──┘

#96 servicio_metricas ─── prerequisito de #90 (badge fuente necesita fuente.nombre en API)

#89 Componentes comunes ─── independiente (solo frontend)
#84 Almacén YAML / reindex ─── ya hecho; solo añadir endpoint si se quiere
#87 Conexiones en Config ─── ya hecho
```

### Propuesta de 3 grupos en paralelo

| Grupo | Issues | Archivos que toca | Toca bundle? | Prerequisito |
|---|---|---|---|---|
| **Agente A** — Backend métricas | #97 `AdaptadorBase` + `engagement_pct` | `mcp-metricas/src/keni_metricas/fuentes/{base,meta,youtube,x,tiktok}.py`, `agregador.py`, `reporte.py` | No | Ninguno |
| **Agente B** — Backend consola | #96 `servicio_metricas` + #99 `escribir_atomico` | `mcp-metricas/src/keni_metricas/servicio.py` (nuevo), `consola/src/keni_consola/api/{metricas,reporte_deportes,config,conexiones}.py`, `consola/src/keni_consola/io_atomico.py` (nuevo), módulos de dominio de consola que usan mkstemp | No | #97 (si `engagement_pct` se mueve a `servicio`) — de lo contrario independiente |
| **Agente C** — Frontend | #89 componentes compartidos + #90 badge fuente | `consola/frontend/src/components/comunes/selectores.ts`, `pages/comercial/DialogoNueva.tsx`, `pages/Termometro.tsx`, `pages/copy/SelectorRedes.tsx` (→ mover a comunes), `pages/Metricas.tsx`, `pages/metricas/TablaCuentas.tsx`, `pages/ReporteDeportes.tsx` | **Sí** — requiere `npm run build` al final | Necesita que #96 exponga `fuente` en la respuesta JSON para mostrar el badge |

### Orden de ejecución recomendado

1. **Agente A** y **Agente B** en paralelo (sin solape de archivos).
2. **Agente C** arranca cuando Agente B haya mergeado la exposición de `fuente` en `api/metricas.py` (necesario para el badge); el resto de #89 puede arrancar antes.
3. Agente C es el único que regenera el bundle; debe hacerlo una sola vez al final de sus cambios.

### Archivos con solape potencial (vigilar)

- `consola/src/keni_consola/api/metricas.py` — lo toca Agente B (#96) y el badge del Agente C depende de su resultado. **Solución:** Agente B entrega primero su PR; Agente C rebasa sobre ella.
- `mcp-metricas/src/keni_metricas/fuentes/base.py` — solo lo toca Agente A.
- Los tests de no-divergencia (`test_marcas.py`, `test_muestra.py`) no los debe tocar ningún agente de Ola 2 salvo que cambie el catálogo de marcas.

---

## 4. Problemas NUEVOS no listados en auditorías anteriores

### N1 — Centinela `"__ninguna__"` sin definición canónica compartida

`selectores.ts` unificó `MARCA_TODAS` y `RED_TODAS` en `"__todas__"`, pero el centinela para "ninguna marca seleccionada / campo opcional vacío" (`"__ninguna__"`) sigue sin estar en `selectores.ts`. Dos componentes lo declaran localmente con nombres distintos:

- `pages/comercial/DialogoNueva.tsx:37` — `const NINGUNA = "__ninguna__"` + `<Select>` inline propio.
- `pages/Termometro.tsx:337` — `const SIN = "__ninguna__"`.

Si alguien cambia el valor del centinela en un sitio sin cambiar el otro, o si el backend empieza a recibir el valor y lo compara, se produce una divergencia silenciosa.

**Fix:** Añadir `export const NINGUNA = "__ninguna__"` a `selectores.ts` y migrar los dos callsites; reemplazar el `<Select>` inline de `DialogoNueva` con `SelectorMarca` + `SelectorRed`.

**Severidad:** Baja-Media. No es un bug activo (el backend recibe `""` cuando el campo es vacío, no el centinela), pero es ruido potencial.

---

### N2 — `sugerencias.py` tiene su propia persistencia JSON fuera de `repos`

`consola/src/keni_consola/sugerencias.py:114–127` escribe a un fichero JSON plano con su propio patrón atómico. No pasa por `repos.py` ni por `ficheros.py`. Para el caso de uso (buzón de ideas de producto) es aceptable, pero:

1. Añade una 10.ª copia del patrón atómico (que ya son 9, issue #99).
2. Si el modelo de sugerencias crece (estados adicionales, asociación a usuario) tendría que migrar a `repos`.

**Fix:** Incluir `sugerencias.py` en la tarea de `io_atomico.py` único (#99). El modelo de datos puede seguir siendo JSON plano.

---

### N3 — `metricas/_reporte_serializable` no expone `fuente` activa

La respuesta JSON de `GET /api/metricas/reporte` no incluye el nombre de la fuente de datos activa (`"muestra"` o `"real"`). El frontend no tiene forma de mostrar un badge de advertencia cuando los datos son ficticios. Para el piloto, donde el equipo de AMX podría confundir datos de muestra con datos reales, esto es un riesgo operativo.

La información está disponible: `construir_fuente(cargar_config()).nombre` devuelve `"muestra"` o el nombre de la fuente real. Solo falta exponerlo en `_reporte_serializable` y consumirlo en el frontend.

**Severidad:** Media. Relacionado con #90 (coser métricas), pero el badge en sí es un cambio de 10 líneas.

---

### N4 — `api/conexiones.py` usa `keni_metricas.asistente.escribir_config_atomico` como su propia escritura atómica

`api/conexiones.py:18` cita explícitamente que reutiliza `escribir_config_atomico` de `asistente` para no duplicar la lógica. Esto es correcto y deliberado. Sin embargo, cuando se implemente #96 (fachada `servicio_metricas`), hay que tener cuidado: `conexiones.py` necesita seguir teniendo acceso a `asistente` para escribir tokens en `config.toml`, aunque el resto de la consola deje de acceder a internals. La fachada `servicio_metricas` debe excluir explícitamente la gestión de credenciales de su alcance, o `conexiones.py` necesitará un contrato separado (p.ej. `keni_metricas.credenciales`).

**Severidad:** Baja. No es un problema hoy; es un riesgo de diseño para cuando se implemente #96.

---

### N5 — `SelectorRedes` (chips) y `SelectorRed` (dropdown) con nombres similares pero diferentes contratos

Existen dos componentes de selección de red:
- `components/comunes/SelectorRed.tsx` — dropdown de selección única, usado en filtros de publicaciones.
- `pages/copy/SelectorRedes.tsx` — chips de selección múltiple, usado en generación de copy.

Los nombres difieren solo en la "s" final. Hay riesgo de importar el incorrecto, especialmente cuando se mueva `SelectorRedes` a `comunes` (parte de #89). Conviene renombrar uno al moverlo: `SelectorRedMultiple.tsx` es más explícito.

**Severidad:** Baja. Riesgo de confusión de imports; sin impacto funcional hoy.

---

## 5. Resumen ejecutivo

**Ola 1: sin regresiones.** Los 4 puntos de verificación están correctamente implementados, con tests de no-divergencia que anclan el catálogo de marcas a través de los tres paquetes del monorepo. El único cabo suelto (sin impacto hoy) es la ausencia de un endpoint REST para forzar la regeneración del índice YAML.

**Ola 2:** De las 7 issues del scope, 2 están completadas (#87, #84), 1 está parcialmente completa (#89 y #90), y 3 están pendientes (#96, #97, #99). Los 4 problemas nuevos (N1–N5) son de baja-media severidad y encajan mayoritariamente dentro del scope de Ola 2 sin requerir una ola extra.

---

*Auditoría completada 2026-05-25. Inspección directa del código; sin ejecución del servidor ni tests en vivo.*
