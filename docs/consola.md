# Consola Keni (interfaz)

La **Consola Keni** es una aplicación web que corre **en tu propia máquina** y te da una **interfaz** para las tareas del día a día, sin teclear comandos. Es una **capa de gestión**: por debajo, el motor que hace el trabajo de verdad sigue siendo **Claude Code** (los prompts de la Texto lanzados con `claude -p` y el servidor de métricas). La consola solo te lo pone fácil de lanzar y de ver.

> **No reemplaza a Claude Code, lo envuelve.** Si prefieres escribirle a Claude directamente, puedes seguir haciéndolo; la consola es la opción para quien quiere botones en vez de comandos.

> Este documento describe el **modo local** (una persona, su máquina). El piloto corre además
> una instancia **alojada multiusuario** (`https://social.kenitech.io`, con usuarios/sesiones,
> Postgres y worker propio) descrita en [`despliegue-hosted.md`](despliegue-hosted.md); ahí la
> misma capacidad se expone también como **tools MCP** en `/mcp` (ver
> [`arquitectura.md`](arquitectura.md) §3).

---

## Cómo se arranca

En una terminal, dentro de la carpeta del proyecto:

```
keni-consola
```

(Si por lo que sea ese comando no existe, sirve el equivalente: `python -m keni_consola`.)

Verás un mensaje con la dirección. Abre en tu navegador:

```
http://127.0.0.1:8765
```

La consola intenta abrir el navegador sola; si no lo hace, copia esa dirección. Para detenerla, vuelve a la terminal y pulsa `Ctrl+C`.

> El puerto por defecto es `8765`. Si lo necesitas cambiar (por ejemplo, porque está ocupado), arranca con la variable `KENI_CONSOLA_PORT`, p. ej. `KENI_CONSOLA_PORT=9000 keni-consola`.

> **Clave de acceso (token).** La consola pide un **token** para usar sus funciones, así ninguna otra web abierta en tu navegador puede dispararlas por error. Al arrancar verás un enlace del tipo `http://127.0.0.1:8765/?token=…`: **ábrelo tal cual la primera vez** y listo, no tienes que volver a escribir nada. Si prefieres una clave fija, arranca con `KENI_CONSOLA_TOKEN=tu-clave keni-consola`. Esto es solo una barrera local; no sustituye a usuarios y contraseñas (eso vendrá después).

---

## Qué es (idea de diseño)

La consola es una **capa de gestión** sobre Claude Code: no hace el trabajo, lo
**lanza y lo muestra**. El motor sigue siendo Claude Code (los prompts de la
Texto, lanzados con `claude -p`) y el servidor de métricas; la consola solo da
botones a quien no quiere teclear comandos.
Dos ideas de diseño la rigen:

- **Un solo almacén operacional (Postgres).** Lo que ves y editas en la consola
  (publicaciones, plantillas, fuentes RSS, hashtags, franjas, tareas, rota) vive en
  **Postgres** (ADR 0004/0006), no en almacenes paralelos. La prosa editorial por marca
  (el `CLAUDE.md` y las voces de cada marca) sigue como ficheros versionados editables a
  mano; la consola es una vista cómoda sobre todo ello.
- **Solo en tu máquina.** Escucha únicamente en `127.0.0.1`; nada se expone a la red.

El sidebar agrupa las páginas en **Trabajo** (uso diario) y **Ajustes**
(configuración). **No listamos aquí las páginas una a una**: la superficie cambia y
esta lista se desfasaría. La referencia viva es la propia app (el sidebar) y, en el
código, `consola/frontend/src/components/layout/navegacion.ts`.

---

## Qué hay por debajo (arquitectura)

- La interfaz es una **aplicación React** (SPA) servida por un **servidor local** (Python/Starlette) que expone una **API JSON** (`/api/...`). La React habla con esa API; la API reutiliza el núcleo de siempre: el servidor de métricas (`keni-metricas`), la **Texto de Prompts** (`texto.py`) y el **lanzador neutro** (`dominio/generar.py`, que arranca `claude -p`).
- El **contenido editorial estructurado** (publicaciones, plantillas, fuentes RSS, hashtags, franjas y el historial de copy) y lo **operacional** (tus tareas, el seguimiento Comercial con su serie temporal, la rota, usuarios/sesiones y la cola de jobs) viven en **Postgres** (`DATABASE_URL`, ADR 0004/0006): un único almacén operacional, sin índices ni SQLite paralelos que se desincronicen. Solo la **prosa editorial por marca** (`marca.yaml`, `CLAUDE.md`, voces) sigue como ficheros versionados editables a mano. La configuración de marcas/fuente sigue en los `.toml` de siempre.
- El SPA se **compila desde fuente** (`vite build`): en producción/CI lo construye el deploy. El paquete Python ya **no incluye un bundle precompilado** (`webapp/` está gitignored); en local, si no lo compilas, el back sirve un placeholder amable. Construir la interfaz requiere Node.

---

## Privacidad

- La consola escucha **solo en `127.0.0.1`** (tu propia máquina). **No** se expone a la red local ni a internet por diseño: nadie más puede entrar.
- Por defecto trabaja con **datos de muestra** (números con la forma real de las marcas, pero ficticios). No se conecta a ninguna cuenta hasta que configures credenciales reales.

---

## Instalar y desarrollar

Este documento es de **diseño**; el cómo-instalar vive donde se mantiene de verdad,
para no duplicarlo aquí:

- **Instalar y arrancar** (paquete `keni-consola`, dependencias del monorepo, `uv`):
  [`../consola/README.md`](../consola/README.md). El SPA se compila desde fuente
  (`vite build`); en producción/CI lo construye el deploy.
- **Tocar la interfaz** (Node ≥ 18, `npm run dev`/`build`, compilar el SPA a
  `webapp/`): [`../consola/frontend/README.md`](../consola/frontend/README.md).

---

## Requisitos

- Tener instalado el servidor de métricas (`keni-metricas`), que necesita **`uv`/`uvx`** o un entorno virtual (`venv`) en la máquina. Ver [`../mcp-metricas/README.md`](../mcp-metricas/README.md) y [`credenciales.md`](credenciales.md).
- Para **"Generar copy"** hace falta tener el **CLI `claude`** instalado y disponible; cada generación **consume tokens** (es Claude trabajando por debajo).
- Para el flujo **clip → copy** (transcripción de audio/video) hace falta **whisper** y, hoy, un **Mac**. La transcripción ocurre **en local**, dentro de tu máquina.
