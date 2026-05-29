# Publicación / programación vía Metricool

Camino de publicación **recomendado**: en vez de pegarle directo a Graph API de Meta
(gated por App Review), a TikTok (gated por auditoría) y a X (tier de pago), entregamos
el post al **scheduler de Metricool**, que AMX ya tiene en plan **Advanced**. Una sola
integración cubre Facebook, Instagram, X, TikTok y YouTube, con **programación nativa**.

Reutiliza **el mismo token por marca** que la lectura de métricas
(`fuentes.metricol.FuenteMetricol`): cabecera `X-Mc-Auth` + query `userId`/`blogId`.

## Piezas

- `publicacion/metricool.py`
  - `BorradorMetricool`: borrador multi-red que aprueba un humano (redes, texto, media,
    hashtags, `publicar_en`, `timezone`, `auto_publish`, `borrador`).
  - `AdaptadorPublicacionMetricool`: construye el `ScheduledPost` y, opcionalmente, lo
    envía. **DRY-RUN por defecto** (cero red). El camino real exige credenciales
    completas o lanza `ProgramacionNoConfigurada` antes de tocar la red.
- `publicacion/flujo_metricool.py`: carga borradores de `.json`/`.toml`, reporta el
  dry-run y, con `--publicar-real --si-publicar` + credenciales en el entorno, programa
  de verdad. Espeja la seguridad de `flujo.py`.

No hace falta cola/agendador propio (a diferencia del camino Meta-directo, donde IG no
agenda por API): **Metricool agenda** con `publicationDate` + `autoPublish`.

## Contrato de la API (swagger oficial)

    POST /v2/scheduler/posts?userId=<uid>&blogId=<bid>
    Headers: X-Mc-Auth: <user_token>
    Body (modelo `ScheduledPost`; requeridos: text, publicationDate, providers):
      {
        "text": "...",
        "publicationDate": {"dateTime": "2026-05-30T20:00:00", "timezone": "America/Mexico_City"},
        "providers": [{"network": "facebook"}, {"network": "instagram"}, {"network": "twitter"}],
        "media": ["https://.../clip.mp4"],
        "mediaAltText": ["texto alternativo"],
        "autoPublish": true,
        "draft": false,
        "saveExternalMediaFiles": true
      }
    Respuesta: {"data": {"id", "providers": [{"network","status"}], ...}}
    status ∈ {PUBLISHED, PUBLISHING, PENDING, ERROR, DRAFT}

Metricool usa `twitter` para X (igual que el adaptador de lectura).

## Credenciales por marca

El adaptador recibe `{user_token, user_id, blog_id}` ya resueltos. Es **exactamente** la
forma que devuelve `config.MetricoolConfig.marcas_configuradas()[marca]`, así que el
cableado programático (Consola) es directo:

```python
creds = MetricoolConfig(...).marcas_configuradas()[marca_id]
ad = AdaptadorPublicacionMetricool(creds=creds)
ad.programar(borrador, dry_run=False)  # programa en Metricool
```

La CLI usa una sola identidad por entorno (`METRICOOL_USER_TOKEN/USER_ID/BLOG_ID`).

## Enganche en la Consola (siguiente paso)

El programador 24-7 (`consola/.../programador.py`, `_preparar`) hoy solo estampa
`preparado_en` en dry-run. Ahí es donde se engancha el posteo real:

1. resolver `creds` de la marca de la pieza (`marcas_configuradas()`),
2. mapear la fila de `publicaciones` (texto, red(es), media del object-store) a
   `BorradorMetricool`,
3. `AdaptadorPublicacionMetricool(creds).programar(borrador, dry_run=not publicar_real)`,
4. guardar `id_post`/`estados` y mover la pieza a `publicado`.

Gateado por flag (defecto OFF). **No** se cableó en este cambio porque la Consola está a
mitad de un merge en `main`; conviene hacerlo cuando ese merge asiente.

## Supuestos sin confirmar (no hay token real para validar en vivo)

Aislados en `cuerpo_para`, corregibles en un solo sitio contra la API real:

- **Media por URL externa.** Se asume que `media` admite URLs públicas externas con
  `saveExternalMediaFiles=true`. Si Metricool exige subir el binario a su media-library
  primero, ese paso se añade en `cuerpo_para` / un `_subir_media`.
- **`autoPublish`**: `true` ⇒ Metricool publica solo en `publicationDate`; `false` ⇒
  queda programado con acción manual. `draft=true` lo guarda como borrador.
- **Datos por red obligatorios** (`youtubeData`/`tiktokData`: título, privacidad…): v1
  envía lo mínimo; se añaden por red cuando se validen contra la API real.

Validación recomendada: como `scripts/probar_metricool.py` (sólo lecturas), crear una
prueba que POSTee un `draft=true` (no publica) y confirme la forma de la respuesta.
