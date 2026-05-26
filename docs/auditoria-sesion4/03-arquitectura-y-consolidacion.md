# Auditoría de arquitectura y plan de consolidación — keni-social

> Sesión 4. Auditoría de la ARQUITECTURA real del monorepo tras una sesión de
> desarrollo en vivo ("vibe coding"). Solo análisis y documentación: **no se ha
> tocado código**. Rutas siempre absolutas; referencias en formato `archivo:línea`.
>
> Repo auditado: `/Users/mm/projects/keni-social` (no es un repo git en este Drive;
> el repo real vive en local). Fecha: 2026-05-25.

---

## 0. Resumen ejecutivo

El monorepo está **sano de higiene básica** (sin secretos en claro, casi sin
TODO/FIXME, CI en 4 jobs en verde, escritura atómica y validación anti-traversal
sistemáticas) pero acumula **deuda estructural** típica de crecer por features
sueltas: el límite de módulos declarado en `docs/arquitectura.md` ("dos sistemas
independientes que se comunican por MCP") **no coincide con el real** (la consola
importa el MCP como librería en proceso), y hay varias **fuentes de verdad
duplicadas** para los mismos conceptos (marcas, límites de plataforma, datos de
muestra, escritura atómica, formato de métricas).

Los **8 hallazgos principales** y las **5 recomendaciones top** están al final
(§6 y §7). El cuerpo (§1–§5) los justifica con rutas concretas.

---

## 1. Arquitectura REAL (mapa)

### 1.1 Módulos y puntos de entrada

```
keni-social/  (monorepo, 3 paquetes Python + 1 frontend + skills + docs)
│
├── mcp-metricas/            paquete `keni-metricas`  (Python 3.11, FastMCP)
│   └── src/keni_metricas/
│       ├── server.py        ENTRY: `keni-metricas` (MCP stdio/HTTP) → tools.py
│       ├── tools.py         7 tools MCP (listar_cuentas, metricas_resumen, …)
│       ├── reporte.py       ENTRY: `keni-reporte` (CLI → markdown/csv/json)
│       ├── reporte_deck.py  ENTRY: `keni-reporte-deck` (CLI → PPTX/PDF deportes)
│       ├── dashboard.py     render HTML autocontenido
│       ├── config.py        Config + FuenteScoped + construir_fuente()  (TOML local)
│       ├── agregador.py     FuenteCompuesta (combina adaptadores reales)
│       ├── schema.py        modelos pydantic/dataclass (Cuenta, Pieza, …)
│       ├── fuentes/         FuenteMetricas + 1 adaptador por red
│       │   ├── _http.py     cliente httpx compartido (get_json/post_json/retry)
│       │   ├── base.py      Protocolos FuenteMetricas / AdaptadorPlataforma
│       │   ├── muestra.py   datos offline deterministas (DEFECTO)
│       │   └── meta.py · youtube.py · x.py · tiktok.py
│       ├── publicacion/     escritura (dry-run) → meta.py, flujo.py, cola.py
│       ├── asistente.py · doctor.py · historico.py · picos.py · notificaciones.py
│       └── presupuesto.py
│
├── consola/                 paquete `keni-consola`  (Starlette + React vendorizado)
│   ├── src/keni_consola/
│   │   ├── __main__.py       ENTRY: `keni-consola` (bind 127.0.0.1)
│   │   ├── termometro_cli.py ENTRY: `keni-termometro` (cron)
│   │   ├── app.py            App Starlette: auto-descubre api/ + sirve el SPA
│   │   ├── api/  (24 módulos) cada uno exporta RUTAS=[Route(...)]  (contrato)
│   │   ├── repos.py          FACHADA de persistencia (db ↔ ficheros)
│   │   ├── db.py             backend SQLite (1592 L)   ─┐ DOS backends
│   │   ├── ficheros.py       backend YAML por marca (1173 L) ─┘ coexisten
│   │   ├── indice.py         índice SQLite regenerable sobre los YAML
│   │   ├── migracion.py      one-shot SQLite → YAML
│   │   ├── agentes.py        dominio "agente" = carpeta por marca/genérico (837 L)
│   │   ├── generaciones.py   orquesta `claude -p` en background (stream-json)
│   │   ├── marcas.py         catálogo ÚNICO de marcas (id canónico ↔ id_metricas)
│   │   ├── secretos.py · media.py · comercial.py · sugerencias.py · termometro.py
│   │   ├── proyectos.py · lanzador.py · preferencias.py · redes.py · skills_catalogo.py
│   │   └── webapp/           BUNDLE vendorizado del SPA (assets/*.js)
│   └── frontend/             React + TS + Vite + shadcn
│       └── src/
│           ├── types.ts      179 interfaces que ESPEJAN el backend a mano (1440 L)
│           ├── lib/api.ts    cliente HTTP (solo 3 helpers fetch genéricos)
│           ├── router.tsx · pages/ (≈20 páginas) · components/
│
├── skills-copy/             Claude Code Agent Skills (plugin)
│   ├── .claude/skills/<skill>/  SKILL.md + keni.yaml [+ scripts .py/.sh]
│   ├── contexto-editorial/  marcas/*.md · voces/ · plataformas.md · reglas-legales.md
│   └── evals/               checks estáticos + de salida
│
├── commands/                comandos `/keni-*` (markdown)
├── docs/                    diseño declarado (arquitectura.md, estado-producto.md, …)
├── .mcp.json                cableado del MCP (uvx --from mcp-metricas)
└── .github/workflows/ci.yml 4 jobs: mcp · consola · frontend · skills
```

