# TikTok: Content Posting API directo — ruta opcional (no necesaria con Metricool)

> **La publicación a TikTok ya está cubierta por Metricool** (ver
> [`publicacion-metricool.md`](publicacion-metricool.md)): no hace falta esta auditoría para publicar
> desde `keni-social`. Este doc describe la **ruta directa** por el **Content Posting API de TikTok**
> como **alternativa opcional**, por si alguna vez se quisiera integrar TikTok sin pasar por
> Metricool. **No es un bloqueante** de publicación.

Si se eligiera la ruta directa, habría que pasar la **auditoría del Content Posting API de TikTok**
para **publicar en público**. Sin esa auditoría, **todo lo que publique la app por esa vía queda en
`SELF_ONLY`** (solo lo ve el propio creador) y el cliente API solo permite **hasta 5 usuarios**
publicando en una ventana de 24 h: inservible para una redacción.

> **Coste de la ruta directa.** La auditoría tarda **2–4 semanas** con **varias rondas de feedback**,
> y **cada revisión que enviemos reinicia el reloj**. Casi todos los rechazos son por **incumplimiento
> de UX** (pantallas de consentimiento, divulgación de la cuenta del creador, nivel de privacidad),
> **no** por el código de subida. Por eso lo que más controla el resultado es dejar la **UI de
> publicación 100% conforme a la primera**. Este coste es exactamente lo que Metricool evita.

**Separación de responsabilidades:**

| Bloque | Qué prepara/construye **Keni** | Qué hace el **humano** (externo) |
|---|---|---|
| App + producto + scopes | Config de la app, Privacy/ToS, redirect OAuth | Crear la app, **enviar** la solicitud |
| UX-compliance | **Construir la pantalla "Publicar en TikTok"** conforme (§2–§3) | — |
| Demo / screencast | Grabar el flujo + (si se pide) dejar un acceso de prueba (§4) | Dar acceso de demo a TikTok si lo piden |
| **Auditoría** | Responder a las rondas de feedback con cambios | **Enviar** y atender la correspondencia de TikTok |

> Ámbito: este doc cubre el **Content Posting API** (publicar vídeo/foto). El adaptador de
> **lectura de métricas** (`fuentes/tiktok.py`, Display API) **no** necesita esta auditoría: usa otra
> superficie y su propio flujo de credenciales (ver `../credenciales.md`). Aquí hablamos de
> **publicar**, que es lo que la auditoría desbloquea.

---

## 0. Mapa rápido

| Bloque | Qué se hace | Bloqueo / tiempo |
|---|---|---|
| App en TikTok for Developers | Crear app bajo Keni Engineering LLC, añadir **Content Posting API** | Minutos |
| Scopes | `video.publish` (Direct Post) y/o `video.upload`, `user.info.basic` | App Review/auditoría |
| Modo sin auditar (sandbox) | Probar el flujo completo; todo sale **`SELF_ONLY`**, máx. 5 usuarios/24h | Inmediato |
| **Construir la UI conforme** | Consentimiento, creator-info (username+avatar), privacidad, divulgación comercial | Trabajo de Keni (lo más controlable) |
| Demo del flujo | Mostrar la UI ejerciendo cada requisito | Trabajo de Keni |
| **Auditoría** | TikTok revisa ToS + UX, varias rondas | **2–4 semanas**; cada revisión **reinicia** |
| Producción | Tras aprobar: publicar en **público** (`PUBLIC_TO_EVERYONE`) | Tras aprobación |

---

## 1. App, producto y scopes — *(config: Keni · envío: humano)*

