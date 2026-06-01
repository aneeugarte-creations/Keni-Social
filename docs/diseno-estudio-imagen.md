# Diseño — Estudio de Diseño de Imagen (superficie de primera clase)

- **Fecha:** 2026-05-31 · **Estado:** IMPLEMENTADO (F1–F3; F4 ya N/A: la skill estaba borrada) · **Rama:** `feat/estudio-imagen`
- **Estado de implementación (2026-05-31):** construido el Estudio como superficie propia: dominio `dominio/estudio_imagen.py` (componer prompt + correr los motores relocalizados por subproceso + importar salidas), API `api/imagenes.py` (`POST /api/imagenes/{generar,editar,expandir}`), página `frontend/src/pages/Estudio.tsx` (ruta `/estudio`, nav), enlace "Abrir en Estudio" desde `EditorImagen`, y semilla de Biblioteca (`prompt/imagen/ilustracion-fondo`, `editorial/reglas/imagen`). "Usar en la pieza" reutiliza el seam existente `PUT /api/publicaciones/{id}` (`imagen`); "Guardar en biblioteca" usa `/api/biblioteca-media/catalogar`. **Diferido:** `POST /api/imagenes/revisar` (revisión legal vía `claude -p`) — se difiere al QA editorial existente (opción §3.5.b); la revisión sigue siendo un gate humano antes de "Usar en la pieza".
- **Para:** retirar `skills-copy/.claude/skills/estudio-imagen` (que se va a borrar con el resto del sistema de skills) y reemplazarlo por un **Estudio de Diseño de Imagen** propio: una superficie de primera clase para crear/editar el arte de cada pieza de la lista dinámica de contenidos.
- **Reemplaza** (no borra) al documento histórico `docs/estudio-imagen.md`, que describe la arquitectura "enrutador + 2 motores + revisor" vía el motor de skills. Este documento la **relocaliza** fuera de `skills-copy/` siguiendo el patrón ya establecido por `verifica-video`.
- **Precedente directo a copiar:** la migración de la skill `verifica-video` → `keni_consola/motores/verifica_video/` + `api/verificaciones.py`. Es el camino ya recorrido para "una skill se vuelve superficie propia con su motor relocalizado y su API de primera clase". Todo este diseño es ese patrón aplicado a imagen.

---

## 0. TL;DR

1. Hoy hay **DOS caminos de imagen distintos** que conviven: (a) un camino **directo HTTP** (`POST /api/media/generar` → `media.generar_imagen` → proveedor OpenRouter → `.png` → almacén media), que es lo que usa el `EditorImagen.tsx` de cada publicación; y (b) un camino **vía motor de skills** (`estudio-imagen` con `editar.py`/`expandir.py`/`generar.py`), que corre `claude -p` como subproceso y aporta el recorte/extensión/composición de marca deterministas + la revisión legal. El Estudio nuevo unifica ambos.
2. La generación cruda por API ya vive **dentro del paquete** (`keni_consola/media.py`) y NO depende de `skills-copy/`. Lo único que vive en `skills-copy/` y hay que **relocalizar** son las herramientas deterministas de Pillow (`editar.py`, `expandir.py`) y el adaptador `generar.py` → a `keni_consola/motores/estudio_imagen/`.
3. El **modelo de datos ya existe**: una publicación (`publicacion`) tiene un campo `imagen` (nombre de objeto en el almacén media) + `imagen_url`. El arte "pertenece a la pieza" por ese campo. El Estudio produce un objeto media y lo asocia a la pieza por ese mismo seam.
4. La **Biblioteca** aporta: los **prompts de imagen** como documentos `tipo: prompt` y la **línea editorial / dirección de arte por marca** (lo que hoy son `diseno-unotv`/`diseno-clarosports`) como documentos `tipo: editorial, clase: marca/voz`. El Estudio los **adjunta** al componer el prompt, igual que `dominio/generar.py` hace con el copy.
5. **Migración en 4 fases sin romper el piloto:** (F1) relocalizar herramientas a `motores/estudio_imagen/` + API `/api/imagenes/...`; (F2) UI de Estudio (lienzo + variantes + editar + elegir final); (F3) cablear con la Biblioteca (prompts + dirección de arte por marca); (F4) borrar `skills-copy/.claude/skills/estudio-imagen`. La generación cruda (`/api/media/generar`) sigue viva todo el tiempo.