### 1.2 Cómo se comunican (canales REALES)

| Origen → Destino | Canal declarado (docs) | Canal REAL (código) |
|---|---|---|
| Claude Code / usuario → métricas | **MCP stdio** (`.mcp.json`, `server.py`) | ✅ MCP stdio para el agente |
| **Consola → métricas** | (implícito: sistema aparte) | ❌ **import en proceso** del paquete `keni_metricas` (no MCP) |
| Consola → copy (skills) | invoca `claude -p` | ✅ `generaciones.lanzar_job_claude` (Popen, stream-json) |
| Skill copy → métricas | "opcional, con degradación" (`arquitectura.md:53`) | ⚠️ vía tools MCP (no verificado en esta auditoría) |
| Frontend → backend | HTTP JSON `/api/*` | ✅ HTTP; **tipos duplicados a mano** (`types.ts`) |
| Persistencia contenido | — | ficheros YAML por marca (defecto) **+** SQLite (tareas, y backend alterno) |
| Estado de generaciones | — | ficheros YAML efímeros en `~/.config/keni-social/generaciones` |
| Credenciales redes | TOML local métricas | `~/.config/keni-metricas/config.toml` |
| Clave imagen IA | almacén único | `~/.config/keni-social/secretos.toml` |

**Punto clave de arquitectura:** `docs/arquitectura.md` describe "dos sistemas
independientes que se complementan" y un MCP que se consume "por stdio o HTTP".
Pero la **Consola no habla MCP**: `consola/pyproject.toml:10` declara
`keni-metricas` como dependencia pip y los módulos de API importan **internals
profundos** del paquete (no la fachada de tools):

- `consola/src/keni_consola/api/metricas.py:17-19` → `keni_metricas.config`,
  `keni_metricas.reporte`, `keni_metricas.schema`
- `consola/src/keni_consola/api/metricas.py:48` → `keni_metricas.config.FuenteScoped`
- `consola/src/keni_consola/api/reporte_deportes.py:18-26` →
  `keni_metricas.config`, `keni_metricas.fuentes.base`, `keni_metricas.reporte_deck`,
  `keni_metricas.schema`
- `consola/src/keni_consola/api/config.py:16-17` y `api/conexiones.py:24-25` →
  `keni_metricas.asistente`, `keni_metricas.config`
- `consola/src/keni_consola/api/estado.py:17` → `keni_metricas.doctor`

Es decir, la frontera "MCP" existe para el agente de Claude, pero la Consola está
**acoplada en compilación** a la implementación interna del MCP. No es
necesariamente malo (evita serializar por stdio dentro de la misma máquina), pero
**el contrato real no es el documentado** y hoy no hay una interfaz estable entre
ambos: cualquier refactor interno de `keni_metricas.config`/`reporte`/`fuentes`
rompe la consola en silencio (solo lo atrapa el CI).

---

## 2. Código DUPLICADO (concreto)

