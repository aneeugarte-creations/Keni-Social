# YouTube: cuota y auditoría · X: modelo de coste 2026

Material para los dos cuellos de botella externos que faltan tras Meta (`docs/meta-app-review.md`)
y TikTok (`docs/tiktok-audit.md`): **(A)** la **cuota** de la YouTube Data API y su **auditoría de
ampliación**; **(B)** el **modelo de coste de la X API en 2026** (pay-per-use), con el problema de
los posts con enlace y la recomendación operativa (issue #7, prep de la fase de publicación).

> Ámbito: la **lectura de métricas** de ambos adaptadores ya está implementada
> (`mcp-metricas/.../fuentes/youtube.py` y `.../x.py`). Aquí evaluamos el coste/cuota de **leer** y,
> sobre todo, de **publicar**, para decidir cuándo y cómo activar cada plataforma.

---

## A. YouTube — cuota y auditoría

### A.1 Cómo funciona la cuota

La **YouTube Data API v3** asigna por defecto **10 000 unidades/día** por proyecto de Google Cloud
(se reinicia a medianoche, hora del Pacífico). **No** es "10 000 llamadas": cada método cuesta un
número de **unidades** distinto, y toda petición —incluso si falla— cuesta como mínimo 1 unidad.

> Importante: la **YouTube Analytics API** (que usa nuestro adaptador para leer métricas:
> `youtubeanalytics.googleapis.com/v2/reports`) tiene su **propia cuota**, separada de la Data API
> v3. Lo que sigue (10 000 unidades) aplica a la **Data API v3**, que es la que usaríamos para
> **subir vídeos** (`videos.insert`) y para resolver títulos (`videos.list`, que ya llamamos en
> `_titulos`).

### A.2 La cuenta de unidades (lectura vs subida)

Costes oficiales por llamada de la Data API v3 (consultados mayo 2026):

| Operación | Unidades | Para qué la usamos |
|---|---|---|
| `videos.list` (leer) | **1** | Resolver títulos de piezas (`_titulos` en `youtube.py`). |
| `channels.list` (leer) | 1 | Resolver canal. |
| `search.list` (leer) | 100 | (No la usamos; cara, evitar.) |
| **`videos.insert` (subir vídeo)** | **~100** | **Publicar un vídeo.** |
| `videos.update` | 50 | Editar metadatos de un vídeo. |
| `thumbnails.set` | 50 | Poner miniatura personalizada. |
| `captions.insert` | 400 | Subir subtítulos. |

**Cambio relevante (4 dic 2025):** Google **redujo `videos.insert` de ~1 600 a ~100 unidades**
(consta en el *Revision History* de la API). Esto cambia por completo el cálculo:

- Antes (≈1 600 u/subida): **~6 subidas/día** con la cuota por defecto → la subida por API era
  prácticamente inviable sin ampliación.
- Ahora (≈100 u/subida): **~100 subidas/día** con los mismos 10 000 u → de sobra para una redacción.

> Muchas guías de terceros **siguen diciendo 1 600 unidades / 6 subidas al día**: están
> desactualizadas. La fuente válida es la *Quota Calculator* oficial de Google. Aun así, verificar
> el número vigente antes de planificar, porque Google puede revertir o ajustar.

**Conclusión cuota:** con `videos.insert ≈ 100`, para un volumen razonable de publicación de una
redacción (decenas de vídeos/día) **la cuota por defecto de 10 000 u/día probablemente alcanza** sin
necesidad de ampliación. El coste de **lectura** de títulos (`videos.list` = 1 u) es despreciable.
La ampliación de cuota deja de ser el bloqueo crítico que era con el coste antiguo de 1 600.

### A.3 Si aun así hace falta ampliar: la auditoría de cumplimiento

Si en algún momento se supera la cuota (alto volumen, varios canales, o si Google revierte el
coste), la ampliación **no es automática**: requiere pasar la **auditoría de cumplimiento de
YouTube API Services**.

- **Formulario:** *YouTube API Services - Audit and Quota Extension Form*.
- **Qué evalúa:** que el proyecto cumple los **YouTube API Services Terms of Service** y las
  **Developer Policies**. El objetivo declarado de Google es "tener visibilidad de los casos de uso
  de proyectos grandes y asegurar que la API no se usa de forma abusiva".
- **Datos que pide** (preparar con antelación): identidad del proyecto (Project ID y número),
  descripción del caso de uso, justificación de la cuota solicitada, **Privacy Policy** y **Terms
  of Service** públicas, y cómo se usan y almacenan los datos de la API. Suele pedirse también una
  **demostración** del cliente (capturas/walkthrough) que evidencie un uso conforme y el respeto a
  las normas de **branding** de YouTube.
- **Tiempos:** semanas, a veces meses; el equipo de YouTube contacta tras enviar el formulario.
  Existen formularios asociados: *Audited Developer Requests Form* (ampliaciones adicionales si ya
  te auditaron en los últimos 12 meses), *Appeals Form* (recurrir un rechazo) y *Change of Control
  Form* (cambio de titularidad del proyecto).

### A.4 Checklist de solicitud (si se pide ampliación)

- [ ] Privacy Policy y ToS públicas y accesibles (la app, no solo la web corporativa).
- [ ] Descripción honesta del caso de uso (publicar contenido propio del cliente; medir
      rendimiento) y **justificación numérica** de la cuota pedida (volumen estimado × coste por
      método).
- [ ] Project ID / número del proyecto correcto.
- [ ] Demostración/walkthrough del cliente usando la API de forma conforme.
- [ ] Cumplimiento de las **Developer Policies** y normas de branding de YouTube.
- [ ] Datos: qué se lee/escribe, dónde vive, alineado con `docs/flujo-de-datos-privacidad.md`.

---

## B. X (Twitter) — modelo de coste 2026

### B.1 El cambio: de tiers a pay-per-use

El **6 de febrero de 2026** X sustituyó el modelo por niveles por un **pay-per-use** como opción
por defecto para nuevos desarrolladores. **No hay tier gratuito** y los antiguos **Basic
($200/mes)** y **Pro ($5 000/mes)** **ya no se pueden contratar como nuevo desarrollador** (solo
siguen para suscriptores existentes). Las únicas puertas para alguien nuevo son **pay-per-use** o
**Enterprise**.

El **20 de abril de 2026** los precios se ajustaron de nuevo. Tarifas vigentes (mayo 2026):

| Acción | Precio | Nota |
|---|---|---|
| **Post estándar** (texto/imagen, **sin enlace**) | **$0.015 / post** | Escritura base. |
| **Post con un enlace (URL)** | **$0.20 / post** | ~13× el post estándar; subida de ~1 900 % vs el $0.010 inicial. |
| Leer **post propio** | $0.001 / recurso | |
| Leer **post de terceros** | $0.005 / recurso | |
| Leer **usuario / following / followers / trends** | $0.010 / recurso | |
| **Tope de lectura** | **2 000 000 lecturas/mes** | Techo duro. |
| **Enterprise** | **desde ~$42 000/mes** (custom, hasta $50 000+) | Firehose, 50M+ lecturas/mes; no es un upgrade de checkout. |

### B.2 El problema del post con enlace

Para una redacción de noticias y deportes (**UnoTV / Claro Sports**), **casi todo post lleva un
enlace** a la nota, al vídeo o al directo. A **$0.20 por post con URL**, publicar en X se vuelve
caro muy rápido. El detalle perverso: el mismo post **sin** enlace costaría **$0.015**; **el enlace
multiplica el coste por ~13**.

### B.3 Ejemplo de coste mensual (redacción de noticias + deportes)

Supuestos ilustrativos (ajustar a los volúmenes reales del cliente):

| Escenario | Volumen/mes | Cálculo | Coste/mes |
|---|---|---|---|
| **Solo lectura de métricas** (lo que ya hace el adaptador) | 100 000 lecturas de posts propios | 100 000 × $0.001 | **$100** |
| Publicar **sin enlace** | 1 000 posts | 1 000 × $0.015 | $15 |
| **Publicar con enlace** (caso real de la redacción) | 1 000 posts | 1 000 × $0.20 | **$200** |
| **Publicar con enlace, volumen alto** | 5 000 posts | 5 000 × $0.20 | **$1 000** |
| Publicar con enlace, volumen muy alto | 10 000 posts | 10 000 × $0.20 | **$2 000** |

Es decir: **leer** es barato (decenas/cientos de dólares al mes), pero **publicar con enlace a
volumen de redacción puede irse a miles de dólares al mes** solo en API, sin contar trabajo. Y si el
volumen exigiera Enterprise, el suelo es **~$42 000/mes**.

### B.4 Recomendación

1. **Arrancar X en modo solo lectura.** El adaptador de métricas (`x.py`) ya lee `public_metrics`
   (impresiones, likes, replies, retweets, quotes) e `impression_count`; el coste de lectura es
   bajo y predecible (y cabe holgadamente bajo el tope de 2M lecturas/mes para una sola marca). Esto
   da valor (medir X) sin asumir el coste de publicación.
2. **Gatear la publicación en X detrás de una decisión explícita de coste.** No activar el publish
   en X "por completar la matriz": antes hay que decidir, con el cliente, si el coste por post con
   enlace (~$0.20) compensa frente al alcance que X aporta a su mix. Es una decisión de negocio, no
   técnica.
3. **Si se publica, mitigar el coste del enlace:** evaluar posts **sin URL** cuando el formato lo
   permita (el copy lleva el contexto; el enlace en la bio/primer comentario), o reservar el enlace
   para piezas de alto valor. Cada enlace cuesta ~13× un post normal.
4. **Vigilar el tope de 2M lecturas/mes** si se amplía a varias marcas, para no toparlo a mitad de
   mes.

> Esto es coherente con `docs/credenciales.md` y `docs/arquitectura.md`: X entra como **fuente de
> lectura** desde ya; la publicación queda condicionada a una decisión de coste explícita.

---

## Fuentes (consultadas mayo 2026)

**YouTube**
- Quota Calculator (costes por método; `videos.insert`): <https://developers.google.com/youtube/v3/determine_quota_cost>
- Getting Started (cuota por defecto de 10 000 u/día): <https://developers.google.com/youtube/v3/getting-started>
- Quota and Compliance Audits (Audit and Quota Extension Form): <https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits>
- Revision History (reducción de `videos.insert` ~1 600 → ~100 u, 4 dic 2025): <https://developers.google.com/youtube/v3/revision_history>

**X (Twitter)**
- Anuncio oficial del pay-per-use (6 feb 2026): <https://devcommunity.x.com/t/announcing-the-launch-of-x-api-pay-per-use-pricing/256476>
- Desglose de precios 2026 (post con URL $0.20, ajuste del 20 abr 2026): <https://www.blotato.com/blog/twitter-api-pricing>
- Tiers y pay-per-use 2026: <https://postproxy.dev/blog/x-api-pricing-2026/>

> Tanto Google como X cambian precios y cuotas sin previo aviso (X ya cambió dos veces en 2026).
> Verificar siempre las tarifas y la cuota vigentes antes de comprometer coste o de planificar.
