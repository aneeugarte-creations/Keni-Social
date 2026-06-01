# Fase 2 — Publicación: dry-run → publicar real vía Metricool

Plan de implementación para cerrar el hueco vs Metricool: pasar del **preview en dry-run** (un
humano aprueba, nada se publica) a **publicación real**, entregando el post al **scheduler de
Metricool** (una sola integración cubre Facebook, Instagram, X, TikTok y YouTube; AMX ya tiene plan
**Advanced**). Reutiliza la **cola de aprobación + scheduler ya construidos en #9**; lo nuevo es
**cablear el adaptador Metricool en el programador** detrás de un flag explícito. Detalle del
adaptador y del contrato de la API en [`publicacion-metricool.md`](publicacion-metricool.md).

> **Sin prerequisito externo.** La publicación real ya **no** está gated por App Review de Meta, ni
> por la auditoría de TikTok, ni por el tier de pago de X: Metricool cubre todas esas plataformas con
> una sola integración. El trabajo restante es **código interno** (cablear Metricool real en el
> programador de la Consola).

> Este es un **plan**, no código. Referencia las tareas de código emparejadas; **no se implementa
> nada en esta tarea de docs**.

**Frontera del producto (invariante):** *el humano aprueba; el sistema no publica solo.* Todo lo de
abajo conserva esa postura: el dry-run es el defecto, y el salto a real es un gate consciente
(`KENI_PUBLICAR_REAL`).

---

## 1. Qué YA está hecho (#9 + andamiaje de publicación) vs qué falta

### Ya construido — NO reinventar

| Pieza | Dónde | Qué hace |
|---|---|---|
| **Cola de aprobación de equipo** | `consola/.../api/aprobacion.py` + `dominio/aprobacion.py` | Estados `borrador → en_revision → aprobado → programado → publicado` (`estados.py`). Regla **"otro par de ojos"**: quien aprueba/rechaza ≠ autor (salvo admin). |
| **Scheduler propio (24-7)** | `consola/.../programador.py` | Hilo demonio en el servidor compartido (ADR 0001): cuando una pieza `programado` **vence** (`fecha_programada <= ahora`), la **PREPARA en dry-run** y estampa `preparado_en`. **No publica en ninguna plataforma.** Cálculo de vencidos es función pura testeable (`piezas_vencidas`). |
| **Adaptador de publicación Metricool (dry-run)** | `mcp-metricas/.../publicacion/metricool.py` | `AdaptadorPublicacionMetricool.programar(borrador, dry_run=True)` arma el `ScheduledPost` **exacto** del scheduler de Metricool (`POST /v2/scheduler/posts`) **sin tocar la red**. POST real **solo** con `dry_run=False` y credenciales completas; si faltan, `ProgramacionNoConfigurada` **antes** de la red. |
| **Modelo de borrador Metricool** | `mcp-metricas/.../publicacion/metricool.py` | `BorradorMetricool` (redes, texto, media por **URL**, hashtags, `publicar_en`, `timezone`, `auto_publish`, `borrador`) = el contrato "copy aprobado → post programado en Metricool". |
| **Flujo de borradores Metricool** | `mcp-metricas/.../publicacion/flujo_metricool.py` | Carga borradores de `.json`/`.toml`, reporta el dry-run y, con `--publicar-real --si-publicar` + credenciales en el entorno, programa de verdad. Espeja la seguridad de `flujo.py`. |
| **Skill demo de preview** | skill `publica-meta` | Previsualiza una publicación en **dry-run** (no publica de verdad). |

### Falta construir (Fase 2)

1. **Cablear Metricool real en el programador** detrás del gate dry-run→real: enganchar
   `AdaptadorPublicacionMetricool.programar(dry_run=not publicar_real)` en
   `programador.py::_preparar` (el propio módulo señala ese punto). Pasos en
   [`publicacion-metricool.md`](publicacion-metricool.md) §"Enganche en la Consola": resolver `creds`
   de la marca (`marcas_configuradas()`), mapear la fila de `publicaciones` a `BorradorMetricool`,
   programar, y guardar `id_post`/`estados` + mover la pieza a `publicado`.
2. **Respetar los límites de rate de Metricool** en el scheduler (no martillar la API; diferir y
   reintentar si responde rate-limit).
3. **Audit-log de publicación** (§4): hoy solo hay observabilidad por petición (`observabilidad.py`),
   **no** un registro de dominio de qué se publicó, quién aprobó y qué respondió Metricool.