### 2.1 Adaptadores por plataforma: boilerplate copiado 4 veces — ALTA

Los 4 adaptadores (`meta.py`, `youtube.py`, `x.py`, `tiktok.py`) repiten el mismo
esqueleto: `disponible()`, el wrapper `try/except + log.warning + return None/[]`,
la construcción del header `Bearer`, y la **fórmula de engagement** idéntica.

- Fórmula `engagement_pct = round(inter / vis * 100, 1) if vis else 0.0` repetida
  **10 veces**:
  `mcp-metricas/src/keni_metricas/fuentes/meta.py:118` y `:165`,
  `.../youtube.py:93` y `:134`, `.../x.py:76` y `:100`,
  `.../tiktok.py:107` y `:133`, `.../muestra.py:277`, y
  `mcp-metricas/src/keni_metricas/agregador.py:133`.
- `if not self.disponible(): return None/[]` repetido en cada `metricas()`/`piezas()`:
  `meta.py:85,123` · `youtube.py:65,97` · `x.py:65,83` · `tiktok.py:96,114`.
- Header `{"Authorization": f"Bearer {self._token}"}` re-construido en
  `youtube.py:36`, `x.py:45`, `tiktok.py:74`.
- Patrón `try: … except Exception: log.warning("<Red> falló…"); return None/[]`
  duplicado: `youtube.py:69-71,101-103` · `x.py:78-80,106-108` ·
  `tiktok.py:109-111,139-141` · `meta.py:89-91,127-129`.
- El bloque de **refresh de token** (leer client_id/secret/refresh_token, POST a
  TOKEN, capturar `access_token` nuevo) es estructuralmente el mismo en
  `youtube.py:38-62`, `tiktok.py:35-60` y `meta.py:58-81` (variando solo los
  nombres de campo y la URL).

**Causa raíz:** la `class Adaptador*` no hereda de una base común; `base.py:31`
solo define un `Protocol` (contrato estructural), sin clase base que aporte el
comportamiento compartido.

### 2.2 Adaptador Meta de lectura vs. de publicación — MEDIA

`mcp-metricas/src/keni_metricas/fuentes/meta.py` y
`mcp-metricas/src/keni_metricas/publicacion/meta.py` declaran **constantes y lógica
de credenciales gemelas**:

- `BASE = "https://graph.facebook.com/v21.0"` en `fuentes/meta.py:25` **y**
  `publicacion/meta.py:42` (dos fuentes de verdad de la versión de Graph API).
- `TIPO_SYSTEM_USER = "system_user"` en `fuentes/meta.py:28` **y**
  `publicacion/meta.py:45`.
- `self._es_system_user = creds.get("tipo_token") == TIPO_SYSTEM_USER` y
  `self._token = creds.get("access_token")` en ambos
  (`fuentes/meta.py:50-52`, `publicacion/meta.py:104-105`).

### 2.3 Catálogo de MARCAS: 3+ fuentes de verdad — ALTA

La lista de las 5 marcas y sus identificadores vive en sitios independientes:

1. `consola/src/keni_consola/marcas.py:59-65` — catálogo canónico (id, etiqueta,
   id_metricas). Bien diseñado y deliberadamente único… **para la consola**.
2. `mcp-metricas/src/keni_metricas/fuentes/muestra.py:41-65` — los mismos ids
   (`claro_sports`, `unotv`, `nacion_gamer`, `piso_15`, `fundacion`) con nombres y
   datos de muestra, **independientes** del catálogo de la consola.
3. `skills-copy/.claude/skills/breaking-express/marcas.json` — tokens de marca
   (colores, etiquetas, wordmark) con un **3.er juego de claves** (`unotv`,
   `claro-sports`, …) y nombres ("UnoTV", "Claro Sports").
4. `skills-copy/contexto-editorial/marcas/*.md` — una ficha editorial por marca
   (claro-sports.md, unotv.md, nacion-gamer.md, piso-15.md, fundacion.md).

El propio `marcas.py:2-6` documenta que **ya hubo** una unificación de dos
catálogos incompatibles dentro de la consola; pero la unificación **no cruzó la
frontera** hacia métricas y skills. Añadir/renombrar una marca exige tocar ≥4
sitios sin que nada lo verifique.

### 2.4 Límites de plataforma: prosa vs. código — MEDIA

