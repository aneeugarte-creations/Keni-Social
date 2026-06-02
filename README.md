# keni-social

**Suite de producción de contenido para equipos de redes sociales.** Convierte una nota, varios cables o un video en copy publicable —en **español de México**, con **auto-verificación** que dice cuándo creerle— y lee las **métricas de tus marcas conversando**, sin abrir cinco pestañas. La **generación de copy y de imagen** se trabaja desde la **Consola** (Biblioteca de prompts + Estudio de imagen); el **plugin de Claude Code** aporta los **MCP** (métricas y tablero) y comandos `/` de apoyo. El audio se transcribe **en tu máquina** y las métricas se leen con **credenciales locales**: privacidad por diseño.

**Para quién:** community managers y su responsable. Diseñado primero para el equipo de **AMX Contenido** (UnoTV / Claro Sports / Nación Gamer / Piso 15 / Fundación) y reutilizable para otros clientes de Keni.

**El diferenciador:** copy tropicalizado es-MX + auto-verificación honesta + transcripción 100% local + métricas conversacionales, todo dentro de Claude Code y con la llave de cada red viviendo en tu máquina, no en la IA.

> **Empieza aquí:** [`docs/primeros-pasos.md`](docs/primeros-pasos.md) — quickstart de ~5 minutos.

Componentes principales:

| Pieza | Qué es | Estado |
|---|---|---|
| [`consola/`](consola/) | La **Consola Keni** (app web local/alojada): **Biblioteca de prompts + línea editorial** (documentos markdown editables) para convertir una nota, varios cables o un clip en copy publicable (voz de marca + tropicalización mexicana + formato por plataforma + auto-verificación), y el **Estudio de imagen**. La generación se lanza con `claude -p`. | En uso (beta). |
| [`mcp-metricas/`](mcp-metricas/) | Servidor **MCP** que lee métricas de redes (Meta FB/IG, YouTube, X, TikTok), multi-marca, y las expone a Claude. Corre **local por persona** con sus propias credenciales. | Núcleo + fuente `muestra` listos; adaptadores reales vía Metricool (lectura y publicación). |
| [`mcp-tablero/`](mcp-tablero/) | Servidor **MCP** que crea/mueve/lista contenido del tablero de la Consola desde Claude Code (necesita `KENI_CONSOLA_URL`/`KENI_CONSOLA_TOKEN`). | En uso (beta). |
| [`keni-shared/`](keni-shared/) | **Capa base** común a la Consola y al MCP de métricas: catálogo de marca, límites de plataforma y utilidades canónicas. | En uso. |

> **Nota.** La generación de copy ya **no** usa el antiguo paquete de skills (`skills-copy/`, retirado): el copy y la imagen viven en la **Consola** (Biblioteca de prompts + Estudio de imagen).

## Consola (interfaz)

¿Prefieres botones a teclear comandos? La **Consola Keni** es una app web que corre **en tu máquina** y te da una interfaz con pestañas (Proyectos, Métricas, Generar copy, Tareas, Nueva carpeta) para el día a día. Es una **capa de gestión**: el motor que hace el trabajo sigue siendo Claude Code. Arráncala con:

```
keni-consola
```

(o el equivalente `python -m keni_consola`) y abre `http://127.0.0.1:8765`. Escucha **solo en localhost** y arranca con datos de muestra. La consola es su propio paquete (`keni-consola`) que, junto con `keni-metricas`, depende de `keni-shared` (la capa más baja: catálogo de marca, límites de plataforma y utilidades canónicas). Instálalos con `pip install -e ./keni-shared -e ./mcp-metricas -e ./consola` (o `uv tool install ./consola` / `uvx --from ./consola keni-consola`; `keni-shared` y `keni-metricas` se arrastran como dependencias dentro del monorepo). Guía completa en [`docs/consola.md`](docs/consola.md).

> **Persistencia (ADR 0004):** la operacional de la consola vive en **Postgres** (ya no SQLite). En desarrollo no se usa Postgres local: la ejecución y validación se hacen en el server (CI Woodpecker / hosted `social.kenitech.io`). Si necesitas correr la consola en local, provee tu propio `DATABASE_URL` apuntando a un Postgres que tú gestiones (p. ej. `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/keni_social`). Sin `DATABASE_URL` el back falla con un mensaje accionable. La privacidad local se preserva (Postgres en la propia máquina); ver [`consola/README.md`](consola/README.md) y [`docs/adr/0004-persistencia-operacional-postgres-unico.md`](docs/adr/0004-persistencia-operacional-postgres-unico.md).