4. **Persistencia del estado de publicación**: el estado ya vive en las publicaciones (estado
   `programado` + `fecha_programada` + `preparado_en`); decidir cómo persistir el `id_post` que
   devuelve Metricool y su `status` por red.

---

## 2. Credenciales de Metricool (por marca)

Detalle en [`publicacion-metricool.md`](publicacion-metricool.md) §"Credenciales por marca".
Resumen para el plan:

- El adaptador reutiliza **el mismo token por marca** que la lectura de métricas
  (`fuentes.metricol.FuenteMetricol`): cabecera `X-Mc-Auth` + query `userId`/`blogId`.
- La Consola resuelve `creds` con `config.MetricoolConfig(...).marcas_configuradas()[marca_id]` —
  exactamente la forma que espera `AdaptadorPublicacionMetricool(creds=...)`, así que el cableado es
  directo.
- En el **hosted** (ADR 0001) el token vive en el sandbox/MCP de Keni, fuera de git, nunca enviado a
  la IA ni al cliente. La generación de copy sigue por `claude -p` (suscripción global), **separada**
  del token de publicación.

---

## 3. Scheduler: Metricool agenda nativamente

**Hecho de la plataforma:** Metricool **agenda nativamente** con `publicationDate` + `autoPublish`,
así que **no** hace falta cola/agendador propio para el camino real (a diferencia del camino
Meta-directo, donde IG no agenda por API). El programador 24-7 de #9 sigue siendo el disparador
interno que decide **cuándo** entregar la pieza a Metricool.

**Diseño del scheduler para Fase 2 (sobre lo ya construido):**

1. Una pieza `aprobado` se **programa** (`api/aprobacion.py::programar`) → `programado` +
   `fecha_programada`.
2. El **programador** (hilo 24-7) detecta las vencidas (`piezas_vencidas`, pura) y, **hoy**, las
   prepara en dry-run estampando `preparado_en`. **Fase 2:** en `_preparar`, si el gate real está
   activo, en vez de solo preparar, **programa en Metricool**
   (`AdaptadorPublicacionMetricool.programar(dry_run=False)`).
3. **Respetar los límites de rate de Metricool:** si la API responde rate-limit, **diferir** la pieza
   (no marcarla publicada, reintentar en la siguiente pasada) y registrar el motivo. **Nunca**
   martillar la API.
4. **Orden estable** (ya en el andamiaje): primero sin hora, luego por hora ascendente.

---

## 4. Diseño del audit-log de publicación

Hoy `observabilidad.py` registra **una línea por petición HTTP** (método + ruta + estado + duración,
**sin** body ni tokens). Eso **no** es un registro de dominio de publicación. Fase 2 añade un
**audit-log de publicación** (tabla operacional en Postgres, junto al resto del estado operacional):

**Qué registra cada intento de publicación (un evento por pieza/red):**

