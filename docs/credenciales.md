# Credenciales (local por persona)

El MCP `keni-metricas` corre **en la máquina de cada persona** con **sus propias credenciales**. Las llaves **nunca salen de tu equipo**: viven en `~/.config/keni-metricas/config.toml` (o la ruta de `KENI_METRICAS_CONFIG`), que está en `.gitignore` y no se versiona.

Principio: **la llave es revocable y vive contigo, no en la IA.** El MCP usa el token; Claude solo le pide datos al MCP. Revocar = borrar el token del archivo (o revocarlo en la plataforma).

## Por defecto no necesitas nada

Sin credenciales configuradas el MCP funciona con `fuente = "muestra"` (datos representativos y deterministas). Configura credenciales solo cuando quieras **datos reales**: la fuente por defecto es `metricool` (la única de pago; con credenciales por marca en el config) y `real` queda como ruta alternativa de APIs directas por red.

## Por plataforma

La ruta recomendada (publicación y lectura) es el **token de Metricool por marca** (`X-Mc-Auth`
+ `userId`/`blogId`), que cubre FB/IG/X/TikTok/YouTube con una sola integración y **no requiere App
Review, auditoría de TikTok ni tier de pago propio de X**. Las filas de abajo describen la **ruta
alternativa opcional** de API directa por red (útil si se quiere leer métricas sin pasar por
Metricool); no son un bloqueo del producto.

| Plataforma | Qué necesitas | Notas |
|---|---|---|
| **Metricool (recomendado)** | `X-Mc-Auth` (token de Metricool) + `userId` y `blogId` por marca | Una integración para FB/IG/X/TikTok/YouTube. AMX ya tiene plan Advanced. No requiere App Review. |
| **Meta (FB/IG)** — directo opcional | OAuth con `pages_read_engagement`, `read_insights`, `instagram_manage_insights`; `access_token` (o token de **System User**, ver abajo) | Ruta alternativa para leer métricas sin Metricool. IG debe ser cuenta Business. |
| **YouTube** — directo opcional | OAuth scope `yt-analytics.readonly`; `access_token`; channel ID por cuenta | Cuota 10k unidades/día (gestionable); pedir ampliación en Google Cloud si hace falta. |
| **X** — directo opcional | `bearer_token` de X API v2 | Leer métricas e `impression_count` por API directa tiene coste de tier; por eso la ruta por defecto es Metricool. |
| **TikTok** — directo opcional | `access_token` de la Display API | Ruta alternativa; acceso limitado sin trámites propios. |

## Dónde se ponen

Copia `mcp-metricas/credenciales.ejemplo.toml` a `~/.config/keni-metricas/config.toml` y rellena solo los bloques que tengas. Si falta un bloque, esa plataforma se **omite con un aviso** (degradación elegante): el resumen se construye con las que sí estén.

## Meta: token de System User (no caduca) — ruta directa opcional

> Solo aplica a la **ruta alternativa de API directa de Meta**; la ruta por defecto es el token de
> Metricool por marca (sin esto).

Los tokens de usuario de Meta **caducan a los ~60 días** y hay que renovarlos a mano. La alternativa es un **token de System User** de Business Manager, que **no caduca** (no hay renovación manual cada ~60 días) y es el que usa el despliegue *hosted* de Keni para esta ruta directa (ver `docs/despliegue-hosted.md`).

**Cómo obtenerlo** (Meta Business Manager / Business Settings):

1. Entra en **Business Settings** del Business Manager dueño de las páginas/cuentas IG: `https://business.facebook.com/settings`.
2. **Users → System Users → Add**. Crea un System User (rol *Admin* o *Employee* según convenga).
3. **Assign Assets**: asígnale las **Páginas** de Facebook (y sus cuentas de Instagram Business vinculadas) con permiso de lectura de métricas, y la **App** con los permisos `pages_read_engagement`, `read_insights`, `instagram_manage_insights`.
4. **Generate New Token**: elige la App, marca los scopes anteriores y genera. **Copia el token en el momento** (no se vuelve a mostrar).
5. (Opcional) Verifica con el [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/): debe salir `Expires: Never`.

**Cómo se configura.** En el bloque `[credenciales.meta]` (o `[credenciales.instagram]`) de `config.toml`, además del `access_token`, añade `tipo_token = "system_user"`:

```toml
[credenciales.meta]
access_token = "EAAG...token-de-system-user..."
tipo_token  = "system_user"   # marca que NO caduca: el MCP no intenta renovarlo
```

Con `tipo_token = "system_user"` el MCP trata el token como permanente y **no intenta el intercambio `fb_exchange_token`** (no hay nada que renovar). Sin esa clave, el comportamiento es el de siempre (token de usuario que puede renovarse vía `app_id`/`app_secret` ante un 401).

## Buenas prácticas
- Un archivo de credenciales **por persona**, en su máquina. No se comparte ni se sube a git.
- Tokens de Meta **de usuario** de larga duración **caducan (~60 días)**: hay que renovarlos. Los de **System User** (`tipo_token = "system_user"`) **no caducan** (preferidos para el despliegue hosted).
- Para revocar el acceso: borra el token del archivo local **y** revócalo en la plataforma (Meta Business, Google, X, TikTok).
- Nada de contraseñas en crudo: todo es OAuth/token.
