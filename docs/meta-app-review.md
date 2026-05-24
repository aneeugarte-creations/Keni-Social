# App Review de Meta: material para Advanced Access

Guía concreta para pasar la **App Review** de Meta y obtener **Advanced Access** a los
permisos que `keni-metricas` necesita para leer insights de Facebook Pages e Instagram
Business de las marcas del cliente (UnoTV, Claro Sports, etc.).

**Por qué importa.** Es el **mayor cuello de botella externo** del producto: App Review +
Business Verification tardan típicamente **2–4+ semanas**, y cada revisión rechazada (o cada
cambio que hagamos a la solicitud) **reinicia el reloj**. Por eso este documento prioriza
hacerlo bien **a la primera**.

> Ámbito: este doc cubre **solo lectura de métricas agregadas** de páginas/cuentas que el
> propio cliente posee y administra. No pedimos publicar, ni gestionar anuncios, ni leer datos
> de terceros. Alineado con `docs/flujo-de-datos-privacidad.md` y `docs/credenciales.md`.

---

## 0. Mapa rápido

| Bloque | Qué se hace | Bloqueo / tiempo |
|---|---|---|
| Tipo de app | Crear app **Business** en developers.facebook.com | Minutos |
| Permisos | Pedir Advanced Access a 5 scopes (abajo) | Requiere los siguientes pasos |
| Business Verification | Verificar Keni Engineering LLC en Security Center | Días (documental) |
| Data Use Checkup | Responder cuestionario de manejo de datos | ~Inmediato si BV aprobada |
| App Review | Descripción + screencast **por permiso** + cuentas de prueba | 1–4+ semanas |
| System User token | Generar token que **no caduca** en Business Settings | Tras aprobación |

---

## 1. Tipo de app y configuración inicial

