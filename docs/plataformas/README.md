# Plataformas — readiness de publicación (issues #5 / #6 / #7 / #8)

Paquetes **listos para ejecutar** que convierten las habilitaciones externas de cada plataforma en
pasos llave-en-mano. Cada doc separa con claridad **qué prepara Keni** (código/doc) de **qué hace el
humano** (enviar / verificar / pagar — externo).

> **Postura del producto en todo el directorio:** *el humano aprueba; el sistema no publica solo.*
> Estos docs son **investigación + plan**. No se llama a ninguna API externa, no se envía ningún
> formulario, no se crea ninguna app ni se gasta dinero aquí.

## Índice

| Doc | Issue | Qué cubre |
|---|---|---|
| [`meta-app-review.md`](meta-app-review.md) | **#5** | App Review + Business Verification de Meta para **leer insights** y **publicar** (FB Pages + IG Business). Justificación permiso a permiso, screencast, System User token, timeline, y la tarea de código emparejada (`seguidores_netos`/`variacion_vs_anterior`). |
| [`tiktok-audit.md`](tiktok-audit.md) | **#6** | Auditoría del Content Posting API + la **UI de UX-compliance** exacta (consent, creator-info) para salir de `SELF_ONLY`. |
| [`youtube-x.md`](youtube-x.md) | **#7** | YouTube: **borrador de solicitud** de ampliación de cuota. X: análisis de coste 2026 (tiers, ~$0.20/post con enlace) + recomendación (arrancar **read-only**, decidir gasto antes de publicar). |
| [`publicacion-fase2-plan.md`](publicacion-fase2-plan.md) | **#8** | Plan de implementación: System User token, scheduler propio (Meta publica al instante, 100 posts/24h), reutilización de la cola de aprobación de #9, audit-log, gate dry-run→real, secuenciación. |

## Orden de gating

```
#5 Meta  ──(gating PRINCIPAL — empezar YA)──►  #8 publicación real Meta
                                                     │
#6 TikTok ──(auditoría)──────────────────────►  #8 publicación real TikTok
                                                     │
#7 YouTube cuota / X coste ──(decisión)──────►  #8 (diferido: X tras decisión de coste; YouTube)
```

- **#5 (Meta) es la puerta principal — empezar YA.** Es el cuello de botella externo más largo
  (App Review + Business Verification, 3–6 semanas, cada rechazo reinicia). Arrancar la **Business
  Verification en paralelo desde el día 1**.
- **#6 (TikTok)** va por su propia auditoría (2–4 semanas, varias rondas); la palanca es dejar la UI
  de publicación **100% conforme antes de enviar**.
- **#7 (YouTube/X)** no son tan urgentes: la cuota de YouTube **probablemente ya alcanza** (subida
  ~100 u, no ~1600 — corregido en el doc), y X conviene arrancar **solo lectura** y decidir el gasto
  de publicación con el cliente.
- **#8 (Fase 2)** consume todo lo anterior: la publicación real se enchufa al andamiaje **dry-run +
  cola de aprobación + scheduler** ya construido en #9, detrás de un gate consciente. Meta tras #5;
  TikTok tras #6.

> Las fuentes citadas se consultaron en **mayo 2026**. Las plataformas cambian requisitos, precios y
> cuotas sin previo aviso: **verificar el estado vigente antes de enviar o de comprometer gasto**.
