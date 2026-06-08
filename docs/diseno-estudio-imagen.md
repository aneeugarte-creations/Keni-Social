# Estudio de Diseño de Imagen (superficie de primera clase)

- **Fecha origen:** 2026-05-31 · **Estado: EN PRODUCCIÓN.** El Estudio es la superficie de
  imagen vigente.
- **Qué es:** el Estudio es una superficie propia de la Consola para crear/editar el arte de cada
  pieza. Su motor vive en `consola/src/keni_consola/motores/estudio_imagen/`
  (`editar.py`, `expandir.py`, `retocar.py`, `generar.py`, `spec_plantilla.py`, `render_node/`,
  `marcas.json`), el dominio en `dominio/estudio_imagen.py` (compone prompt, corre los motores por
  subproceso, importa salidas), la API en `api/imagenes.py`
  (`POST /api/imagenes/{generar,editar,expandir,retocar,componer,set,revisar}` + `GET .../matriz`),
  y la UI integrada en el editor de imagen (`frontend/src/components/media/EditorImagen.tsx` +
  `frontend/src/editor/PanelIA.tsx`), no como página/ruta propia. "Usar en la pieza" reutiliza el
  seam `PUT /api/publicaciones/{id}` (`imagen`);
  "Guardar en texto" usa `/api/catalogo-media/catalogar`. La revisión legal (`POST
  /api/imagenes/revisar`, `claude -p`) está implementada como cierre opcional; la aprobación sigue
  siendo un gate humano antes de "Usar en la pieza".
- **Editor visual de plantillas por marca:** además del motor determinista/generativo, el Estudio
  tiene un editor de plantillas de marca (`api/plantillas_marca.py` + `keni_consola/plantillas_marca.py`):
  el equipo diseña y guarda un *spec* por marca (logo, pleca, titular, geometría por lienzo) que el
  motor estampa con `render_node/` (renderizador Node). `componer`/`set`/`marca_tiene_plantilla`
  (`dominio/estudio_imagen.py:88`) materializan ese spec sobre la foto.
- **Reemplazó** al documento histórico `docs/estudio-imagen.md` (ya borrado), que describía la
  arquitectura "enrutador + 2 motores + revisor". El motor sigue el patrón de `verifica-video`
  (`keni_consola/motores/verifica_video/` + `api/verificaciones.py`): un motor propio con su
  API de primera clase.

---

## 0. TL;DR

1. Conviven **dos caminos de imagen**, ambos dentro del paquete: (a) el camino **directo HTTP**
   (`POST /api/media/generar` → `media.generar_imagen` → proveedor OpenRouter → `.png` → almacén media),
   que usa el `EditorImagen.tsx` de cada publicación para el caso simple; y (b) el **Estudio**
   (`/api/imagenes/*` + motor `motores/estudio_imagen/`), que aporta recorte/extensión/retoque/
   composición de marca + variantes + revisión legal. El camino directo no se rompió: el Estudio es el
   "modo avanzado" sobre las mismas piezas.
2. La generación cruda por API vive en `keni_consola/media.py`; las herramientas del motor
   (`editar.py`, `expandir.py`, `retocar.py`, `generar.py`, `spec_plantilla.py`, `render_node/`) viven
   en `keni_consola/motores/estudio_imagen/`.
3. El **modelo de datos**: una publicación (`publicacion`) tiene un campo `imagen` (nombre de objeto en
   el almacén media) + `imagen_url`. El arte "pertenece a la pieza" por ese campo. El Estudio produce un
   objeto media y lo asocia a la pieza por ese mismo seam.
4. La **Texto** aporta: los **prompts de imagen** como documentos `tipo: prompt` y la **línea
   editorial / dirección de arte por marca** como documentos `tipo: editorial, clase: marca/voz`. El
   Estudio los **adjunta** al componer el prompt, igual que `dominio/generar.py` hace con el copy.
5. **Dirección de arte por marca = dos vías:** el prompt generativo se angula con la dirección de arte
   editable en la Texto; y para la identidad exacta (logo + pleca + titular) hay un **editor visual
   de plantillas por marca** cuyo *spec* estampa el renderizador `render_node/` de forma determinista
   (`componer`/`set`/`marca_tiene_plantilla`).

---

## 1. Cómo funciona (pipeline real, con rutas y líneas)