---

## 1. Cómo funciona HOY (pipeline real, con rutas y líneas)

Hay **dos pipelines** de imagen. Conviene tenerlos separados en la cabeza porque el Estudio nuevo los funde.

### 1.A — Camino DIRECTO por API (el que usa la consola hoy para "generar/adjuntar imagen a una pieza")

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

### 1.B — Camino vía MOTOR DE SKILLS (el `estudio-imagen` que se va a borrar)

Este es el que aporta lo que el camino directo NO hace: recortar a formato, comprimir a un peso, extender fondo, componer marca/breaking, outpainting fiel y la **revisión legal/editorial**. Corre como un trabajo de `claude -p`, no como una llamada HTTP directa.

```
formulario de skill (imagen subida + petición + formato + peso + ajuste)
  → POST /api/skills/ejecutar-archivo   api/skills_generacion_api.py:347
  → guarda la subida en un temporal      _guardar_subida_segura  api/skills_generacion_api.py:123
  → encola un job claude (cwd = skills-copy/, --add-dir <temporal>)
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

### 1.C — Biblioteca de medios (catálogo interno, ya existe)

`api/biblioteca_media.py` cataloga objetos del almacén con metadatos editoriales y etiquetas (`GET/POST /api/biblioteca-media`, `POST /api/biblioteca-media/catalogar` para catalogar un objeto YA generado). Es la "cosecha de imágenes": el activo aprobado, reutilizable, etiquetable. El Estudio escribe aquí cuando el usuario marca una variante como reutilizable.

---

## 2. Qué reutilizar y qué relocalizar

### Se reutiliza TAL CUAL (no se toca, ya vive en el paquete)
- `keni_consola/media.py` — generación cruda por API, validación, `guardar_bytes`, `importar_imagen`, `MODELOS_IMAGEN`, `_proveedor_openrouter` (mockeable). **Es el corazón generativo y se queda.**
- `keni_consola/almacen_media.py` — almacén de objetos disco/S3, anti-traversal. **Sin cambios.**
- `keni_consola/secretos.py` — clave/proveedor/modelo de imagen, `0600`. **Sin cambios.**
- `keni_consola/generaciones.py:lanzar_job_imagen` — runner genérico de un callable en hilo + sondeo. **Es el motor de ejecución del Estudio.**
- `api/media.py` (`/api/media`, `/api/media/{nombre}`, `/api/media/generar`) — subir, servir, generar. **Se queda viva** (es el camino que no debe romperse).
- `api/biblioteca_media.py` (`/api/biblioteca-media`) — cosecha/catálogo. **Se queda.**
- `EditorImagen.tsx` — sigue funcionando contra `/api/media/generar`. El Estudio es un "modo avanzado"; el editor inline simple no desaparece.

### Se RELOCALIZA fuera de `skills-copy/` (que se borra) → `keni_consola/motores/estudio_imagen/`
Patrón idéntico a `motores/verifica_video/` (un `__init__.py` vacío + los scripts del motor, invocados por subproceso desde una API de primera clase).

| Origen (se borra con la skill) | Destino | Naturaleza |
|---|---|---|
| `skills-copy/.claude/skills/estudio-imagen/editar.py` | `keni_consola/motores/estudio_imagen/editar.py` | Determinista (Pillow): recortar/redimensionar/comprimir/extender/placa |
| `skills-copy/.claude/skills/estudio-imagen/expandir.py` | `keni_consola/motores/estudio_imagen/expandir.py` | Generativo (outpainting fiel vía OpenRouter) |
| `skills-copy/.claude/skills/estudio-imagen/generar.py` | `keni_consola/motores/estudio_imagen/generar.py` | Generativo (ilustración/fondo). **Solapa con `media.py`** — ver nota |
| `skills-copy/.claude/skills/estudio-imagen/test_editar.py`, `test_expandir.py` | `consola/tests/motores/test_editar.py`, `test_expandir.py` | Tests Pillow (proveedor IA mockeado) |
| `skills-copy/.claude/skills/breaking-express/componer.py` (+ `marcas.json`, assets) | `keni_consola/motores/estudio_imagen/componer.py` (+ assets) | Determinista: logo + pleca + breaking |

Nota sobre `generar.py` vs `media.py`: ambos llaman a OpenRouter `chat/completions` con `modalities:["image","text"]`. Al relocalizar, **`generar.py` deja de hacer su propia llamada HTTP**: la operación "generar ilustración" del Estudio debe pasar por `media.generar_imagen()` (fuente única de proveedor/clave/modelo/log/anti-SSRF). De `generar.py` solo se conserva `construir_prompt` (estilo por marca + aspecto por formato), y eso se mueve a la composición de prompt del Estudio (ver §3, donde la dirección de arte viene de la Biblioteca). Resultado: un solo punto que toca la red para generar (`media._PROVEEDOR`), mockeable en tests.

### Se RECONCEPTUALIZA como documentos de la Biblioteca (no se relocaliza como código)
- `diseno-unotv/guia-diseno.md`, `plantillas-prompt.md` → `editorial/marcas/unotv` (clase `marca`, `marcas:[unotv]`).
- `diseno-clarosports/guia-diseno.md`, `plantillas-prompt.md` → `editorial/marcas/claro-sports`.
- Las reglas legales de `revisa-imagen` (`contexto-editorial/reglas-legales.md`) → `editorial/reglas/imagen` (clase `reglas`, global).
- Prompts de imagen reutilizables → `prompt/imagen/<slug>` (p. ej. `prompt/imagen/ilustracion-fondo`).

---

## 3. Diseño del ESTUDIO DE IMAGEN como superficie propia

### 3.1 Modelo: el arte pertenece a la pieza
- Una imagen es un **objeto del almacén media** (`<uuid>.png`). El vínculo con la pieza ya existe: `publicacion.imagen` + `imagen_url` (`dominio/publicaciones.py:140,159`; handoff A→C `crear_borrador(... imagen=...)`).
- El Estudio se **abre desde una pieza** de la lista dinámica (radar/RSS/green/obligatorios) o desde Parrilla/Publicaciones. Recibe contexto de la pieza: `copy` (el texto ya generado), `marca`, `red` (→ formato sugerido: feed 4:5, vertical 9:16…), `titulo`.
- El Estudio mantiene una **sesión efímera** con N candidatas (variantes + ediciones). Persistir la sesión completa es opcional; lo durable es: (a) los objetos media generados (en el almacén), (b) la elección final (escrita en `publicacion.imagen`), y (c) opcionalmente la candidata marcada "reutilizable" (catalogada en `biblioteca-media`). Reutilizar el registro de generación (`generaciones.py`, efímero+sondeable) como contenedor de cada operación encaja perfecto: cada "generar/editar variante" es un job tipo `imagen` que el front sondea.

### 3.2 De dónde sale el prompt de imagen
La operación generativa del Estudio compone el prompt **igual que `dominio/generar.py` compone el copy** (`componer()` = cuerpo del prompt + editorial adjunta + contexto):

```
prompt_imagen_final =
    <prompt base de imagen>            (Biblioteca: prompt/imagen/<slug>, editable)
  + <dirección de arte de la marca>    (Biblioteca: editorial/marcas/<marca>, auto-adjunto por marca)
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
  - **Revisar** (opcional, cierre): pasa la candidata por la revisión legal/editorial (ver §3.5).
