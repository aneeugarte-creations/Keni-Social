# Plataformas — publicación y rutas por plataforma

La publicación real a redes va por el **scheduler de Metricool**: una sola integración cubre
Facebook, Instagram, X, TikTok y YouTube (AMX ya tiene plan **Advanced**). Eso quita los antiguos
bloqueos externos de publicación; lo que queda es **trabajo de código interno** (cablear el
adaptador Metricool en el programador de la Consola). Estos docs cubren ese camino y las **rutas
directas por API oficial** de cada plataforma como **alternativa opcional** (no necesaria con
Metricool).

> **Postura del producto en todo el directorio:** *el humano aprueba; el sistema no publica solo.*
> El dry-run es el defecto; la publicación real se enciende con un flag consciente.

## Índice

| Doc | Qué cubre |
|---|---|
| [`publicacion-metricool.md`](publicacion-metricool.md) | **Camino de publicación vigente.** Entregar el post al scheduler de Metricool (FB/IG/X/TikTok/YouTube en una sola integración). Adaptador, contrato de la API, credenciales por marca, enganche en la Consola. Incluye el **apéndice de rutas directas por API** (TikTok/YouTube/X) como alternativa NO usada. |

## Cómo encaja

- **Publicar de verdad = Metricool.** Camino recomendado y único necesario; lo restante es código
  interno (ver `publicacion-metricool.md`). El dry-run es el defecto; la publicación real se activa
  con el flag `KENI_PUBLICAR_REAL`.
- **Rutas directas por API oficial (TikTok, YouTube, X) = alternativa opcional.** Documentadas por si
  alguna vez se quisiera integrar una plataforma directamente sin pasar por Metricool; **no son
  bloqueantes** de publicación ni de métricas.
- **Las métricas reales también llegan vía Metricool** (`FuenteMetricol`), sin necesidad de
  habilitaciones externas por plataforma.

> Las fuentes citadas se consultaron en **mayo 2026**. Las plataformas cambian requisitos, precios y
> cuotas sin previo aviso: **verificar el estado vigente antes de comprometer gasto o de integrar una
> ruta directa**.