> **Nota histórica:** §1.B describe el camino **vía motor de skills** tal como era cuando el Estudio
> aún vivía como skill `estudio-imagen`. Ese motor se relocalizó a
> `keni_consola/motores/estudio_imagen/` y hoy se invoca desde `api/imagenes.py` (no desde `claude -p`
> para las operaciones deterministas). Se conserva la descripción porque las capacidades (recorte,
> extensión, retoque, composición de marca, revisión) siguen siendo las mismas; solo cambió cómo se
> invoca el motor. El camino directo de §1.A no cambió.

### 1.A — Camino DIRECTO por API (el que usa la consola para "generar/adjuntar imagen a una pieza")

Es el camino vivo y el que NO depende de skills. Es síncrono en HTTP solo para crear el registro; la generación corre en background.

```
prompt (texto)
  → POST /api/media/generar            consola/src/keni_consola/api/media.py:58  (generar)
  → media.proveedor_configurado()      api/media.py:69  → media.py:293
  → generaciones.crear({tipo:"imagen"})api/media.py:86   → generaciones.py:235 (crear)
  → generaciones.lanzar_job_imagen()   api/media.py:96   → generaciones.py:692
        (hilo simple, sin Popen; callable _generar)
        _generar():                    api/media.py:79
          → media.generar_imagen(prompt)            media.py:420
              → _PROVEEDOR == _proveedor_openrouter media.py:351/417
                  POST https://openrouter.ai/api/v1/chat/completions
                  headers Bearer <clave>, modalities:["image","text"]
                  clave: media._clave_imagen() → secretos.obtener_clave_imagen()  media.py:282, secretos.py:176
                  modelo: media._modelo()  (secretos > OPENROUTER_IMAGE_MODEL > "openai/gpt-5-image-mini")  media.py:298
                  respuesta: base64 → bytes                                       media.py:399-403
          → media.guardar_bytes(crudos, ext="png")  media.py:234
              → almacen_media.guardar_objeto()       almacen_media.py:139  (disco o S3)
          → return {id: <uuid>.png, url: "/api/media/<uuid>.png"}
  → registro de generación pasa a "completado" con resultado={id,url}  generaciones.py:706-709
Frontend:
  EditorImagen.tsx genera vía api.generarMedia → /media/generar  (lib/api.ts:820)
     y SONDEA GET /api/generaciones/{id} con useGeneracion()      components/media/EditorImagen.tsx:64-99
  Al completar: onCambio(r.id, r.url) → el padre guarda `imagen` en la pieza
Preview / servido:
  GET /api/media/{nombre}   api/media.py:45 (servir) → media.leer_media → almacen_media.leer_objeto (anti-traversal / S3)
```

Puntos clave:
- El almacén de media es **backend-neutral**: disco local (`KENI_CONSOLA_MEDIA`, def. bajo la raíz de estado) o S3/Garage si está cableado (`almacen_media.py:32` `s3_activo`). El nombre del objeto SIEMPRE lo genera el servidor (uuid+ext), nunca el cliente (`media.py:224`, `almacen_media.py:82`).
- `lanzar_job_imagen` (`generaciones.py:692`) es un **runner genérico de un callable en un hilo** — NO es específico de imagen: ya lo reusa `api/verificaciones.py:118`. El Estudio lo reutiliza tal cual para cada operación que llame a un proveedor/herramienta.
- La clave del proveedor es **una sola fuente de verdad**: `secretos.toml` (`0600`, gestionado por la UI) con fallback a entorno (`KENI_IMAGEN_API_KEY`/`OPENROUTER_API_KEY`/`OPENAI_API_KEY`); ver `secretos.py:162-201`. El modelo se elige de la lista curada `media.MODELOS_IMAGEN` (`media.py:85-105`).

### 1.B — Capacidades del motor (origen: skill `estudio-imagen`, hoy relocalizado)

Estas son las capacidades que el camino directo NO da: recortar a formato, comprimir a un peso, extender fondo, componer marca/breaking, outpainting fiel, retoque por instrucción y la **revisión legal/editorial**. El diagrama de abajo refleja cómo corría como skill (`claude -p`); hoy las deterministas las invoca `api/imagenes.py` por subproceso del motor (ver §3.4).

