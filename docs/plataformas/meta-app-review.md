# Meta (Facebook/Instagram): App Review + Business Verification — paquete de envío

Paquete **listo para ejecutar** para pasar la **App Review** y la **Business Verification** de
Meta y obtener **Advanced Access** a los permisos que `keni-social` necesita para sus **dos casos
de uso**:

- **(a) LECTURA de insights/métricas** de Facebook Pages e Instagram Business de las marcas del
  cliente (UnoTV, Claro Sports, etc.) — lo que ya hace `keni-metricas`.
- **(b) PUBLICACIÓN de contenido** (posts en Página de Facebook + publicación en Instagram) — el
  camino de la Fase 2 (issue #8), hoy en **dry-run** (ver `publicacion-fase2-plan.md`).

> **Issue #5 — el gating principal. Empezar YA.** App Review + Business Verification tardan
> típicamente **2–6 semanas**, y **cada rechazo o cambio reinicia el reloj**. Es el mayor cuello de
> botella externo del producto. Este documento prioriza hacerlo bien **a la primera**.

**Separación de responsabilidades (regla de todo el directorio `plataformas/`):**

| Bloque | Qué prepara **Keni** (código/doc) | Qué hace el **humano** (externo) |
|---|---|---|
| App + config | Privacy Policy URL, screencast, justificaciones, app en modo dev | Crear la app, subirla a revisión, **enviar** |
| Business Verification | Checklist + documentos listos (§3) | Subir documentos y **confirmar el código** en Security Center |
| Permisos | Texto de justificación por permiso (§2) + screencast (§4) | Pegar/enviar en la consola de Meta |
| System User token | Plan + dónde se configura (§6) | Generar el token en Business Settings tras la aprobación |
| Código emparejado | Rellenar `seguidores_netos`/`variacion_vs_anterior` en el camino real (§7) | Validar contra cuentas reales de AMX |

> Alineado con [`../flujo-de-datos-privacidad.md`](../flujo-de-datos-privacidad.md) (la Privacy
> Policy de la app debe reflejar esa declaración) y [`../credenciales.md`](../credenciales.md).

---

## 0. Mapa rápido

| Bloque | Qué se hace | Bloqueo / tiempo |
|---|---|---|
| Tipo de app | Crear app **Business** en developers.facebook.com, vinculada al Business de Keni | Minutos |
| Permisos LECTURA | Advanced Access a `pages_read_engagement`, `read_insights`, `instagram_basic`, `instagram_manage_insights` (+`pages_show_list`) | App Review |
| Permisos PUBLICACIÓN | Advanced Access a `pages_manage_posts`, `instagram_content_publish` | App Review |
| Business Verification | Verificar Keni Engineering LLC en Security Center | Días (documental) |
| Data Use Checkup | Cuestionario de manejo de datos | ~Inmediato si BV aprobada |
| App Review | Descripción + screencast **por permiso** + instrucciones de prueba | 1–4+ semanas |
| System User token | Token que **no caduca** en Business Settings | Tras aprobación |

**Versión de Graph API:** **v21.0** (la que usa el código; ver `meta.py`, constante `BASE`).
Meta versiona cada trimestre y soporta ~2 años; confirmar la vigente antes de enviar.

---

## 1. Tipo de app y configuración inicial — *(prepara Keni / envía el humano)*

1. En [developers.facebook.com](https://developers.facebook.com/) → **My Apps → Create App**, tipo
   **Business**. Vincular la app al **Business portfolio / Business Manager de Keni Engineering
   LLC** desde el inicio (no a una cuenta personal): App Review y Business Verification se evalúan
   a nivel de negocio.
2. Configuración mínima antes de poder enviar a revisión (**App Settings → Basic** y **App Review
   → Requests**):
   - **Nombre y app icon** (1024×1024), **categoría** (p. ej. *Business and Pages*).
   - **Privacy Policy URL** pública y accesible (**obligatoria**) que describa los datos tratados
     (§5). Sin política válida → rechazo.
   - **(Recomendado) User Data Deletion** — URL o instrucciones de eliminación.
   - **Contacto principal** (email del business).
3. Añadir los productos **Facebook Login for Business** e **Instagram** (camino *Instagram API
   setup with Facebook login*, **no** *Instagram Login* — ver §2.7).
4. En **modo desarrollo / Standard Access** la app ya puede llamar a la Graph API sobre cuentas con
   rol (admin/developer/tester) y **Test Users**. Eso basta para **grabar los screencast** y para
   generar las llamadas que Meta exige ver registradas antes de aceptar la solicitud de Advanced
   Access. La publicación se prueba aquí en dry-run (no toca la red) y, contra una Página de
   prueba, en real con `dry_run=False`.

---

## 2. Permisos / scopes (con justificación por permiso)

> **Regla de oro nº1:** cada permiso pedido **debe aparecer ejercido** en el screencast; nada en el
> screencast debe usar un permiso no pedido. **Regla nº2:** **no copiar/pegar** justificaciones
> entre permisos — Meta penaliza textos idénticos; cada uno explica *su* uso concreto.

El código usa **Graph API v21.0**. LECTURA: `fuentes/meta.py` consulta
`GET /{page-id}/insights` (`page_impressions`, `page_impressions_unique`, `page_post_engagements`)
y por pieza `GET /{page-id}/posts`; para IG, `GET /{ig-user-id}/insights` (`impressions`, `reach`,
`accounts_engaged`) y `GET /{ig-user-id}/media`. PUBLICACIÓN: `publicacion/meta.py` arma
`POST /{page_id}/feed|photos|videos` (FB) y el flujo de dos pasos IG `POST /{ig_user_id}/media` →
`POST /{ig_user_id}/media_publish`. Todo sobre **activos que el cliente posee y nos asigna** en su
Business Manager.

### Caso de uso (a) — LECTURA de insights

**2.1 `pages_read_engagement`** — *App Review.*
> La aplicación lee únicamente las métricas e insights agregados de las Páginas de Facebook que el
> cliente administra y nos asigna en su Business Manager (impresiones de página, impresiones
> únicas, interacciones de publicaciones y metadatos de las publicaciones). No modifica ni responde
> contenido en esta función. Estos datos se consolidan en un informe interno de rendimiento para
> que el equipo del cliente decida su estrategia editorial.

**2.2 `read_insights`** — *App Review.*
> La aplicación lee los insights agregados de las Páginas que el cliente posee (impresiones diarias
> y engagement de publicaciones) para construir resúmenes de rendimiento por marca y periodo. Es
> estrictamente de lectura y se limita a los activos asignados a la app.

**2.3 `pages_show_list`** — *App Review (estándar para datos no propios).*
> La aplicación enumera y verifica las Páginas que el cliente administra para resolver el
> identificador de Página correcto y confirmar que el cliente es administrador legítimo. Es además
> **prerrequisito** para resolver el Instagram Business User ID vinculado.

**2.4 `instagram_basic`** — *App Review.*
> La aplicación lee la información de perfil básica y el listado de media de las cuentas de
> **Instagram Business** que el cliente vincula a sus Páginas, como prerrequisito para leer insights
> y para **publicar** en esas cuentas. Es la identificación de la cuenta destino.

**2.5 `instagram_manage_insights`** — *App Review.*
> La aplicación lee los insights agregados (alcance, impresiones, cuentas que interactuaron,
> interacciones totales) de las cuentas de Instagram Business que el cliente administra y vincula a
> sus Páginas, y los insights por publicación, para consolidarlos en informes de rendimiento.

### Caso de uso (b) — PUBLICACIÓN de contenido

**2.6 `pages_manage_posts`** — *App Review.*
> La aplicación publica en el feed de las Páginas de Facebook que el cliente administra y nos asigna,
> **solo después de que un humano del equipo del cliente apruebe el contenido** (cola de aprobación
> con doble revisión; ver el plan de Fase 2). Crea publicaciones (texto, foto o vídeo) a partir del
> copy aprobado. No elimina contenido de terceros ni gestiona anuncios.

**2.7 `instagram_content_publish`** — *App Review.*
> La aplicación publica contenido en las cuentas de **Instagram Business** que el cliente vincula a
> sus Páginas, mediante el flujo de dos pasos de la API (crear contenedor de media y publicarlo),
> **solo tras la aprobación humana** del copy. El contenido es producido y revisado por el equipo de
> redacción del cliente; la app no publica de forma autónoma.

> **Nota crítica — camino de Instagram (riesgo nº1 de rechazo).** Leemos y publicamos en Instagram
> **a través de la Página de Facebook vinculada** (Graph API; `/{ig-user-id}` obtenido desde la
> Página). Ese es el camino **"Instagram API setup with Facebook login"**, cuyos permisos son los de
> §2.4–2.5 + §2.7 (con sus dependencias `pages_show_list` / `pages_read_engagement`). **NO** usamos
> los scopes del camino *Instagram Login* (`instagram_business_*`), que no pasa por Página ni Business
> Manager y rompería el modelo de System User. Pedir el grupo equivocado es causa frecuente de
> rechazo.

### 2.8 `business_management` (opcional / evaluar) — *App Review + Advanced Access + BV obligatoria.*
> Solo si la asignación de activos al System User o la lectura programática de qué Páginas/IG
> pertenecen al Business del cliente se hace **vía API**. Para el caso base (insights y publicación
> sobre activos ya asignados al System User) los §2.1–2.7 bastan. **Si no se ejerce en el
> screencast, NO pedirlo** — un permiso sin uso demostrable es rechazo directo.

> **Verificado contra el *Permissions Reference* de Meta (mayo 2026):** todos los scopes anteriores
> (`pages_read_engagement`, `read_insights`, `pages_show_list`, `pages_manage_posts`,
> `instagram_basic`, `instagram_manage_insights`, `instagram_content_publish`) **requieren App
> Review**; `business_management` requiere además **Advanced Access + Business Verification**.
> Confirmar el estado vigente en la consola antes de enviar (Meta cambia requisitos sin aviso).

**Resumen — lista exacta de permisos a pedir:**

```
LECTURA:     pages_read_engagement · read_insights · pages_show_list
             instagram_basic · instagram_manage_insights
PUBLICACIÓN: pages_manage_posts · instagram_content_publish
OPCIONAL:    business_management   (solo si se gestionan asignaciones por API)
```

---

## 3. Business Verification — checklist *(documentos: Keni · subida/confirmación: humano)*

Requisito para Advanced Access. Una sola vez por Business Manager, sobre **Keni Engineering LLC**.
**Dónde:** Business Manager → **Business Settings → Security Center → Business verification → Start
verification**.

**Datos (deben coincidir EXACTAMENTE con los documentos legales):**

- [ ] **Nombre legal:** `Keni Engineering LLC` (sin abreviar; respetar puntuación del documento).
- [ ] **Dirección legal** (Wyoming) tal cual en los documentos.
- [ ] **Teléfono** del negocio.
- [ ] **Sitio web** / dominio (`kenitech.io`).
- [ ] **Email en el dominio verificado** (p. ej. `owner@kenitech.io`) para recibir el código.

**Documentos aceptados (uno o varios, < 1 año, con nombre + dirección visibles):**

- [ ] Documento de constitución / registro (*Articles of Organization* de la LLC de Wyoming, o
      certificado equivalente).
- [ ] Identificación fiscal (EIN).
- [ ] Comprobante de domicilio del negocio (factura/estado de cuenta a nombre del negocio), si lo
      piden.

**Pasos del humano:** rellenar el formulario con nombre/dirección **idénticos** al documento →
subir documento(s) → recibir y **confirmar el código** (email del dominio, SMS, llamada o WhatsApp)
→ esperar la revisión documental (varios días). Si rechazan, casi siempre es por **discrepancia de
nombre/dirección**: corregir y reenviar.

---

## 4. Guion de screencast — escena por escena *(graba Keni)*

Meta **exige ver cada permiso ejercido** en la app real (no maquetas). Una grabación por permiso, o
una continua donde cada permiso quede claramente identificado en pantalla.

**Requisitos técnicos (Meta, 2026):** **1080p+**, **sin audio** (usar subtítulos/anotaciones en
**inglés**), mostrar el **cursor**, y mostrar **cómo se otorga el permiso** (pantalla de
consentimiento del Login) **y** cómo la app lo **usa** después. El revisor debe ver **los números/
el resultado renderizados** en el producto, no respuestas crudas de la API (`curl`).

**Setup:** una cuenta de prueba (o real con rol) con ≥1 Página de Facebook con publicaciones y una
cuenta de Instagram Business **vinculada**, ambas con datos de insights. MCP en `fuente = "real"` y
el front mostrando los números. Para las escenas de publicación, publicar contra la Página/IG de
**prueba** (con `dry_run=False`) para mostrar el resultado real.

- **Escena 0 — Login y consentimiento (común):** botón "Conectar con Facebook" → **pantalla de
  permisos** con los scopes visibles ("User grants the requested permissions") → conexión
  establecida.
- **Escena 1 — `pages_show_list`:** la app lista las Páginas que administra el usuario y selecciona
  la objetivo.
- **Escena 2 — `pages_read_engagement` + `read_insights`:** insights de la Página (`page_impressions`,
  `page_impressions_unique`, `page_post_engagements`) + top de publicaciones; que se vea el periodo
  (since/until) y los números en el informe.
- **Escena 3 — `instagram_basic`:** identifica la cuenta IG Business vinculada y lista su media.
- **Escena 4 — `instagram_manage_insights`:** insights de IG (`reach`, `impressions`,
  `accounts_engaged`, `total_interactions`) por cuenta y por pieza.
- **Escena 5 — `pages_manage_posts` (publicación FB):** mostrar la **cola de aprobación** (un humano
  aprueba el copy) → la app publica en la Página de prueba (`POST /{page_id}/feed|photos`) → el post
  aparece publicado. Anotar: *"Human approves; app posts to the Page (pages_manage_posts)"*.
- **Escena 6 — `instagram_content_publish` (publicación IG):** tras la aprobación, mostrar el flujo
  de dos pasos (`/media` → `/media_publish`) y el post publicado en IG. Anotar el doble paso.
- **Escena 7 — (solo si se pide §2.8) `business_management`:** la app lee la estructura de activos /
  flujo de asignación. Si no hay pantalla que lo demuestre, **no pedir el permiso**.
- **Cierre:** el informe consolidado de métricas (resultado del caso de uso (a)) y la cola de
  aprobación (frontera del caso (b): el humano aprueba, el sistema no publica solo).

---

## 5. Declaración de uso de datos / privacidad *(prepara Keni)*

Para el **Data Use Checkup** y la **Privacy Policy URL**. Alineado con
[`../flujo-de-datos-privacidad.md`](../flujo-de-datos-privacidad.md).

**Qué datos se tratan:** (lectura) **números agregados** de insights de Páginas e IG Business
—impresiones, alcance, interacciones, engagement— y el texto/enlace de las publicaciones para
identificarlas en el informe; (publicación) el **copy aprobado por el humano** y referencias de
media. **No** se recogen datos personales de seguidores ni de la audiencia.

**Qué NO se almacena:** datos personales de la audiencia (no se solicitan); credenciales del usuario
final (el acceso es por **token de System User**, fuera del control de versiones, nunca enviado al
cliente/IA — ver `../credenciales.md`, `../despliegue-hosted.md`). El MCP **no persiste una BD de
métricas**: lee bajo demanda y devuelve números agregados.

**Dónde viven los datos:** tokens/credenciales en la máquina o el sandbox de Keni (fuera de git);
audio/vídeo y transcripciones **100% local / en sandbox**, nunca a un tercero; números agregados de
métricas y copy → MCP de Keni + API de Anthropic (subprocesador del texto). **Sin datos personales.**

**Garantía de mínimo necesario y aprobación humana:** la app no gestiona anuncios; **publica solo lo
que un humano aprueba** (cola de aprobación con doble revisión, #9) y **el sistema no publica solo**
(modo borrador/dry-run por defecto). Esta declaración es la que debe reflejar la Privacy Policy URL.

---

## 6. System User token (no caduca) — *(plan: Keni · genera: humano tras aprobación)*

**Por qué.** Los tokens de **usuario** de Meta caducan a ~60 días y hay que renovarlos a mano: es el
dolor de Metricool ("se desconecta" sola). El **System User** de Business Manager da un token que
**no caduca**, y es la mitad *hosted* de la arquitectura (`../despliegue-hosted.md`). El adaptador lo
marca con `tipo_token = "system_user"` para **no intentar renovarlo** (refresh = no-op; ver
`fuentes/meta.py`). El mismo token sirve para **leer y publicar** (escenas §4), porque la
publicación reutiliza el cliente HTTP de lectura.

**Cómo obtenerlo** (tras la App Review aprobada para los scopes de §2):

1. Business Manager dueño de las Páginas/IG → **Business Settings → Users → System Users → Add**.
2. **Assign assets:** asignar al System User las **Páginas** (con sus IG Business vinculadas) con
   permiso de lectura/insights **y de gestión de contenido** (para publicar), y darle **control de
   la App**.
3. **Generate new token:** elegir la **App**, marcar los scopes aprobados (los 7 de §2 + opcional).
4. **Token expiration → "Never"**. Si se elige con caducidad, vale 60 días y hay que refrescar vía
   API — no es lo que queremos para el hosted.
5. **Copiar el token en el momento** (no se vuelve a mostrar).
6. Verificar en el [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/):
   debe decir **`Expires: Never`**.

**Configurarlo** en `config.toml` (ver `../credenciales.md`):

```toml
[credenciales.meta]
access_token = "EAAG...token-de-system-user..."
tipo_token  = "system_user"   # NO caduca: el MCP no intenta renovarlo
```

> Aviso: Meta empuja hacia tokens **con caducidad** "por seguridad". La opción no-expira sigue
> disponible al generar; si la retiran, el adaptador soporta refresh con `app_id`/`app_secret` para
> tokens de usuario. Confirmar el comportamiento al generar.

---

## 7. Tarea de código emparejada (issue #5) — `seguidores_netos` / `variacion_vs_anterior`

Issue #5 pide, **en el camino real**, rellenar dos campos que hoy salen vacíos, para validarlos
contra las cuentas reales de AMX cuando la App Review aterrice. **Esto es código, NO se toca en esta
tarea de docs**; se documenta aquí para ejecutarlo en paralelo a la habilitación externa.

**Estado actual (verificado en el repo):**

- `agregador.py` (el camino **real**, clase del servicio sobre `FuenteMetricas`) **hardcodea**:
  ```python
  seguidores_netos=0,        # requiere historico; no se calcula en v1   (agregador.py:155)
  variacion_vs_anterior={},  # idem                                       (agregador.py:156)
  ```
- En cambio el camino **muestra** (`fuentes/muestra.py:376-380`) **sí** rellena ambos (con valores
  deterministas de demo), y `historico.py` **ya tiene la maquinaria** para la variación real:
  `aplicar_variacion(resumen)` busca el `periodo_anterior` guardado y sustituye
  `variacion_vs_anterior` por la variación real de `visualizaciones`/`engagement_pct`
  (`historico.py:130-135`). La tabla `lecturas` ya guarda `seguidores_netos`
  (`historico.py:33,84,96`).

**Trabajo emparejado (resumen para el issue, no se implementa aquí):**

1. **`variacion_vs_anterior` (real):** dejar de hardcodear `{}` en `agregador.py:156` y enganchar
   `historico.aplicar_variacion(...)` en el camino real (igual que se hace para la muestra/CLI), de
   modo que cuando exista una lectura del periodo anterior, la variación sea real (no `{}`).
2. **`seguidores_netos` (real):** el adaptador `fuentes/meta.py` aún no pide el conteo de
   seguidores. Añadir la lectura del conteo (FB Página: `fan_count` / `followers_count`; IG
   Business: `followers_count`) en `_metricas`, propagarlo a `MetricaPlataforma`, y calcular
   `seguidores_netos` como **delta** contra el conteo del periodo anterior (la tabla `lecturas` ya
   lo persiste). Sin histórico previo, el neto es `0` (correcto: no hay base de comparación).
3. **Validación (humano):** con el System User token y cuentas reales de AMX, comprobar que ambos
   campos cuadran con lo que muestran Meta Business Suite / Insights nativos.

> Nota: leer el conteo de seguidores **no añade un permiso nuevo** más allá de los de §2 (lo
> devuelven las mismas lecturas de Página/IG ya cubiertas por `pages_read_engagement` /
> `instagram_basic`). No cambia el alcance de la App Review.

---

## 8. Timeline realista

| Fase | Tiempo estimado | Quién |
|---|---|---|
| Crear app Business + config + Privacy Policy | 1–2 días | Keni + humano (envía) |
| Generar llamadas en modo dev (que Meta exige ver registradas) | 1 día | Keni |
| **Business Verification (Keni Engineering LLC)** | **3–10 días** | Humano (documental); reintentos si hay discrepancias |
| Data Use Checkup | ~Inmediato si BV aprobada | Humano |
| Grabar screencast por permiso + justificaciones (lectura + publicación) | 2–3 días | Keni |
| **App Review (revisión de Meta)** | **1–4+ semanas** | Externo. Cada rechazo/cambio **reinicia** |

**Total realista: 3–6 semanas** desde cero, sin rechazos. Arrancar **Business Verification en
paralelo desde el día 1** (es lo más lento e independiente). Nota: pedir lectura **y** publicación
en la misma revisión amplía la superficie de screencast pero evita un segundo ciclo de revisión.

---

## 9. Errores comunes que provocan rechazo

- **Permiso pedido pero no demostrado** en el screencast (o screencast que ejerce un permiso no
  pedido). Crítico ahora que pedimos publicación: cada escena §5–§6 debe verse.
- **Descripciones idénticas** entre permisos (§2).
- **Grupo de scopes equivocado de Instagram** (`instagram_business_*` del camino Instagram Login en
  vez de `instagram_basic`/`instagram_manage_insights`/`instagram_content_publish` del camino
  Facebook Login) — **riesgo nº1** (§2.7).
- **Publicación sin frontera humana visible:** si el screencast da a entender que la app publica
  sola, contradice la postura del producto. Mostrar la **cola de aprobación**.
- **Privacy Policy URL** ausente, inaccesible o que no describe los datos tratados.
- **Business Verification** con nombre/dirección que no coinciden con el documento (no abreviar;
  documentos < 1 año).
- **Screencast con audio**, baja resolución, UI en español sin subtítulos en inglés, o sin la
  pantalla de consentimiento del Login.
- Usar **credenciales personales del revisor** en vez de cuentas de prueba / instrucciones claras.
- Mostrar **respuestas crudas de la API** en vez del producto usando el dato.
- Pedir `business_management` "por si acaso" sin un flujo que lo ejerza.

---

## Fuentes (consultadas mayo 2026)

- Permissions Reference — Meta for Developers: <https://developers.facebook.com/docs/permissions/>
- `instagram_content_publish` (reference): <https://developers.facebook.com/docs/permissions/reference/instagram_content_publish>
- `instagram_manage_insights` (reference): <https://developers.facebook.com/docs/permissions/reference/instagram_manage_insights>
- App Review — Instagram Platform: <https://developers.facebook.com/docs/instagram-platform/app-review/>
- App Review submission guide: <https://developers.facebook.com/docs/resp-plat-initiatives/individual-processes/app-review/submission-guide>
- Publish Content using the Instagram Platform (flujo de dos pasos): <https://developers.facebook.com/docs/instagram-platform/content-publishing/>
- Content Publishing Limit (100 posts/24h): <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit/>
- System Users — Generate Tokens (Business Management APIs): <https://developers.facebook.com/docs/business-management-apis/system-users/install-apps-and-generate-tokens/>
- Verificar tu negocio en Meta: <https://www.facebook.com/business/help/159334372093366>
- Access Token Debugger: <https://developers.facebook.com/tools/debug/accesstoken/>

> Meta cambia requisitos y nombres de permisos sin previo aviso. Verificar siempre el estado vigente
> en la consola de la app antes de enviar la solicitud.
