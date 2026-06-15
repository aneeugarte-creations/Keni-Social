# ADR 0007 — Histórico de métricas por pieza (serie temporal general)

- **Estado:** Aceptado
- **Fecha:** 2026-06-02
- **Decisores:** equipo keni-social
- **Componente:** persistencia operacional de `keni-consola` (`consola/src/keni_consola/db.py`, `repos.py`, `metricas_pieza.py`, `metricas_piezas_refresco.py`, `config.py`)
- **Relación:** se apoya en [ADR 0004](0004-persistencia-operacional-postgres-unico.md) (Postgres único). Complementa —no sustituye— el `comercial_snapshots` introducido para el módulo Comercial.

---

## Contexto

El daemon `metricas_piezas_refresco` recalcula cada 4h
(`KENI_METRICAS_PIEZAS_REFRESCO_HORAS`) el rendimiento de TODAS las piezas publicadas en los
últimos 30 días, sobre TODAS las marcas (vía `metricas_pieza.refrescar_piezas_recientes` →
`recalcular` → `servicio.construir_metricas_pieza`). Hoy ese refresco solo escribe a
`metricas_cache`: una entrada por pieza con el valor ACTUAL, **sobrescrita** en cada barrido.
No queda traza temporal.

La única serie temporal por pieza que existe es `comercial_snapshots`, pero **solo** para las
piezas registradas en el módulo Comercial (seguimiento de objetivos comerciales). El resto del
catálogo —la inmensa mayoría de las piezas del piloto AMX— no tiene histórico alguno.

Sin histórico no se pueden responder preguntas que el equipo de redes necesita: ¿a qué
velocidad acumula interacciones un reel en sus primeras horas?, ¿cuál es la curva de
crecimiento típica por red/formato?, ¿correlaciona el engagement temprano con el alcance
final? Todas requieren **una fila por pieza por instante de medición**, no un único valor
actual.

El dato ya se está calculando 6 veces al día por pieza (cada 4h); simplemente se descarta.
El coste marginal de persistirlo es una fila por pieza por barrido.

## Decisión

**Añadir una tabla `metricas_pieza_snapshots` que captura una fila por pieza por refresco para
TODAS las piezas** (no solo las del módulo Comercial), alimentada por el daemon de refresco
existente, con una **política de retención** que acota su crecimiento.

### Esquema

Declarativa en `_DDL_ESQUEMA` (`CREATE TABLE IF NOT EXISTS`, idempotente, portable a
Postgres 16 como el resto del DDL):

```
metricas_pieza_snapshots (
    id TEXT PK,                       -- uuid generado por la app
    pieza_id TEXT,                    -- id del post (id_post_metricool)
    marca TEXT, red TEXT, formato TEXT DEFAULT '',
    ts TEXT,                          -- ISO, momento de la medición (reloj del daemon)
    visualizaciones, interacciones, alcance INTEGER DEFAULT 0,
    engagement_pct REAL DEFAULT 0,
    likes, comentarios, compartidos, guardados,
    video_views, tiempo_medio_vis_s, clics_enlace,
    seguidores_netos_atribuidos INTEGER DEFAULT 0
)
```

Índices:

- `UNIQUE (pieza_id, ts)` — idempotencia: re-capturar el mismo instante no duplica el punto
  (`INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`, mismo patrón que `comercial_snapshots`).
- `(marca, red, ts)` — análisis agregados por marca×red sobre una ventana temporal.
- `(pieza_id)` — lectura de la serie de una pieza concreta.

Las columnas de métricas se declaran a partir de una sola tupla DRY
(`_METRICAS_PIEZA_SNAPSHOT`, pares `(columna, "int"|"float")`) que mantiene alineados el DDL,
el INSERT y el SELECT. Dato ausente o `None` → 0 (defensivo); la UI distingue "sin dato" por
`encontrado`, no por estos ceros.

### Captura (enganche al daemon)

