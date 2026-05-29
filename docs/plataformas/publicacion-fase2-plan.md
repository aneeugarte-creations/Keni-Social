# Fase 2 — Publicación: dry-run → publicar real (Meta) → TikTok (issue #8)

Plan de implementación para cerrar el hueco vs Metricool: pasar del **preview en dry-run** (un
humano aprueba, nada se publica) a **publicación real**, primero en **Meta** (tras #5) y luego en
**TikTok** (tras #6). Reutiliza la **cola de aprobación + scheduler ya construidos en #9**; lo nuevo
es el **puente a la red real** detrás de un gate explícito.

> Este es un **plan**, no código. Referencia las tareas de código emparejadas; **no se implementa
> nada en esta tarea de docs**.

**Frontera del producto (invariante):** *el humano aprueba; el sistema no publica solo.* Todo lo de
abajo conserva esa postura: el dry-run es el defecto, y el salto a real es un gate consciente.

---

## 1. Qué YA está hecho (#9 + andamiaje de publicación) vs qué falta

### Ya construido — NO reinventar

| Pieza | Dónde | Qué hace |
|---|---|---|
| **Cola de aprobación de equipo** | `consola/.../api/aprobacion.py` + `dominio/aprobacion.py` | Estados `borrador → en_revision → aprobado → programado → publicado` (`estados.py`). Regla **"otro par de ojos"**: quien aprueba/rechaza ≠ autor (salvo admin). |
| **Scheduler propio (24-7)** | `consola/.../programador.py` | Hilo demonio en el servidor compartido (ADR 0001): cuando una pieza `programado` **vence** (`fecha_programada <= ahora`), la **PREPARA en dry-run** y estampa `preparado_en`. **No publica en ninguna plataforma.** Cálculo de vencidos es función pura testeable (`piezas_vencidas`). |
| **Adaptador de publicación Meta (dry-run)** | `mcp-metricas/.../publicacion/meta.py` | `AdaptadorPublicacionMeta.publicar(borrador, dry_run=True)` arma las peticiones **exactas** de Graph API (FB `feed`/`photos`/`videos`; IG `media` → `media_publish`) **sin tocar la red**. POST real **solo** con `dry_run=False` y token real; si falta token, error **antes** de la red. |
| **Modelo de borrador** | `mcp-metricas/.../publicacion/modelos.py` | `Borrador` (plataforma FB/IG, cuenta, texto, media por **URL** —no binario—, hashtags) = el contrato "copy aprobado → petición a Meta". |
| **Cola/agendador mínimo de borradores** | `mcp-metricas/.../publicacion/cola.py` | `ColaPublicacion` en memoria: encola borradores aprobados con hora opcional; `publicar_pendientes(ahora, dry_run=True)` dispara los vencidos. Hereda el dry-run. En dry-run un item **no** se marca publicado (un ensayo no consume la cola). |
| **Skill demo de preview** | skill `publica-meta` | Previsualiza una publicación para Meta en **dry-run** (no publica de verdad). |

### Falta construir (Fase 2)

1. **Puente a la red real (Meta)** detrás del gate dry-run→real: cablear el System User token
   (`tipo_token = "system_user"`) y permitir `dry_run=False` **solo** cuando #5 esté aprobado y un
   flag/permiso explícito lo habilite. Enganchar el posteo real en `programador.py::_preparar` (el
   propio módulo señala ese punto: *"cuando #5/#8 aterricen, el posteo real se engancha aquí"*).
2. **Respetar el límite de 100 posts/24h de Meta** en el scheduler (§3).
3. **Audit-log de publicación** (§4): hoy solo hay observabilidad por petición (`observabilidad.py`),
   **no** un registro de dominio de qué se publicó, quién aprobó y qué respondió la API.
4. **Persistencia de la cola de borradores Meta**: `ColaPublicacion` es **en memoria** (andamiaje);
   en producción el estado de publicación ya vive en las publicaciones (estado `programado` +
   `fecha_programada` + `preparado_en`). Decidir si la cola en memoria se retira a favor del estado
   persistido de las publicaciones (recomendado) o se persiste.
5. **TikTok** (tras #6): adaptador de publicación + la **UI de UX-compliance** (consent, creator-info)
   — ver `tiktok-audit.md`. No empieza la publicación pública hasta pasar la auditoría.

---

## 2. Flujo del System User token (Meta)

Detalle completo en [`meta-app-review.md §6`](meta-app-review.md). Resumen para el plan:

- Token de **System User** de Business Manager → **no caduca** → sin renovación manual cada ~60 días.
- El **mismo token** lee y publica (la publicación reutiliza el cliente HTTP de lectura,
  `publicacion/meta.py` importa `_http.post_json` y la constante `BASE`/`TIPO_SYSTEM_USER` de
  `fuentes/meta.py`).
- Se configura en `config.toml` con `tipo_token = "system_user"`; el adaptador **no intenta
  renovarlo** (refresh = no-op).
- En el **hosted** (ADR 0001) el token vive en el sandbox/MCP de Keni, fuera de git, nunca enviado a
  la IA ni al cliente. La generación de copy sigue por `claude -p` (suscripción global), **separada**
  del token de publicación.

---

## 3. Scheduler propio (Meta publica al instante, sin scheduling nativo)

**Hecho de la plataforma:** la Graph API de Meta **publica al instante**; **no agenda** IG (ni Page)
nativamente. El agendado tiene que ser **nuestro** — y ya lo es (`programador.py` + `cola.py`).

**Límite a respetar:** **100 posts publicados por API en una ventana móvil de 24 h por cuenta de
Instagram** (carruseles = 1 post). Meta recomienda que la app **lo haga cumplir**, sobre todo si
permite programar a futuro. Se puede consultar el uso con `GET /{ig-user-id}/content_publishing_limit`.

**Diseño del scheduler para Fase 2 (sobre lo ya construido):**

1. Una pieza `aprobado` se **programa** (`api/aprobacion.py::programar`) → `programado` +
   `fecha_programada`.
2. El **programador** (hilo 24-7) detecta las vencidas (`piezas_vencidas`, pura) y, **hoy**, las
   prepara en dry-run estampando `preparado_en`. **Fase 2:** en `_preparar`, si el gate real está
   activo, en vez de solo preparar, **publica** (`AdaptadorPublicacionMeta.publicar(dry_run=False)`).
3. **Cumplir el límite 100/24h:** antes de publicar, comprobar el contador por cuenta (consultar
   `content_publishing_limit` o llevar un contador local de las últimas 24 h en el audit-log). Si se
   alcanzó, **diferir** la pieza (no marcarla publicada, reintentar en la siguiente pasada) y
   registrar el motivo. **Nunca** forzar por encima del límite.
4. **Orden estable** (ya en `cola.py`): primero sin hora, luego por hora ascendente.

---

## 4. Diseño del audit-log de publicación

Hoy `observabilidad.py` registra **una línea por petición HTTP** (método + ruta + estado + duración,
**sin** body ni tokens). Eso **no** es un registro de dominio de publicación. Fase 2 añade un
**audit-log de publicación** (tabla operacional en SQLite, junto al resto del estado operacional):

**Qué registra cada intento de publicación (un evento por pieza/plataforma):**

| Campo | Descripción |
|---|---|
| `pieza_id` | La publicación de origen. |
| `plataforma` / `cuenta` | FB/IG/TikTok + Page ID / IG User ID. |
| `autor` / `aprobado_por` | Quién la creó y quién la aprobó (de la cola #9; refuerza "otro par de ojos"). |
| `accion` | `dry_run` \| `publicado` \| `diferido_por_limite` \| `error`. |
| `peticiones` | Las `PeticionPublicacion` que se armaron (método + url + paso; **sin el token**). |
| `respuesta_api` | El `id_publicacion` / id de media devuelto (real); o el error. |
| `cuando` | Timestamp. |

**Privacidad (regla heredada de `observabilidad.py`):** **nunca** registrar el token ni credenciales.
El `PeticionPublicacion.data` que se muestra en dry-run **ya omite el token** por diseño (ver
`publicacion/meta.py`). El audit-log mantiene esa garantía.

**Para qué sirve:** trazabilidad ("¿quién publicó qué y cuándo, y quién lo aprobó?"), contador para
el límite 100/24h, y base de un panel ligero de actividad de publicación.

---

## 5. El gate dry-run → real

El salto a real es un **gate consciente**, no un flag suelto:

1. **Pre-requisito externo:** #5 (Meta App Review) aprobado y System User token configurado. Sin
   token real, el adaptador **falla antes de tocar la red** (ya implementado).
2. **Flag/permiso explícito de servidor:** una config (p. ej. `KENI_PUBLICACION_REAL=meta`) y/o un
   permiso de usuario que habilite `dry_run=False`. Por defecto **todo es dry-run**.
3. **Doble revisión ya activa** (#9): solo piezas `aprobado` (por alguien ≠ autor) pueden
   programarse y, por tanto, publicarse.
4. **Validación previa con cuenta de prueba:** antes de apuntar a las cuentas reales de AMX, publicar
   contra una Página/IG de **prueba** con `dry_run=False` (también necesario para el screencast de
   #5, ver `meta-app-review.md §4`).
5. **Reversibilidad:** quitar el flag o el token vuelve todo a dry-run sin cambios de código.

```
borrador --(autor)--> en_revision --(revisor≠autor)--> aprobado --(programar)--> programado
                                                                                     |
                                            programador (24-7) detecta vencida -------+
                                                                                     |
                          gate OFF (defecto): PREPARA en dry-run, estampa preparado_en
                          gate ON  (#5 ok + flag + token): PUBLICA real, respeta 100/24h,
                                                            escribe audit-log, -> publicado
```

---

## 6. Secuenciación

| Orden | Hito | Depende de |
|---|---|---|
| 1 | **Meta real** — cablear System User token + gate dry-run→real + límite 100/24h + audit-log | **#5** aprobado (App Review + BV) |
| 2 | Validar `seguidores_netos`/`variacion_vs_anterior` en el camino real contra cuentas de AMX | Tarea de código de #5 (ver `meta-app-review.md §7`) |
| 3 | **TikTok real** — adaptador de publicación + **UI de UX-compliance** (consent, creator-info) | **#6** auditoría aprobada (ver `tiktok-audit.md`) |
| 4 | (Diferido / decisión de coste) X publicación; YouTube subida | #7 (decisión de coste X · cuota YouTube ya suele alcanzar) |

> **Gating principal = #5.** Meta es la primera y mayor puerta; TikTok va detrás de su propia
> auditoría (#6); X/YouTube quedan tras la decisión de coste/cuota de #7. Nada publica de forma real
> hasta que su puerta externa esté abierta **y** el gate interno se active conscientemente.

---

## Referencias

- [`meta-app-review.md`](meta-app-review.md) — App Review, System User token, tarea de código de #5.
- [`tiktok-audit.md`](tiktok-audit.md) — auditoría + UI de UX-compliance de TikTok.
- [`youtube-x.md`](youtube-x.md) — cuota YouTube + decisión de coste X.
- [ADR 0001](../adr/0001-runtime-servicio-compartido.md) — servidor compartido 24-7 que aloja el
  scheduler; generación por `claude -p` (no API de Claude), separada del token de publicación.
- [`../flujo-de-datos-privacidad.md`](../flujo-de-datos-privacidad.md) — el audit-log hereda la regla
  de no registrar tokens/credenciales.
- Código existente: `mcp-metricas/.../publicacion/` (adaptador dry-run + cola + modelos),
  `consola/.../programador.py` (scheduler 24-7), `consola/.../api/aprobacion.py` (cola de aprobación
  #9), `consola/.../estados.py` (estados del flujo editorial).
