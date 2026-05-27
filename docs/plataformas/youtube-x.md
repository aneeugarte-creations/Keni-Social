# YouTube (cuota + borrador de solicitud) · X (decisión de coste) — issue #7

Los dos cuellos de botella externos que faltan tras Meta ([`meta-app-review.md`](meta-app-review.md))
y TikTok ([`tiktok-audit.md`](tiktok-audit.md)): **(A)** la **cuota** de la YouTube Data API y un
**borrador de solicitud de ampliación listo para enviar**; **(B)** la **decisión de coste de la X
API 2026** (pay-per-use), con recomendación operativa.

**Separación de responsabilidades:**

| Bloque | Qué prepara **Keni** | Qué hace el **humano** (externo) |
|---|---|---|
| YouTube cuota | El **borrador del formulario** (§A.5), el cálculo de uso | **Enviar** el formulario en Google Cloud y atender al equipo de YouTube |
| X coste | El **análisis de tiers + coste por post** (§B), la recomendación | **Decidir el gasto** antes de habilitar publicación; contratar pay-per-use |

> Ámbito: la **lectura de métricas** de ambos adaptadores ya está implementada
> (`fuentes/youtube.py` y `fuentes/x.py`). Aquí evaluamos el coste/cuota de **leer** y, sobre todo,
> de **publicar**, para decidir cuándo y cómo activar cada plataforma.

---

## A. YouTube — cuota y solicitud de ampliación

### A.1 Cómo funciona la cuota
La **YouTube Data API v3** asigna por defecto **10 000 unidades/día** por proyecto de Google Cloud
(reinicio a medianoche, hora del Pacífico). **No** son "10 000 llamadas": cada método cuesta un
número de **unidades** distinto, y toda petición —incluso fallida— cuesta como mínimo 1 unidad.

> La **YouTube Analytics API** (que usa nuestro adaptador para leer métricas:
> `youtubeanalytics.googleapis.com/v2/reports`) tiene su **propia cuota**, separada de la Data API
> v3. Las 10 000 unidades aplican a la **Data API v3**, que es la que usaríamos para **subir vídeos**
> (`videos.insert`) y para resolver títulos (`videos.list`, ya en `_titulos`).

### A.2 La cuenta de unidades (lectura vs subida)
Costes oficiales por llamada de la Data API v3 (consultados mayo 2026):

| Operación | Unidades | Para qué la usamos |
|---|---|---|
| `videos.list` (leer) | **1** | Resolver títulos de piezas (`_titulos` en `youtube.py`). |
| `channels.list` (leer) | 1 | Resolver canal. |
| `search.list` (leer) | 100 | (No la usamos; cara, evitar.) |
| **`videos.insert` (subir vídeo)** | **~100** | **Publicar un vídeo.** |
| `videos.update` | 50 | Editar metadatos. |
| `thumbnails.set` | 50 | Miniatura personalizada. |
| `captions.insert` | 400 | Subir subtítulos. |

