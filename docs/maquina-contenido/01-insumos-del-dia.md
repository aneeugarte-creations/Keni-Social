# Ola 1 — Insumos del día (cajones)

Contrato compartido entre backend y frontend. **No cambiar las formas JSON sin
actualizar este doc.** Marca foco: UnoTV y Claro Sports.

## Qué resuelve

El equipo de redes de AMX recibe cada día material de otros equipos en formatos
muy distintos. Necesitan **soltarlos en cajones** y que la consola los **parsee
con un agente Haiku**, los presente limpios y ordenados, **fechados por día**, y
permita llevarlos al tablero. Hay **6 cajones** (los 4 primeros de UnoTV; `notas` y
`contexto` de Claro Sports):

- `portal` — lista numerada de Portal/SMS (`1.- TITULAR ... cuerpo`).
- `corresponsales` — el "así vamos" (`VOSOT OAXACA (J. CORTÉS) TITULAR - Tengo/Espero material y guión-`).
- `reporteros` — PDF de agenda de coberturas (tabla con REPORTERO, HORA Y LUGAR, ASIGNACIÓN, ...).
- `eventos_claro` — Excel/CSV de eventos y programación de TV de Claro Sports.
- `notas` — volcado heterogéneo de WhatsApp (notas, links, tweets, texto de PDFs) → una `nota` por unidad.
- `contexto` — indicaciones/correcciones del equipo → ítems `tipo=contexto`: GUÍA EDITORIAL que **nunca** entra al pool ni al tablero (backstops en `api/insumos.py` e `dominio/ingesta.py`).

Cada item nace **fechado con el día editorial** y hay **historial**: poder ver
las listas de cualquier día pasado.

## Modelo de datos (db.py `_DDL_ESQUEMA` + repos.py)

### Tabla `insumos_lote` (un "drop" en un cajón)
```
id            TEXT PRIMARY KEY
fecha         TEXT NOT NULL DEFAULT ''   -- día editorial ISO YYYY-MM-DD
cajon         TEXT NOT NULL DEFAULT ''   -- portal|corresponsales|reporteros|eventos_claro|notas|contexto
marca         TEXT NOT NULL DEFAULT ''   -- opcional; eventos_claro => claro-sports
origen_texto  TEXT NOT NULL DEFAULT ''   -- texto pegado (si lo hubo)
origen_archivo TEXT NOT NULL DEFAULT ''  -- nombre del archivo (si lo hubo)
estado        TEXT NOT NULL DEFAULT 'listo' -- listo|error
error         TEXT NOT NULL DEFAULT ''
total_items   INTEGER NOT NULL DEFAULT 0
creado_por    TEXT NOT NULL DEFAULT ''
creado        TEXT NOT NULL DEFAULT ''   -- timestamp ISO
```
Índices: `(fecha, cajon)`, `(creado)`.

### Tabla `insumos_item` (un item parseado)
```
id              TEXT PRIMARY KEY
lote_id         TEXT NOT NULL DEFAULT ''
fecha           TEXT NOT NULL DEFAULT ''   -- = lote.fecha (copiado para filtrar)
cajon           TEXT NOT NULL DEFAULT ''
marca           TEXT NOT NULL DEFAULT ''   -- unotv|claro-sports|nacion-gamer|'' (clasificado)
linea           TEXT NOT NULL DEFAULT ''   -- línea de contenido sugerida (texto libre)
titulo          TEXT NOT NULL DEFAULT ''
resumen         TEXT NOT NULL DEFAULT ''
hora            TEXT NOT NULL DEFAULT ''   -- coberturas/eventos
lugar           TEXT NOT NULL DEFAULT ''   -- coberturas
estado_material TEXT NOT NULL DEFAULT ''   -- corresponsales: tengo|espero|''
tipo            TEXT NOT NULL DEFAULT 'nota' -- nota|cobertura|evento|contexto
idioma          TEXT NOT NULL DEFAULT 'es'
usado           INTEGER NOT NULL DEFAULT 0
contenido_id    TEXT NOT NULL DEFAULT ''    -- si se llevó al tablero
orden           INTEGER NOT NULL DEFAULT 0
creado          TEXT NOT NULL DEFAULT ''
```
Índices: `(fecha, cajon)`, `(lote_id)`, `(marca, fecha)`.

## Parseo (dominio/insumos_parse.py)

