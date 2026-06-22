/**
 * TimelineFuentes — la LÍNEA DE TIEMPO de outlets de una historia: quién la ABRIÓ, quién se
 * fue sumando y cuándo. El primero de la lista abrió la historia.
 */

import { Badge } from "@/components/ui/badge";
import { tiempoRelativo } from "@/lib/fecha";
import type { FuenteHistoria } from "@/types";

function horaLocal(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

/** La línea de tiempo de outlets: el primero ABRIÓ la historia. */
export function TimelineFuentes({ fuentes }: { fuentes: FuenteHistoria[] }) {
  if (fuentes.length === 0) {
    return <p className="text-xs text-muted-foreground">Sin fuentes aún.</p>;
  }
  return (
    <ol className="space-y-1.5" data-testid="timeline-fuentes">
      {fuentes.map((f, i) => (
        <li key={`${f.fuente_id}-${i}`} className="flex items-baseline gap-2 text-xs">
          <span className="w-12 shrink-0 tabular-nums text-muted-foreground" title={f.primer_visto}>
            {horaLocal(f.primer_visto)}
          </span>
          <span className="h-2 w-2 shrink-0 self-center rounded-full bg-sky-500" />
          <span className="font-medium">{f.fuente || f.fuente_id}</span>
          {i === 0 && (
            <Badge variant="outline" className="text-[10px] font-normal">
              la abrió
            </Badge>
          )}
          {f.n_items > 1 && <span className="text-muted-foreground">· {f.n_items} notas</span>}
          {f.primer_visto && (
            <span className="ml-auto text-muted-foreground">{tiempoRelativo(f.primer_visto)}</span>
          )}
        </li>
      ))}
    </ol>
  );
}
