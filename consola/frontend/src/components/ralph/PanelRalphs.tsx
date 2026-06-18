/**
 * Panel de bolitas del overlay Ralph: una bolita flotante por Ralph del pool
 * (color por estado) más el botón [＋ lanzar Ralph]. Click en una bolita abre su
 * chat; click en [＋] abre el lanzador. Estilo Nolan v1: bolitas seleccionables.
 */
import { Plus } from "lucide-react";

import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useRalphStore } from "@/store/ralphStore";
import type { EstadoRalph } from "@/types/ralph";

/** Color de fondo de una bolita según el estado del Ralph. */
export const COLOR_ESTADO: Record<EstadoRalph, string> = {
  activo: "bg-emerald-500",
  idle: "bg-zinc-400",
  esperando: "bg-amber-500",
  error: "bg-red-500",
};

/** Etiqueta legible del estado de un Ralph. */
export const ETIQUETA_ESTADO: Record<EstadoRalph, string> = {
  activo: "Trabajando",
  idle: "En reposo",
  esperando: "Esperándote",
  error: "Con error",
};

export function PanelRalphs() {
  const ralphs = useRalphStore((s) => s.ralphs);
  const seleccionado = useRalphStore((s) => s.seleccionado);
  const seleccionar = useRalphStore((s) => s.seleccionar);
  const abrirLanzador = useRalphStore((s) => s.abrirLanzador);

  return (
    <div className="flex flex-col items-end gap-2">
      {ralphs.map((r) => {
        const activa = r.id === seleccionado;
        return (
          <Tooltip key={r.id} label={`${r.nombre} · ${ETIQUETA_ESTADO[r.estado]}`} side="left">
            <button
              type="button"
              onClick={() => seleccionar(activa ? null : r.id)}
              className={cn(
                "flex h-11 w-11 items-center justify-center rounded-full text-sm font-semibold text-white shadow-md transition-transform hover:scale-105",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-keni focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                COLOR_ESTADO[r.estado],
                activa && "ring-2 ring-keni ring-offset-2 ring-offset-background",
              )}
              aria-label={`${r.nombre}: ${ETIQUETA_ESTADO[r.estado]}`}
            >
              {r.nombre.slice(0, 1).toUpperCase()}
            </button>
          </Tooltip>
        );
      })}

      <Tooltip label="Lanzar Ralph" side="left">
        <button
          type="button"
          onClick={abrirLanzador}
          className={cn(
            "flex h-11 w-11 items-center justify-center rounded-full border-2 border-dashed border-keni/60 text-keni shadow-sm transition-colors hover:bg-keni/10",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-keni focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          )}
          aria-label="Lanzar Ralph"
        >
          <Plus className="h-5 w-5" />
        </button>
      </Tooltip>
    </div>
  );
}