- **Elegir final:** botón "Usar en la pieza" → escribe `publicacion.imagen = <objeto>`; botón "Guardar en biblioteca" → `POST /api/biblioteca-media/catalogar`.

Encaje con la lista dinámica: a las 9am el equipo recorre la lista; cada pieza con copy ya generado ofrece "Abrir en Estudio". El Estudio devuelve la pieza con su arte asociado, lista para revisar/aprobar/programar. El editor inline simple (`EditorImagen.tsx`) sigue para el caso trivial "adjunta o describe una imagen"; el Estudio es para el caso rico (variantes + edición + marca + revisión).

### 3.4 API propuesta (`/api/imagenes/...`)
Un módulo nuevo `api/imagenes.py` (auto-descubierto por `api/__init__.py`, solo hay que exportar `RUTAS`). TODO reusa `generaciones.lanzar_job_imagen` + el almacén media. Cada endpoint que "produce píxeles" responde de inmediato con un registro de generación y el front sondea `GET /api/generaciones/{id}`.

| Endpoint | Hace | Reutiliza |
|---|---|---|
| `POST /api/imagenes/generar` | genera N variantes desde prompt+marca+formato (compone prompt con la Biblioteca) | `media.generar_imagen`, `lanzar_job_imagen`, `biblioteca.cuerpo_efectivo` + `editoriales_de_marca` |
| `POST /api/imagenes/editar` | operación determinista (recortar/redimensionar/comprimir/extender/placa/breaking) sobre un objeto media | motor `motores/estudio_imagen/editar.py` por subproceso (patrón `verificaciones.analizar`), `media.importar_imagen` |
| `POST /api/imagenes/expandir` | outpainting fiel a un formato | `motores/estudio_imagen/expandir.py`, `lanzar_job_imagen` |
| `POST /api/imagenes/revisar` | revisión legal/editorial de un objeto media | `claude -p` (job claude) con `editorial/reglas/imagen` adjunta, o un job determinista que devuelve checklist |
| `POST /api/imagenes/usar` | asocia un objeto media a una pieza (`publicacion.imagen`) | `repos`/`publicaciones` (handoff existente) |