Los límites de caracteres por red están definidos dos veces, sin enlace:

- `skills-copy/contexto-editorial/plataformas.md:6,13,27,34,46` — prosa para la
  skill (X 280, IG ~2.200, TikTok ~2.200/4.000, YouTube título 100…).
- `consola/frontend/src/pages/publicaciones/meta.ts:29-33` — código
  (`x:280, instagram:2200, facebook:null, tiktok:2200, youtube:null`).

El contador de caracteres del frontend (`ContadorCaracteres`,
`DialogoEditar.tsx:169`) usa `meta.ts`; la skill usa `plataformas.md` + su propio
`contar.py`. Si AMX cambia un límite, hay que editar dos verdades y no fallaría
ningún test.

### 2.5 Escritura atómica (tmp + os.replace): 9 copias — MEDIA

El mismo patrón "mkstemp en el mismo dir → write → os.replace [→ chmod 0600]" está
copiado en 9 módulos:
`consola/.../ficheros.py`, `secretos.py:63-82`, `sugerencias.py`,
`skills_catalogo.py`, `agentes.py`, `preferencias.py`, `termometro.py`,
`generaciones.py:119-135`, y `mcp-metricas/.../asistente.py`. Los propios
docstrings lo reconocen ("mismo patrón que `secretos.py`",
`ficheros.py` cabecera; "mismo patrón que `keni_metricas.asistente`",
`secretos.py:66`). No hay un `escribir_atomico(ruta, texto)` compartido.

### 2.6 Render de métricas: 3 caminos con helpers gemelos — MEDIA

Tres renderizadores consumen el mismo `reporte` y reimplementan formato/colores:

- `reporte.py:93,153` (markdown/csv) · `dashboard.py:57-66,422,438` (HTML, con
  `_clase_engagement`/`_etiqueta_engagement`) · `reporte_deck.py:62-100` (PPTX).
- En el frontend hay **otra** capa de formato:
  `consola/frontend/src/pages/metricas/formato.ts` y
  `consola/frontend/src/pages/comercial/formato.ts` (dos `formato.ts` separados).
- `api/metricas.py` reconstruye a mano la serialización (`_reporte_serializable`,
  `_comparar_totales`, `_variacion_pct` en `:60-154`) en vez de reutilizar la del
  CLI; el propio docstring dice "misma serialización que el CLI" pero la
  **reimplementa**.

### 2.7 Tipos frontend ↔ backend espejados a mano — MEDIA

`consola/frontend/src/types.ts` (1440 L, **179 interfaces**) replica a mano las
respuestas de cada endpoint `/api/*`. El backend devuelve dicts construidos a mano
(p. ej. `api/metricas.py:_reporte_serializable`); no hay esquema compartido ni
generación de tipos. Cualquier cambio de forma en el backend desincroniza
`types.ts` y solo se detecta si alguien actualiza ambos. `lib/api.ts` solo tiene
3 helpers genéricos de `fetch`, así que el tipado vive todo en `types.ts`.

### 2.8 Datos de muestra duplicados — BAJA/MEDIA

