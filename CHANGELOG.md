# Registro de cambios

Todos los cambios relevantes de este proyecto se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto sigue [Versionado Semántico](https://semver.org/lang/es/).

## [No publicado]

### Verificación de procedencia de video (experimental)

- Nueva skill **`verifica-video`**: pega el enlace de un video viral (X, TikTok,
  Facebook, Instagram, YouTube o un archivo local) y dice si **parece nuevo o si
  ya circulaba desde antes** (material reciclado / re-viralizado), antes de
  decidir si retomarlo. Resuelve el "me como 20 minutos comprobando si el video
  es de verdad de hoy o salió hace años".
- Motor local y **gratis** (`analiza-video.py`, solo stdlib + binarios): fecha de
  subida con `yt-dlp`, fotogramas con `ffmpeg`, lectura de **fechas/años en
  pantalla** (timestamp de cámara, marcas de agua) con OCR (`tesseract`), y
  **enlaces de búsqueda inversa listos para un clic** (TinEye ordenado por más
  antiguo, Google Lens, Yandex, Bing) sobre la miniatura pública. Consulta la
  Google Fact Check API si hay `GOOGLE_FACTCHECK_API_KEY` (opcional).
- **Privacidad por diseño:** no sube los fotogramas a ningún servicio ni scrapea
  buscadores; la búsqueda inversa la confirma el humano con un clic. Abre con el
  bloque veredicto + leyenda como el resto de skills y **el humano decide**.
- Disponible también en la **Consola** (grupo *experimentales*) vía `keni.yaml`.

### Moderación en vivo (experimental)

- Nueva skill **`modera-en-vivo`**: modera un chat/comentarios **en vivo** de YouTube para
  eventos como **México Siglo XXI** de la Fundación. Clasifica cada mensaje (ok / pregunta /
  grosería / tóxico-acoso / spam-bot / riesgo legal o sensible) y **propone** una acción
  (dejar pasar, ocultar/borrar, expulsar, escalar) con veredicto ✅/⚠️/❌, y **separa las
  preguntas legítimas en una bandeja** para la skill `responde-comentarios` — el mismo sistema
  modera el ruido y contesta lo legítimo. Conservadora con lo legítimo (ante la duda, revisar,
  nunca autoborrar) y prudente con datos personales / menores (reglas legales).
- Feed de muestra **`ejemplos/chat-en-vivo-mexico-siglo-xxi.md`** (mezcla de legítimos,
  preguntas, groserías, spam/bots y casos sensibles) para probar la skill sin tocar la red.
- **Dry-run, como el resto de la suite:** no borra, no expulsa, no llama a la API de YouTube.
  La moderación real (leer/borrar/expulsar vía API, OAuth del canal y ampliación de cuota)
  queda como fase futura, igual que la publicación real.

## [0.2.0] - 2026-05-24

Primera versión presentable como producto: el flujo completo de producción de
contenido (nota/cable/clip → copy publicable y verificado) más métricas-insight
multi-marca, empaquetado como plugin de Claude Code.

> **Nota.** La publicación real en las plataformas y los datos reales por
> plataforma (Meta, TikTok, X, YouTube) están pausados por gating externo (App
> Review, auditorías y costes de API). El código de los adaptadores ya existe y
> degrada con elegancia; lo que está bloqueado es el permiso para encenderlo. El
> dashboard y las skills funcionan hoy con una fuente de datos de muestra.

### Copy + auto-verificación

- Generación de copy desde texto (una nota o varios cables) con una variante por
  plataforma (X, Instagram, Facebook, TikTok, YouTube), conteo de caracteres y la
  voz editorial de cada marca.
- Cada copy abre con un **veredicto en semáforo** y su leyenda (🟢 listo /
  🟡 revísalo / 🔴 no publicar) y cierra con la **auto-verificación** que marca
  fechas, nombres, cifras y reglas legales.

### Clip → copy local

- De un video o audio a copy por plataforma **más las mejores citas con marca de
  tiempo**, con transcripción 100% local vía whisper.cpp (el audio no sale de la
  máquina).
- El texto de transcripción se trata como **no verificado** y se marca para
  confirmar contra el audio.

### MCP de métricas + dashboard

- Servidor MCP de métricas multi-marca / multi-plataforma: alcance, engagement,
  mejores piezas, comparación de periodos, tendencia histórica y picos.
- Histórico propio en SQLite local y **fuente de datos de muestra** representativa
  de las cinco marcas para demostrar sin depender de credenciales.
- **Dashboard HTML autocontenido** (sin JS, sin CDN, sin red): KPIs, ranking por
  marca, sparklines, vista de engagement (north-star) y picos; imprimible /
  apto para PDF.
- Notificador proactivo de picos a webhook (seguro por defecto) y comando
  `doctor` de autodiagnóstico del entorno.

### Editorial es-MX

- Tropicalización mexicana enriquecida y **detector de españolismos**.
- Reglas legales y especificaciones por plataforma incorporadas a la
  verificación del copy.
- Corpus editorial versionado: cinco marcas con línea editorial, voz personal por
  persona y reglas de tropicalización.

### UX

- Veredicto en semáforo y leyenda al inicio de cada skill.
- Nombres de marca legibles en CLI y dashboard; picos top-N en reporte y digest.
- `doctor` con credenciales agrupadas en una línea y siguiente paso accionable.
- Asistente de onboarding guiado para `config.toml` con progreso (paso X/N) y
  recap final con el próximo paso.
- Comandos `/` (slash commands) que envuelven los flujos comunes.

### Skills

- Nueva skill `responde-comentarios` (community management con verificación).
- Skill `revisa-imagen` para revisión legal de artes antes de publicar.
- Flujo de aprobación de publicación punta-a-punta en **dry-run por defecto**
  (preview → cola → dry-run), sin publicar ni subir media.

### Calidad y tests

- ~370 pruebas automatizadas del MCP (cobertura de las 7 tools, adaptadores,
  agregador, dashboard, doctor, histórico, picos, notificaciones, publicación,
  reporte y transporte) más chequeos estáticos de las skills.
- Integración continua en verde en cada cambio.

### Documentación

- Estado del producto, resumen para dirección, análisis competitivo y roadmap de
  UX/UI.
- Guía del community manager, manual de operación, primeros pasos (quickstart),
  flujo de datos / privacidad y despliegue local y alojado.

### Empaquetado

- Distribución como plugin de Claude Code (instalación en dos comandos, sin
  permisos de administrador) mediante manifiestos `plugin.json` y
  `marketplace.json`.

### Changed

- Capa de render consolidada en `formato.py` (DRY) y type hints en los CLIs y
  módulos del MCP.

### Fixed

- `doctor` y los CLIs ya no muestran tracebacks ante config corrupto o ausente.
- Extracción portable de la línea del error TOML (Python 3.11–3.14).
- Nombres de marca legibles en la sección de alertas (picos) del dashboard.

[0.2.0]: https://github.com/kenitech-io/keni-social/releases/tag/v0.2.0