1. En [developers.tiktok.com](https://developers.tiktok.com/) → crear app bajo **Keni Engineering
   LLC**.
2. Añadir el producto **Content Posting API**. Método (se pueden pedir ambos):
   - **Direct Post** (`video.publish`): la app arma metadatos (título, privacidad, interacción) y
     **publica directamente**. Es lo que queremos para una redacción (un solo paso desde el copy
     aprobado). **Exige la UI de UX-compliance completa** de §2–§3.
   - **Upload** (`video.upload`): la app **sube** pero el usuario **termina la publicación dentro de
     la app de TikTok**. Menos superficie de cumplimiento, peor UX. Camino de respaldo.
3. Scopes: `video.publish` y/o `video.upload`, más `user.info.basic` (perfil básico del creador).
4. Config mínima antes de auditar:
   - **Nombre, icono y descripción** reales (no genéricos/de prueba).
   - **Privacy Policy URL** y **Terms of Service URL** públicas y accesibles.
   - **Redirect URL** OAuth válida.
   - Si se usa `PULL_FROM_URL` (pasar una `video_url` en vez de subir el binario), **verificar la
     propiedad del dominio/prefijo de URL**. Con `FILE_UPLOAD` (subida en chunks) no hace falta.

---

## 2. Qué revisa la auditoría (cumplimiento de UX)

La auditoría verifica los **Content Sharing Guidelines**: que **el creador siempre sepa y controle
qué se publica, con qué cuenta y con qué privacidad**, sin valores por defecto que decidan por él.

### 2.1 Consulta de "creator info" (obligatoria antes de mostrar la pantalla de publicar)

La app **debe llamar** a `POST https://open.tiktokapis.com/v2/post/publish/creator_info/query/`
cada vez que se renderiza la pantalla de "Publicar en TikTok" (datos **frescos**, no cacheados). La
respuesta alimenta la UI:

| Campo | Uso obligatorio en la UI |
|---|---|
| `creator_nickname` / `creator_username` | Mostrar **a qué cuenta** se publica. **Requisito duro** que TikTok verifica: si no se ve el username, rechazo. |
| `creator_avatar_url` | Avatar de la cuenta destino (recomendado; TTL ~2 h). |
| `privacy_level_options` | Renderizar **solo** estas opciones; el `privacy_level` enviado **debe** ser una de ellas. |
| `comment_disabled` / `duet_disabled` / `stitch_disabled` | Atenuar los toggles de interacción que la cuenta tiene desactivados. |
| `max_video_post_duration_sec` | Validar la duración antes de subir; si excede, no publicar. |

`privacy_level_options` depende del tipo de cuenta: **públicas** → `PUBLIC_TO_EVERYONE`,
`MUTUAL_FOLLOW_FRIENDS`, `SELF_ONLY`; **privadas** → `FOLLOWER_OF_CREATOR`, `MUTUAL_FOLLOW_FRIENDS`,
`SELF_ONLY`.

### 2.2 Selección de privacidad — **sin valor por defecto**
- La pantalla **no puede traer privacidad preseleccionada**: el usuario **elige** explícitamente.
- El `privacy_level` enviado a `/v2/post/publish/video/init/` **debe coincidir** con una opción de
  creator-info; si no, TikTok responde `privacy_level_option_mismatch` (rechazo en auditoría).
- **Branded content no puede ser privado**: con "Branded Content" activo, `SELF_ONLY` no se ofrece.

### 2.3 Toggles de interacción (comentarios / dúo / stitch)
- **Desmarcados por defecto**; **atenuados/bloqueados** si la cuenta los tiene desactivados (no se
  puede forzar lo que la cuenta no permite).

### 2.4 Divulgación de contenido comercial
- Toggle **"Promociono una marca o producto"**, **desactivado por defecto**. Al activarlo:
  - **"Tu propia marca"** (`brand_organic_toggle`) → etiqueta **"Contenido promocional"**.
  - **"Contenido de marca / partnership"** (`brand_content_toggle`) → etiqueta **"Colaboración
    pagada"**.
- Con Branded Content activo, la privacidad **no** puede ser `SELF_ONLY`.

### 2.5 Consentimiento de música y de publicación
- Antes de publicar contenido **no comercial**, mostrar: *"Al publicar, aceptas la Confirmación de
  Uso de Música de TikTok"* (Music Usage Confirmation) con enlace.
- El usuario **consiente explícitamente** antes de que empiece la subida (botón claro de "Publicar";
  nada de auto-publicar).

### 2.6 Vista previa, marca de agua y avisos
- **Vista previa** del contenido y de la portada (`video_cover_timestamp_ms`).
- **Prohibidas las marcas de agua** promocionales de terceros sobre el contenido.
- **Notificar** los tiempos de procesamiento (la publicación no es instantánea).
- Si el contenido es generado por IA, marcarlo (`is_aigc`).

### 2.7 Límites del creador
- Si creator-info indica que el creador alcanzó sus **límites de publicación**, la app **detiene** el
  intento y avisa (no reintentar a la fuerza).

---

## 3. Checklist de la pantalla "Publicar en TikTok" — *(esto lo construye Keni)*

La UX exacta a construir para salir de `SELF_ONLY`. Es lo que más se revisa. Marcar todo antes de
enviar a auditoría.

- [ ] Al abrir, la app llama a `creator_info/query` y muestra **datos frescos**.
- [ ] Se ve **claramente la cuenta destino** (`creator_username` + avatar) — **requisito duro**.
- [ ] **Nivel de privacidad sin preselección**; solo se ofrecen las `privacy_level_options`.
- [ ] El `privacy_level` enviado **coincide** con una opción válida (evita
      `privacy_level_option_mismatch`).
- [ ] Toggles de **comentarios/dúo/stitch** desmarcados por defecto; atenuados si la cuenta los
      tiene desactivados.
- [ ] Toggle de **contenido comercial** desactivado por defecto; etiquetas correctas al activarlo
      ("Contenido promocional" / "Colaboración pagada").
- [ ] **Branded Content** nunca queda en `SELF_ONLY`.
- [ ] Texto de **consentimiento de música** visible antes de publicar.
- [ ] **Vista previa** del contenido y de la portada.
- [ ] **Sin marcas de agua** promocionales.
- [ ] Aviso de **tiempos de procesamiento**.
- [ ] El usuario **consiente explícitamente** antes de que arranque la subida.
- [ ] Si hay límite del creador, la app **se detiene** y avisa.
- [ ] (Si `PULL_FROM_URL`) **dominio verificado** en la consola de la app.

> Encaje con keni-social: esta pantalla es la cara "publicar a TikTok" de la **cola de aprobación**
> ya construida en #9 (un humano aprueba el copy → la pantalla conforme recoge el consentimiento de
> publicación a TikTok). Hereda la postura "el humano aprueba; el sistema no publica solo".

