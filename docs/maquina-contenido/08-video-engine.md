# Ola G — Motor de edición de video (toque RRSS)

El motor de **edición** de video cubre el "toque redes" sobre video **ya editado**:
reencuadre por formato, overlays/marcos/image-in-video, doble pista/PiP y subtítulos
quemados es-MX. La edición cruda (blur, cortar silencios) **no** se cubre (eso es Premiere).

Decisión de arquitectura (tomada):
- **Render server-side con FFmpeg** (filtergraph: `scale`/`crop`/`pad` reencuadre, `overlay`
  para marcos/PiP/image-in-video, `xstack`/`vstack` doble pista, `subtitles=ASS` para
  subtítulos quemados).
- Los overlays/marcos/miniaturas **reutilizan el Estudio de imagen**: una capa de overlay es
  un `Documento` que se renderiza a PNG transparente con
  `dominio.estudio_imagen.renderizar_documento_bytes(documento, bindings=...)` y luego se
  compone con `overlay` en ffmpeg. **No se reinventan capas.**
- **ASR con faster-whisper** (word-level) para subtítulos; import **perezoso y opcional** (si
  la lib no está instalada, degrada con error claro, sin romper el import).
- Los jobs de render/transcripción **reutilizan la infra de `generaciones`/`jobs`/worker** para
  colgarse de Actividad IA + streaming, vía un **camino de job genérico (no-claude)**.

Esta Ola G nació como **BASE COMPARTIDA / CONTRATO** entre cuatro agentes en paralelo.
**Ya está toda construida** (render FFmpeg, ASR, `api/video.py`, UI `Video.tsx`). Lo que
sigue describe el esquema JSON, las tablas, los job kinds, la superficie API, las
convenciones S3 y los presets de formato — sigue siendo la referencia vigente del motor.

---

## 0. Quién posee qué (dueños de módulo) — todo construido

| Pieza | Dueño | Estado |
|---|---|---|
| Render FFmpeg | `consola/src/keni_consola/motores/estudio_video/` (`ejecutar_render`) | **listo** |
| ASR subtítulos | `consola/src/keni_consola/motores/transcripcion/` (`ejecutar_transcripcion`) | **listo** |
| API HTTP | `consola/src/keni_consola/api/video.py` | **listo** (declarado en `apps/produccion.toml`) |
| UI Estudio de Video | `consola/frontend/src/pages/Video.tsx` | **listo** |
| Presets + validador | `keni-shared/src/keni_shared/video.py` | **listo** |
| Tablas + CRUD | `db.py` / `repos.py` | **listo** |
| Seam job genérico | `dominio/jobspec.py` + `generaciones.py` + `worker.py` | **listo** |

> No confundir `motores/transcripcion/` (ASR de subtítulos, faster-whisper, word-level) con
> `keni_consola.transcripcion` de nivel raíz (whisper.cpp del flujo clip-a-copy). Son caminos
> distintos a propósito.

---

## 1. Esquema de COMPOSICIÓN (JSON)

Una composición describe el render completo. Vive en `video_composiciones.documento` (JSON) y se
valida con `keni_shared.video.validar_composicion(doc)`.

