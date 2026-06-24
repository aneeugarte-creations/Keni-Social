/**
 * TimelineFuentes — la LÍNEA DE TIEMPO de outlets de una historia: quién la ABRIÓ, quién se
 * fue sumando y cuándo. El primero de la lista abrió la historia.
 */

import { Badge } from "@/components/ui/badge";
import { formatearHora, tiempoRelativo } from "@/lib/fecha";
import { nombreFuente } from "@/lib/trends";
import type { FuenteHistoria } from "@/types";

/** La línea de tiempo de outlets: el primero ABRIÓ la historia. */
export function TimelineFuentes({ fuentes }: { fuentes: FuenteHistoria[] }) {
  if (fuentes.length === 0) {
    return <p className="text-xs text-muted-foreground">Sin fuentes aún.</p>;
  }
  return (
    <ol className="space-y-1.5" data-testid="timeline-fuentes">
      {fuentes.map((f, i) => (
        <li key={`${f.fuente_id}-${i}`} className="flex items-baseline gap-2 text-xs">
          <span className="shrink-0 tabular-nums text-muted-foreground" title={f.primer_visto}>
            {formatearHora(f.primer_visto) || "—"}
          </span>
          <span className="h-2 w-2 shrink-0 self-center rounded-full bg-sky-500" />
          <span className="font-medium">{nombreFuente(f.fuente, f.fuente_id) || f.fuente_id}</span>
          {i === 0 && (
            <Badge variant="outline" className="text-[10px] font-normal">
              la abrió
            </Badge>
          )}
          {f.n_items > 1 && <span className="text-muted-foreground">· {f.n_items} notas</span>}
          {f.primer_visto && (
            <span className="text-muted-foreground">· {tiempoRelativo(f.primer_visto)}</span>
          )}
        </li>
      ))}
    </ol>
  );
}
