# Ola 6 — Agentes de investigación

Objetivo: agentes que investigan por marca/línea/tema y **dejan candidatos
fechados** en las fuentes del día. **Proponen; el humano filtra** (aceptar→tablero
o descartar). Nunca publican ni crean piezas solos.

## Modelo de datos (db.py `_DDL_ESQUEMA` + repos)

### `inv_brief` (un encargo de investigación reutilizable)
```
id           TEXT PRIMARY KEY
nombre       TEXT NOT NULL DEFAULT ''
marca        TEXT NOT NULL DEFAULT ''
linea        TEXT NOT NULL DEFAULT ''   -- línea/tema (texto)
instrucciones TEXT NOT NULL DEFAULT ''  -- qué buscar, fuentes preferidas, tono
idiomas      TEXT NOT NULL DEFAULT ''   -- CSV de idiomas a rastrear ('' = cualquiera)
activo       INTEGER NOT NULL DEFAULT 1
creado       TEXT NOT NULL DEFAULT ''
```
Índices: `(marca)`, `(activo)`.

### `inv_candidato` (resultado de una corrida)
```
id           TEXT PRIMARY KEY
brief_id     TEXT NOT NULL DEFAULT ''
fecha        TEXT NOT NULL DEFAULT ''   -- día editorial ISO YYYY-MM-DD
marca        TEXT NOT NULL DEFAULT ''
linea        TEXT NOT NULL DEFAULT ''
titulo       TEXT NOT NULL DEFAULT ''
resumen      TEXT NOT NULL DEFAULT ''
por_que      TEXT NOT NULL DEFAULT ''   -- por qué es relevante hoy
fuente       TEXT NOT NULL DEFAULT ''   -- medio/origen
enlace       TEXT NOT NULL DEFAULT ''
idioma       TEXT NOT NULL DEFAULT 'es'
estado       TEXT NOT NULL DEFAULT 'nuevo'  -- nuevo|aceptado|descartado
contenido_id TEXT NOT NULL DEFAULT ''   -- si se aceptó → tablero
creado       TEXT NOT NULL DEFAULT ''
```
Índices: `(fecha, marca)`, `(brief_id)`, `(estado)`.

## Ejecución (dominio/investigacion_agente.py)

Espeja el modelo de ejecución del endpoint de `importador_calendario`
(`_ejecutar_claude_json`, síncrono, JSON). Diferencias:
- **Con web**: el prompt pide al agente investigar en la web y devolver
  EXCLUSIVAMENTE `{"candidatos":[{titulo,resumen,por_que,fuente,enlace,idioma}]}`.
- Modelo: usa `config.insumos_modelo()` o un flag propio; timeout más alto
  (p.ej. 300 s). Ejecutor inyectable para tests (NUNCA toca red/binario en test).
- Correr SIEMPRE en threadpool desde el handler async (`starlette.concurrency.run_in_threadpool`)
  para no bloquear el event loop (mira cómo lo hace el endpoint de importar).
- `correr_brief(brief, *, fecha, ejecutor=None) -> tuple[list[dict], list[dict]]`
  (candidatos, errores). Tropicaliza/normaliza marca por nombre→id.

## API (api/investigacion.py — RUTAS auto-descubierta)
- `GET /api/investigacion/briefs` → `{ "briefs": [Brief...] }`
- `POST /api/investigacion/briefs` `{nombre, marca, linea?, instrucciones, idiomas?}` → `{ "brief": Brief }`
- `PUT /api/investigacion/briefs/{id}` (parcial) · `DELETE /api/investigacion/briefs/{id}`
- `POST /api/investigacion/correr` `{brief_id}` (o ad-hoc `{marca, linea, instrucciones}`)
  → corre el agente (threadpool), inserta candidatos `estado=nuevo` fechados HOY,
  → `{ "candidatos": [Candidato...], "errores": [...] }`
- `GET /api/investigacion/candidatos?fecha=&marca=&estado=` → `{ "candidatos": [...] }` (def fecha=hoy)
- `POST /api/investigacion/candidatos/{id}/aceptar` `{redes?, generar?}` → lleva al
  tablero reutilizando el camino de aportación/desde-radar (origen='investigacion'),
  marca `estado=aceptado` + `contenido_id`. → `{ "candidato": Candidato, "contenido_id": "..." }`
- `POST /api/investigacion/candidatos/{id}/descartar` → `estado=descartado`

## Daemon (gateado)
`config.py`: `ENV_INVESTIGACION = "KENI_INVESTIGACION_AUTO"` → `investigacion_auto_activa()` (def False).
`daemons.py`: `iniciar_investigacion()` que, si ON, corre los briefs activos
periódicamente (best-effort, dedup por enlace/título+día, cap por corrida). DRAFT
de candidatos, nunca tablero automático.

## Frontend
- `types.ts`: `InvBrief`, `InvCandidato`, respuestas.
- `lib/api.ts`: grupo `investigacion` con briefs CRUD, `correr`, `candidatos`,
  `aceptar`, `descartar`.
- Página `pages/AgentesInvestigacion.tsx` bajo el hub Investigación
  (`/datos/investigacion/agentes`, tab nuevo en `TABS_INVESTIGACION`):
  - Gestión de briefs (alta/edición/activar).
  - Botón "Investigar ahora" por brief (loading mientras corre) → lista de
    candidatos del día con badges (marca, línea, idioma, fuente) + enlace, y
    acciones **Aceptar** (→ tablero) / **Descartar**. Selector de día (historial).
  - React Query; invalida candidatos tras correr/aceptar/descartar.

## Reglas
- Worktree `~/projects/keni-social-maquina`. No pytest/Postgres local; ruff + ast +
  (frontend) tsc -b + vite build + vitest. Proponen, no publican. SQLite `?`.
  snake_case JSON. No tocar `webapp/`.