```jsonc
{
  "version": 2,
  "marca": "claro-sports",
  "formato": {"w": 1080, "h": 1920, "fps": 30, "preset": "9:16"},
  "duracion_ms": 30000,
  "pistas": [
    {"id": "base", "tipo": "video", "clips": [
      // VARIOS clips = SEGMENTOS concatenados en orden (corte/split). Un solo clip = sin corte.
      {"id": "c1", "media_id": "videos/<sha>.mp4", "inicio_ms": 0, "fin_ms": 30000,
       "recorte_in_ms": 0, "recorte_out_ms": 30000,
       "x": 0, "y": 0, "w": 1080, "h": 1920, "ajuste": "cover", "foco": [0.5, 0.5],
       "volumen": 1, "silenciar": false}]},
    {"id": "pip", "tipo": "video", "clips": [ /* clip único con x/y/w/h de posición PiP */ ]},
    {"id": "overlay", "tipo": "overlay", "capas": [ /* capas estilo Documento del Estudio */ ]},
    {"id": "subs", "tipo": "subtitulos", "subtitulo_id": "<id>",
     "estilo": {"fuente": "Barlow", "tam": 64, "color": "#FFFFFF", "borde": "#000000",
                "posicion": "inferior", "karaoke": true}},
    {"id": "audio", "tipo": "audio", "clips": [
      // Música (u otra fuente) mezclada con `amix` sobre el audio del clip base.
      {"id": "a1", "media_id": "videos/<sha>.mp3", "inicio_ms": 0, "fin_ms": 12000,
       "recorte_in_ms": 0, "recorte_out_ms": 12000, "offset_ms": 0,
       "volumen": 0.6, "silenciar": false}]}
  ]
}
```

Notas del contrato:
- La pista `overlay` usa el **mismo modelo `Documento.capas`** del Estudio de imagen
  (`motores/estudio_imagen/documento.py`): así el render del overlay es
  `renderizar_documento_bytes({..., "capas": <capas>})` → PNG transparente → `overlay` en ffmpeg.
- `ajuste` ∈ `cover|contain` y `foco: [fx, fy]` (0..1) dirigen el `crop` del reencuadre.
- **Segmentos (split)**: la pista `base` admite **varios clips** que el render **concatena** en
  orden (FFmpeg `trim`+`concat`). Cada clip lleva su propio `recorte_in_ms`/`recorte_out_ms`. La
  pista `pip` usa un único clip. `duracion_ms` = suma de los segmentos tras su recorte.
- **Audio**: `volumen` (0..1) y `silenciar` por clip controlan su sonido. El audio del clip `base`
  se mezcla con los clips de la pista `audio` (música) vía `amix`; `offset_ms` posiciona la música.
  Los clips de música admiten `fade_in_ms`/`fade_out_ms` (fundidos, el render los aplica con `afade`).
- **PiP**: su clip admite `recorte_in_ms`/`recorte_out_ms` (trim propio, igual que el base).
- **Marcadores**: `marcadores: [{id, ms, etiqueta?}]` a nivel de composición (en tiempo de SALIDA),
  para sincronizar cortes/revisiones; no afectan al render.
- `media_id` es una **clave de media** (`videos/<sha>.mp4`), no una URL.
- El validador de la BASE comprueba **solo la forma del sobre** (formato w/h enteros > 0;
  `pistas` lista; cada pista con `id` único + `tipo` ∈ `{video, overlay, subtitulos, audio}`);
  normaliza `version`/`marca`/`duracion_ms`/`formato.fps`/`formato.preset`. **No** valida las capas
  (eso es del Estudio de imagen), los clips/segmentos, ni los media reales (eso es del render).

---

## 2. Presets de formato (`keni_shared/video.py`)

`PRESETS_FORMATO` define resolución + zonas seguras por aspecto:

| preset | w×h | fps | safe_top | safe_bottom |
|---|---|---|---|---|
| `9:16` | 1080×1920 | 30 | 220 | 320 |
| `1:1`  | 1080×1080 | 30 | 120 | 120 |
| `16:9` | 1920×1080 | 30 | 80 | 120 |

Helpers: `preset_para_aspecto(asp)`, `preset_para_red(red_id)` (mapea sobre
`limites_plataforma.VIDEO_SPECS`: X=16:9, resto 9:16), `aspectos()`. Red/aspecto desconocido →
`ASPECTO_DEFECTO = "9:16"`.

---

## 3. Tablas (Postgres; `db.py` + `repos.py`)

`video_composiciones`
| col | tipo |
|---|---|
| `id` | TEXT PK |
| `contenido_id` | TEXT (liga opcional a una pieza del tablero) |
| `marca` | TEXT |
| `documento` | TEXT (JSON de composición) |
| `creado`, `actualizado` | TEXT ISO |

