/**
 * ChipInvestigacion — indicador COMPACTO del loop de Investigación (ADR 0011, Fase 3).
 *
 * Sustituye al antiguo panel «Monitor de investigación» embebido en la página de Noticias
 * (que duplicaba la vista del Monitor): un chip con los jobs del loop en el pool compartido
 * («Investigación: N en curso · M en cola», del MISMO snapshot `GET /api/actividad/cola`)
 * que enlaza a la Cola compartida prefiltrada (`/maquina/cola?proceso=investigacion`), donde
 * viven la vista completa (tablas, serie, economía) y la operación de la cola.
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
  // Back anterior (sin desglose por proceso): sin chip, para no mentir con ceros.
  const inv = cola.data?.por_proceso?.investigacion;
  if (!inv) return null;
  return (
    <Link
      to="/maquina/cola?proceso=investigacion"
      data-testid="chip-investigacion"
      className="inline-flex w-fit items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
      title="Abrir Workers prefiltrado al loop de investigación"
    >
      <Microscope className="h-3.5 w-3.5 text-sky-600" aria-hidden="true" />
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
