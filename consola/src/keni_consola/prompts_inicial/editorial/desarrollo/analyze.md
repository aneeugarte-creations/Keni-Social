---
titulo: "Analyze · explorar el repo"
descripcion: "Cómo un agente de desarrollo explora keni-social ANTES de tocar nada: mapa del monorepo, dónde vive cada cosa y qué leer primero."
tipo: editorial
clase: desarrollo
marcas: []
pipelines: []
creado: 2026-06-18T00:00:00+00:00
actualizado: 2026-06-18T00:00:00+00:00
---

# Analyze · explorar antes de tocar

Fase de SOLO LECTURA. No edites, no instales, no levantes nada. Sal de aquí con un mapa mental del sistema y una hipótesis de dónde vive el cambio. Si no puedes señalar el archivo o seam exacto, sigues en esta fase.

## Mapa del monorepo

keni-social es un monorepo git (NO vive en el Drive; el Drive es solo contexto). Raíz con estos paquetes:

- `consola/` — el producto. Backend Starlette/uvicorn (Python 3.11+) en `consola/src/keni_consola/`; frontend React+TS+Vite+shadcn en `consola/frontend/src/`. La generación de copy NO la corre el back: el back encola jobs y un servicio `worker` aparte ejecuta `claude -p`.
- `mcp-metricas/` — MCP de LECTURA de métricas (FastMCP, stdio, local por persona). Solo lectura.
- `mcp-tablero/` — MCP de ESCRITURA sobre el tablero (crear/mover/actualizar piezas vía la API HTTP de la consola).
- `keni-shared/` — código compartido (p. ej. `marcas`). Es la FUENTE de varias fachadas de reexport.
- `deploy/` — Docker Compose, Dockerfiles, Traefik, Woodpecker CI.
- `docs/` — ADRs y documentación. Lee los ADR antes de cruzar fronteras.

## Dónde vive cada cosa en `consola/src/keni_consola/`

- `api/` — routers HTTP. Se autodescubren (`api/__init__.py::descubrir`). `api/sistema/` para el panel admin.
- `dominio/` — lógica de negocio (jobspec, generar, recibir, perfiles, clasificador de marca, desarrollo…).
- `libprompts/` — Biblioteca de Prompts: `_comun.py` (constantes `TIPOS`/`CLASES`/`PIPELINES`), `_validacion.py`, `_io.py`, `_inicial.py` (siembra desde `prompts_inicial/`), `_editorial.py` (auto-adjunto/pilares).
- `prompts_inicial/editorial/` y `prompts_inicial/prompt/` — semillas `.md` con frontmatter que pueblan el store en el primer arranque.
- `db.py` (barrel) + `db_*.py` + `_db_core/` — Postgres. Migraciones en `migracion.py` + `_db_core/migraciones*.py`.
- `cola.py` / `db_jobs.py` — cola de jobs (reclamar/encolar, filtrado por carril).
- `worker.py` — worker de contenido (ejecuta `claude -p`). Carriles dev se reclaman aparte.
- `webapp/` — outDir de `vite build`. GITIGNORED, NO se versiona. No lo toques a mano.

## Qué leer, en este orden

1. El o los `CLAUDE.md` del repo y de las carpetas que vas a tocar (reglas que MANDAN).
2. `docs/adr/` — sobre todo ADR 0005 (fronteras/seams) y los que cubran tu área (0001-0002 auth `claude -p`, 0004/0006 almacenamiento).
3. El módulo objetivo y sus tests (`consola/tests/test_*.py` con el mismo nombre temático).
4. Los CONSUMIDORES del símbolo/firma/forma que vas a cambiar: `grep -rn` por el nombre antes de asumir el alcance.

## Señales de que un seam está cerca (anótalas para la fase plan)

- Fachadas de reexport: `keni_consola.marcas` reexporta `keni_shared.marcas` (hay más). Un símbolo nuevo debe ir a la fuente Y al `__all__`/import de la fachada.
- Routers nuevos que importan de otra app = CRUCE de frontera (ADR 0005).
- Formas observables que un test fija: etapas de un daemon, contrato de salida de un prompt, claves u orden de una respuesta de API, el esquema o las restricciones de la base de datos.

## Salida de esta fase

Un resumen con: archivos relevantes (rutas absolutas), el seam o seams que cruza el cambio, los consumidores encontrados, y los tests que afirman la forma actual. Eso alimenta directamente la fase `plan`.
