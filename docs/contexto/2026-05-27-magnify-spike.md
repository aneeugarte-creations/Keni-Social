# Spike: ¿se puede exportar la parrilla a Magnify? (API / formato de import)

- **Fecha:** 2026-05-27
- **Issue:** [#148](https://github.com/kenitech-io/keni-social/issues/148) · Ficha **F8** del
  spec operativo (`docs/contexto/2026-05-27-elias-spec-operativo.md`).
- **Tipo:** spike de investigación documental (no es build).
- **Pregunta:** ¿podemos meter la parrilla (eventos + horarios de transmisiones en vivo) en
  "Magnify" de forma automática —vía API o un formato de import (CSV/XML/EPG/ICS/JSON)— en lugar de
  recapturarla a mano? Solo entonces decidir build.

---

## TL;DR

- El producto es casi con seguridad **Magnifi by VideoVerse** (no "Magnify"; ahora propiedad de
  Minute Media), la plataforma de clipping automático de deportes en vivo. **Confirmar el nombre
  exacto con Elías** (§5 Q4) porque hay varios productos de nombre parecido.
- **Sí existe API.** Magnifi publica una **Partner Integration API** (REST/JSON sobre HTTPS) con un
  grupo **Match Schedule** dedicado: `POST /v1/match-schedule` crea cada evento de la parrilla, y
  hay endpoints para listar / actualizar / borrar e incluso disparar el clipeo del stream
  (`invoke-stream`). Auth por par de cabeceras `x-access-key` + `x-access-secret`.
- **NO hay import de archivo** (ni CSV, ni XML, ni EPG, ni ICS, ni carga masiva). La parrilla se
  carga **evento por evento vía JSON**. Eso ya nos quita el "re-tecleo a mano", que es el objetivo.
- **Recomendación: NO-BUILD ahora; build pequeño después, condicionado** a que (1) Elías confirme
  que usan Magnifi by VideoVerse y (2) AMX/Claro nos consiga **credenciales de partner**. Sin esas
  dos cosas no se puede integrar. Esfuerzo si se desbloquea: **~2–4 días** para un puente
  parrilla→Match Schedule. Fallback inmediato sin API: ver §6.

---

## 1. ¿Qué "Magnify" es?

"Magnify" no aparece como producto de clipping; los candidatos reales de clipping de deportes en
vivo son:

| Candidato | Qué es | Encaje con "clipeo de transmisiones en vivo" |
|---|---|---|
| **Magnifi by VideoVerse** | Plataforma SaaS de IA que detecta momentos clave en feeds en vivo (HLS/RTMP/SRT) y genera highlights/clips cortos, recortados por plataforma. Adquirida por Minute Media (2024). | **Muy alto.** Mismo dominio fonético ("Magnify"≈"Magnifi"), mismo caso de uso, presencia fuerte en LatAm/deportes. Candidato principal. |
| WSC Sports | Highlights automáticos por IA para ligas grandes (NBA, PGA, NHL). Entrega vía API/CMS. | Posible, pero suele ser para rights-holders muy grandes; no calza con "poner la parrilla yo a mano". |
| Grabyo | Clipping/edición/publicación en vivo. **Se integra con Magnifi** (partnership NAB 2024). | Posible, pero más herramienta de edición/publicación que de parrilla. |

**Conclusión de identificación:** el más probable es **Magnifi by VideoVerse**, y el resto de la
investigación se centra en él. Hay que **validar con Elías** (Q4) antes de construir nada.

Fuentes: <https://magnifi.ai/> · <https://magnifi.ai/about-us> ·
<https://about.grabyo.com/automated-highlights-magnifi/> ·
<https://www.minutemedia.com/post/minute-media-acquires-videoverse-owner-of-magnifi-a-leading-ai-sports-video-technology-platform> ·
<https://wsc-sports.com/> (descartado como principal).

---

## 2. ¿Magnifi tiene API o import? Sí — API REST de partner

Magnifi publica documentación de integración para partners (portal Postman público en
**`https://docs.prod.videoverse.dev/`**). El propio documento dice:

> "Magnifi offers a comprehensive suite of API endpoints… These endpoints support key functions such
> as stream ingestion, video downloads, metadata retrieval, and **management of match schedules** and
> team rosters."

- **Base URL:** `https://partner.prod.videoverse.dev/v1/`
- **Transporte:** HTTPS, cuerpos **JSON** (REST). No hay endpoints de carga de archivo / bulk / CSV.
- **Autenticación:** dos cabeceras en cada request:
  - `x-access-key: pak_xxxxxxxx-...` (Access Key)
  - `x-access-secret: <secret>`
  - Las credenciales **las entrega Magnifi al partner** ("provided by Magnifi… contact your Magnifi
    representative"). Un key/secret incorrecto devuelve `401 Unauthorized`. → **Es API de partner,
    no abierta: requiere que AMX/Claro nos dé (o nos comparta) credenciales.**

Fuente: <https://docs.prod.videoverse.dev/> (colección Postman "Magnifi x Partner Integration
Documentation"). Verificado descargando la colección JSON el 2026-05-27.

### 2.1 Grupo "Match Schedule" (esto es la parrilla)

Endpoints verificados en la colección:

| Método | Endpoint | Para qué |
|---|---|---|
| `POST` | `/v1/match-schedule` | **Crear un evento de la parrilla** |
| `GET` | `/v1/match-schedule?startTime=…&endTime=…` | Listar la parrilla en un rango de fechas |
| `GET` | `/v1/match-schedule/{id}` | Leer un evento |
| `PATCH` | `/v1/match-schedule/{id}` | Actualizar un evento |
| `DELETE` | `/v1/match-schedule/{id}` | Borrar un evento |
| `POST` | `/v1/match-schedule/{id}/de-link` | Desvincular del stream |
| `POST` | `/v1/match-schedule/{id}/invoke-stream` | **Disparar el clipeo del stream** del evento |

**Payload de "Create match schedule"** (verbatim del ejemplo oficial):

```json
{
  "name": "Example Match",
  "matchStartTime": "2024-11-15T23:30:00",
  "timezone": "Etc/UTC",
  "teams": [
    { "teamId": "EzuBP0z12", "type": "HOME" },
    { "teamId": "8pAIPh9.y", "type": "AWAY" }
  ],
  "tournament": "KQerB10o3",
  "category": "cricket"
}
```

Es decir, la parrilla se modela como **un POST por evento**, con nombre, hora de inicio, zona
horaria, equipos, torneo y categoría/deporte.

### 2.2 Dependencia: equipos/torneos por ID

El payload referencia `teamId` y `tournament` por ID, no por texto libre. Hay endpoints
`POST /…Team` (`Add team`) y `POST /…Tournament` (`Add tournament`) y sus `GET all` para
resolver/crear esos IDs primero. Para deportes con equipos (fútbol) habría que mantener un mapeo
nombre→ID. Para eventos sin equipos fijos puede bastar `name` + `matchStartTime` (a confirmar con la
estructura real de la parrilla de Elías).

### 2.3 invoke-stream (clipeo)

`POST /v1/match-schedule/{id}/invoke-stream` arranca el procesamiento de un feed:

```json
{
  "templateName": "Test mp4 template",
  "url": "https://…/master_highest.m3u8",
  "homeTeamId": "EzuBP0123",
  "awayTeamId": "8pAIPh321",
  "title": "new title",
  "fireAt": "2025-11-10T09:30:30.293Z"
}
```

Confirma el flujo completo: parrilla → stream → clips. Lo que pide Elías (cargar la parrilla) es la
**parte de programación**, lo demás ya lo opera su equipo en Magnifi.

---

## 3. Formatos de import (CSV/XML/EPG/ICS/JSON)

- **JSON vía API:** sí (único camino oficial encontrado).
- **CSV / XML / EPG / ICS / carga masiva de archivo:** **no encontrado.** Búsqueda exhaustiva en la
  colección Postman completa (337 KB) → cero menciones de `csv`, `xml`, `EPG`, `bulk`, `import`,
  `upload schedule`. No existe endpoint de import de archivo ni bulk insert.

Implicación: si quisiéramos cargar 20 eventos, son 20 llamadas `POST` (o un loop nuestro), no un
"sube tu .csv".

---

## 4. Recomendación: build vs. no-build

**NO-BUILD ahora. Build pequeño y condicionado después.** Razonamiento:

1. **Bloqueo externo real (doble):** la API es de **partner** y exige `x-access-key`/`x-access-secret`
   que **solo entrega Magnifi**. Sin que AMX/Claro nos consiga esas credenciales (o nos deje usarlas)
   no hay integración posible — coincide con la etiqueta `bloqueado-externo` del issue.
2. **Falta confirmar el producto.** Si Elías no usa Magnifi by VideoVerse sino otra herramienta, todo
   lo anterior no aplica.

**Si se desbloquea (producto confirmado + credenciales), el build es chico:**

- Un puente `parrilla → POST /v1/match-schedule` (un POST por evento; mapear equipos/torneos a IDs
  si aplica). Reutilizaría el patrón cliente HTTP que ya hay en el monorepo (httpx en
  `mcp-metricas`).
- **Esfuerzo estimado: ~2–4 días** (1 día cliente+auth+modelo de evento; 1 día mapeo
  equipos/torneos + manejo de errores/`401`/reintentos; 1–2 días pruebas contra el entorno real y
  hand-off). Sube si la parrilla trae muchos equipos que mapear por ID.
- **No** automatizar `invoke-stream` en v1: cargar la parrilla ya elimina el re-tecleo; disparar el
  clipeo es decisión operativa del equipo (frontera creativa, §4 del spec).

---

## 5. Qué confirmar con Elías (§5 Q4 del spec)

1. **¿El producto se llama exactamente "Magnifi by VideoVerse" / vverse?** ¿La URL de login es de
   `videoverse.dev` / `magnifi.ai`? (descartar WSC Sports, Grabyo u otra).
2. **¿Cómo metes hoy la parrilla?** ¿a mano evento por evento en una pantalla de "Match Schedule"?
   ¿o ya importas algo?
3. **¿AMX/Claro tiene credenciales de API de partner** (Access Key/Secret) y nos las puede compartir,
   o hay que pedírselas al representante de Magnifi?
4. **Estructura de tu parrilla:** ¿qué campos lleva cada fila (evento, hora, deporte, equipos,
   torneo)? ¿son eventos con equipos fijos (fútbol) o genéricos? — define si necesitamos el mapeo de
   `teamId`/`tournament`.
5. **¿Te sirve un fallback de archivo** (te generamos un .csv/.json para que lo pegues/cargues) si la
   API tarda en desbloquearse?

---

## 6. Fallback sin API (hand-off mínimo viable)

Si la API no se desbloquea pronto:

- Generamos la parrilla en un **archivo estructurado** (CSV o el **mismo JSON con la forma del
  payload de `Create match schedule`**) a partir de la fuente que ya tenga el equipo, y se carga a
  mano. No elimina el clic humano, pero sí el re-tecleo campo por campo y los errores de captura.
- Alternativa de baja dependencia: un **.ics** de la parrilla para vista de calendario del equipo
  (no lo consume Magnifi, pero ordena la coordinación). Solo si Elías lo ve útil; no es el objetivo
  central.

---

## Fuentes

- Magnifi (producto): <https://magnifi.ai/> · <https://magnifi.ai/about-us>
- Adquisición por Minute Media: <https://www.minutemedia.com/post/minute-media-acquires-videoverse-owner-of-magnifi-a-leading-ai-sports-video-technology-platform>
- **Docs de integración de partner (API):** <https://docs.prod.videoverse.dev/> (colección Postman
  "Magnifi x Partner Integration Documentation"; base API `https://partner.prod.videoverse.dev/v1/`).
  Endpoints, payloads y auth verificados descargando la colección JSON el 2026-05-27.
- Formatos de feed en vivo (contexto): <https://www.sportsvideo.org/2025/07/17/magnifi-brings-ai-powered-solutions-to-live-and-archival-video-storytelling/>
- Partnership Grabyo×Magnifi: <https://about.grabyo.com/automated-highlights-magnifi/>
- Descartado como principal: WSC Sports <https://wsc-sports.com/>

> Nota de honestidad: la API y los payloads están verificados contra la documentación pública de
> partner de Magnifi/VideoVerse. Lo **no** verificable desde fuera: que AMX/Claro use exactamente
> este producto y que el acceso de partner esté disponible para nosotros. Ambos puntos son los
> gatillos del go/no-go.
