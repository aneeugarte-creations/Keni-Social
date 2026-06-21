# ADR 0007 — Histórico de métricas por pieza

Cada pieza publicada mantiene una serie temporal de su rendimiento: una fila por
pieza por refresco, sobre las piezas que el refresco cubre. Esto habilita el análisis
que el equipo de redes necesita y que un único valor actual no puede dar: a qué
velocidad acumula interacciones un reel en sus primeras horas, cuál es la curva de
crecimiento típica por red y formato, si el engagement temprano correlaciona con el
alcance final.

## Principio

El rendimiento de cada pieza ya se recalcula periódicamente. Persistir cada cálculo
como un punto en el tiempo —en lugar de descartarlo— da la serie histórica con coste
marginal mínimo. La granularidad es la del refresco proactivo del tablero: un post no
cambia minuto a minuto, y esa cadencia captura bien la fase interesante (las primeras
horas y días).

La COBERTURA (qué piezas entran), la CADENCIA (cada cuánto se captura) y la RETENCIÓN
(cuánto se conserva) son parámetros operativos —ya expuestos como variables de
entorno— y se ajustan según coste y necesidad. No son parte de la decisión. Lo que sí
fija este ADR es el QUÉ: una serie por pieza, en una tabla separada, con captura
best-effort.

## Invariantes

- **Serie por pieza, no valor único.** Cada punto guarda la clave (pieza, marca, red,
  formato, instante) y las métricas medidas en ese instante. La granularidad la fija la
  cadencia del refresco; el instante lo aporta el llamante (el daemon tiene su reloj),
  de modo que la captura y la purga son deterministas y testeables.

- **Idempotencia por (pieza, instante).** Re-capturar el mismo momento no duplica el
  punto.

- **Escritura best-effort.** Un fallo transitorio puede perder un punto suelto; la serie
  es densa y el siguiente barrido recupera la tendencia. La captura nunca bloquea el
  refresco.

- **Crecimiento acotado por retención.** Una política de retención purga los puntos
  antiguos. El refresco solo cubre piezas recientes, así que las piezas frías dejan de
  acumular puntos y la purga las vacía. El total queda acotado por (piezas activas) ×
  (puntos en la ventana de retención), no es ilimitado.

- **Serie general, separada de las demás.** El valor ACTUAL por pieza (sobrescrito) es
  la fuente del tablero y la lectura instantánea; esta serie no lo sustituye. La serie de
  OBJETIVOS comerciales sigue su propio ciclo de vida. Hay solape de datos con las piezas
  comerciales, pero los propósitos y los lectores son distintos: unificarlas acoplaría el
  análisis general al modelo comercial.

- **Tabla dedicada.** Una serie temporal general no se modela versionando una cache de
  "valor actual" (rompería su semántica) ni reutilizando un modelo comercial (forzaría
  columnas y ciclos ajenos). Una tabla propia se indexa para lectura por pieza y para
  agregados por marca×red sobre una ventana temporal.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- Metricool (u otra fuente) exponga serie temporal por post → quizá delegar el histórico en vez de re-snapshotear.
- El coste de cubrir todo el catálogo reciente moleste → ajustar cobertura/cadencia/retención (son parámetros, no invariantes).
- Se quiera mover el histórico a un TSDB dedicado.