1. En [developers.facebook.com](https://developers.facebook.com/) → **My Apps → Create App**.
2. Elegir tipo **Business** (es el tipo correcto para apps que usan Graph API de Pages e
   Instagram a través de Business Manager y System Users). Vincular la app al **Business
   portfolio / Business Manager de Keni Engineering LLC** desde el inicio (no a una cuenta
   personal): App Review y Business Verification se evalúan a nivel de negocio.
3. Configuración mínima de la app antes de poder enviar a revisión (**App Settings → Basic** y
   **App Review → Requests**):
   - **Nombre y app icon** (1024×1024).
   - **Categoría** (p. ej. *Business and Pages* / *Utility & Productivity*).
   - **Privacy Policy URL** pública y accesible (obligatoria). Debe describir qué datos se
     tratan; ver §5. Sin URL de política válida, la revisión se rechaza.
   - **(Recomendado) User Data Deletion** — URL o instrucciones de eliminación de datos.
   - **App purpose / "Verify the legitimacy of your business"**: indicar que el acceso es
     para tu propio negocio y sus clientes.
   - **Contacto principal** (email del business).
4. Añadir los productos **Facebook Login for Business** e **Instagram** (la opción *Instagram
   API setup with Facebook login*, no la de Instagram Login — ver §2.5).
5. Mientras tanto, con **Standard Access / modo de desarrollo** la app puede llamar a la Graph
   API sobre cuentas con rol en la app (admin/developer/tester) y **App Roles → Test Users**.
   Eso basta para grabar los screencast y para generar las llamadas que Meta exige ver
   registradas antes de aceptar la solicitud de Advanced Access.

---

## 2. Permisos / scopes que pedimos (con justificación)

`keni-metricas` lee insights a través de **Graph API v21.0** (ver
`mcp-metricas/src/keni_metricas/fuentes/meta.py`, constante `BASE`). El adaptador consulta:

- Facebook Page: `GET /{page-id}/insights` con métricas `page_impressions`,
  `page_impressions_unique`, `page_post_engagements`; y por pieza `GET /{page-id}/posts` con
  `post_impressions`, `post_engaged_users`.
- Instagram Business **vinculado a la Página**: `GET /{ig-user-id}/insights` (`impressions`,
  `reach`, `accounts_engaged`) y por pieza `GET /{ig-user-id}/media` con `impressions`,
  `total_interactions`.

Es **solo lectura** y **solo de cuentas que el propio cliente posee y nos asigna** en su
Business Manager. Pedimos **Advanced Access** a estos permisos (el texto de justificación va
literal en cada solicitud; **no copiar/pegar entre permisos** — Meta lo penaliza):

### 2.1 `pages_read_engagement`
> **Justificación (ES):** La aplicación lee únicamente las métricas e insights agregados de las
> Páginas de Facebook que el propio cliente administra y nos asigna en su Business Manager
> (impresiones de página, impresiones únicas, interacciones de publicaciones y metadatos de las
> publicaciones). No publicamos, no modificamos ni respondemos contenido. Estos datos se
> consolidan en un informe interno de rendimiento para que el equipo del cliente decida su
> estrategia editorial. Sin este permiso no podemos leer las estadísticas de la Página.

Acceso: requiere App Review.

### 2.2 `read_insights`
> **Justificación (ES):** La aplicación lee los insights agregados de las Páginas que el cliente
> posee (impresiones diarias y engagement de publicaciones) para construir resúmenes de
> rendimiento por marca y periodo. Es estrictamente de lectura y se limita a los activos
> asignados a la app. Sin este permiso no podemos acceder a las series temporales de insights de
> la Página.

Acceso: requiere App Review.

### 2.3 `pages_show_list`
> **Justificación (ES):** La aplicación necesita enumerar y verificar las Páginas que el cliente
> administra para resolver el identificador de Página correcto sobre el que leer métricas y para
> confirmar que el cliente es administrador legítimo de esas Páginas. No lista ni accede a
> Páginas de terceros.

Acceso: este permiso **no requiere Advanced Access** (disponible en Standard Access), pero lo
declaramos porque es **dependencia** de la lectura de Páginas e Instagram vinculado.

### 2.4 `instagram_basic`
> **Justificación (ES):** La aplicación lee la información de perfil básica y el listado de
> contenido (media) de las cuentas de **Instagram Business** que el cliente tiene vinculadas a
> sus Páginas de Facebook, como prerrequisito para leer los insights de esas cuentas y de cada
> pieza. Es solo lectura. Sin este permiso no podemos identificar la cuenta de Instagram ni sus
> publicaciones para medir su rendimiento.

Acceso: requiere App Review. Dependencia de `instagram_manage_insights`.

### 2.5 `instagram_manage_insights`
> **Justificación (ES):** La aplicación lee los insights agregados (alcance, impresiones,
> cuentas que interactuaron, interacciones totales) de las cuentas de **Instagram Business** que
> el cliente administra y vincula a sus Páginas, así como los insights de cada publicación, para
> consolidarlos en informes de rendimiento. Es exclusivamente de lectura sobre activos del
> propio cliente. Sin este permiso no podemos medir el rendimiento del contenido de Instagram.

Acceso: requiere App Review.

> **Nota importante sobre el camino de Instagram.** Nuestro adaptador lee los insights de
> Instagram **a través de la Página de Facebook vinculada** (Graph API; `/{ig-user-id}` obtenido
> desde la Página). Ese es el camino **"Instagram API setup with Facebook login"**, cuyos
> permisos son `instagram_basic` + `instagram_manage_insights` (con sus dependencias
> `pages_show_list` / `pages_read_engagement`). **NO** usamos los permisos
> `instagram_business_basic` / `instagram_business_manage_insights`: esos pertenecen al camino
> distinto **"Instagram API with Instagram login"**, que no pasa por una Página de Facebook ni
> por Business Manager y por tanto no encaja con nuestra arquitectura de System User. Pedir los
> scopes del camino equivocado es una causa frecuente de rechazo. (Si en el futuro se migrara a
> Instagram Login, habría que rehacer la solicitud con esos otros scopes.)

### 2.6 `business_management` (opcional / evaluar)
> **Justificación (ES):** Solo si el flujo de asignación de activos al System User o la lectura
> programática de qué Páginas/IG pertenecen al Business del cliente lo requiere. Permite leer la
> estructura de activos del Business Manager del cliente.

Acceso: requiere App Review **y Advanced Access** (y Business Verification). **Evaluar si de
verdad hace falta**: pedir un permiso que el screencast no demuestre en uso es causa directa de
rechazo. Para nuestro caso base (insights de Páginas/IG ya asignados al System User) los §2.1–2.5
suelen bastar; `business_management` solo si gestionamos asignaciones vía API. **Si no se ejerce,
no pedirlo.**

> Verificado contra el *Permissions Reference* de Meta (mayo 2026): `pages_read_engagement`,
> `read_insights`, `instagram_basic`, `instagram_manage_insights` requieren App Review;
> `pages_show_list` no requiere Advanced Access; `business_management` requiere App Review +
> Advanced Access. Confirmar siempre el estado vigente en la consola antes de enviar (Meta
> cambia requisitos sin aviso).

---

## 3. Business Verification — checklist

Business Verification es **requisito** para Advanced Access. Se hace una sola vez por Business
Manager, sobre **Keni Engineering LLC** (la entidad legal; ver naming en el `CLAUDE.md` raíz).

**Dónde:** Business Manager → **Business Settings → Security Center → Business verification →
Start verification**.

**Checklist de datos (deben coincidir EXACTAMENTE con los documentos legales):**

- [ ] **Nombre legal:** `Keni Engineering LLC` (sin abreviar; no usar "LLC"→"L.L.C." salvo que el
      documento lo haga así).
- [ ] **Dirección legal** (Wyoming) tal cual aparece en los documentos.
- [ ] **Teléfono** del negocio.
- [ ] **Sitio web** / dominio (`kenitech.io`).
- [ ] **Email en el dominio verificado** (p. ej. `owner@kenitech.io`) para recibir el código.

**Documentos aceptados (uno o varios, con < 1 año de antigüedad y nombre + dirección visibles):**

- [ ] Documento de constitución / registro del negocio (p. ej. *Articles of Organization* de la
      LLC de Wyoming, o certificado equivalente).
- [ ] Número de identificación fiscal (EIN en EE. UU.).
- [ ] Comprobante de domicilio del negocio (factura de servicios o estado de cuenta bancario a
      nombre del negocio), si lo solicitan.

**Pasos:**

1. Rellenar el formulario con el nombre/dirección **idénticos** al documento (sin abreviaturas).
2. Subir el/los documento(s).
3. Recibir y confirmar el **código de verificación** (email del dominio verificado, SMS o
   llamada al teléfono del negocio, o WhatsApp).
4. Esperar la revisión documental (varios días). Si rechazan, suele ser por **discrepancia de
   nombre/dirección** con el documento: corregir y reenviar.

---

## 4. Guion de screencast — escena por escena

Meta **exige ver cada permiso ejercido** en la app real (no maquetas). Una grabación por
permiso, o una continua donde cada permiso quede claramente identificado en pantalla.

**Requisitos técnicos del video (Meta, 2026):**

- Resolución **1080p o superior** (ancho ≤ 1440 px recomendado).
- **Sin audio** (usar subtítulos/anotaciones/tooltips para narrar).
- **UI en inglés** si es posible; si la UI está en español, añadir subtítulos en inglés.
- Mostrar el **cursor del ratón** en cada interacción (no solo teclado).
- Mostrar **cómo un usuario otorga el permiso** (pantalla de consentimiento de Login) **y** cómo
  la app **usa** ese permiso después.

**Setup previo a grabar:** una **cuenta de prueba** (o cuenta real del cliente con rol en la app)
con al menos una Página de Facebook con publicaciones y una cuenta de Instagram Business
vinculada, ambas con datos de insights. Tener el MCP corriendo (modo `fuente = "real"`) o el
front que muestre los números — el revisor debe **ver los números renderizados**, no solo la
respuesta cruda de la API.

### Escena 0 — Login y consentimiento (común)
1. Mostrar el botón de "Conectar con Facebook" / inicio de Facebook Login for Business.
2. Mostrar la **pantalla de permisos** de Meta donde el usuario concede el acceso, con los
   scopes visibles. Anotar en pantalla: *"User grants the requested permissions"*.
3. Mostrar que la conexión queda establecida.

### Escena 1 — `pages_show_list`
- Tras el login, mostrar la app **listando las Páginas que administra el usuario** y la
  selección de la Página objetivo. Anotar: *"App lists Pages the user manages
  (pages_show_list)"*.

### Escena 2 — `pages_read_engagement` + `read_insights`
- Con la Página seleccionada, mostrar la app **trayendo y mostrando los insights de la Página**:
  impresiones (`page_impressions`), impresiones únicas (`page_impressions_unique`) e
  interacciones (`page_post_engagements`), y el listado de publicaciones top con
  `post_impressions` / `post_engaged_users`.
- Anotar: *"App reads Page insights and post engagement to build the performance report
  (pages_read_engagement, read_insights)"*. Que se vea el periodo (since/until) y los números en
  el informe.

### Escena 3 — `instagram_basic`
- Mostrar la app **identificando la cuenta de Instagram Business vinculada a la Página** y
  listando su media. Anotar: *"App reads the linked Instagram Business account profile and media
  (instagram_basic)"*.

### Escena 4 — `instagram_manage_insights`
- Mostrar la app **trayendo y mostrando los insights de Instagram**: alcance (`reach`),
  impresiones (`impressions`), cuentas que interactuaron (`accounts_engaged`) e interacciones
  por pieza (`total_interactions`).
- Anotar: *"App reads Instagram Business insights (account and per-media) for the report
  (instagram_manage_insights)"*.

### Escena 5 — (solo si se pide §2.6) `business_management`
- Mostrar la app leyendo la **estructura de activos del Business** (qué Páginas/IG pertenecen al
  negocio del cliente) y/o el flujo de asignación. Si no hay una pantalla que lo demuestre, **no
  pedir el permiso**.

> Regla de oro: **cada permiso pedido debe aparecer ejercido** en el screencast, y **nada en el
> screencast debe usar un permiso no pedido**. Cierre del video: vista del informe consolidado de
> métricas (números agregados) que es el resultado final del producto.

---

## 5. Declaración de uso de datos / privacidad

(Para el **Data Use Checkup** y para la sección de privacidad. Alineado con
`docs/flujo-de-datos-privacidad.md`.)

**Qué datos se leen:** exclusivamente **números agregados** de insights de las Páginas e
Instagram Business del cliente —impresiones, alcance, interacciones, engagement y el texto/título
y enlace de las publicaciones para identificarlas en el informe (piezas top). **No** se recogen
datos personales de seguidores ni de la audiencia.

**Qué NO se almacena:**

- No se almacenan datos personales de la audiencia (no se solicitan ni se procesan).
- No se almacenan credenciales del usuario final: el acceso es vía **token de System User** que
  vive en el `config.toml` del entorno (local por persona o el hosted de Keni), **fuera del
  control de versiones** y nunca se envía al cliente/IA (ver `docs/credenciales.md`,
  `docs/despliegue-hosted.md`).
- El MCP no persiste una base de datos de métricas: lee bajo demanda y devuelve **números
  agregados** para construir el resumen de la conversación.

**Dónde viven los datos:**

- **Tokens y credenciales:** en la máquina / entorno hosted, en archivos de configuración fuera
  de git. Nunca salen hacia la IA como parte del copy.
- **Audio/vídeo originales y transcripciones:** **100% local**, nunca salen del equipo.
- **Números agregados de métricas:** los lee el MCP (local o hosted por Keni) y se usan en la
  conversación; viajan, ya agregados, al MCP de Keni y a la API de Anthropic (subprocesador del
  texto). **Sin datos personales.**

**Subprocesadores:** Anthropic (procesa el texto/números agregados que entran en la
conversación). Ver tabla completa "qué dato vive dónde" en `docs/flujo-de-datos-privacidad.md`.

**Garantía de mínimo necesario y solo lectura:** la app **no publica, no programa, no responde y
no gestiona anuncios**; solo lee insights agregados de activos que el cliente posee y asigna. El
humano aprueba todo (modo borrador). Esta declaración es la que debe reflejar la **Privacy Policy
URL** pública de la app (§1).

---

## 6. System User token (no caduca)

**Por qué.** Los tokens de **usuario** de Meta caducan a ~60 días y hay que renovarlos a mano: es
exactamente el dolor de herramientas tipo Metricool que "se desconectan" solas. El **System
User** de Business Manager permite un token que **no caduca**, eliminando esas desconexiones. Es
la mitad *hosted* de la arquitectura (`docs/despliegue-hosted.md`) y lo que el adaptador marca con
`tipo_token = "system_user"` para **no intentar renovarlo** (refresh = no-op; ver `meta.py`).

**Cómo obtenerlo** (tras tener la App Review aprobada para los scopes de §2):

1. Business Manager dueño de las Páginas/IG → **Business Settings → Users → System Users → Add**.
   Crear el System User (rol *Admin* o *Employee* según convenga).
2. **Assign assets:** asignar al System User las **Páginas de Facebook** (con sus cuentas de
   Instagram Business vinculadas) con permiso de lectura/insights, y darle **control de la App**
   (Manage app). Recargar para confirmar la asignación.
3. **Generate new token:** elegir la **App**, marcar los scopes aprobados
   (`pages_read_engagement`, `read_insights`, `pages_show_list`, `instagram_basic`,
   `instagram_manage_insights`).
4. **Token expiration → "Never"** (equivale a *no* marcar el caducado a 60 días). Si se elige el
   modo con caducidad, el token vale 60 días y hay que refrescarlo vía API — **no es lo que
   queremos** para el hosted.
5. **Copiar el token en el momento** (no se vuelve a mostrar).
6. Verificar en el [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/):
   debe decir **`Expires: Never`**.

**Configurarlo** en `config.toml` (ver `docs/credenciales.md`):

```toml
[credenciales.meta]
access_token = "EAAG...token-de-system-user..."
tipo_token  = "system_user"   # NO caduca: el MCP no intenta renovarlo
```

> Aviso: Meta empuja cada vez más hacia tokens **con caducidad** "por seguridad" y puede exigir
> renovación periódica vía la Refresh API en ciertos casos. La opción no-expira sigue disponible
> al generar el token; si en el futuro la retiran, el adaptador soporta el refresh con
> `app_id`/`app_secret` para tokens de usuario. Confirmar el comportamiento al generar.

---

## 7. Timeline realista

| Fase | Tiempo estimado | Notas |
|---|---|---|
| Crear app Business + configuración básica + privacy policy | 1–2 días | Trabajo nuestro. |
| Generar llamadas a la API (modo dev) que Meta exige ver registradas | 1 día | Necesario antes de poder solicitar Advanced Access. |
| Business Verification (Keni Engineering LLC) | **3–10 días** | Documental; reintentos si hay discrepancias de nombre/dirección. |
| Data Use Checkup | ~Inmediato | Si la BV está aprobada. |
| Grabar screencast por permiso + redactar justificaciones | 1–2 días | Trabajo nuestro; lo más controlable. |
| App Review (revisión de Meta) | **1–4+ semanas** | Externo. Cada rechazo o cambio **reinicia** el ciclo. |

**Total realista: 3–6 semanas** desde cero, asumiendo que no hay rechazos. Empezar **Business
Verification en paralelo** desde el día 1 porque es la parte más lenta e independiente.

---

## 8. Errores comunes que provocan rechazo

- **Permiso pedido pero no demostrado** en el screencast (o al revés, screencast que ejerce un
  permiso no solicitado).
- **Descripciones copiadas/idénticas** entre permisos: cada una debe explicar *su* uso concreto.
- **Pedir el grupo de scopes equivocado de Instagram** (`instagram_business_*` del camino
  Instagram Login en vez de `instagram_basic` + `instagram_manage_insights` del camino Facebook
  Login) — ver §2.5. Es nuestro riesgo nº1.
- **Privacy Policy URL** ausente, inaccesible, o que no describe los datos tratados.
- **Business Verification** con nombre/dirección que **no coinciden** con el documento legal (no
  abreviar; documentos < 1 año).
- **Screencast con audio**, baja resolución, UI en español sin subtítulos en inglés, o sin
  mostrar la pantalla de consentimiento del Login.
- Usar **credenciales personales del revisor** en vez de **cuentas de prueba** / instrucciones de
  acceso claras.
- Mostrar **respuestas crudas de la API** en vez del producto usando realmente el dato (el
  revisor quiere ver el caso de uso, no un `curl`).
- Pedir `business_management` "por si acaso" sin un flujo que lo ejerza.

---

## Fuentes (consultadas mayo 2026)

- Permissions Reference — Meta for Developers: <https://developers.facebook.com/docs/permissions/>
- `instagram_manage_insights` (reference): <https://developers.facebook.com/docs/permissions/reference/instagram_manage_insights>
- App Review submission guide (Tutorial): <https://developers.facebook.com/docs/resp-plat-initiatives/individual-processes/app-review/submission-guide>
- Instagram Platform — Instagram API (Facebook Login vs Instagram Login): <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api>
- System Users — Install Apps, Generate, Refresh, Revoke Tokens (Business Management APIs): <https://developers.facebook.com/docs/business-management-apis/system-users/install-apps-and-generate-tokens/>
- System Users overview: <https://developers.facebook.com/docs/business-management-apis/system-users/overview/>
- Verificar tu negocio en Meta / Upload official documents: <https://www.facebook.com/business/help/159334372093366>
- Access Token Debugger: <https://developers.facebook.com/tools/debug/accesstoken/>

> Meta cambia requisitos y nombres de permisos sin previo aviso. Verificar siempre el estado
> vigente en la consola de la app antes de enviar la solicitud.