```
formulario de skill (imagen subida + petición + formato + peso + ajuste)
  → POST /api/skills/ejecutar-archivo   api/skills_generacion_api.py:347
  → guarda la subida en un temporal      _guardar_subida_segura  api/skills_generacion_api.py:123
  → encola un job claude (cwd = raíz del repo, --add-dir <temporal>)
        generaciones.encolar_job_claude → worker → lanzar_job_claude  generaciones.py:400 / 444
        _argv_claude: claude -p <prompt> stream-json …               generaciones.py:341
        _entorno_skill: exporta la clave de imagen del almacén al     generaciones.py:375
            entorno del subproceso (proveedor → OPENROUTER/OPENAI/GEMINI_API_KEY)
  → claude carga la skill estudio-imagen (SKILL.md enruta) y ejecuta UNA de:
        editar.py recortar|redimensionar|comprimir|extender|placa   (Pillow, determinista)
        expandir.py   (outpainting de fondo vía OpenRouter, re-compone el sujeto intacto)
        generar.py    (ilustración/fondo vía OpenRouter; modo sin-key = dirección de arte)
        ../breaking-express/componer.py  (logo + pleca + breaking)
     cada script escribe .png en el temporal e imprime un bloque "DATOS <json>"  editar.py:689
  → post-procesado `procesar`: importa los .png al almacén media     media.importar_imagen  media.py:248
        (por eso el temporal se borra AL FINAL, tras `procesar`)      generaciones.py:504-509, 580-583
  → la skill CIERRA con la revisión legal/editorial (revisa-imagen): lee
        contexto-editorial/reglas-legales.md, marca ✅/⚠️/❌            SKILL.md:54
Frontend: este camino se muestra en la pestaña "Imágenes" de Generación
  Generacion.tsx (toggle Copy/Imágenes) → FlujoGeneracion con filtroImagen  pages/Generacion.tsx:91-103
  esSkillDeImagen filtra el catálogo por `media: true`                       pages/copy/dynamico
```

Puntos clave de 1.B que el Estudio debe **preservar** como capacidades:
- **Deterministas (Pillow, gratis, exactas):** recortar a 9:16/4:5/1:1/16:9, "las 3 medidas", redimensionar, comprimir a un peso objetivo, extender fondo uniforme, placa/tarjeta de texto en marca (`editar.py`, `FORMATOS = {vertical:(1080,1920), feed:(1080,1350), cuadrado:(1080,1080), horizontal:(1920,1080)}`).
- **Generativas (IA por API, OpenRouter):** ilustración/fondo (`generar.py`) y outpainting de fondo que **re-compone la foto original sobre su región exacta** (`expandir.py`, sujeto intacto pixel a pixel).
- **Dirección de arte por marca** (`generar.py:ESTILO_MARCA`, y los skills `diseno-unotv`/`diseno-clarosports` con `guia-diseno.md` + `plantillas-prompt.md`).
- **Revisión legal/editorial** como cierre (bandera/escudo, menores, datos personales, derechos, texto).

### 1.C — Texto de medios (catálogo interno, ya existe)

`api/catalogo_media.py` cataloga objetos del almacén con metadatos editoriales y etiquetas (`GET/POST /api/catalogo-media`, `POST /api/catalogo-media/catalogar` para catalogar un objeto YA generado). Es la "cosecha de imágenes": el activo aprobado, reutilizable, etiquetable. El Estudio escribe aquí cuando el usuario marca una variante como reutilizable.

---

## 2. Qué se reutiliza y de dónde vino el motor

### Se reutiliza TAL CUAL (ya vive en el paquete)
- `keni_consola/media.py` — generación cruda por API, validación, `guardar_bytes`, `importar_imagen`, `MODELOS_IMAGEN`, `_proveedor_openrouter` (mockeable). **Es el corazón generativo y se queda.**
- `keni_consola/almacen_media.py` — almacén de objetos disco/S3, anti-traversal. **Sin cambios.**
- `keni_consola/secretos.py` — clave/proveedor/modelo de imagen, `0600`. **Sin cambios.**
- `keni_consola/generaciones.py:lanzar_job_imagen` — runner genérico de un callable en hilo + sondeo. **Es el motor de ejecución del Estudio.**
- `api/media.py` (`/api/media`, `/api/media/{nombre}`, `/api/media/generar`) — subir, servir, generar. **Se queda viva** (es el camino que no debe romperse).
- `api/catalogo_media.py` (`/api/catalogo-media`) — cosecha/catálogo. **Se queda.**
- `EditorImagen.tsx` — sigue funcionando contra `/api/media/generar`. El Estudio es un "modo avanzado"; el editor inline simple no desaparece.