Hay **dos** generadores de datos sintéticos deterministas independientes:
`mcp-metricas/.../fuentes/muestra.py` (métricas por marca/plataforma) y la curva
sintética por link de `consola/.../comercial.py` (su cabecera: "curva sintética
DETERMINISTA por link"). El módulo Comercial **no reutiliza** la fuente de muestra
del MCP, reinventa la suya.

---

## 3. ACOPLAMIENTO (funcionalidades que deberían desacoplarse)

### 3.1 Consola ↔ internals de keni_metricas — ALTA
Ver §1.2. La consola depende de la implementación interna del MCP, no de un
contrato. Debería existir una **interfaz de servicio de métricas** estable
(fachada) que la consola consuma, igual que el agente consume las *tools*.

### 3.2 Dos backends de persistencia conviviendo — ALTA
`repos.py` es una fachada que conmuta entre `db.py` (SQLite, 1592 L) y
`ficheros.py` (YAML, 1173 L) según `KENI_CONSOLA_BACKEND` (`repos.py:41-48`).
El defecto es `ficheros`, pero:
- `db.py` sigue íntegro (no es solo legado: las `tareas` viven **siempre** en
  SQLite, `repos.py:56-78`).
- `indice.py` mantiene **otro** SQLite (índice regenerable sobre los YAML).
- `migracion.py` es un one-shot SQLite→YAML que todavía vive en el árbol.

Resultado: ~2.700 líneas de persistencia para un producto en validación, con dos
modelos de datos mantenidos en paralelo y un tercer índice SQLite. Es el mayor
foco de complejidad accidental.

### 3.3 `agentes.py` ⟂ `ficheros.py`/`marcas.py` sobre el mismo disco — MEDIA
`agentes.py` (837 L) introduce el concepto "agente" cuya carpeta es **la misma**
`<KENI_CONSOLA_RAIZ>/<marca>/` que usa `ficheros.py`, y re-deriva la lista de
marcas-agente de `marcas.opciones()`. Hay dos dominios ("contenido por marca" y
"agente") montados sobre el mismo layout en disco, con validación anti-traversal
duplicada (`agentes.py` reusa la de `api.carpetas`, según su cabecera). El límite
entre "marca", "agente" y "carpeta de contenido" está difuminado.

### 3.4 Lógica de negocio dentro de handlers HTTP — MEDIA
`api/skills.py` (1694 L) y `api/metricas.py` mezclan, en el mismo archivo,
enrutado HTTP + construcción de prompt + parseo de la salida de `claude` +
serialización + reglas de dominio (allowlists, verdicto ✅/⚠️/❌, instrucción
"sin emojis" en `api/skills.py:106-109`). `api/skills.py` además importa
`generaciones`, `marcas`, `redes`, `repos`, `skills_catalogo` y la privada
`from .publicaciones import _publicacion_a_dict` (`api/skills.py:62`) — un handler
importando un helper **privado** de otro handler.

### 3.5 Import perezoso para romper ciclos — MEDIA (síntoma)
`generaciones.py` hace `from .api import skills` **dentro** de funciones
(`:278`, `:332`) con el comentario "import local: evita el ciclo
generaciones↔api.skills". El acumulador de stream (`AcumuladorStream`,
`metricas_a_dict`, `_arg_presupuesto`) vive en `api/skills.py` pero lo necesita la
capa de dominio `generaciones.py` → la dependencia va **en sentido contrario** al
deseado (dominio → API). Indica que el parser de stream y el presupuesto están en
el archivo equivocado.

### 3.6 Métricas acopladas a copy — BAJA (declarado, no verificado)
`arquitectura.md:53` dice que `copy-desde-nota` puede consultar `mejores_piezas`
del MCP "con degradación". Está bien planteado como opcional; se deja como nota
porque no se verificó el camino real en esta auditoría.

### 3.7 Inyección de lanzadores en `crear_app` — BAJA (deuda menor)
`app.py:114-150` recibe 4 callbacks opcionales (`abrir`, `lanzar_run`,
`lanzar_generacion`, `lanzar_imagen`) y los **monkey-patchea** sobre módulos
(`api_proyectos.abrir_en_claude_code = abrir`, `gen_modulo.lanzar_job_claude = …`).
Funciona para los tests, pero es inyección por reasignación de atributos de módulo,
no por un puerto/protocolo explícito; frágil ante renombrados.

---

## 4. INCONSISTENCIAS por vibe coding

- **Higiene buena, para sorpresa:** no hay secretos en claro (el único match,
  `consola/tests/test_api_config.py:103`, es un placeholder de test
  `"PENDIENTE_PON_TU_TOKEN_AQUI"`). No hay TODO/FIXME/HACK reales (los matches de
  "TODO" son la palabra española "todo"/"todos"). Sin `shell=True`. Validación
  anti-traversal sistemática. Esto sube la línea base: la deuda es **estructural**,
  no de pulcritud.
- **Código muerto:** `consola/frontend/src/components/layout/EnConstruccion.tsx`
  está **definido pero nunca importado** (0 usos fuera de su archivo). Candidato a
  borrar.
- **Naming mixto en ids de marca:** `slug-guion` (canónico consola) vs
  `guion_bajo` (id_metricas / muestra) vs claves de `breaking-express/marcas.json`.
  `marcas.py` lo gestiona **dentro** de la consola, pero la inconsistencia persiste
  al cruzar a métricas y skills (§2.3).
