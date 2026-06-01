# Registro de cambios

Todos los cambios relevantes de este proyecto se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto sigue [Versionado Semántico](https://semver.org/lang/es/).

## [No publicado]

### Tablero: menú contextual unificado en lista y feed

- Las vistas **lista** y **feed** del tablero ahora comparten **exactamente las mismas
  opciones** por pieza. Antes la lista tenía un menú de 3 puntos (kebab) y el feed no tenía
  ninguno.
- El menú pasa de **kebab (3 puntos)** a **menú contextual de click derecho** sobre la propia
  tarjeta, con "Generar / mejorar copy con IA" y "Borrar".
- Se **quita "Detalle" del menú**: el click izquierdo en la tarjeta ya abre el detalle
  (comentarios, versiones, aprobación), así que tenerlo también en el menú era redundante.
- Consolidado en un único componente `AccionesPieza` que envuelve la tarjeta de ambas vistas
  (dueño del menú, los diálogos de IA/colaboración y el borrado); la prioridad sigue como
  control en línea de la vista lista.

### Diálogo de confirmación propio (sin pop-ups del navegador)

- La app deja de usar el `window.confirm` (y cualquier diálogo/alerta por defecto del
  navegador): se introduce un **diálogo de confirmación propio** con el estilo de la app
  (shadcn `Dialog`), con API imperativa `confirmar(...)` al estilo de `toast` y un contenedor
  único montado junto al `<Toaster />`. Soporta título, mensaje, textos de botón y modo
  **destructivo** (botón rojo); se cierra con Escape/clic fuera (= cancelar).
- Se migran **todas** las confirmaciones de la app (~20 sitios en Rota, Tareas, Fuentes,
  Webhooks, Sugerencias, Biblioteca, Sistema, comercial, plantillas, hashtags, franjas y el
  panel de colaboración) de `window.confirm` a `confirmar(...)`.

### Explorador S3 (Sistema): borrar un objeto

- El explorador del bucket en **avatar → Sistema** (solo admin) deja de ser estrictamente de
  lectura: ahora cada objeto tiene un **botón de borrar** (en la fila y en la previsualización),
  con **confirmación** antes de eliminar. Nuevo endpoint `POST /api/sistema/s3/borrar {key}`
  (admin) que valida la key (anti-traversal, rechaza prefijos terminados en `/`), confirma
  existencia con `head_object` para dar un **404 honesto** y borra con `delete_object`; 400 key
  inválida, 409 sin S3 configurado, 502 fallo de almacenamiento. Tras borrar se refresca el
  listado y el conteo/uso del bucket. El resto del panel sigue siendo solo lectura.

### Termómetro con descubrimiento en vivo + nuevo Brief de tendencias (MX/Internacional)

- **`termometro-mundial`** integra **descubrimiento con WebSearch/WebFetch** cuando el bloque
  `CONTEXTO` viene escaso o vacío (antes solo trabajaba con notas inyectadas), conservando el
  guardarraíl anti-invención: ahora la regla de oro exige que **todo dato trace a una fuente real
  con su URL**. Añade **ancla de fecha** (`date`) antes de buscar, **mezcla de registros**
  serio/viral con etiqueta por slide, **cruce de ≥2 fuentes** para frescura y una sección
  **"Fuentes:"** con enlaces markdown.
- **Nuevo prompt `brief-tendencias`**: brief matutino de **descubrimiento** (10 temas, 5 México +
  5 internacional, mezcla serio/viral) que se entrega en el chat. Es la versión endurecida del
  flujo de búsqueda en vivo: añade nuestra disciplina anti-invención, **tropicalización MX** de
  los títulos y **marcas de riesgo legal** (⚠️ menores, "presunto", datos personales) antes de
  convertir una tendencia en posteo. Cubre el **pulso nacional**, que el Termómetro (mesa
  internacional, una por región) no daba.
- **Política de emojis coherente**: se retira el «sin emojis» absoluto de `copy-desde-nota` y
  `termometro-mundial`; ahora **manda la plataforma y la marca** (`plataformas.md`): cero en
  UnoTV/Fundación, 0–2 en Instagram/Facebook, naturales en TikTok para las marcas que los
  admitan. El texto-en-imagen (`copy_in`) sigue **siempre sin emojis**.
- **`tropicalizacion.md`**: «Registro por marca» completa las 5 marcas (faltaban **Fundación** y
  **Piso 15**).

### Biblioteca de Prompts en lugar del «sistema de skills»

- El antiguo **sistema de skills** (carpetas `SKILL.md` + `keni.yaml` con formularios, y la
  carpeta `skills-copy/`) se retira y se reemplaza por una **Biblioteca de Prompts**: un
  almacén único de **documentos markdown** editables (`biblioteca.py`, bajo `KENI_BIBLIOTECA_DIR`)
  donde conviven dos `tipo` — `prompt` (lo que se lanza) y `editorial` (la línea editorial por
  marca, que se adjunta al lanzar). El arranque de `claude -p` pasa por un **lanzador NEUTRO**
  (`dominio/generar.py`): compone el prompt autocontenido (cuerpo + línea editorial + contexto
  + redes) y encola el job con un cwd neutro, sin depender de `skills-copy/`.
- **Imagen preservada**: las herramientas del Estudio de imagen (Pillow/outpaint/breaking) viven
  ahora dentro del paquete (`keni_consola/motores/estudio_imagen/`); la generación cruda por API
  (`media.py`) no se ve afectada.
- **Limpieza de huérfanos** tras la migración: se retiran los accesores y vars `KENI_SKILLS_*`
  de `config.py`, el sembrado de skills falso de los tests (`conftest`) y los tipos de skills
  sin uso del frontend (`types.ts`). Se conservan los endpoints neutros `/api/skills/historial*`
  (compat) y la derivación de `skill_disponible` desde la Biblioteca. Sin cambios de comportamiento.

### «Mi cuenta»: configuración de la propia cuenta + auth reorganizada (#130)

- Nueva página **Mi cuenta** (en *Ajustes*, para cualquier rol, también desde el menú de
  cuenta del lateral): consulta tus datos (usuario, rol, fecha de creación y último acceso)
  y **cambia tu propia contraseña** de forma voluntaria, sin pasar por el cambio forzado del
  primer acceso. Reutiliza `POST /api/auth/cambiar-password`: el backend invalida el resto de
  sesiones y re-emite la de este dispositivo, así que **no** hay que volver a iniciar sesión.
- `GET /api/auth/me` ahora incluye `creado` y `ultimo_acceso` (el **login** mantiene su forma
  mínima de 4 campos); los consume la nueva página.
- **Reorganización del dominio de auth**: `auth.py` pasa a ser el paquete `auth/` (`hashing`,
  `usuarios`, `sesiones`, `bootstrap` y `_comun`) con una **fachada** que conserva el contrato
  público intacto. Sin cambios de seguridad ni de esquema: scrypt+salt, comparación en tiempo
  constante, sesiones server-side deslizantes, bloqueo anti fuerza bruta, topes anti-DoS y la
  barrera CSRF siguen igual. La gestión de **otras** cuentas (alta/rol/reset/baja, solo admin)
  no cambia.

### Generar copy desde una URL (#149, ficha F9)

- Nuevo atajo en **Generar copy**: pegas el **enlace** de una nota y obtienes copy por
  plataforma con su veredicto (✅/⚠️/❌), sin copiar el texto a mano. Es un *enhance* de
  Generar copy, no una app nueva: reutiliza la pipeline de `copy-desde-nota` (piezas por
  red + autoguardado de borradores). Solo produce el borrador; **el humano aprueba**.
- **El paso de extracción ocurre en el servidor** (`dominio.extraccion_url`), no en la
  skill (las skills de copy son *dry-run* y no hacen peticiones de red): se valida la URL
  (solo `http`/`https`, guard **SSRF** igual que `api.rss`), se descarga con `httpx` (en
  trozos, con timeout y tope de tamaño) y se extrae el texto legible con la stdlib
  (`html.parser`). El texto extraído se envuelve con un aviso de **CONTENIDO NO
  VERIFICADO** y se pasa a la skill para que marque nombres/cifras/fechas «a verificar».
- **Degradación honesta**: si el enlace es de **video/transmisión** (YouTube, TikTok,
  Instagram, etc.), responde con error y sugiere `clip-a-copy` (transcripción **local**
  con whisper, el audio/video no sale del equipo); igual ante 4xx/5xx, timeout, SSRF o
  páginas sin texto útil. Nunca inventa contenido. A Anthropic solo viaja **texto**.
- **Backend**: nuevo metadato `ingesta` (`""` | `"url"`) en `SkillDef`/`keni.yaml`
  (round-trip en catálogo y opciones), endpoint `POST /api/skills/ejecutar-url` y la skill
  `url-a-copy` como puerta de entrada en el catálogo. **Frontend**: el formulario dinámico
  rinde el campo de enlace y enruta las skills `ingesta === "url"` al nuevo endpoint.

### Normalización de métricas: no sumar magnitudes incomparables (#138)

- La agregación entre plataformas dejaba un **número combinado engañoso**: sumaba
  `visualizaciones` heterogéneas (impresiones de FB/IG/X con reproducciones de
  YouTube/TikTok) como si fueran lo mismo, rellenaba `alcance` con **0** para las
  redes que no lo miden (YouTube/X/TikTok) y calculaba un `engagement_pct` global
  dividiendo interacciones entre esas bases incomparables.
- **Semántica explícita de agregación** (en `schema.py`/`agregador.py`):
  `interacciones` es la única magnitud homogénea → **se suma**; `visualizaciones`
  se suma solo como **total informativo** (el desglose fiable vive en
  `por_plataforma`) y **no** es base del engagement global; `alcance` solo lo
  miden FB/IG y ahora se representa **AUSENTE (`None`)** —nunca 0— en las demás,
  sumándose solo entre las que sí lo miden (y `None` si ninguna lo mide); el
  `engagement_pct` agregado es **`None`** cuando combina bases heterogéneas (no se
  divide sobre bases incomparables) y conserva el suyo con una sola plataforma.
- **Schema**: `MetricaPlataforma.alcance` y `ResumenMetricas.alcance`/`engagement_pct`
  pasan a opcionales (`None` = no medible / no comparable, distinto de 0 real). Los
  consumidores (reporte, dashboard, notificaciones, histórico, picos, tools) muestran
  `n/d` y excluyen lo no comparable en vez de propagar ceros falsos. La fuente
  `muestra` se alinea: ya no inventa alcance para redes que no lo miden.

### Eliminado el lazo de auto-merge/auto-desarrollo del buzón (#132)

- Se **elimina del producto entregable** el lazo de auto-desarrollo del buzón de
  sugerencias (nunca llegó a publicarse). Permitía que la Consola implementara una
  sugerencia con IA y **mergeara/pusheara sola a `main`** (`git push origin HEAD:main`)
  y ejecutara un comando de CI arbitrario configurable por entorno. Embebido en una app
  web local sin autenticación, era una **superficie de RCE/exfiltración fuera de la misión**
  de una herramienta de redes sociales.
- Quitados el dominio `keni_consola.autodesarrollo`, su capa HTTP
  `keni_consola.api.autodesarrollo` (endpoints `/api/autodesarrollo*`), la inyección
  `disparar_autodesarrollo` de `crear_app`, el panel/botones de auto-desarrollo del frontend
  y la documentación asociada. El **buzón de sugerencias** sigue igual: solo recoge ideas
  (todo local, sin push ni ejecución).

### Termómetro mundial (experimental)

- Nueva skill **`termometro-mundial`**: arma el posteo de **galería** diario con las
  **5–8 noticias internacionales** más importantes de la coyuntura, **una por región**.
  **Jerarquiza** las notas que se le pasan por relevancia internacional, impacto y
  frescura, elige el top, lo reparte por región en slides y cierra con el **copy del
  posteo** (tropicalizado a MX) más su auto-verificación. Abre con el bloque
  veredicto + leyenda (✅/⚠️/❌) y carga el contexto editorial; el humano aprueba.
- **Página dedicada en la Consola** (*Termómetro mundial*, grupo *Trabajo*): configura
  número de slides, regiones, hora y marca; pega las noticias (o las **trae del RSS**
  con un clic) y genera en segundo plano, con el progreso en vivo y el resultado listo
  para guardar como publicación. Endpoints `GET/PUT /api/termometro` y
  `POST /api/termometro/generar`, reutilizando el motor de generación de Skills.
- **Generación programada (cron 07:00)**: nuevo CLI **`keni-termometro`** que, sin
  servidor, reúne las noticias de los feeds RSS activos (o de un archivo), corre la
  skill y deja el termómetro en el **historial** para encontrarlo a primera hora. Ver
  `docs/termometro-mundial.md` para la instalación con launchd (macOS) o cron.

### Brief matutino (experimental)

- Nueva skill **`brief-matutino`**: el brief de la mañana para la mesa editorial de
  AMX. Reúne las noticias y tendencias del día (Google News + Google Trends, en
  vivo, vía `buscar.py` — solo stdlib, sin claves) más lo que el community ya vio a
  mano en X/TikTok, las **jerarquiza** por frescura, relevancia y agenda del día
  (mañanera), y **sugiere un formato por pieza** (tuit / imagen / carrusel / video).
  Es un brief para **decidir qué cubrir**, no copy final.
- Abre con el bloque estado + leyenda (✅/⚠️/❌) y marca riesgo legal por pieza.
  Disponible también en la **Consola** (grupo *experimentales*) vía `keni.yaml`.

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