### Motor en `keni_consola/motores/estudio_imagen/` (hecho)
Patrón idéntico a `motores/verifica_video/` (un `__init__.py` vacío + los scripts del motor, invocados por subproceso desde una API de primera clase). La tabla documenta la **procedencia** de cada motor (el origen ya no existe). El motor sumó además `retocar.py` (retoque generativo por instrucción), `spec_plantilla.py` y `render_node/` (composición de plantilla de marca), que no estaban en el origen.

| Origen (ya borrado) | Destino | Naturaleza |
|---|---|---|
| `estudio-imagen/editar.py` | `keni_consola/motores/estudio_imagen/editar.py` | Determinista (Pillow): recortar/redimensionar/comprimir/extender/placa |
| `estudio-imagen/expandir.py` | `keni_consola/motores/estudio_imagen/expandir.py` | Generativo (outpainting fiel vía OpenRouter) |
| `estudio-imagen/generar.py` | `keni_consola/motores/estudio_imagen/generar.py` | Generativo (ilustración/fondo). **Solapa con `media.py`** — ver nota |
| `estudio-imagen/test_editar.py`, `test_expandir.py` | `consola/tests/motores/test_editar.py`, `test_expandir.py` | Tests Pillow (proveedor IA mockeado) |
| `breaking-express/componer.py` (+ `marcas.json`, assets) | `keni_consola/motores/estudio_imagen/componer.py` (+ assets) | Determinista: logo + pleca + breaking |

Nota sobre `generar.py` vs `media.py`: ambos llaman a OpenRouter `chat/completions` con `modalities:["image","text"]`. La operación "generar variante" del Estudio pasa por `media.generar_imagen()` (vía `dominio/estudio_imagen.generar_variante`): fuente única de proveedor/clave/modelo/log/anti-SSRF, un solo punto de red mockeable en tests. La dirección de arte de marca se compone desde la Texto (§3.2/§3.6). El script `generar.py` conserva su propia ruta HTTP (`generar_con_openrouter`) y su `ESTILO_MARCA`/`construir_prompt` como CLI de respaldo (modo sin-key → dirección de arte), pero el camino del Estudio no la usa para producir variantes.

### Se RECONCEPTUALIZA como documentos de la Texto (no se relocaliza como código)
- `diseno-unotv/guia-diseno.md`, `plantillas-prompt.md` → `editorial/marcas/unotv` (clase `marca`, `marcas:[unotv]`).
- `diseno-clarosports/guia-diseno.md`, `plantillas-prompt.md` → `editorial/marcas/claro-sports`.
- Las reglas legales de `revisa-imagen` (`contexto-editorial/reglas-legales.md`) → `editorial/reglas/imagen` (clase `reglas`, global).
- Prompts de imagen reutilizables → `prompt/imagen/<slug>` (p. ej. `prompt/imagen/ilustracion-fondo`).

---

## 3. Diseño del ESTUDIO DE IMAGEN como superficie propia

### 3.1 Modelo: el arte pertenece a la pieza
- Una imagen es un **objeto del almacén media** (`<uuid>.png`). El vínculo con la pieza ya existe: `publicacion.imagen` + `imagen_url` (`dominio/publicaciones.py:140,159`; handoff A→C `crear_borrador(... imagen=...)`).
- El Estudio se **abre desde una pieza** de la lista dinámica (radar/RSS/green/obligatorios) o desde Parrilla/Publicaciones. Recibe contexto de la pieza: `copy` (el texto ya generado), `marca`, `red` (→ formato sugerido: feed 4:5, vertical 9:16…), `titulo`.
- El Estudio mantiene una **sesión efímera** con N candidatas (variantes + ediciones). Persistir la sesión completa es opcional; lo durable es: (a) los objetos media generados (en el almacén), (b) la elección final (escrita en `publicacion.imagen`), y (c) opcionalmente la candidata marcada "reutilizable" (catalogada en `catalogo-media`). Reutilizar el registro de generación (`generaciones.py`, efímero+sondeable) como contenedor de cada operación encaja perfecto: cada "generar/editar variante" es un job tipo `imagen` que el front sondea.

