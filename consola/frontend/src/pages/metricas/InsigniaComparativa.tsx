/**
 * Insignia comparativa de una métrica entre dos periodos (A = antes, B = actual).
 *
 * Generaliza la antigua `InsigniaVariacion` de CompararPeriodos para reutilizarla
 * también en los KPIs del dashboard. Dos criterios según el tipo de métrica:
 *
 * - CONTEOS (vistas, interacciones, granulares, seguidores): variación porcentual
 *   relativa (`variacion_pct`). Caso especial base-0: el backend devuelve
 *   `variacion_pct = 0.0` cuando a=0 (división imposible) y un BadgeDelta "0.0 %"
 *   OCULTARÍA el arranque desde cero — se muestra un badge "Nuevo" en su lugar.
 *
 * - ENGAGEMENT (`engagement_pct`): NUNCA variación relativa del porcentaje (2.0 % →
 *   2.4 % NO es "+20 %"): se muestra la `diferencia` en PUNTOS porcentuales
 *   ("+0.4 pts"), que el backend ya emite redondeada a 1 decimal. Si es null
 *   (engagement no calculable en algún periodo), no se pinta nada.
 */
import { BadgeDelta, type DeltaType } from "@tremor/react";

import { Badge } from "@/components/ui/badge";
import { puntosPct, variacion } from "@/lib/formato";
import type { ComparativaMetrica } from "@/types";

/** Traduce la variación porcentual de un CONTEO al `deltaType` de Tremor BadgeDelta.
 * Una variación ausente o no finita (métrica no comparable) se trata como "sin
 * cambio", no revienta. */
function deltaTypeConteo(variacionPct: number | null | undefined): DeltaType {
  if (variacionPct == null || !Number.isFinite(variacionPct)) return "unchanged";
  if (variacionPct > 5) return "increase";
  if (variacionPct > 0) return "moderateIncrease";
  if (variacionPct < -5) return "decrease";
  if (variacionPct < 0) return "moderateDecrease";
  return "unchanged";
}

/** `deltaType` para una diferencia en PUNTOS porcentuales (engagement): los umbrales
 * fuerte/moderado van en puntos (±0.5), no en variación relativa. */
function deltaTypePuntos(diferencia: number): DeltaType {
  if (diferencia > 0.5) return "increase";
  if (diferencia > 0) return "moderateIncrease";
  if (diferencia < -0.5) return "decrease";
  if (diferencia < 0) return "moderateDecrease";
  return "unchanged";
}

export function InsigniaComparativa({
  comp,
  title,
}: {
  comp: ComparativaMetrica;
  /** Tooltip opcional (p. ej. "vs periodo anterior (Mes cerrado)"). */
  title?: string;
}) {
  if (comp.metrica === "engagement_pct") {
    // El tipo generado dice `number`, pero el backend emite null cuando el
    // engagement no es calculable en alguno de los periodos: sin dato, sin badge.
    const diferencia = comp.diferencia as number | null;
    if (diferencia == null || !Number.isFinite(diferencia)) return null;
    return (
      <BadgeDelta
        deltaType={deltaTypePuntos(diferencia)}
        size="xs"
        className="shrink-0"
        title={title}
      >
        {puntosPct(diferencia)}
      </BadgeDelta>
    );
  }
  if (comp.a === 0 && comp.b > 0) {
    return (
      <Badge variant="ok" className="shrink-0" title={title}>
        Nuevo
      </Badge>
    );
  }
  return (
    <BadgeDelta
      deltaType={deltaTypeConteo(comp.variacion_pct)}
      size="xs"
      className="shrink-0"
      title={title}
    >
      {variacion(comp.variacion_pct)}
    </BadgeDelta>
  );
}