---

## 4. Guion de la demo / screencast — *(graba Keni)*

TikTok quiere **ver la UI real ejerciendo el flujo conforme**, no maquetas ni una herramienta
interna. Si pide probar en vivo, hay que **dar acceso a una demo** (URL para abrir la app, email +
contraseña de prueba, y una guía breve de cómo publicar). Grabar el flujo completo (anotaciones en
inglés):

1. **Login / autorización:** el creador concede los scopes (`video.publish`/`video.upload`,
   `user.info.basic`); mostrar la pantalla de consentimiento de TikTok.
2. **Apertura de la pantalla de publicar:** que se vea **creator-info fresco** y **la cuenta destino**
   (username + avatar).
3. **Selección de privacidad:** **sin preselección**; solo las opciones válidas; el usuario elige.
4. **Toggles de interacción:** desmarcados por defecto; demostrar uno atenuado si es posible.
5. **Divulgación comercial:** activar el toggle y mostrar las etiquetas resultantes.
6. **Consentimiento de música** + **vista previa** + **aviso de procesamiento**.
7. **Publicar:** el usuario pulsa explícitamente; mostrar el resultado con la privacidad elegida.

> Regla de oro (igual que Meta): **cada requisito de UX debe verse ejercido** y **cada scope pedido**
> debe aparecer en la demo; nada debe contradecir las guías (sin defaults, sin watermark, sin
> auto-publicar).