### 3.2 De dónde sale el prompt de imagen
La operación generativa del Estudio compone el prompt **igual que `dominio/generar.py` compone el copy** (`componer()` = cuerpo del prompt + editorial adjunta + contexto):

```
prompt_imagen_final =
    <prompt base de imagen>            (Texto: prompt/imagen/<slug>, editable)
  + <dirección de arte de la marca>    (Texto: editorial/marcas/<marca>, auto-adjunto por marca)
  + <copy / titular de la pieza>       (contexto: lo que dice la publicación)
  + <formato/aspecto>                  (derivado de la red destino: 4:5, 9:16, 1:1, 16:9)
```

Esto sustituye al hard-code `ESTILO_MARCA` de `generar.py:36-40`: el estilo de marca pasa a ser un documento editable por el equipo, no una constante en código.

### 3.3 UX (lienzo + prompt + variantes + editar + elegir final)
Una página `Estudio.tsx` (o un panel/drawer abrible desde una pieza), con tres zonas:
- **Origen:** foto subida (`POST /api/media`) o "desde cero" (solo generativo). Muestra el copy de la pieza como contexto.
- **Lienzo + acciones:**
  - **Generar variantes** (generativo): prompt de imagen + marca + formato → lanza N jobs `imagen`, muestra una rejilla de candidatas conforme completan (sondeo `useGeneracion`).
  - **Editar** una candidata (determinista, sin coste): recortar a formato / las 3 medidas / redimensionar / comprimir a peso / extender fondo uniforme / placa / breaking. Cada acción es un job que corre el motor `estudio_imagen` por subproceso y re-importa el .png.
  - **Expandir** (generativo, fiel): outpainting cuando el fondo no es uniforme; re-compone el sujeto intacto.
  - **Retocar** (generativo, por instrucción): edita la imagen según una instrucción en lenguaje natural (`retocar.py`, image-to-image vía OpenRouter).
  - **Componer plantilla de marca / set de formatos** (determinista): estampa la identidad de marca (logo + pleca + titular) según el *spec* de la marca (`componer`/`set`, renderizador `render_node/`).
  - **Revisar** (opcional, cierre): pasa la candidata por la revisión legal/editorial (ver §3.5).
- **Elegir final:** botón "Usar en la pieza" → escribe `publicacion.imagen = <objeto>`; botón "Guardar en texto" → `POST /api/catalogo-media/catalogar`.

Encaje con la lista dinámica: a las 9am el equipo recorre la lista; cada pieza con copy ya generado ofrece "Abrir en Estudio". El Estudio devuelve la pieza con su arte asociado, lista para revisar/aprobar/programar. El editor inline simple (`EditorImagen.tsx`) sigue para el caso trivial "adjunta o describe una imagen"; el Estudio es para el caso rico (variantes + edición + marca + revisión).

### 3.4 API (`/api/imagenes/...`)
El módulo `api/imagenes.py` (auto-descubierto por `api/__init__.py`, exporta `RUTAS`) reusa
`generaciones.lanzar_job_imagen` + el almacén media. Cada endpoint que "produce píxeles" responde de
inmediato con un registro de generación y el front sondea `GET /api/generaciones/{id}`.

| Endpoint | Hace | Reutiliza |
|---|---|---|
| `GET  /api/imagenes/matriz` | lista lienzos canónicos (aspecto/medida) + las plantillas de marca disponibles | `formatos_red`, `plantillas_marca` |
| `POST /api/imagenes/generar` | genera N variantes desde prompt+marca+formato (compone prompt con `estudio_imagen.componer_prompt` + la Texto) | `media.generar_imagen`, `lanzar_job_imagen`, `texto.cuerpo_efectivo` + `editoriales_de_marca` |
| `POST /api/imagenes/editar` | operación determinista (recortar/redimensionar/comprimir/extender/placa) sobre un objeto media | motor `motores/estudio_imagen/editar.py` por subproceso (patrón `verificaciones.analizar`), `media.importar_imagen` |
| `POST /api/imagenes/expandir` | outpainting fiel a un formato | `motores/estudio_imagen/expandir.py`, `lanzar_job_imagen` |
| `POST /api/imagenes/retocar` | retoque generativo por instrucción (image-to-image) | `motores/estudio_imagen/retocar.py` |
| `POST /api/imagenes/componer` | estampa la plantilla de marca (logo + pleca + titular) sobre una foto | `spec_plantilla.py` + `render_node/`, `plantillas_marca` |
| `POST /api/imagenes/set` | genera el set de formatos de una red estampando la identidad de marca | `estudio_imagen.generar_set_formatos`, `formatos_red` |
| `POST /api/imagenes/revisar` | revisión legal/editorial de un objeto media (cierre opcional, gate humano) | `claude -p` con `editorial/reglas/imagen` adjunta |