> **⚠️ Aclaración sobre el coste de subida (corrige el supuesto del issue #7).** El issue dice
> "subir vídeo ~1600 unidades → ~6/día". Ese era el coste **histórico**. El **4 dic 2025 Google
> redujo `videos.insert` de ~1 600 a ~100 unidades** (consta en el *Revision History* de la API).
> Recalculado:
> - Antes (~1 600 u/subida): **~6 subidas/día** → la subida por API era casi inviable sin ampliación.
> - Ahora (~100 u/subida): **~100 subidas/día** con los mismos 10 000 u → de sobra para una redacción.
>
> Muchas guías de terceros **siguen diciendo 1 600 u / 6 subidas**; están desactualizadas. La fuente
> válida es la *Quota Calculator* oficial. **Aun así, verificar el número vigente antes de
> planificar**, porque Google puede revertir o ajustar.

### A.3 Conclusión cuota
Con `videos.insert ≈ 100`, para el volumen de una redacción (decenas de vídeos/día) **la cuota por
defecto de 10 000 u/día probablemente alcanza** sin ampliación. La lectura de títulos
(`videos.list` = 1 u) es despreciable. **La ampliación deja de ser el bloqueo crítico** que era con
el coste antiguo. Solo hace falta solicitarla si: alto volumen sostenido, varios canales, o si
Google revierte el coste. Por eso el borrador de §A.5 queda **listo pero no urgente** (a diferencia
de Meta, que sí es el gating principal).

### A.4 La auditoría de cumplimiento (si se pide ampliar)
La ampliación **no es automática**: requiere pasar la **auditoría de cumplimiento de YouTube API
Services**.
- **Formulario:** *YouTube API Services - Audit and Quota Extension Form* (en Google Cloud, sección
  de la YouTube Data API).
- **Qué evalúa:** que el proyecto cumple los **YouTube API Services Terms of Service** y las
  **Developer Policies**; da a YouTube visibilidad de los casos de uso de proyectos grandes.
- **Tiempos:** "un miembro del equipo de YouTube te contactará lo antes posible" — sin plazo fijo;
  en la práctica **semanas, a veces meses**. Formularios asociados: *Audited Developer Requests Form*
  (ampliaciones adicionales si ya te auditaron en 12 meses), *Appeals Form* (recurrir un rechazo),
  *Change of Control Form* (cambio de titularidad).

### A.5 Borrador de solicitud — *(listo para que el humano lo pegue/envíe)*

> Rellenar los `<...>` con los datos reales del proyecto antes de enviar. Adjuntar capturas del
> producto usando la API de forma conforme.

**Project ID / number:** `<keni-social-prod / 000000000000>`
**API:** YouTube Data API v3

**Use case (qué hace la app):**
> keni-social es una herramienta de producción para equipos de redes sociales. El equipo del cliente
> (redacción de noticias y deportes — UnoTV / Claro Sports) produce contenido propio y lo publica en
> sus **propios canales de YouTube**. La app usa la YouTube Data API v3 para (1) **subir vídeos**
> producidos y aprobados por el equipo (`videos.insert`) y (2) **resolver metadatos** de esos vídeos
> para informes de rendimiento (`videos.list`). Todo el contenido es propiedad del cliente; **un
> humano aprueba cada publicación** (cola de aprobación con doble revisión). La app no extrae
> contenido de terceros ni hace scraping de búsqueda.

**Why additional quota is needed (justificación + uso esperado):**
> Volumen estimado: `<N>` subidas/día en `<M>` canales propios del cliente.
> Cálculo: `<N>` × ~100 u (`videos.insert`) + lecturas de títulos (`videos.list`, ~1 u c/u) ≈
> `<total>` u/día. Con el límite por defecto de 10 000 u/día esto `<alcanza / se queda corto en
> picos de cobertura (eventos deportivos, jornadas electorales)>`. Solicitamos `<X>` u/día para
> absorber picos sin interrumpir la publicación del cliente. *(Si con el coste vigente las 10 000 u
> alcanzan, NO enviar el formulario: pedir cuota sin necesidad real ralentiza y no aporta.)*

**Data handling (cómo se usan y almacenan los datos):**
> La app no recoge datos personales de la audiencia. Los tokens OAuth viven en la configuración del
> entorno (local por persona o el sandbox alojado de Keni), fuera del control de versiones, y nunca
> se envían a terceros. Los datos de rendimiento son números agregados. Detalle en la política de
> privacidad pública del producto. (Coherente con `../flujo-de-datos-privacidad.md`.)

**Compliance:** Privacy Policy URL pública `<url>`; Terms of Service `<url>`; cumplimiento de las
Developer Policies y normas de branding de YouTube; demo/walkthrough adjunta.

### A.6 Checklist de envío
- [ ] Privacy Policy y ToS públicas y accesibles (de la app, no solo la web corporativa).
- [ ] Project ID / número correcto.
- [ ] Justificación numérica (volumen × coste por método) honesta.
- [ ] Demostración/walkthrough del cliente usando la API de forma conforme.
- [ ] Cumplimiento de Developer Policies + branding de YouTube.
- [ ] Descripción de datos alineada con `../flujo-de-datos-privacidad.md`.

---

## B. X (Twitter) — decisión de coste 2026

### B.1 El modelo: pay-per-use, sin tier gratuito
El **6 feb 2026** X sustituyó el modelo por niveles por un **pay-per-use** como opción por defecto
para nuevos desarrolladores. **No hay tier gratuito.** Los antiguos **Basic ($200/mes)** y **Pro
($5 000/mes)** **ya no se contratan como nuevo desarrollador** (solo siguen para suscriptores
existentes). Para alguien nuevo, las puertas son **pay-per-use** o **Enterprise**.

El **20 abr 2026** los precios se ajustaron de nuevo. Tarifas vigentes (mayo 2026):

| Acción | Precio | Nota |
|---|---|---|
| **Post estándar** (texto/imagen, **sin enlace**) | **$0.015 / post** | Escritura base. |
| **Post con un enlace (URL)** | **$0.20 / post** | ~13× el post estándar. |
| Leer **post propio / bookmarks / followers / lists** ("owned reads") | $0.001 / recurso | |
| Leer **post de terceros** | $0.005 / recurso | |
| Leer **usuario / trends** | $0.010 / recurso | |
| **Tope de lectura** | **2 000 000 lecturas/mes** | Techo duro. |
| **Enterprise** | **desde ~$42 000/mes** (custom) | Firehose, 50M+ lecturas/mes; no es upgrade de checkout. |

| Tier | Estado 2026 | Para nosotros |
|---|---|---|
| **Free** | Discontinuado | — |
| **Pay-per-use** | Por defecto para nuevos | **El que aplica.** Coste = uso real. |
| **Basic ($200/mes)** | Solo suscriptores existentes | No disponible (somos nuevos). |
| **Pro ($5 000/mes)** | Solo suscriptores existentes | No disponible. |
| **Enterprise (~$42 000+/mes)** | Custom | Solo si el volumen lo exigiera. |

### B.2 El problema del post con enlace
Para una redacción de noticias y deportes (**UnoTV / Claro Sports**), **casi todo post lleva un
enlace** a la nota, el vídeo o el directo. A **$0.20/post con URL**, publicar en X se encarece muy
rápido: el mismo post **sin** enlace cuesta **$0.015** — **el enlace multiplica por ~13**.

### B.3 Coste mensual ilustrativo (ajustar a volúmenes reales del cliente)

| Escenario | Volumen/mes | Cálculo | Coste/mes |
|---|---|---|---|
| **Solo lectura de métricas** (lo que ya hace el adaptador) | 100 000 lecturas propias | 100 000 × $0.001 | **$100** |
| Publicar **sin enlace** | 1 000 posts | 1 000 × $0.015 | $15 |
| **Publicar con enlace** (caso real de la redacción) | 1 000 posts | 1 000 × $0.20 | **$200** |
| Publicar con enlace, volumen alto | 5 000 posts | 5 000 × $0.20 | **$1 000** |
| Publicar con enlace, volumen muy alto | 10 000 posts | 10 000 × $0.20 | **$2 000** |

**Leer es barato** (decenas/cientos de USD/mes); **publicar con enlace a volumen de redacción puede
irse a miles de USD/mes** solo en API. Si el volumen exigiera Enterprise, el suelo es **~$42 000/mes**.

> Nota: el coste de X API es **independiente** del coste de generación de copy de keni-social, que va
> por **suscripción global de Claude Code** (`claude -p`, no API de Claude) — ver
> [ADR 0001](../adr/0001-runtime-servicio-compartido.md). El gasto de X es puramente de publicación/
> lectura en la plataforma.

### B.4 Recomendación (issue #7)
1. **Arrancar X en modo solo lectura.** El adaptador (`x.py`) ya lee `public_metrics` e
   `impression_count`; el coste de lectura es bajo y predecible (cabe holgadamente bajo las 2M
   lecturas/mes para una marca). Da valor (medir X) sin asumir coste de publicación.
2. **Gatear la publicación en X tras una decisión explícita de coste.** No activar el publish "por
   completar la matriz": decidir **con el cliente** si el coste por post con enlace (~$0.20)
   compensa frente al alcance que X aporta a su mix. Es **decisión de negocio, no técnica**.
3. **Si se publica, mitigar el coste del enlace:** posts **sin URL** cuando el formato lo permita
   (contexto en el copy, enlace en bio/primer comentario), o reservar el enlace para piezas de alto
   valor. Cada enlace cuesta ~13× un post normal.
4. **Vigilar el tope de 2M lecturas/mes** si se amplía a varias marcas, para no toparlo a mitad de mes.

> Coherente con `../credenciales.md` y `../arquitectura.md`: X entra como **fuente de lectura** desde
> ya; la publicación queda condicionada a una decisión de coste explícita.

---

## Fuentes (consultadas mayo 2026)

**YouTube**
- Quota Calculator (costes por método; `videos.insert`): <https://developers.google.com/youtube/v3/determine_quota_cost>
- Getting Started (cuota por defecto 10 000 u/día): <https://developers.google.com/youtube/v3/getting-started>
- Quota and Compliance Audits (Audit and Quota Extension Form): <https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits>
- Revision History (reducción `videos.insert` ~1 600 → ~100 u, 4 dic 2025): <https://developers.google.com/youtube/v3/revision_history>

**X (Twitter)**
- Anuncio oficial del pay-per-use (6 feb 2026): <https://devcommunity.x.com/t/announcing-the-launch-of-x-api-pay-per-use-pricing/256476>
- Desglose de precios 2026 (post con URL $0.20, ajuste 20 abr 2026): <https://www.blotato.com/blog/twitter-api-pricing>
- Tiers y pay-per-use 2026: <https://postproxy.dev/blog/x-api-pricing-2026/>

> Google y X cambian precios y cuotas sin previo aviso (X ya cambió dos veces en 2026). Verificar
> siempre las tarifas y la cuota vigentes antes de comprometer coste o de planificar.