## Por dónde empezar

- **Primeros pasos (recomendado):** [`docs/primeros-pasos.md`](docs/primeros-pasos.md) — quickstart de ~5 min, sin tecnicismos.
- **Día a día del community manager:** [`docs/guia-community-manager.md`](docs/guia-community-manager.md) — qué le escribes a Claude para cada tarea.
- **Generar copy:** desde la Consola (Biblioteca de prompts). Ver [`docs/consola.md`](docs/consola.md) y [`consola/README.md`](consola/README.md).
- **Conectar métricas a Claude:** ver [`mcp-metricas/README.md`](mcp-metricas/README.md).
- **Credenciales y despliegue local:** ver [`docs/`](docs/).

### Documentación clave

- [`docs/arquitectura.md`](docs/arquitectura.md) — cómo encajan la Biblioteca de prompts, el MCP de métricas y la Consola.
- [`docs/estado-producto.md`](docs/estado-producto.md) — panorama honesto: qué está listo, qué está pausado por gating externo.

## Instalación como plugin

El plugin `keni-social` aporta a Claude Code los **servidores MCP** (métricas y tablero) y unos **comandos `/`** de apoyo. **La generación de copy y de imagen NO va en el plugin: vive en la Consola** (Biblioteca de prompts + Estudio de imagen). Se instala desde el marketplace privado de Keni en **dos comandos**, sin permisos de administrador.

1. Añade el marketplace de Keni (solo la primera vez):

   ```
   /plugin marketplace add kenitech-io/keni-social
   ```

2. Instala el plugin:

   ```
   /plugin install keni-social@keni
   ```

Listo. Cierra y vuelve a abrir Claude Code (o ejecuta `/reload-plugins`). El plugin declara dos servidores MCP:

- **`keni-metricas`** — lee las métricas multi-marca y las expone a Claude (Meta FB/IG, YouTube, X, TikTok).
- **`keni-tablero`** — crea/mueve/lista contenido del tablero de la Consola desde Claude Code (necesita `KENI_CONSOLA_URL`/`KENI_CONSOLA_TOKEN`).

> El servidor de **métricas** (`keni-metricas`) necesita `uv`/`uvx` en la máquina para arrancar y, para datos reales, credenciales locales. Para configurarlo sin tocar archivos a mano hay un **asistente guiado** (`python -m keni_metricas.asistente`): te lleva **paso a paso** (te indica en qué `paso X/N` vas) y cierra con un **recap** de lo que dejó configurado y el próximo paso (`verifica con doctor`). Ver [`mcp-metricas/README.md`](mcp-metricas/README.md) y [`docs/credenciales.md`](docs/credenciales.md). El cableado de ejemplo del servidor está en [`.mcp.json`](.mcp.json).

### Comandos disponibles

El plugin trae **comandos `/`** que envuelven los flujos de métricas más comunes para que sean fáciles de descubrir y lanzar (escríbelos con `/` dentro de Claude Code). Son **seguros**: solo lectura o dry-run, nunca publican ni borran nada.

- `/keni-social:keni-reporte` — genera y **explica en claro** el reporte consolidado multi-marca con picos/anomalías (acepta rango, p. ej. `mes` o `semana`).
- `/keni-social:keni-dashboard` — genera el **dashboard HTML** autocontenido (reporte + picos) y te dice dónde quedó y qué contiene.
- `/keni-social:keni-doctor` — corre el **autodiagnóstico** del entorno de métricas y explica cada ❌ con el paso para arreglarlo.
- `/keni-social:keni-preview` — guía el **pre-vuelo (dry-run)** de una publicación con la skill `publica-meta`: muestra exacto qué se publicaría, sin publicar.

### Actualizar

Cuando Keni publique una versión nueva, actualízala con:

```
/plugin marketplace update keni
```

### Repositorio privado

`kenitech-io/keni-social` es privado. Para que `/plugin marketplace add` funcione tienes que tener acceso al repo y estar autenticado con GitHub (por ejemplo `gh auth login`). Pídele acceso a Keni si el comando falla con un error de permisos.

## Principio

La IA produce; el humano aprueba. El copy sale con una **auto-verificación** que dice cuándo creerle, y las métricas se leen con **credenciales locales y revocables** (la llave vive en tu máquina, no en la IA).