- **Dos `claves.ts` / dos `formato.ts`** en el frontend:
  `pages/agentes/claves.ts`, `pages/comercial/claves.ts`, `pages/publicaciones/claves.ts`,
  `pages/skills/claves.ts` (4 ficheros "claves" de React Query, patrón aceptable),
  y `pages/metricas/formato.ts` + `pages/comercial/formato.ts` (formato de números
  duplicable, §2.6).
- **Manejo de errores ad hoc por endpoint:** cada handler repite
  `except ValueError → 400` / `except Exception → 500 "mensaje en español"`
  (p. ej. `api/metricas.py:176-179, 191-194, 224-227, …`). Es consistente en
  intención pero copiado endpoint a endpoint; no hay middleware/decorador de
  errores. Riesgo bajo, ruido alto.
- **Comentarios "por ahora" como límites conocidos** (no bugs, pero deuda
  rastreada en prosa, no en issues): `lanzador.py:13,45` ("solo macOS por ahora"),
  `Configuracion.tsx:63` ("por ahora solo OpenAI"), `comercial.py` y `muestra.py`
  ("mientras no estén las APIs reales… basta sustituir `metrica_en`").
- **God-files** (umbral ~400 L de un módulo de responsabilidad única):
  `api/skills.py` 1694 · `db.py` 1592 · `types.ts` 1440 · `ficheros.py` 1173 ·
  `dashboard.py` 917 · `Fuentes.tsx` 983 · `Configuracion.tsx` 882 ·
  `asistente.py` 838 · `agentes.py` 837 · `api/rss.py` 730 ·
  `ResultadoRedes.tsx` 640 · `api/agentes.py` 611 · `doctor.py` 610.
- **Dependencia direccional invertida** dominio→API (§3.5): el parser de stream y
  el presupuesto viven en `api/skills.py` pero los consume `generaciones.py`.

---

## 5. DISEÑO FUNCIONAL CONSOLIDADO (objetivo)

### 5.1 Fronteras y contratos propuestos

```
┌──────────────────────────────────────────────────────────────────────┐
│ keni-shared  (paquete NUEVO, pequeño — la capa común que falta)        │
│   · modelos.py     Plataforma, Marca, Cuenta, Pieza, MetricaPlataforma │
│   · marcas.py      CATÁLOGO ÚNICO de marcas (id↔etiqueta↔id_metricas)  │
│   · plataformas.py límites/char-limit por red (1 fuente de verdad)     │
│   · io_atomico.py  escribir_atomico(ruta, texto, *, modo=0o600)        │
│   · engagement.py  engagement_pct(inter, vis)  + formato de números    │
└──────────────────────────────────────────────────────────────────────┘
        ▲                    ▲                         ▲
        │ importa            │ importa                 │ genera tipos TS
┌───────┴────────┐  ┌────────┴───────────┐   ┌─────────┴──────────────┐
│ keni-metricas  │  │ keni-consola       │   │ frontend (React)        │
│  · fuentes/    │  │  · servicio_metricas│  │  · types.ts GENERADO    │
│    AdaptadorBase│ │    (fachada estable)│  │    desde el contrato     │
│    + 4 redes   │  │  · persistencia    │   │  · usa keni-shared/      │
│  · tools (MCP) │  │    (UN backend)    │   │    plataformas (límites) │
│  · render      │  │  · api/ delgado    │   └─────────────────────────┘
└────────────────┘  │  · dominio/ grueso │
                    └────────────────────┘
       │ MCP stdio (agente)        │ fachada en proceso (consola)
       └──────────► el MISMO servicio de métricas, dos transportes ◄──┘
```

**Contratos clave:**

1. **Servicio de métricas** = una sola fachada (p. ej. `keni_metricas.servicio`)
   que expone `cuentas() / reporte(rango,marca) / comparar(...) / piezas(...)` y
   serializa a una forma estable. Tanto las *tools* MCP **como** la consola la
   consumen; la consola deja de importar `config`/`reporte`/`fuentes` internos.
2. **`AdaptadorBase`** (clase base, no solo `Protocol`) en `fuentes/base.py` que
   aporte: `disponible()`, el wrapper try/except+log, el header `Bearer`, el
   refresh genérico parametrizado por `(url_token, campos)`, y la construcción de
   `MetricaPlataforma`/`Pieza` con `engagement_pct` calculado una sola vez. Cada
   red solo define endpoints + mapeo de campos.
