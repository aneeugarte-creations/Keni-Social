# Auditoría de TikTok: material para el Content Posting API

Guía concreta para pasar la **auditoría del Content Posting API de TikTok** lo más rápido
posible y poder **publicar en modo público** desde `keni-social` (issue #6, prep de la fase de
publicación). Sin esta auditoría, **todo lo que publique la app queda en `SELF_ONLY`** (solo el
propio creador lo ve): inservible para una redacción.

**Por qué importa.** Es un cuello de botella externo análogo al App Review de Meta
(`docs/meta-app-review.md`): la auditoría tarda típicamente **2–4 semanas** y **cada revisión que
hagamos a la solicitud reinicia el reloj**. Casi todos los rechazos son por **incumplimiento de las
guías de UX** (pantallas de consentimiento, divulgación de la cuenta del creador, selección de
nivel de privacidad), no por el código de subida en sí. Por eso este documento prioriza dejar la
**UI de publicación conforme a la primera**.

> Ámbito: este doc cubre el **Content Posting API** (publicar vídeo/foto). El adaptador de
> **lectura de métricas** (`mcp-metricas/.../fuentes/tiktok.py`, Display API) **no** necesita esta
> auditoría de publicación: usa otra superficie (`video/list`) y su propio flujo de credenciales
> (ver `docs/credenciales.md`). Aquí hablamos de **publicar**, que es lo que la auditoría desbloquea.

---

## 0. Mapa rápido

| Bloque | Qué se hace | Bloqueo / tiempo |
|---|---|---|
| App en TikTok for Developers | Crear app, añadir el producto **Content Posting API** | Minutos |
| Scopes | Pedir `video.publish` (Direct Post) y/o `video.upload` (Upload), `user.info.basic` | Requiere los pasos siguientes |
| Modo sandbox (sin auditar) | Probar el flujo completo; todo sale **`SELF_ONLY`** | Inmediato |
| Construir la UI conforme a UX | Pantallas de consentimiento, creator-info, nivel de privacidad, divulgación comercial | Trabajo nuestro (lo más controlable) |
| Screencast / demo del flujo | Mostrar la UI ejerciendo cada requisito de UX | Trabajo nuestro |
| **Auditoría** (revisión de TikTok) | Enviar app + demo; TikTok revisa el cumplimiento de ToS y UX | **2–4 semanas**; cada revisión **reinicia** |
| Acceso de producción | Tras aprobar: publicar en **público** (`PUBLIC_TO_EVERYONE`) | Tras aprobación |

---

## 1. App, producto y scopes

