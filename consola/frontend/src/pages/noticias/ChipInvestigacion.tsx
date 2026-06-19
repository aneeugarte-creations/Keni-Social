/**
 * ChipInvestigacion — indicador COMPACTO del loop de Investigación (ADR 0011, Fase 3).
 *
 * Un chip con los jobs del loop en el pool compartido («Investigación: N en curso · M en cola»,
 * del MISMO snapshot `GET /api/actividad/cola`) que enlaza a Cómputo prefiltrado
 * (`/maquina/computo?proceso=investigacion`), donde se ve y opera la cola del loop.
 */
import { useQuery } from "@tanstack/react-query";
import { Microscope } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";

export function ChipInvestigacion() {
  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });
  const inv = cola.data?.por_proceso?.investigacion;
  if (!inv) return null;
  return (
    <Link
      to="/maquina/computo?proceso=investigacion"
      data-testid="chip-investigacion"
      className="inline-flex w-fit items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
      title="Abrir Cómputo prefiltrado al loop de investigación"
    >
      <Microscope className="h-3.5 w-3.5" aria-hidden="true" />
      <span>
        Investigación:{" "}
        <span className="font-medium tabular-nums text-foreground">{inv.procesando}</span> en
        curso ·{" "}
        <span className="font-medium tabular-nums text-foreground">{inv.pendientes}</span> en
        cola
      </span>
    </Link>
  );
}
