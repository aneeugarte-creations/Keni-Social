# Consola Keni (interfaz)

La **Consola Keni** es una pequeña aplicación web que corre **en tu propia máquina** y te da una **interfaz con pestañas** para las tareas del día a día, sin tener que teclear comandos. Es una **capa de gestión**: por debajo, el motor que hace el trabajo de verdad sigue siendo **Claude Code** (las skills de copy y el servidor de métricas). La consola solo te lo pone fácil de lanzar y de ver.

> **No reemplaza a Claude Code, lo envuelve.** Si prefieres escribirle a Claude directamente, puedes seguir haciéndolo; la consola es la opción para quien quiere botones en vez de comandos.

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

---

## Las 7 pestañas

Agrupadas en **Trabajo** (lo del día a día) y **Ajustes** (configuración):

**Trabajo**
- **Generar copy** — eliges el tipo de contenido y la marca, y pegas tu nota **o subes un archivo**; la consola corre el asistente por debajo y te devuelve el copy (con botones para copiarlo o descargarlo). Nada se publica.
- **Métricas** — dashboard consolidado de las redes de tus marcas, comparar dos periodos y descargar los datos (CSV / Markdown / JSON).
- **Tareas** — organiza tareas por proyecto y abre el asistente en la carpeta de cada una con su prompt.

**Ajustes**
- **Proyectos** — edita el `CLAUDE.md` de tus carpetas y abre el asistente dentro de ellas.
- **Nueva carpeta** — crea una carpeta de proyecto con un `CLAUDE.md` de partida (plantilla por tipo de marca) y la deja registrada.
- **Estado** — autodiagnóstico del entorno (✅ / ⚠️ / ❌) y el siguiente paso, en lenguaje claro.
- **Configuración** — elige tus marcas, su alcance y la fuente de datos (muestra / real) sin tocar archivos.

---

## Privacidad

- La consola escucha **solo en `127.0.0.1`** (tu propia máquina). **No** se expone a la red local ni a internet por diseño: nadie más puede entrar.
- Por defecto trabaja con **datos de muestra** (números con la forma real de las marcas, pero ficticios). No se conecta a ninguna cuenta hasta que configures credenciales reales.

---

## Instalación

La consola es su propio paquete (`keni-consola`) y **depende de `keni-metricas`**. Instala primero la dependencia y luego la consola:

```
pip install -e ./mcp-metricas
pip install -e ./consola
```

Con `uv` también puedes instalarla como herramienta desde la ruta del paquete (`uv tool install ./consola`) o ejecutarla sin instalar (`uvx --from ./consola keni-consola`).

---

## Requisitos

- Tener instalado el servidor de métricas (`keni-metricas`), que necesita **`uv`/`uvx`** o un entorno virtual (`venv`) en la máquina. Ver [`../mcp-metricas/README.md`](../mcp-metricas/README.md) y [`credenciales.md`](credenciales.md).
- Para **"Generar copy"** hace falta tener el **CLI `claude`** instalado y disponible; cada generación **consume tokens** (es Claude trabajando por debajo).
- Para el flujo **clip → copy** (transcripción de audio/video) hace falta **whisper** y, hoy, un **Mac**. La transcripción ocurre **en local**, dentro de tu máquina.

---

Para empezar de cero con el sistema, ver [`primeros-pasos.md`](primeros-pasos.md). Para el día a día del community manager, ver [`guia-community-manager.md`](guia-community-manager.md).
