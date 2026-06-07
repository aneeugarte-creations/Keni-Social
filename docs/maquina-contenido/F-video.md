# Ola F — Aceptar VIDEO (no solo foto)

Una pieza puede ser **foto** (3 redes: instagram, x, facebook) o **video**
(5 redes: + youtube + tiktok). `contenido.formato` ya existe; `redes.redes_de_formato`
ya mapea foto=3 / video=5; la publicación a Metricool **ya soporta** `TipoMedia.video`
(meta.py publica foto/video). Falta el asset de video y el cableado.

## 1. DB (db.py)
`contenido_plataforma` gana, como espejo de imagen (migración idempotente ADD COLUMN):
- `video TEXT NOT NULL DEFAULT ''` — clave del asset de video (como `imagen`).
- `falta_video INTEGER NOT NULL DEFAULT 0` — checklist (como `falta_imagen`).
Añadir a `_COLS_CONTENIDO_PLATAFORMA`, a editables, a `crear_contenido_plataforma`
(params `video=""`, `falta_video=None`), y a la serialización de plataforma.

Regla de checklist por formato de la pieza:
- pieza `formato='foto'`  → cada plataforma usa `falta_imagen` (video N/A, `falta_video=0`).
- pieza `formato='video'` → cada plataforma usa `falta_video` (necesita el asset de
  video); `falta_imagen=0` (la imagen pasa a ser opcional: portada/thumbnail).

## 2. Almacén + subida de video (media.py / almacen_media.py / api/media.py)
- Nueva categoría `videos` en `almacen_media.CATEGORIAS`.
- `media.guardar_video_subida(archivo)`: mimes de video (`video/mp4`,
  `video/quicktime`, `video/webm`, `video/x-matroska`, `video/mpeg`, `video/3gpp`),
  límite de tamaño (config `KENI_VIDEO_MAX_MB`, def 300). Clave `videos/<sha256>.<ext>`.
  Content-addressed dedup como las imágenes.
- `POST /api/media/video` (multipart `archivo`) → `{id, url}` (igual que `POST /api/media`).
- Servir vía el `/api/media/{nombre}` existente (ya resuelve disk/S3).
- Límites de video por red (keni-shared `limites_plataforma`): añade specs básicos
  (duración/size/aspecto sugeridos) para tiktok/youtube/instagram/facebook/x;
  best-effort/informativo (no bloquear), úsalos para avisos en la UI.

## 3. Redes según formato + flip (api/contenido.py)
- Al **crear** una pieza con `formato`: las `contenido_plataforma` se crean para
  `redes.redes_de_formato(formato)` (foto→3, video→5). (El auto-feed/pipeline ya
  ponen formato='foto'+3; aquí cubrimos la creación manual y el flip.)
- **Flip** PATCH `/api/contenido/{id}` con `{formato}`:
  - `foto→video`: set `contenido.formato='video'`; ASEGURA filas para las 5 redes
    (crea las que falten —youtube, tiktok— con `falta_copy=1`, `falta_video=1`);
    en TODAS las filas pon `falta_video=1` si no hay `video`, `falta_imagen=0`.
  - `video→foto`: set `formato='foto'`; deja las 3 de foto; las filas extra
    (youtube/tiktok) se ELIMINAN solo si están vacías (sin copy ni video); si
    tienen contenido, consérvalas y devuelve un aviso (no perder trabajo).
  - Añade `formato` a editables de contenido; añade helper
    `repos.ajustar_plataformas_por_formato(contenido_id, formato) -> {creadas, eliminadas, conservadas}`.
- PATCH plataforma acepta `{video}` (set asset) y limpia `falta_video=0`
  (espejo de cómo `imagen` limpia `falta_imagen`).

## 4. Publicación (programador.py)
En `_borrador_de_publicacion`: si la pieza es video (pieza `formato='video'`),
usa `pub["video"]` y construye `MediaRef(tipo=TipoMedia.video, url=_url_media_publica(video))`
en vez de imagen. Si no hay video, no publica esa red (queda pendiente). Imagen
sigue igual para foto. (La capa metricool ya distingue foto/video.)

## 5. Frontend
- `types`: regenerar (formato ya está; añadir `video`/`falta_video` a la plataforma
  en el esquema API + `gen:types`). 
- Editor de pieza: **toggle Formato (Foto/Video)** que:
  - cambia el editor de media: **Foto** → `EditorImagen` (actual); **Video** →
    nuevo `EditorVideo` (input `type=file accept=video/*`, sube vía
    `api.subirVideo`, preview con `<video>`, avisos de límite por red).
  - al cambiar formato, llama al flip (PATCH formato) y refresca las redes de la pieza.
- Checklist/feed: para piezas video, el hueco de media es "Falta video" (usa
  `falta_video`); el badge "Video" ya existe (Ola anterior). Mostrar las 5 redes.
- `lib/api.ts`: `subirVideo(archivo)` → `POST /api/media/video`; PATCH plataforma con `{video}`.

## Reglas
- Worktree `~/projects/keni-social-video`. Migraciones idempotentes. ruff
  (`datetime.UTC`) + ast + tsc -b + vite build + vitest + `PYTHONPATH=src` pytest +
  `gen:types:check`. snake_case. Nada autopublica (sigue gateado por PUBLICAR_REAL).
  No tocar `webapp/`.