---

## 5. Modo sin auditar (sandbox / `SELF_ONLY`) — qué se puede y qué no

Mientras la app **no esté auditada**:

- Se puede **construir y probar el flujo completo** (init + subida en chunks + estado), pero **todo
  queda en `SELF_ONLY`** (solo lo ve el creador). Sirve para grabar la demo y validar la
  integración, **no para difundir**.
- El cliente API permite **hasta 5 usuarios** publicando en una ventana de 24 h; el acceso se limita
  a cuentas del propio equipo / usuarios de prueba de la app.
- `PUBLIC_TO_EVERYONE` y `MUTUAL_FOLLOW_FRIENDS` **no** están disponibles hasta aprobar la auditoría.

**Implicación:** por la ruta directa, la publicación a TikTok puede integrarse y demostrarse en modo
privado **desde ya** (encaja con "el humano aprueba todo"); la **difusión pública real estaría gateada
por la auditoría**. Por eso el camino vigente es **Metricool**, que publica en público sin esa
auditoría.

---

## 6. Errores comunes que provocan rechazo

- **Valores por defecto** en privacidad o interacción (causa nº1): la privacidad **debe** elegirse.
- **No mostrar la cuenta destino** (`creator_username` + avatar): requisito duro verificado.
- **No usar creator-info fresco**.
- **`privacy_level` fuera de `privacy_level_options`** → `privacy_level_option_mismatch`.
- **Branded Content en `SELF_ONLY`**.
- **Falta el consentimiento de música** o se **auto-publica** sin acción explícita.
- **Marcas de agua / logos / texto promocional** añadidos sobre el contenido.
- **Caso de uso poco claro / herramienta interna / agregador** que copia contenido de otras
  plataformas: TikTok rechaza casos que no sean publicación legítima de contenido propio.
- **Privacy Policy / ToS** ausentes o inaccesibles.
- (`PULL_FROM_URL`) **dominio no verificado**.
- **No responder a la correspondencia** de TikTok / demo con caídas de uptime / scope sin cobertura
  en la demo.

---

## 7. Timeline realista

| Fase | Tiempo estimado | Quién |
|---|---|---|
| App + producto + scopes + Privacy/ToS | 1–2 días | Keni + humano (envía) |
| Integración en sandbox (`SELF_ONLY`) + UI de UX-compliance | 3–5 días | Keni (donde se gana/pierde la auditoría) |
| Grabar la demo + (si piden) montar acceso de prueba | 1 día | Keni |
| **Auditoría (revisión de TikTok)** | **2–4 semanas**, varias rondas | Externo. **Cada revisión reinicia** |

**Total realista: 3–6 semanas** desde cero asumiendo aprobación a la primera. La palanca es dejar la
UI **100% conforme antes de enviar** (checklist §3) — el código de subida casi nunca es el problema.

---

## Fuentes (consultadas mayo 2026)

- Content Sharing Guidelines — TikTok for Developers: <https://developers.tiktok.com/doc/content-sharing-guidelines>
- Content Posting API — Get Started (audited vs unaudited / `SELF_ONLY` / 5 usuarios/24h): <https://developers.tiktok.com/doc/content-posting-api-get-started>
- Content Posting API — Direct Post reference: <https://developers.tiktok.com/doc/content-posting-api-reference-direct-post>
- Query Creator Info (`creator_info/query`): <https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info>
- Portal de solicitud de auditoría: <https://developers.tiktok.com/application/content-posting-api>

> TikTok cambia las guías y los requisitos sin previo aviso. Verificar el estado vigente en la
> consola de la app y en los Content Sharing Guidelines antes de enviar a auditoría.
