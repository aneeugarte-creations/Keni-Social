# keni-social

**Suite de producción de contenido para equipos de redes sociales**, instalable como **plugin de Claude Code**. Convierte una nota, varios cables o un video en copy publicable —en **español de México**, con **auto-verificación** que dice cuándo creerle— y lee las **métricas de tus marcas conversando**, sin abrir cinco pestañas. El audio se transcribe **en tu máquina** y las métricas se leen con **credenciales locales**: privacidad por diseño.

**Para quién:** community managers y su responsable. Diseñado primero para el equipo de **AMX Contenido** (UnoTV / Claro Sports / Nación Gamer / Piso 15 / Fundación) y reutilizable para otros clientes de Keni.

**El diferenciador:** copy tropicalizado es-MX + auto-verificación honesta + transcripción 100% local + métricas conversacionales, todo dentro de Claude Code y con la llave de cada red viviendo en tu máquina, no en la IA.

> **Empieza aquí:** [`docs/primeros-pasos.md`](docs/primeros-pasos.md) — quickstart de ~5 minutos para quien acaba de instalar el plugin.

Dos componentes independientes pero complementarios:

| Carpeta | Qué es | Estado |
|---|---|---|
| [`mcp-metricas/`](mcp-metricas/) | Servidor **MCP** que lee métricas de redes (Meta FB/IG, YouTube, X, TikTok), multi-marca, y las expone a Claude. Corre **local por persona** con sus propias credenciales. | Núcleo + fuente `muestra` listos; adaptadores reales escalonados por App Review/auditoría. |
| [`skills-copy/`](skills-copy/) | **Agent Skills** de Claude Code + contexto editorial versionado, que convierten una nota, varios cables o un clip en copy publicable (voz de marca + tropicalización mexicana + formato por plataforma + auto-verificación) y ayudan a responder comentarios en voz de marca. | Listo para usar. |

## Consola (interfaz)

¿Prefieres botones a teclear comandos? La **Consola Keni** es una app web que corre **en tu máquina** y te da una interfaz con pestañas (Proyectos, Métricas, Generar copy, Tareas, Nueva carpeta) para el día a día. Es una **capa de gestión**: el motor que hace el trabajo sigue siendo Claude Code. Arráncala con:

```
keni-consola
```

(o el equivalente `python -m keni_consola`) y abre `http://127.0.0.1:8765`. Escucha **solo en localhost** y arranca con datos de muestra. La consola es su propio paquete (`keni-consola`) que, junto con `keni-metricas`, depende de `keni-shared` (la capa más baja: catálogo de marca, límites de plataforma y utilidades canónicas). Instálalos con `pip install -e ./keni-shared -e ./mcp-metricas -e ./consola` (o `uv tool install ./consola` / `uvx --from ./consola keni-consola`; `keni-shared` y `keni-metricas` se arrastran como dependencias dentro del monorepo). Guía completa en [`docs/consola.md`](docs/consola.md).

## Por dónde empezar

- **Primeros pasos (recomendado):** [`docs/primeros-pasos.md`](docs/primeros-pasos.md) — quickstart de ~5 min, sin tecnicismos.
- **Día a día del community manager:** [`docs/guia-community-manager.md`](docs/guia-community-manager.md) — qué le escribes a Claude para cada tarea.
- **Generar copy:** ver [`skills-copy/README.md`](skills-copy/README.md).
- **Conectar métricas a Claude:** ver [`mcp-metricas/README.md`](mcp-metricas/README.md).
- **Credenciales y despliegue local:** ver [`docs/`](docs/).

### Documentación clave

- [`docs/arquitectura.md`](docs/arquitectura.md) — cómo encajan el sistema de copy y el MCP de métricas.
- [`docs/estado-producto.md`](docs/estado-producto.md) — panorama honesto: qué está listo, qué está pausado por gating externo.

## Instalación como plugin

La forma más sencilla de tener todo (las skills de copy + las métricas) es instalar `keni-social` como **plugin de Claude Code** desde el marketplace privado de Keni. Son **dos comandos**, dentro de Claude Code, sin permisos de administrador.

1. Añade el marketplace de Keni (solo la primera vez):

   ```
   /plugin marketplace add kenitech-io/keni-social
   ```

2. Instala el plugin:

   ```
   /plugin install keni-social@keni
   ```

Listo. Cierra y vuelve a abrir Claude Code (o ejecuta `/reload-plugins`). Después de instalarlo tendrás disponibles las skills, con el nombre del plugin por delante:

- `/keni-social:copy-desde-nota` — de una o varias notas/cables (o una transcripción) a copy publicable por plataforma.
- `/keni-social:clip-a-copy` — de un video/audio a copy (transcribe en local) con las mejores citas y su marca de tiempo.
- `/keni-social:nota-a-formato` — normaliza una nota cruda al estilo editorial de la casa (paso previo opcional).
- `/keni-social:resumen-tendencia` — brief corto de un tema: qué pasa, ángulo por marca y riesgos legales.
- `/keni-social:publica-meta` — pre-vuelo en dry-run: prepara y previsualiza la publicación en cada red (copy final, conteos, hashtags, media), sin publicar.
- `/keni-social:revisa-imagen` — repaso legal y editorial de un arte propuesto (bandera/escudo, menores, datos personales, marcas) antes de publicar.
- `/keni-social:verifica-video` — pega el enlace de un video viral y dice si parece **nuevo o ya circulaba desde antes** (reciclado), antes de decidir si retomarlo. Análisis local y gratis (fecha de subida, fechas en pantalla por OCR, enlaces de búsqueda inversa para un clic). Requiere `yt-dlp`, `ffmpeg` y `tesseract`. *Experimental.*
- `/keni-social:responde-comentarios` — clasifica un comentario y redacta la respuesta en voz de marca tropicalizada, con auto-verificación. **Nunca publica:** tú apruebas y respondes. Para el día a día, ver [`docs/guia-community-manager.md`](docs/guia-community-manager.md).
- `/keni-social:brief-matutino` — el brief de la mañana para la mesa editorial: reúne noticias y tendencias del día (Google News + Google Trends, en vivo) más lo que viste a mano en redes, las jerarquiza por frescura/relevancia/agenda y sugiere un formato por pieza. Es un brief para **decidir qué cubrir**, no copy final. *Experimental.*

> Las skills de copy funcionan solas. El servidor de **métricas** (`keni-metricas`) viene declarado en el plugin pero necesita `uv`/`uvx` en la máquina para arrancar y, para datos reales, credenciales locales. Para configurarlo sin tocar archivos a mano hay un **asistente guiado** (`python -m keni_metricas.asistente`): te lleva **paso a paso** (te indica en qué `paso X/N` vas) y cierra con un **recap** de lo que dejó configurado y el próximo paso (`verifica con doctor`). Ver [`mcp-metricas/README.md`](mcp-metricas/README.md) y [`docs/credenciales.md`](docs/credenciales.md). El cableado de ejemplo del servidor está en [`.mcp.json`](.mcp.json).

### Comandos disponibles

Además de las skills, el plugin trae **comandos `/`** que envuelven los flujos más comunes para que sean fáciles de descubrir y lanzar (escríbelos con `/` dentro de Claude Code). Son **seguros**: solo lectura o dry-run, nunca publican ni borran nada.

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