Reutiliza el patrón **síncrono** de `importador_calendario._ejecutar_claude_json`
/ `extraer_con_claude` (escribe a temp dir, corre `claude -p <prompt>
--output-format json --add-dir <dir>`, lee `result`, extrae JSON). Diferencias:

- **Modelo Haiku**: añade `--model` al argv. Flag de config nuevo
  `KENI_INSUMOS_MODELO` (config.py), por defecto `"haiku"`. Si vacío, no se pasa
  `--model` (usa el default). Reutiliza `stream.arg_skip_permisos()`.
- **Texto pegado**: si no hay archivo, vuelca el texto a un `.txt` temporal y se
  parsea igual (o se embebe en el prompt; preferible temp file + `--add-dir`).
- Ejecutor **inyectable** (`Ejecutor = Callable[[str, str], str]`) para tests.
- Salida esperada: `{"items": [ {item}, ... ]}`. Tolera fences ```json y `{"items":[…]}`/lista pelada (reusa la lógica de `_extraer_json`).

Cada item del JSON de Haiku: `titulo` (oblig.), `resumen`, `marca` (nombre o
""), `linea`, `hora`, `lugar`, `estado_material` (tengo|espero|""), `tipo`
(nota|cobertura|evento), `idioma`. Normaliza marca por nombre→id con
`marcas`. Item sin título => error de fila, no rompe el resto.

**Prompt por cajón** (uno por tipo, en `insumos_parse.py`):
- `portal`: parte la lista numerada; cada `N.- TITULAR`+cuerpo => item
  `tipo=nota`. Clasifica marca: deportes→`claro-sports`, videojuegos→`nacion-gamer`, resto→`unotv`.
- `corresponsales`: cada línea `VOSOT/VO/FT ESTADO (REPORTERO) TITULAR - Tengo/Espero material`
  => item `tipo=cobertura`, `lugar`=estado, `estado_material`=tengo|espero. Marca igual.
- `reporteros`: lee la tabla del PDF. **Toma solo coberturas reales** (columna
  ASIGNACIÓN con un evento/historia); **descarta** filas de `GUARDIA`,
  `VACACIONES`, `CONDUCCIÓN`, `INCAPACIDAD` y guardias de canal. `titulo`=resumen
  corto de ASIGNACIÓN, `resumen`=texto completo, `hora`+`lugar`=col HORA Y LUGAR,
  `tipo=evento`. Marca: deportes (selección, América, Pumas, tenis, NASCAR,
  fútbol...)→`claro-sports`; política/nacional→`unotv`.
- `eventos_claro`: Excel/CSV de eventos/programación TV => items `tipo=evento`,
  `marca=claro-sports`, con `fecha`/`hora` si aparecen.

## API (api/insumos.py — auto-descubierta vía `RUTAS`)

Todas devuelven JSON. Validar antes de tocar repos. Errores: `JSONResponse({"error": "..."}, status_code=4xx)`.

### `GET /api/insumos?fecha=YYYY-MM-DD&cajon=&marca=`
`fecha` por defecto = hoy (servidor). Devuelve:
```json
{
  "fecha": "2026-06-04",
  "cajones": [
    { "cajon": "portal",
      "lotes": [ {Lote}, ... ],
      "items": [ {Item}, ... ] },
    { "cajon": "corresponsales", "lotes": [...], "items": [...] },
    { "cajon": "reporteros",     "lotes": [...], "items": [...] },
    { "cajon": "eventos_claro",  "lotes": [...], "items": [...] }
  ]
}
```
Siempre devuelve las 6 entradas de cajón (aunque vacías), en ese orden.

### `GET /api/insumos/dias`
```json
{ "dias": [ { "fecha": "2026-06-04", "total": 23,
              "por_cajon": {"portal":12,"corresponsales":9,"reporteros":2,"eventos_claro":0} }, ... ] }
