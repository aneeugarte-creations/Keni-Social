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
| `npm run build`     | `tsc -b` + `vite build` → bundle en `webapp/`.      |
| `npm run lint`      | ESLint sobre `src/`.                                |
| `npm run typecheck` | `tsc --noEmit` (chequeo de tipos).                  |
| `npm run preview`   | Sirve el bundle compilado localmente.               |
| `npm run test`      | Tests con Vitest (incluye el de la página Estado).  |

## Estructura

```
src/
  main.tsx              Monta React + React Query + Router + Toaster
  router.tsx            Las 7 rutas del SPA (landing → /generar-copy)
  index.css             Tailwind + tokens shadcn + modo oscuro
  types.ts              Contrato tipado de la API (/api/*)
  lib/
    api.ts              Cliente fetch tipado (JSON, multipart, descargas)
    utils.ts            cn() (clsx + tailwind-merge)
  hooks/
    use-tema.tsx        Tema claro/oscuro persistido en localStorage
  components/
    ui/                 Componentes shadcn (button, card, input, ...)
    layout/             AppShell, Sidebar, Wordmark, PageHeader, EnConstruccion
  pages/                Estado (referencia, completa) + 6 stubs
```

## Estado de las páginas

- **Estado** (`/estado`): implementada por completo (consume `GET /api/estado`).
- Las otras seis (`/generar-copy`, `/metricas`, `/tareas`, `/proyectos`,
  `/carpetas`, `/configuracion`) son _stubs_ "🚧 En construcción", listas para
  que cada una se rellene editando solo su archivo en `src/pages/`.