Subir/servir/cosechar siguen en `/api/media` y `/api/biblioteca-media` (sin duplicar). `/api/media/generar` se mantiene como alias del caso simple (1 variante) para no romper `EditorImagen.tsx`.

Las operaciones deterministas (`editar`) NO necesitan `claude`: corren el motor con el python de la consola (`sys.executable motores/estudio_imagen/editar.py …`), exactamente como `api/verificaciones.py:_ruta_motor`/`analizar` corre `analiza-video.py`. La clave de imagen para `expandir`/`generar` se transporta al subproceso reutilizando el mapeo de `generaciones._entorno_skill` (proveedor → `OPENROUTER/OPENAI/GEMINI_API_KEY`).

### 3.5 Revisión legal/editorial
Hoy la hace la skill (Claude *ve* el PNG y aplica `reglas-legales.md`). Tras borrar la skill hay dos opciones, ambas viables:
- **(a) Job `claude` puntual:** `POST /api/imagenes/revisar` lanza un `claude -p` con la imagen vía `--add-dir` y la regla `editorial/reglas/imagen` adjunta en el prompt; devuelve el checklist ✅/⚠️/❌. Reutiliza `encolar_job_claude`/`_argv_claude` que ya saben pasar `--add-dir` de un temporal (`generaciones.py:341,613`).
- **(b) Diferir** la revisión al QA editorial existente (`api/qa_editorial.py`, `dominio/qa_editorial.py`) extendido a imagen. Recomendado a medio plazo para no fragmentar la verificación.
La revisión NO bloquea la generación: es el cierre antes de "Usar en la pieza" (gate humano), igual que hoy.

### 3.6 Relación con la Biblioteca
- **Prompts de imagen** = documentos `tipo: prompt` (p. ej. `prompt/imagen/ilustracion-fondo`). El Estudio los carga con `biblioteca.cuerpo_efectivo(id)` (mismo seam que `dominio/generar.py:180`).
- **Dirección de arte por marca** = documentos `tipo: editorial, clase: marca` (`editorial/marcas/unotv`, `editorial/marcas/claro-sports`), auto-adjuntos por marca con `biblioteca.editoriales_de_marca(marca)` (igual que el copy). Editables por el equipo; sustituyen al `ESTILO_MARCA` hard-coded.
- **Reglas legales de imagen** = `editorial/reglas/imagen` (clase `reglas`, global), adjunta al job de revisión.
- Estos documentos viajan en la **semilla** de la Biblioteca (`keni_consola/biblioteca_semilla/{prompt,editorial}/`), igual que ya viajan los prompts de copy.

---

## 4. Plan de migración por fases (sin romper el piloto)