```
Orden: fecha desc. Para el historial.

### `POST /api/insumos/aportar`  (multipart/form-data O JSON)
Campos: `cajon` (oblig.), `fecha` (opc, def hoy), `marca` (opc),
`texto` (opc), `archivo` (opc, File). Debe venir `texto` **o** `archivo`.
Parsea **síncrono** con Haiku, inserta lote + items, devuelve:
```json
{ "lote": {Lote}, "items": [ {Item}, ... ] }
```
Si el parse falla: lote con `estado:"error"`, `error:"..."`, `items:[]` (200, no 500).

### `GET /api/insumos/lote/{id}`  → `{ "lote": {Lote}, "items": [...] }`

### `PATCH /api/insumos/item/{id}`  (JSON parcial)
Campos editables: `titulo,resumen,marca,linea,hora,lugar,estado_material,tipo`.
→ `{ "item": {Item} }`

### `POST /api/insumos/item/{id}/usar`  (JSON: `{ "redes": ["x",...]?, "generar": bool? }`)
Lleva el item al tablero reutilizando el camino existente de aportación
(`repos.crear_contenido` con `origen="insumo"`, `flujo="importante"`; si
`generar` y hay marca, encola copy como hace `api/fuentes.aportar`). Marca el
item `usado=1`, guarda `contenido_id`. → `{ "item": {Item}, "contenido_id": "..." }`

### `DELETE /api/insumos/lote/{id}`  → `{ "ok": true }` (borra lote + sus items)

## Formas JSON (frontend types.ts)

**La API de este repo serializa en `snake_case`** (verificado en `api/rss.py`:
`marca_nombre`, `ultimo_conteo`, `redes_def`). Por tanto el JSON y los tipos TS
usan snake_case en las claves:

```ts
type CajonInsumo = "portal" | "corresponsales" | "reporteros" | "eventos_claro" | "notas" | "contexto";

interface InsumoLote {
  id: string; fecha: string; cajon: CajonInsumo; marca: string;
  origen_texto: string; origen_archivo: string;
  estado: "listo" | "error"; error: string;
  total_items: number; creado: string;
}
interface InsumoItem {
  id: string; lote_id: string; fecha: string; cajon: CajonInsumo;
  marca: string; marca_nombre: string; linea: string;
  titulo: string; resumen: string; hora: string; lugar: string;
  estado_material: "tengo" | "espero" | "";
  tipo: "nota" | "cobertura" | "evento" | "contexto"; idioma: string;
  usado: boolean; contenido_id: string; orden: number;
}
interface CajonConItems { cajon: CajonInsumo; lotes: InsumoLote[]; items: InsumoItem[]; }
interface RespuestaInsumos { fecha: string; cajones: CajonConItems[]; }
interface DiaInsumos { fecha: string; total: number; por_cajon: Record<CajonInsumo, number>; }
interface RespuestaDiasInsumos { dias: DiaInsumos[]; }
```
El backend devuelve `marca_nombre` resolviendo `marca` con `marcas.etiqueta_de(...)`
(como `api/rss.py`). `usado` se serializa como `bool`.

## Frontend (página + navegación)

- Ruta nueva `/datos/investigacion/cajones` (lazy en `router.tsx`).
- Tab "Cajones del día" en `TABS_INVESTIGACION` (`components/layout/hub-tabs.ts`),
  icono lucide adecuado (p.ej. `Inbox`).
- Página `pages/CajonesDia.tsx`:
  - `PageHeader` + selector de **fecha** (def hoy) + selector de **historial**
    de días (de `GET /api/insumos/dias`).
  - 4 tarjetas (Portal/SMS · Corresponsales · Reporteros · Eventos Claro). Cada
    una: `textarea` para pegar + `input file` + botón **Procesar** →
    `POST aportar` (loading mientras parsea) → lista de items **limpia y
    ordenada** con badges (marca, línea, hora, `estado_material`), acciones
    **Llevar al tablero** / editar / borrar lote.
  - Reusa primitivas shadcn de `@/components/ui` y badges de
    `@/components/comunes`. React Query (`useQuery`/`useMutation`).
- `lib/api.ts`: `insumos.listar(fecha, signal)`, `insumos.dias(signal)`,
  `insumos.aportar(form)`, `insumos.lote(id)`, `insumos.editarItem(id, campos)`,
  `insumos.usarItem(id, body)`, `insumos.borrarLote(id)`. Subida de archivo con
  `FormData` y `timeoutMs: 200_000` (el parse Haiku puede tardar).

## Reglas de trabajo (CLAUDE.md)
- Trabajar SOLO en el worktree `~/projects/keni-social-maquina`.
- **No** correr la suite de pytest ni levantar Postgres en local. Backend: valida
  con `ruff check` y un import sano (`python -c "import keni_consola.api.insumos"`
  con `DATABASE_URL` dummy si hace falta). Escribe tests (los corre el CI).
- Frontend: valida con `npm run typecheck`/`tsc -b` y `npm run lint`. Escribe tests
  (vitest) colocalizados.
- No tocar el bundle vendorizado en `webapp/`.