Índices: `marca`, `contenido_id`.

`video_subtitulos`
| col | tipo |
|---|---|
| `id` | TEXT PK |
| `composicion_id` | TEXT |
| `idioma` | TEXT (def `es-MX`) |
| `estado` | TEXT ∈ `{pendiente, transcrito, editado, listo}` |
| `segmentos` | TEXT (JSON word-level del ASR) |
| `ass` | TEXT (ASS renderizado para quemar) |
| `transcrito_en` | TEXT ISO |
| `actualizado` | TEXT ISO |

Índices: `composicion_id`, `estado`.

CRUD (db.py) y fachadas (repos.py):
- composiciones: `crear_video_composicion`, `listar_video_composiciones`,
  `obtener_video_composicion`, `actualizar_video_composicion`.
- subtítulos: `crear_video_subtitulo`, `listar_video_subtitulos`, `obtener_video_subtitulo`,
  `actualizar_video_subtitulo`.

Usa SIEMPRE las fachadas de `repos.py` desde la API/motores (no `db.*` directo).

---

## 4. Job genérico (no-claude) — el SEAM

La cola/worker existentes solo corrían `claude -p`. La BASE añade un **camino de job de
PROCESO** (no-claude) que reutiliza `generaciones`/`jobs`/worker para colgarse de Actividad IA.

- Kinds (`dominio/jobspec.py`): `PROC_RENDER_VIDEO = "render-video"`,
  `PROC_TRANSCRIBIR = "transcribir"`; conjunto `KINDS_PROCESO`.
- Registro de ejecutores: `EJECUTORES_PROCESO = {"render-video":
  "keni_consola.motores.estudio_video:ejecutar_render", "transcribir":
  "keni_consola.motores.transcripcion:ejecutar_transcripcion"}`, resuelto por import perezoso
  con `jobspec.resolver_ejecutor_proceso(kind)`.
- Encolar (`generaciones.py`): `encolar_job_proceso(gen_id=None, *, kind, params, etiqueta=None,
  marca=None)` crea el registro (`tipo=kind`), toma el cupo de admisión y encola el spec PLANO
  `{"version":1, "kind":kind, **params}` (lo arma `jobspec.construir_proceso`). Devuelve el
  registro público (incluye `id`).
- Dispatch (`worker.py`): tras reclamar un job, si `jobspec.es_kind_proceso(spec)` →
  `_procesar_job_proceso(job_id, gen_id, spec)` (resuelve el ejecutor, lo llama, libera el cupo
  y termina el job; si el ejecutor revienta, marca error). Si no, sigue el camino claude intacto.

**Firma del ejecutor (CONTRATO, no cambiar):**

```python
def ejecutar(gen_id: str, spec: dict) -> None: ...
```

Cada ejecutor reporta progreso/estado/errores vía `generaciones.actualizar(gen_id, {...})`:
- en marcha: `{"estado": ESTADO_EJECUTANDO, "fase": "...", "salida": "..."}` (opcional)
- éxito: `{"estado": ESTADO_COMPLETADO, "resultado": {...}, "fecha_fin": ahora_iso()}`
- error: `{"estado": ESTADO_ERROR, "error": "<es>", "fecha_fin": ahora_iso()}`

### 4.1 Contrato `ejecutar_render` (agente A)

`spec`: `{"version":1, "kind":"render-video", "composicion_id": "<id>", ...}`.
Debe: cargar la composición (`repos.obtener_video_composicion`), validarla
(`keni_shared.video.validar_composicion`), bajar clips de S3 (`media.leer_objeto`, categoría
`videos`), renderizar la pista `overlay` a PNG con `renderizar_documento_bytes` y los subtítulos
a ASS, componer con FFmpeg (`config.ffmpeg_bin()`, timeout `config.video_render_timeout()`),
guardar el mp4 en media **categoría `render`** (content-addressed sha256, igual que el Estudio
de imagen guarda el PNG) y marcar `completado` con
`resultado = {"media_id": "render/<sha>.mp4", "url": "/api/media/render/<sha>.mp4"}`.