Cuando `metricas_pieza.recalcular` obtiene una pieza con `encontrado=True`, **además** de
cachear el valor actual en `metricas_cache`, persiste un punto en el histórico vía
`repos.registrar_snapshot_pieza(pieza_id, marca, red, formato, ts, métricas)`. El `ts` es el
mismo reloj del daemon (`ahora.isoformat`), lo que da la idempotencia por `(pieza_id, ts)`. La
escritura es **best-effort**: si falla, se loguea y el refresco continúa (el cache ya quedó
actualizado).

### Retención y purga

Tras cada barrido, `refrescar_piezas_recientes` dispara
`repos.purgar_snapshots_piezas(retención, ahora_iso)`, que borra las filas con
`ts < (ahora − retención)`. La retención es configurable
(`KENI_METRICAS_HISTORICO_RETENCION_DIAS`, **default 90 días**). El "ahora" lo pasa el
llamante (el daemon ya tiene un reloj): **db.py no genera la hora del sistema**, para que la
purga sea testeable de forma determinista.

### Cadencia y crecimiento acotado

La cadencia es la del daemon (**4h**), que ya casa con el TTL del cache por pieza: el
rendimiento de un post no cambia minuto a minuto, y 6 puntos/día capturan bien la curva de las
primeras horas/días (la fase interesante). Con 90 días de retención son ~540 puntos por pieza
viva; el daemon solo refresca las piezas de los últimos 30 días, así que las piezas frías
dejan de recibir puntos nuevos y la purga las vacía progresivamente. El crecimiento queda
**acotado** por (piezas activas) × (puntos en la ventana de retención), no es ilimitado.

### Relación con las otras dos series

- **`metricas_cache`**: valor ACTUAL por pieza, sobrescrito. Sigue siendo la fuente del
  tablero (lectura instantánea). Esta tabla NO la sustituye: es la SERIE histórica.
- **`comercial_snapshots`**: sigue para el seguimiento de OBJETIVOS de piezas comerciales
  (no se toca). `metricas_pieza_snapshots` es la serie GENERAL para todas las piezas. Hay
  solape de datos por las piezas comerciales, pero los propósitos y los lectores son
  distintos; unificarlas acoplaría el análisis general al modelo comercial.

## Consecuencias

**Positivas**

- Habilita análisis temporales (velocidad, curvas de crecimiento, correlación) por
  marca×red×formato para TODO el catálogo, no solo el módulo Comercial.
- Coste marginal mínimo: reaprovecha un cálculo que ya se hace 6 veces/día y hoy se descarta.
- Crecimiento acotado por retención + ventana de refresco; idempotencia por `(pieza_id, ts)`.

**Negativas / coste a asumir**

- Una tabla más que crece con la actividad (acotada, pero no nula). Mitigado por la purga.
- Best-effort en la escritura: en un fallo transitorio se puede perder un punto puntual de
  una pieza; aceptable (la serie es densa y el siguiente barrido recupera la tendencia).
- El solape de datos con `comercial_snapshots` para las piezas comerciales es deliberado
  (modelos y lectores distintos), no una duplicación a deduplicar.

## Alternativas consideradas

- **Reutilizar `comercial_snapshots` para todas las piezas.** Descartada: acoplaría el
  análisis general al modelo comercial (objetivos, cliente, campaña), forzaría columnas
  comerciales nulas en piezas no comerciales y mezclaría dos ciclos de vida distintos.
- **Versionar `metricas_cache` (no sobrescribir).** Descartada: `metricas_cache` es una
  cache genérica tipo×rango×marca con TTL; convertirla en log temporal rompería su semántica
  de "valor actual" y su clave. Una tabla dedicada es más clara y se indexa para series.
- **Retención ilimitada.** Descartada: crecimiento sin cota para un piloto. 90 días cubre de
  sobra el análisis de curvas de las primeras semanas y es configurable si hace falta más.
- **Cadencia más fina (p. ej. 1h) para la captura.** Descartada por ahora: multiplicaría el
  consumo de cuota de la fuente sin ganancia analítica clara a este nivel de piloto; la
  cadencia de 4h del daemo­n es suficiente y no añade un segundo reloj que mantener.