"Usar en la pieza" no es endpoint propio: reutiliza `PUT /api/publicaciones/{id}` (`imagen`).
Subir/servir/cosechar siguen en `/api/media` y `/api/catalogo-media` (sin duplicar). `/api/media/generar` se mantiene como caso simple (1 variante) para no romper `EditorImagen.tsx`.

Las operaciones deterministas (`editar`) NO necesitan `claude`: corren el motor con el python de la consola (`sys.executable motores/estudio_imagen/editar.py …`), exactamente como `api/verificaciones.py:_ruta_motor`/`analizar` corre `analiza-video.py`. La clave de imagen para `expandir`/`generar` se transporta al subproceso reutilizando el mapeo de `generaciones._entorno_skill` (proveedor → `OPENROUTER/OPENAI/GEMINI_API_KEY`).

### 3.5 Revisión legal/editorial
Implementada como **job `claude` puntual**: `POST /api/imagenes/revisar` lanza un `claude -p` con la imagen vía `--add-dir` y la regla `editorial/reglas/imagen` adjunta en el prompt; devuelve el checklist ✅/⚠️/❌ (`dominio/estudio_imagen.revisar`, reutiliza `encolar_job_claude`/`_argv_claude`). La revisión NO bloquea la generación: es el cierre antes de "Usar en la pieza" (gate humano). Pendiente a medio plazo: unificarla con el QA editorial existente (`api/qa_editorial.py`) para no fragmentar la verificación.

### 3.6 Relación con la Texto
- **Prompts de imagen** = documentos `tipo: prompt` (p. ej. `prompt/imagen/ilustracion-fondo`). El Estudio los carga con `texto.cuerpo_efectivo(id)` (mismo seam que `dominio/generar.py:180`).
- **Dirección de arte por marca** = documentos `tipo: editorial, clase: marca` (`editorial/marcas/unotv`, `editorial/marcas/claro-sports`), auto-adjuntos por marca con `texto.editoriales_de_marca(marca)` (igual que el copy). Editables por el equipo; sustituyen al `ESTILO_MARCA` hard-coded.
- **Reglas legales de imagen** = `editorial/reglas/imagen` (clase `reglas`, global), adjunta al job de revisión.
- Estos documentos viajan en la **semilla** de la Texto (`keni_consola/texto_semilla/{prompt,editorial}/`), igual que ya viajan los prompts de copy.

---

## 4. Estado de implementación (todo construido)

La migración descrita por este documento ya se completó. Resumen del estado actual:

- **Motor relocalizado** a `keni_consola/motores/estudio_imagen/` (`editar.py`, `expandir.py`,
  `retocar.py`, `generar.py`, `spec_plantilla.py`, `render_node/`, `marcas.json`), con tests Pillow en
  el CI del back. El origen ya no existe (el sistema de skills se retiró).
- **API de primera clase** `api/imagenes.py` con `generar/editar/expandir/retocar/componer/set/revisar`
  + `matriz` (ver §3.4).
- **UI** integrada en el editor de imagen (`frontend/src/components/media/EditorImagen.tsx` +
  `frontend/src/editor/PanelIA.tsx`), no como página/ruta propia; "Usar en la pieza"
  (`PUT /api/publicaciones/{id}`) y "Guardar en texto" (`/api/catalogo-media/catalogar`).
- **Texto cableada:** el prompt generativo compone con `texto.cuerpo_efectivo` +
  `editoriales_de_marca` (sustituye el `ESTILO_MARCA` hard-coded); las reglas legales van como
  `editorial/reglas/imagen` adjuntas a la revisión.