3. **Un único backend de persistencia** de contenido (YAML por marca, ya es el
   defecto). SQLite queda solo para `tareas` o se migra también; `db.py` deja de
   ser un backend conmutable y `migracion.py` se archiva tras correr una vez.
4. **Tipos TS generados** desde el contrato del backend (o un esquema pydantic
   exportado a JSON Schema → `types.ts`), no espejados a mano.
5. **`api/*` delgado**: handler = validar + llamar a dominio + serializar. El
   parseo de stream, el verdicto y el presupuesto salen de `api/skills.py` a
   `generaciones`/`dominio` (elimina el ciclo y el import privado cruzado).

### 5.2 Dónde vive cada responsabilidad (objetivo)

| Responsabilidad | Hoy (disperso) | Objetivo |
|---|---|---|
| Catálogo de marcas | consola/marcas.py + muestra.py + marcas.json + fichas md | `keni-shared/marcas.py` (datos) + fichas editoriales referenciándolo |
| Límite por plataforma | plataformas.md + frontend/meta.ts | `keni-shared/plataformas.py` (+ doc generada/enlazada) |
| engagement_pct | 10 sitios | `keni-shared/engagement.py` |
| Escritura atómica | 9 sitios | `keni-shared/io_atomico.py` |
| Cliente HTTP redes | `_http.py` (ya central) ✅ | mantener; mover refresh genérico a base |
| Métricas → consola | imports internos | fachada `servicio_metricas` |
| Render reporte | reporte/dashboard/deck + 2 formato.ts | helpers de formato compartidos; render por destino |
| Persistencia contenido | db.py + ficheros.py + indice.py | un backend YAML + índice |
| Tipos API | types.ts a mano | generados |

---

## 6. Hallazgos principales (priorizados)

| # | Hallazgo | Severidad | Evidencia |
|---|---|---|---|
| H1 | **La Consola importa internals del MCP** en proceso; la frontera "MCP/stdio" documentada no es el contrato real. | **ALTA** | `consola/pyproject.toml:10`; `api/metricas.py:17-19,48`; `api/reporte_deportes.py:18-26`; `api/config.py:16-17`; `api/estado.py:17` |
| H2 | **Dos backends de persistencia** (SQLite `db.py` + YAML `ficheros.py`) + índice SQLite + migración one-shot conviven (~2.700 L). | **ALTA** | `repos.py:41-48`; `db.py` (1592 L); `ficheros.py` (1173 L); `indice.py`; `migracion.py` |
| H3 | **Catálogo de marcas duplicado** en ≥4 fuentes de verdad con 3 esquemas de id. | **ALTA** | `marcas.py:59-65`; `muestra.py:41-65`; `breaking-express/marcas.json`; `contexto-editorial/marcas/*.md` |
| H4 | **Boilerplate de adaptadores copiado 4×** (engagement 10 copias, disponible/Bearer/refresh/try-except). Falta clase base. | **ALTA** | `fuentes/meta.py`,`youtube.py`,`x.py`,`tiktok.py`; fórmula en 10 líneas (§2.1); `base.py:31` solo Protocol |
| H5 | **Tipos front↔back espejados a mano** (179 interfaces, 1440 L) sin esquema compartido. | **MEDIA** | `frontend/src/types.ts`; `api/metricas.py:_reporte_serializable` |
| H6 | **Lógica de negocio en handlers HTTP** + dependencia invertida dominio→API (ciclo roto con import perezoso). | **MEDIA** | `api/skills.py` (1694 L, `:62,106-109`); `generaciones.py:278,332` |
| H7 | **Escritura atómica + límites de plataforma + render/formato + datos de muestra** duplicados (sin capa común). | **MEDIA** | atómica en 9 módulos; límites `plataformas.md` vs `meta.ts:29-33`; render §2.6; muestra §2.8 |
| H8 | **Código muerto y god-files**: `EnConstruccion.tsx` sin usar; 13 archivos >600 L; constantes Meta (`BASE`,`TIPO_SYSTEM_USER`) duplicadas lectura/publicación. | **BAJA/MEDIA** | `EnConstruccion.tsx`; `fuentes/meta.py:25,28` vs `publicacion/meta.py:42,45`; conteos §4 |

