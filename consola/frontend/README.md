# Frontend de la Consola Keni

SPA de la Consola Keni: una herramienta web **local** (corre en `127.0.0.1`) que
envuelve a Claude Code. Stack: **Vite + React 18 + TypeScript**, **Tailwind v3**,
**shadcn/ui** (Radix + CVA + lucide-react), **@tremor/react** para gráficas,
**react-router-dom v6** y **@tanstack/react-query v5**.

Todo el texto visible está en español (es-MX). Marca: naranja `#ff5a1f`,
wordmark "KENI · Consola". Modo claro y oscuro (persistido en `localStorage`).

## Requisitos

- Node 18+ y npm.

## Desarrollo (`npm run dev`)

El backend de la consola (Starlette/uvicorn) corre en `http://127.0.0.1:8765`.
Arráncalo en otra terminal, por ejemplo:

```bash
keni-consola            # o: python -m keni_consola
```

Luego, en esta carpeta:

```bash
npm install
npm run dev             # Vite en http://localhost:5173
```

En dev, Vite **proxea** `/api` hacia `http://127.0.0.1:8765`, así que el SPA
habla con el backend real sin configuración extra.

## Compilar para producción (`npm run build`)

```bash
npm run build
```

Esto genera el bundle en `../src/keni_consola/webapp/` (`index.html` +
`assets/*`). Ese bundle **se versiona** (se commitea) para distribuir la consola
sin necesidad de Node: el paquete Python lo sirve desde el mismo origen.

## Scripts

| Script              | Qué hace                                            |
| ------------------- | --------------------------------------------------- |
| `npm run dev`       | Servidor de desarrollo (HMR) con proxy a `/api`.    |
| `npm run build`     | `tsc -b` + `vite build` → `webapp/` (gitignored).   |
| `npm run lint`      | ESLint sobre `src/`.                                |
| `npm run typecheck` | `tsc --noEmit` (chequeo de tipos).                  |
| `npm run preview`   | Sirve el bundle compilado localmente.               |
| `npm run test`      | Tests con Vitest.                                   |
| `npm run gen:types` | Regenera `src/types.gen.ts` desde el backend.       |
| `npm run gen:types:check` | Falla si `types.gen.ts` está desincronizado.  |

## Estructura

```
src/
  main.tsx              Monta React + React Query + Router + Toaster
  router.tsx            Rutas del SPA (landing → /generar-copy) + redirecciones
  index.css             Tailwind + tokens shadcn + modo oscuro
  types.ts              Contrato tipado de la API (/api/*)
  lib/
    api.ts              Cliente fetch tipado (JSON, multipart, descargas)
    utils.ts            cn() (clsx + tailwind-merge)
  hooks/
    use-tema.tsx        Tema claro/oscuro persistido en localStorage
  components/
    ui/                 Componentes shadcn (button, card, input, ...)
    layout/             AppShell, Sidebar, Wordmark, PageHeader, IndicadorEstado
  pages/                páginas de trabajo y ajustes (Configuración, Métricas, ...)
```

## Tipos derivados del backend (`types.gen.ts`)

El contrato tipado de la API vive en `src/types.ts`. Un **subconjunto estable**
(estado, configuración, límites/redes, métricas y las respuestas genéricas) ya
**no se mantiene a mano**: se **genera** desde el backend para que no se
desincronice en silencio (era el hallazgo H5/E6, #101).

- **Fuente única**: `keni_consola.esquema_api` (Python) define esas formas como
  `TypedDict` y emite su **JSON Schema** (`python -m keni_consola.esquema_api`).
- **Generación**: `scripts/gen-types.mjs` toma ese esquema y produce
  `src/types.gen.ts` con `json-schema-to-typescript`. `types.ts` lo **re-exporta**,
  así que el resto del código sigue importando todo desde `@/types` sin cambios.
- El **resto** de `types.ts` sigue a mano: la mayoría de los ~50 handlers construyen
  sus respuestas como dicts ad-hoc (no como modelos), y generarlos todos sería
  frágil. Se eligió un subset robusto y reproducible.

### Regenerar

Necesitas el backend instalado en un Python (p. ej. un venv con `keni-consola`):

```bash
# Con el python por defecto (debe importar keni_consola):
npm run gen:types

# O apuntando a un venv concreto:
KENI_PYTHON=/ruta/al/venv/bin/python npm run gen:types
```

Commitea `src/types.gen.ts` (es un artefacto versionado, como el bundle).

### Guard anti-divergencia

Dos pruebas evitan que el TS generado se separe del backend:

- **Frontend** (`src/types.gen.test.ts`, Vitest): el archivo existe, está marcado
  como GENERADO y todas sus interfaces se re-exportan desde `types.ts`. No necesita
  Python.
- **Backend** (`consola/tests/test_esquema_api.py`, pytest): compara el esquema
  actual del backend contra el `types.gen.ts` comiteado (interfaces y **campos**).
  Si cambias un `TypedDict` y olvidas `npm run gen:types`, **falla**.

## Páginas

Cada ruta del SPA es una página en `src/pages/` (algunas con subcarpetas para sus
piezas). Las páginas están implementadas y consumen la API; no quedan _stubs_. La
lista viva y autoritativa de rutas es `router.tsx`, agrupadas en el sidebar por
`components/layout/navegacion.ts` (Trabajo / Ajustes). El router también mantiene
las redirecciones de páginas fusionadas o retiradas (p. ej. `/estado` y
`/conexiones` → `/configuracion`), así que enlaces antiguos no rompen.
