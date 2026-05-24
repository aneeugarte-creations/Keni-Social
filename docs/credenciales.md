# Credenciales (local por persona)

El MCP `keni-metricas` corre **en la máquina de cada persona** con **sus propias credenciales**. Las llaves **nunca salen de tu equipo**: viven en `~/.config/keni-metricas/config.toml` (o la ruta de `KENI_METRICAS_CONFIG`), que está en `.gitignore` y no se versiona.

Principio: **la llave es revocable y vive contigo, no en la IA.** El MCP usa el token; Claude solo le pide datos al MCP. Revocar = borrar el token del archivo (o revocarlo en la plataforma).

## Por defecto no necesitas nada

Con `fuente = "muestra"` (valor por defecto) el MCP funciona con datos representativos. Configura credenciales solo cuando quieras **datos reales** (`fuente = "real"`).

## Por plataforma

| Plataforma | Qué necesitas | Bloqueo externo | Notas |
|---|---|---|---|
| **Meta (FB/IG)** | OAuth con `pages_read_engagement`, `read_insights`, `instagram_manage_insights`; `access_token` | **App Review de Meta (semanas)** | Hasta aprobar, usa un dev token sobre cuentas de prueba. IG debe ser cuenta Business. |
| **YouTube** | OAuth scope `yt-analytics.readonly`; `access_token`; channel ID por cuenta | Cuota 10k unidades/día (gestionable) | Subir/leer comparten cuota; pedir ampliación en Google Cloud si hace falta. |
| **X** | `bearer_token` de X API v2 | **Tier de pago** | Leer métricas e `impression_count` cuesta. Decidir el coste antes de activar (ver arquitectura). |
| **TikTok** | `access_token` de la Display API | **Auditoría de TikTok** | Sin auditar, acceso muy limitado. |

## Dónde se ponen

Copia `mcp-metricas/credenciales.ejemplo.toml` a `~/.config/keni-metricas/config.toml` y rellena solo los bloques que tengas. Si falta un bloque, esa plataforma se **omite con un aviso** (degradación elegante): el resumen se construye con las que sí estén.

## Buenas prácticas
- Un archivo de credenciales **por persona**, en su máquina. No se comparte ni se sube a git.
- Tokens de Meta de larga duración **caducan (~60 días)**: hay que renovarlos.
- Para revocar el acceso: borra el token del archivo local **y** revócalo en la plataforma (Meta Business, Google, X, TikTok).
- Nada de contraseñas en crudo: todo es OAuth/token.