---

## 7. Plan de consolidación (priorizado: quick wins → estructural)

### Quick wins (bajo esfuerzo, bajo riesgo) — hacer ya

| Paso | Acción | Esfuerzo | Riesgo |
|---|---|---|---|
| Q1 | Borrar código muerto: `EnConstruccion.tsx` (0 usos). | XS (<0.5 d) | Muy bajo |
| Q2 | Extraer `engagement_pct()` a un helper y reemplazar las 10 copias. Cubierto por tests existentes de cada adaptador. | S (0.5 d) | Bajo |
| Q3 | Centralizar constantes Meta (`BASE`, `TIPO_SYSTEM_USER`) en un módulo y que `fuentes/meta.py` y `publicacion/meta.py` las importen. | S (0.5 d) | Bajo |
| Q4 | `escribir_atomico()` único; migrar los 9 callsites (mecánico, mismo patrón ya probado). | M (1 d) | Bajo |

### Estructural (mayor esfuerzo / riesgo) — planificar en olas

| Paso | Acción | Esfuerzo | Riesgo |
|---|---|---|---|
| E1 | **Capa `keni-shared`**: marcas (1 catálogo), límites de plataforma (1 fuente), io_atomico, engagement/formato. Migrar consola y métricas a importarla; las skills/fichas referencian el catálogo. **Resuelve H3, H4(parc.), H7.** | L (3-5 d) | Medio (toca 3 paquetes; cubierto por CI) |
| E2 | **Clase `AdaptadorBase`** que absorba disponible/Bearer/refresh genérico/try-except; cada red define solo endpoints+campos. **Resuelve H4.** | M (2 d) | Medio (los 4 adaptadores tienen tests; refresh es delicado) |
| E3 | **Fachada `servicio_metricas`** estable; la consola deja de importar internals (`config/reporte/fuentes/asistente/doctor`). **Resuelve H1.** | M-L (2-4 d) | Medio (define el contrato real; reduce roturas futuras) |
| E4 | **Adelgazar `api/skills.py`**: mover `AcumuladorStream`/parseo/verdicto/presupuesto a `generaciones`/dominio; quitar el import privado `_publicacion_a_dict` y el ciclo. **Resuelve H6.** | M (2 d) | Medio (mucha lógica, buena cobertura de tests) |
| E5 | **Unificar persistencia**: decidir destino de `tareas` (YAML o SQLite-solo-tareas), retirar `db.py` como backend conmutable, archivar `migracion.py` tras correrla. **Resuelve H2.** | L (3-5 d) | **Alto** (datos en producción del piloto; requiere migración verificada y plan de rollback) |
| E6 | **Generar `types.ts`** desde el contrato (pydantic→JSON Schema→TS o similar). **Resuelve H5.** | M (2 d) | Medio (cambio de tooling; reduce desincronización permanente) |
| E7 | (Opcional) Reconciliar `agentes.py` con el dominio "contenido por marca" para un único modelo de carpeta. **Resuelve H8/§3.3.** | L (3 d) | Medio-alto (concepto central, mucho frontend encima) |

**Orden recomendado:** Q1→Q4 (en un día limpian ruido y crean el hábito de capa
común), luego **E1** (la base sobre la que apoyan E2/E3), después **E3** (estabiliza
la frontera consola↔métricas, el riesgo nº1 de roturas silenciosas), **E2** y **E4**
en paralelo, y **E5** (el más arriesgado) al final con migración verificada. **E6**
y **E7** cuando el resto esté estable.

**Principio rector:** el producto está en validación con datos del piloto AMX. La
prioridad es **reducir las fuentes de verdad duplicadas y estabilizar la frontera
consola↔métricas** (donde un refactor interno rompe la consola sin aviso), antes
que la gran unificación de persistencia (E5), que es la de mayor riesgo operativo.

---

*Auditoría de arquitectura, solo análisis. No se modificó código. Las severidades
y esfuerzos son estimaciones para priorizar; afínense contra la cobertura de tests
real (consola y mcp-metricas tienen suites amplias; el frontend tiene vitest + tsc
en CI, lo que abarata E1/E2/E4).*