| Campo | Descripción |
|---|---|
| `pieza_id` | La publicación de origen. |
| `red` / `marca` | Red(es) de destino (FB/IG/X/TikTok/YouTube) + marca/`blogId`. |
| `autor` / `aprobado_por` | Quién la creó y quién la aprobó (de la cola #9; refuerza "otro par de ojos"). |
| `accion` | `dry_run` \| `programado` \| `diferido_por_rate` \| `error`. |
| `peticion` | El `ScheduledPost` que se armó (**sin el token**). |
| `respuesta_api` | El `id` de post de Metricool y el `status` por red (`PUBLISHED`/`PENDING`/…); o el error. |
| `cuando` | Timestamp. |

**Privacidad (regla heredada de `observabilidad.py`):** **nunca** registrar el token ni credenciales.
El audit-log mantiene esa garantía.

**Para qué sirve:** trazabilidad ("¿quién publicó qué y cuándo, y quién lo aprobó?") y base de un
panel ligero de actividad de publicación.

---

## 5. El gate dry-run → real

El salto a real es un **gate consciente**, no un flag suelto:

1. **Sin prerequisito externo:** no hay App Review, auditoría ni tier de pago que esperar — Metricool
   cubre las cinco redes. El único requisito técnico son las **credenciales de Metricool** de la
   marca; sin ellas, el adaptador **falla antes de tocar la red** (`ProgramacionNoConfigurada`, ya
   implementado).
2. **Flag explícito de servidor:** `KENI_PUBLICAR_REAL` habilita `dry_run=False`. Por defecto **todo
   es dry-run**.
3. **Doble revisión ya activa** (#9): solo piezas `aprobado` (por alguien ≠ autor) pueden
   programarse y, por tanto, publicarse.
4. **Validación previa con `draft=true`:** antes de programar de verdad contra las cuentas reales de
   AMX, POSTear un `draft=true` (no publica) para confirmar la forma de la respuesta de Metricool
   (ver `publicacion-metricool.md` §"Supuestos sin confirmar").
5. **Reversibilidad:** apagar el flag o quitar las credenciales vuelve todo a dry-run sin cambios de
   código.

```
borrador --(autor)--> en_revision --(revisor≠autor)--> aprobado --(programar)--> programado
                                                                                     |
                                            programador (24-7) detecta vencida -------+
                                                                                     |
              flag OFF (defecto): PREPARA en dry-run, estampa preparado_en
              flag ON  (KENI_PUBLICAR_REAL + creds Metricool): PROGRAMA en Metricool,
                                                respeta rate-limits, escribe audit-log, -> publicado
```

---

## 6. Secuenciación

| Orden | Hito | Depende de |
|---|---|---|
| 1 | **Publicación real vía Metricool** — cablear el adaptador en `programador.py::_preparar` + gate dry-run→real + límites de rate + audit-log | Código interno (sin prerequisito externo) |
| 2 | Validar `seguidores_netos`/`variacion_vs_anterior` en el camino real contra cuentas reales de AMX (vía Metricool) | Tarea de código (§7) |
| 3 | Datos por red obligatorios de Metricool (`youtubeData`/`tiktokData`: título, privacidad…) cuando se validen contra la API real | Token real de Metricool para validar |

> **Sin puerta externa.** Nada bloquea la publicación real salvo el trabajo de código y el gate
> interno consciente (`KENI_PUBLICAR_REAL`). El cableado se hará cuando el merge en curso de la
> Consola en `main` asiente (ver `publicacion-metricool.md` §"Enganche en la Consola").

---

## 7. Tarea de código emparejada — `seguidores_netos` / `variacion_vs_anterior`

En el **camino real** hay que rellenar dos campos que hoy salen vacíos, para validarlos contra las
cuentas reales de AMX (vía Metricool). **Esto es código, NO se toca en esta tarea de docs.**

**Estado actual (verificado en el repo):**

- `agregador.py` (el camino **real**, sobre `FuenteMetricas`) **hardcodea**:
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

**Trabajo emparejado (resumen, no se implementa aquí):**

1. **`variacion_vs_anterior` (real):** dejar de hardcodear `{}` en `agregador.py:156` y enganchar
   `historico.aplicar_variacion(...)` en el camino real (igual que para la muestra/CLI).
2. **`seguidores_netos` (real):** leer el conteo de seguidores por red desde `FuenteMetricol`,
   propagarlo a `MetricaPlataforma`, y calcular `seguidores_netos` como **delta** contra el conteo
   del periodo anterior (la tabla `lecturas` ya lo persiste). Sin histórico previo, el neto es `0`.
3. **Validación (humano):** con las cuentas reales de AMX, comprobar que ambos campos cuadran con lo
   que muestran las analíticas nativas / Metricool.

---

## Referencias

- [`publicacion-metricool.md`](publicacion-metricool.md) — adaptador Metricool, contrato de la API,
  credenciales por marca, enganche en la Consola.
- [`tiktok-audit.md`](tiktok-audit.md) — ruta directa opcional por el Content Posting API de TikTok
  (no necesaria con Metricool).
- [`youtube-x.md`](youtube-x.md) — rutas directas opcionales por API oficial de YouTube y X (no
  necesarias con Metricool).
- [ADR 0001](../adr/0001-runtime-servicio-compartido.md) — servidor compartido 24-7 que aloja el
  scheduler; generación por `claude -p` (no API de Claude), separada del token de publicación.
- [`../flujo-de-datos-privacidad.md`](../flujo-de-datos-privacidad.md) — el audit-log hereda la regla
  de no registrar tokens/credenciales.
- Código existente: `mcp-metricas/.../publicacion/metricool.py` (adaptador dry-run + modelo),
  `mcp-metricas/.../publicacion/flujo_metricool.py` (flujo CLI),
  `consola/.../programador.py` (scheduler 24-7), `consola/.../api/aprobacion.py` (cola de aprobación
  #9), `consola/.../estados.py` (estados del flujo editorial).