Invariante: en TODO momento la generación de imagen funciona. El camino directo `POST /api/media/generar` + `EditorImagen.tsx` NO se toca hasta el final. Cada fase es desplegable por separado.

### Fase 0 — Preparación (sin cambios de comportamiento)
- Confirmar que `media.py` (proveedor) y `lanzar_job_imagen` cubren el camino directo (ya cubren). Asegurar que `Pillow`/`httpx` son dependencias del back (hoy Pillow solo lo necesitaba la skill; ver §5).
- Crear `keni_consola/motores/estudio_imagen/__init__.py` (vacío), espejando `motores/verifica_video/`.

### Fase 1 — Relocalizar el motor + API de primera clase (la skill sigue viva en paralelo)
1. Copiar `editar.py`, `expandir.py`, `componer.py` (+ `marcas.json`/assets) a `motores/estudio_imagen/`. Ajustar rutas relativas internas (el `marcas.json` hermano del breaking) a la nueva ubicación. NO borrar aún el original.
2. Mover los tests Pillow a `consola/tests/motores/` y hacerlos correr en el CI del back (instalar Pillow en el entorno de test).
3. Crear `api/imagenes.py` con `POST /api/imagenes/editar` y `/expandir` que invocan el motor por subproceso (patrón `api/verificaciones.py`), reusan `lanzar_job_imagen` y re-importan con `media.importar_imagen`. Reusar `_entorno_skill` para la clave en `expandir`.
4. `POST /api/imagenes/generar`: 1ª versión = wrapper de `media.generar_imagen` con N variantes (sin Biblioteca todavía; prompt crudo). Verificable contra el proveedor real o mockeado.
- **Estado tras F1:** existe la API nueva; la skill `estudio-imagen` sigue funcionando por su camino. Nada roto.

### Fase 2 — UI del Estudio (lienzo + variantes + editar + elegir final)
1. `Estudio.tsx` (página o drawer) consumiendo `/api/imagenes/*`, con sondeo `useGeneracion`.
2. Abrir el Estudio desde una pieza (Radar/RSS/Parrilla/Publicaciones) pasando `copy/marca/red/titulo` por router state.
3. Botón "Usar en la pieza" (`POST /api/imagenes/usar` → `publicacion.imagen`) y "Guardar en biblioteca" (`/api/biblioteca-media/catalogar`).
4. Mantener `EditorImagen.tsx` como editor inline simple; añadir un enlace "Abrir en Estudio".
- **Estado tras F2:** el equipo ya hace todo el flujo rico desde la Consola sin la pestaña de skill.

### Fase 3 — Cablear con la Biblioteca (prompts + dirección de arte por marca)
1. Sembrar `prompt/imagen/<slug>`, `editorial/marcas/<marca>`, `editorial/reglas/imagen` en `biblioteca_semilla/` (portando el contenido de `guia-diseno.md`/`plantillas-prompt.md`/`reglas-legales.md`).
2. `POST /api/imagenes/generar` compone el prompt con `biblioteca.cuerpo_efectivo` + `editoriales_de_marca` (sustituye `ESTILO_MARCA`).
3. `POST /api/imagenes/revisar` adjunta `editorial/reglas/imagen` a un job `claude`.
- **Estado tras F3:** estilo de marca y reglas son editables por el equipo; el Estudio es autónomo de `skills-copy/`.

### Fase 4 — Borrar la skill
1. Quitar `estudio-imagen` (y los `diseno-*`/`revisa-imagen` si ya no los usa nada) del catálogo de skills; quitar el filtro `esSkillDeImagen` y la pestaña "Imágenes" de `Generacion.tsx`.
2. Borrar `skills-copy/.claude/skills/estudio-imagen/` (y `breaking-express/` si solo lo usaba el motor relocalizado).
3. Limpiar `generaciones._entorno_skill` si ya no hay subprocesos `claude` de imagen (mantenerlo si la revisión usa `claude`).
- **Precondición de F4:** F1-F3 desplegadas y el Estudio cubriendo todas las capacidades. La generación directa `/api/media/generar` sigue intacta.

---

## 5. Riesgos y dependencias