### 4.2 Contrato `ejecutar_transcripcion` (agente B)

`spec`: `{"version":1, "kind":"transcribir", "subtitulo_id": "<id>", "media_id":
"videos/<sha>.mp4", "idioma": "es-MX"}`.
Debe: extraer audio con ffmpeg (wav 16 kHz mono), transcribir con faster-whisper
(`config.whisper_modelo()`, word-level; **import perezoso y opcional**), escribir en
`video_subtitulos` (`repos.actualizar_video_subtitulo`) `segmentos` (JSON word-level) + `ass` +
`estado='transcrito'` + `transcrito_en`, y marcar la generación `completado`.

---

## 5. Superficie API (`api/video.py`)

Sugerida (el agente la concreta; debe usar `repos.*` y `encolar_job_proceso`):
- `POST /api/video/composiciones` → crea (valida con `keni_shared.video.validar_composicion`).
- `GET /api/video/composiciones` / `GET /api/video/composiciones/{id}` → listar/obtener.
- `PUT /api/video/composiciones/{id}` → actualiza el `documento`.
- `POST /api/video/composiciones/{id}/render` → `encolar_job_proceso(kind="render-video",
  params={"composicion_id": id}, marca=...)` (local/bajo demanda: sin kill-switch).
- `POST /api/video/subtitulos` + `POST /api/video/subtitulos/{id}/transcribir` →
  `encolar_job_proceso(kind="transcribir", ...)` (local/bajo demanda: sin kill-switch).
- `GET/PUT /api/video/subtitulos/{id}` → leer/editar (corrección humana → `estado='editado'`).

Registrar el router en el manifest ya hecho (`apps/produccion.toml` → `modulos_backend` incluye
`"video"`).

---

## 6. Convenciones S3 / media

- Clips de entrada: categoría `videos` (`media.guardar_video_subida` → `videos/<sha>.<ext>`).
- mp4 de salida del render: categoría `render` (`render/<sha>.mp4`), reciclable/regenerable.
- Servir vía el `GET /api/media/{nombre}` existente (resuelve disco/S3).

---

## 7. Config (sin kill-switch)

El render (ffmpeg) y la transcripción (faster-whisper) son **locales, gratuitos y BAJO DEMANDA**
(los dispara un humano al pulsar "Renderizar"/"Transcribir"; no hay daemon que los lance ni
consumen tokens). Por eso **NO tienen interruptor de apagado ni están gateados por la máquina**:
no aparecen como toggles en Configuración. El kill-switch de máquina + los toggles existen solo
para evitar operación autónoma (daemons) y para no gastar tokens; nada de eso aplica aquí.

`config.py` conserva solo configuración legítima (no kill-switches):
- `KENI_WHISPER_MODELO` (str, def `"medium"`) → `config.whisper_modelo()`.
- `KENI_FFMPEG_BIN` (str, def `"ffmpeg"`) → `config.ffmpeg_bin()`.
- `KENI_VIDEO_RENDER_TIMEOUT` (int, def 1800) → `config.video_render_timeout()`.

---

## 8. Deploy

- `deploy/worker/Dockerfile` instala `ffmpeg` (apt). El servicio `worker` es quien ejecuta los
  jobs de proceso (reclama la cola); `daemons` solo encola, no necesita ffmpeg.
- faster-whisper/torch **no** se bakean (pesado): se instalan en el servidor cuando se active la
  transcripción. El import es perezoso y degrada con error claro si falta.

---

## 9. Etiquetas frontend

`consola/frontend/src/lib/generaciones.ts` → `ETIQUETAS_TIPO_GENERACION`:
`"render-video": "Render de video"`, `"transcribir": "Transcripción"`.