- **Editor visual de plantillas por marca** (`api/plantillas_marca.py` + `keni_consola/plantillas_marca.py`):
  el equipo diseña el *spec* de marca; `render_node/` lo estampa.
- El camino directo `/api/media/generar` + `EditorImagen.tsx` sigue intacto.

---

## 5. Riesgos y dependencias

- **Clave del proveedor (OpenRouter):** fuente única `secretos.toml` (`0600`) con fallback a entorno. Sin clave, lo generativo degrada a "dirección de arte" (prompt para herramienta externa) como hoy (`generar.py:salida_sin_key`). Riesgo: que el subproceso del motor no reciba la clave → mitigado reusando `_entorno_skill` (`generaciones.py:375`). NUNCA loguear la clave (ya respetado en `media.py`/`secretos.py`).
- **Pillow en el back:** con el motor en el paquete, **Pillow es dependencia del back** (del worker que ejecuta los motores deterministas). Asegurar que el entorno de ejecución y de test lo tiene.
- **ffmpeg / tesseract / yt-dlp:** NO los necesita imagen (son del motor de video `verifica_video`). Imagen solo necesita Pillow + httpx. No introducir esa dependencia aquí.
- **Tamaño de media:** límite vigente 15 MB por imagen (`media.LIMITE_IMAGEN`). Generar N variantes multiplica el almacenamiento; sin recolección, el almacén crece. Mitigar: las variantes NO elegidas son objetos huérfanos — definir una política (TTL/limpieza de objetos no referenciados por ninguna pieza ni catalogados en texto). Hoy `catalogo_media.borrar` ya borra el binario al descatalogar; falta un GC de huérfanos del Estudio.
- **Coste por imagen:** cada variante generativa cuesta. El determinista (recortar/comprimir/extender uniforme/placa) es gratis y debe ser el camino por defecto cuando aplica. La UI debe empujar a lo determinista y limitar el nº de variantes generativas por defecto.
- **S3/Garage:** en hosted la media va a bucket; el motor determinista escribe en un **temporal local** y `media.importar_imagen` lo sube al backend activo. Verificar que el subproceso del motor tiene acceso al temporal (patrón `--add-dir` / `tempfile.mkdtemp` de `verificaciones.analizar`).
- **Outpainting fiel:** `expandir.py` re-compone el sujeto pixel a pixel — es la línea roja editorial: la IA no inventa sobre el sujeto de una foto real. Conservar esa garantía en cualquier cambio del motor.

---

## 6. Archivos críticos (mapa del código)

- `consola/src/keni_consola/api/imagenes.py` — la API del Estudio (endpoints de §3.4).
- `consola/src/keni_consola/dominio/estudio_imagen.py` — compone el prompt, corre los motores por subproceso, importa salidas; `componer`/`set`/`marca_tiene_plantilla`/`revisar`.
- `consola/src/keni_consola/motores/estudio_imagen/` — los motores: `editar.py`, `expandir.py`, `retocar.py`, `generar.py`, `spec_plantilla.py`, `render_node/`, `marcas.json`.
- `consola/src/keni_consola/api/plantillas_marca.py` + `keni_consola/plantillas_marca.py` — editor visual de plantillas de marca (el *spec* que estampa `render_node/`).
- `consola/src/keni_consola/api/verificaciones.py` — el patrón "motor en `motores/` + API que lo corre por subproceso y reusa `lanzar_job_imagen`" que sigue `api/imagenes.py`.
- `consola/src/keni_consola/media.py` — corazón generativo (proveedor, `generar_imagen`, `guardar_bytes`, `importar_imagen`, `MODELOS_IMAGEN`).
- `consola/src/keni_consola/generaciones.py` — `lanzar_job_imagen` (runner del Estudio) y `_entorno_skill`/`_argv_claude` (clave al subproceso, `--add-dir` para la revisión).
- `consola/src/keni_consola/dominio/generar.py` — patrón de composición de prompt (`componer()` = prompt + editorial + contexto) que replica el prompt de imagen con la Texto.
- `consola/frontend/src/components/media/EditorImagen.tsx` + `consola/frontend/src/editor/PanelIA.tsx` — la UI del Estudio, integrada en el editor de imagen (no hay página/ruta propia).