- **Clave del proveedor (OpenRouter):** fuente única `secretos.toml` (`0600`) con fallback a entorno. Sin clave, lo generativo degrada a "dirección de arte" (prompt para herramienta externa) como hoy (`generar.py:salida_sin_key`). Riesgo: que el subproceso del motor no reciba la clave → mitigado reusando `_entorno_skill` (`generaciones.py:375`). NUNCA loguear la clave (ya respetado en `media.py`/`secretos.py`).
- **Pillow en el back:** hoy Pillow lo cargaba el subproceso de la skill; el CI estático de skills no lo instalaba (ver `docs/estudio-imagen.md` §8). Al relocalizar `editar.py`/`expandir.py` al paquete, **Pillow pasa a ser dependencia del back** (o del worker que ejecuta los motores). Asegurar que el entorno de ejecución y de test lo tiene.
- **ffmpeg / tesseract / yt-dlp:** NO los necesita imagen (son del motor de video `verifica_video`). Imagen solo necesita Pillow + httpx. No introducir esa dependencia aquí.
- **Tamaño de media:** límite vigente 15 MB por imagen (`media.LIMITE_IMAGEN`). Generar N variantes multiplica el almacenamiento; sin recolección, el almacén crece. Mitigar: las variantes NO elegidas son objetos huérfanos — definir una política (TTL/limpieza de objetos no referenciados por ninguna pieza ni catalogados en biblioteca). Hoy `biblioteca_media.borrar` ya borra el binario al descatalogar; falta un GC de huérfanos del Estudio.
- **Coste por imagen:** cada variante generativa cuesta. El determinista (recortar/comprimir/extender uniforme/placa) es gratis y debe ser el camino por defecto cuando aplica (regla de oro de `docs/estudio-imagen.md` §3). La UI debe empujar a lo determinista y limitar el nº de variantes generativas por defecto.
- **S3/Garage:** en hosted la media va a bucket; el motor determinista escribe en un **temporal local** y `media.importar_imagen` lo sube al backend activo (igual que hoy importa los .png de la skill). Verificar que el subproceso del motor tiene acceso al temporal (patrón `--add-dir` / `tempfile.mkdtemp` de `verificaciones.analizar`).
- **Outpainting fiel:** `expandir.py` re-compone el sujeto pixel a pixel; al relocalizar, conservar esa garantía (es la línea roja editorial: la IA no inventa sobre el sujeto de una foto real).
- **Acoplamiento generar.py ↔ media.py:** al unificar la generación en `media.generar_imagen`, `expandir.py` (que SÍ manda la imagen de entrada con `image_config.strength`) puede necesitar un parámetro extra que `media._proveedor_openrouter` hoy no expone (solo manda texto). Riesgo: el outpainting necesita su propio camino de proveedor o ampliar `media.py` para aceptar imagen de entrada + strength. Decidir en F1: ampliar `media._proveedor_openrouter` para aceptar `imagen_base64`/`strength` opcionales (preferible, una sola puerta de red) vs. mantener `expandir.py` con su httpx propio (más simple pero duplica el punto de red).

---

## 6. Archivos críticos para la implementación

- `consola/src/keni_consola/api/verificaciones.py` — **plantilla exacta** de "skill relocalizada → motor en `motores/` + API de primera clase que corre el motor por subproceso y reusa `lanzar_job_imagen`". Copiar su forma para `api/imagenes.py`.
- `consola/src/keni_consola/media.py` — corazón generativo (proveedor, `generar_imagen`, `guardar_bytes`, `importar_imagen`, `MODELOS_IMAGEN`); se reutiliza y posiblemente se amplía para outpainting.
- `consola/src/keni_consola/generaciones.py` — `lanzar_job_imagen` (runner del Estudio) y `_entorno_skill`/`_argv_claude` (clave al subproceso, `--add-dir` para la revisión).
- `consola/src/keni_consola/dominio/generar.py` — patrón de composición de prompt (`componer()` = prompt + editorial + contexto) a replicar para el prompt de imagen con la Biblioteca.
- `skills-copy/.claude/skills/estudio-imagen/{editar,expandir,generar}.py` — los motores a relocalizar a `keni_consola/motores/estudio_imagen/`.