1. En [developers.tiktok.com](https://developers.tiktok.com/) → crear una app bajo la
   organización de **Keni Engineering LLC** (la entidad legal; ver naming en el `CLAUDE.md` raíz).
2. Añadir el producto **Content Posting API**. Decidir el método (se pueden pedir ambos):
   - **Direct Post** (`video.publish`): la app construye los metadatos (título, privacidad,
     interacción) y **publica directamente**. Es lo que queremos para una redacción (un solo paso
     desde el copy aprobado). **Exige la UI de UX-compliance completa** de §2–§4.
   - **Upload** (`video.upload`): la app **sube** el contenido pero el usuario **termina la
     publicación dentro de la app de TikTok** (elige privacidad y publica en TikTok). Menos
     superficie de cumplimiento, pero peor UX para nuestro flujo. Útil como camino de respaldo.
3. Scopes a solicitar: `video.publish` (Direct Post) y/o `video.upload` (Upload), más
   `user.info.basic` (perfil básico del creador).
4. Configuración mínima de la app antes de poder enviar a auditoría:
   - **Nombre, icono y descripción** reales de la app (no genéricos/de prueba).
   - **Privacy Policy URL** y **Terms of Service URL** públicas y accesibles.
   - **URL de redirección** OAuth válida.
   - Si se usará `PULL_FROM_URL` como método de transferencia (la app pasa una `video_url` en vez
     de subir el binario), hay que **verificar la propiedad del dominio/prefijo de URL** desde el
     que se sirve el vídeo. Con `FILE_UPLOAD` (subida del binario en chunks) no hace falta.

---

## 2. Qué revisa la auditoría (cumplimiento de UX)

La auditoría verifica que la app respeta los **Content Sharing Guidelines** de TikTok. El núcleo es
que **el creador siempre sepa y controle qué se publica, con qué cuenta y con qué privacidad**, sin
valores por defecto que decidan por él. Estos son los requisitos exactos.

### 2.1 Consulta de "creator info" (obligatoria antes de mostrar la pantalla de publicar)

La app **debe llamar** a:

```
POST https://open.tiktokapis.com/v2/post/publish/creator_info/query/
```

…cada vez que se renderiza la pantalla de "Publicar en TikTok" (con datos **frescos**, no
cacheados). La respuesta trae los campos que **deben** alimentar la UI:

| Campo | Uso obligatorio en la UI |
|---|---|
| `creator_nickname` / `creator_username` | Mostrar **a qué cuenta** se va a publicar (el creador debe reconocerla). |
| `creator_avatar_url` | (Recomendado) avatar de la cuenta destino. TTL ~2 h. |
| `privacy_level_options` | Renderizar **solo** estas opciones de privacidad; el `privacy_level` que enviemos al publicar **debe** ser una de ellas. |
| `comment_disabled` / `duet_disabled` / `stitch_disabled` | Atenuar (greyed out) los toggles de interacción que el creador tiene desactivados en su cuenta. |
| `max_video_post_duration_sec` | Validar la duración del vídeo antes de subir; si excede, no permitir publicar. |

`privacy_level_options` depende del tipo de cuenta: las **públicas** ofrecen
`PUBLIC_TO_EVERYONE`, `MUTUAL_FOLLOW_FRIENDS`, `SELF_ONLY`; las **privadas** ofrecen
`FOLLOWER_OF_CREATOR`, `MUTUAL_FOLLOW_FRIENDS`, `SELF_ONLY`.

### 2.2 Selección de nivel de privacidad — **sin valor por defecto**

- La pantalla **no puede traer una privacidad preseleccionada**. El usuario tiene que **elegir**
  explícitamente el nivel.
- El `privacy_level` enviado en `/v2/post/publish/video/init/` **debe coincidir** con una de las
  `privacy_level_options` devueltas por creator-info. Si no coincide, TikTok responde
  `privacy_level_option_mismatch` (y en auditoría, es rechazo directo).
- **Contenido de marca (branded content) no puede ser privado**: si el toggle de "Branded Content"
  está activo, `SELF_ONLY` no puede ofrecerse como privacidad.

### 2.3 Toggles de interacción (comentarios / dúo / stitch)

- Se muestran como toggles **desmarcados por defecto** (ninguna interacción se desactiva sin que el
  usuario lo decida).
- Si la cuenta del creador tiene desactivada una capacidad (p. ej. `duet_disabled = true`), ese
  toggle aparece **atenuado/bloqueado** (no se puede forzar a habilitar algo que la cuenta no
  permite).

### 2.4 Divulgación de contenido comercial

- Toggle de **"Promociono una marca o producto"**, **desactivado por defecto**.
- Al activarlo, el usuario elige entre:
  - **"Tu propia marca"** (`brand_organic_toggle`): la UI debe mostrar que el contenido se
    etiquetará como **"Contenido promocional"**.
  - **"Contenido de marca / partnership"** (`brand_content_toggle`): la UI debe mostrar que se
    etiquetará como **"Colaboración pagada"**.
- Recordatorio: con "Branded Content" activo, la privacidad **no** puede ser `SELF_ONLY`.

### 2.5 Consentimiento de música y de publicación

- Antes de publicar contenido **no comercial**, mostrar el texto:
  *"Al publicar, aceptas la Confirmación de Uso de Música de TikTok"* (Music Usage Confirmation),
  con enlace a las condiciones correspondientes.
- El usuario debe **consentir explícitamente** antes de que empiece la subida (botón claro de
  "Publicar"/"Subir"; nada de auto-publicar sin acción del usuario).

### 2.6 Vista previa, marca de agua y avisos

- Mostrar una **vista previa** del contenido y del fotograma de portada
  (`video_cover_timestamp_ms`).
- **Prohibidas las marcas de agua promocionales** de terceros sobre el contenido.
- **Notificar** al usuario de los tiempos de procesamiento (la publicación no es instantánea).
- Si el contenido es generado por IA, marcarlo (`is_aigc`).

### 2.7 Límites del creador

- Si creator-info indica que el creador alcanzó sus **límites de publicación**, la app debe
  **detener** el intento y avisar (no reintentar a la fuerza).

---

## 3. Checklist de la pantalla "Publicar en TikTok" (UX-compliance)

Marcar todo antes de enviar a auditoría. Esta pantalla es **lo que más se revisa**.

- [ ] Al abrir la pantalla, la app llama a `creator_info/query` y muestra **datos frescos**.
- [ ] Se ve **claramente la cuenta destino** (`creator_nickname`/avatar).
- [ ] El **nivel de privacidad** se presenta **sin preselección**; solo se ofrecen las
      `privacy_level_options` de creator-info.
- [ ] El `privacy_level` enviado **coincide** con una opción válida (evita
      `privacy_level_option_mismatch`).
- [ ] Toggles de **comentarios/dúo/stitch** desmarcados por defecto; atenuados si la cuenta los
      tiene desactivados.
- [ ] Toggle de **contenido comercial** desactivado por defecto; al activarlo, etiquetas correctas
      ("Contenido promocional" / "Colaboración pagada").
- [ ] **Branded Content** nunca queda en privacidad `SELF_ONLY`.
- [ ] Texto de **consentimiento de música** visible antes de publicar.
- [ ] **Vista previa** del contenido y de la portada.
- [ ] **Sin marcas de agua** promocionales.
- [ ] Aviso de **tiempos de procesamiento**.
- [ ] El usuario **consiente explícitamente** antes de que arranque la subida.
- [ ] Si hay límite de publicación del creador, la app **se detiene** y avisa.
- [ ] (Si `PULL_FROM_URL`) **dominio verificado** en la consola de la app.

---

## 4. Guion de la demo / screencast para la auditoría

TikTok quiere **ver la UI real ejerciendo el flujo conforme**, no maquetas ni una herramienta
interna. Grabar el flujo completo de publicación (puede ir con anotaciones en pantalla, en inglés):

1. **Login / autorización**: el creador concede los scopes (`video.publish`/`video.upload`,
   `user.info.basic`). Mostrar la pantalla de consentimiento de TikTok.
2. **Apertura de la pantalla de publicar**: que se vea que la app trae **creator-info fresco** y
   muestra **la cuenta destino** (nickname/avatar).
3. **Selección de privacidad**: mostrar que **no hay preselección** y que solo aparecen las
   opciones válidas; el usuario elige una.
4. **Toggles de interacción**: desmarcados por defecto; demostrar uno atenuado por configuración de
   la cuenta si es posible.
5. **Divulgación comercial**: activar el toggle y mostrar las etiquetas resultantes ("Contenido
   promocional" / "Colaboración pagada").
6. **Consentimiento de música** + **vista previa** + **aviso de procesamiento**.
7. **Publicar**: el usuario pulsa explícitamente; mostrar el resultado publicado con la privacidad
   elegida.

> Regla de oro (igual que en Meta): **cada requisito de UX debe verse ejercido** y nada debe
> contradecir las guías (sin defaults, sin watermark, sin auto-publicar).

---

## 5. Modo sin auditar (sandbox / `SELF_ONLY`) — qué se puede y qué no

Mientras la app **no esté auditada**:

- Se puede **construir y probar el flujo completo** de publicación (init + subida en chunks +
  estado), pero **todo el contenido publicado queda en `SELF_ONLY`** (modo privado: solo lo ve el
  propio creador). No sirve para difundir, pero **sí** para grabar la demo y validar la integración.
- El acceso suele limitarse a **cuentas del propio equipo / usuarios de prueba** asociados a la app.
- `PUBLIC_TO_EVERYONE` y `MUTUAL_FOLLOW_FRIENDS` **no** están disponibles hasta aprobar la auditoría.

**Implicación para `keni-social`:** la publicación a TikTok puede integrarse y demostrarse en modo
borrador/privado desde ya (encaja con el principio de "el humano aprueba todo"), pero la
**difusión pública real está gateada por la auditoría**. Planificar la auditoría con antelación.

---

## 6. Errores comunes que provocan rechazo

- **Valores por defecto en privacidad o interacción**: la causa nº1. La privacidad **debe** elegirse;
  nada preseleccionado.
- **No usar creator-info fresco** o no mostrar la cuenta destino → el usuario no sabe a qué cuenta
  publica.
- **`privacy_level` que no está en `privacy_level_options`** → `privacy_level_option_mismatch`.
- **Branded Content en privado** (`SELF_ONLY`) → contradice las guías.
- **Falta el consentimiento de música** o se auto-publica sin acción explícita del usuario.
- **Marcas de agua promocionales** sobre el contenido.
- **App de prueba / herramienta interna / agregador que copia contenido de otras plataformas**:
  TikTok rechaza casos de uso que no sean publicación legítima de contenido propio.
- **Privacy Policy / ToS** ausentes o inaccesibles.
- (`PULL_FROM_URL`) **dominio no verificado**.
- Mostrar **respuestas crudas de la API** en vez de la UI real ejerciendo el flujo.

---

## 7. Timeline realista

| Fase | Tiempo estimado | Notas |
|---|---|---|
| App + producto Content Posting + scopes + Privacy/ToS | 1–2 días | Trabajo nuestro. |
| Integración del flujo en sandbox (`SELF_ONLY`) + UI de UX-compliance | 3–5 días | Lo más controlable; es donde se gana o se pierde la auditoría. |
| Grabar la demo del flujo conforme | 1 día | Trabajo nuestro. |
| **Auditoría (revisión de TikTok)** | **2–4 semanas** | Externo. **Cada revisión que enviemos reinicia el reloj.** |

**Total realista: 3–6 semanas** desde cero asumiendo que se aprueba a la primera. La palanca para
no repetir ciclos es **dejar la UI 100% conforme antes de enviar** (checklist §3) — el código de
subida casi nunca es el problema, lo es el cumplimiento de UX.

---

## Fuentes (consultadas mayo 2026)

- Content Sharing Guidelines — TikTok for Developers: <https://developers.tiktok.com/doc/content-sharing-guidelines>
- Content Posting API — Get Started (audited vs unaudited / SELF_ONLY): <https://developers.tiktok.com/doc/content-posting-api-get-started>
- Content Posting API — Direct Post reference: <https://developers.tiktok.com/doc/content-posting-api-reference-direct-post>
- Query Creator Info (creator_info/query): <https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info>
- Portal de solicitud de auditoría: <https://developers.tiktok.com/application/content-posting-api>

> TikTok cambia las guías y los requisitos sin previo aviso. Verificar siempre el estado vigente en
> la consola de la app y en los Content Sharing Guidelines antes de enviar a auditoría.
