/**
 * Panel de bolitas del overlay Ralph: una bolita por Ralph del pool (color por estado) en
 * una barra HORIZONTAL a la izquierda de la burbuja, más el botón [＋ lanzar Ralph]. Click en
 * una bolita abre su chat; click en [＋] abre el lanzador. Estilo Nolan v1: bolitas seleccionables.
 */
import { Plus } from "lucide-react";

import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useRalphStore } from "@/store/ralphStore";
import type { EstadoRalph } from "@/types/ralph";

/** Color de fondo de una bolita según el estado del Ralph. Solid dot (inicial en blanco sobre el
 *  círculo), no el badge tintado de `ChipEstado`: misma familia semántica (verde=activo, ámbar=
 *  esperando, rojo=error, cielo=dormido, gris=reposo), expresada como relleno 500 en vez de /15+700. */
export const COLOR_ESTADO: Record<EstadoRalph, string> = {
  activo: "bg-emerald-500",
  idle: "bg-zinc-400",
  esperando: "bg-amber-500",
  error: "bg-red-500",
  dormido: "bg-sky-400",
};

/** Etiqueta legible del estado de un Ralph. */
export const ETIQUETA_ESTADO: Record<EstadoRalph, string> = {
  activo: "Trabajando",
  idle: "En reposo",
  esperando: "Esperándote",
  error: "Con error",
  dormido: "Dormido · escríbele para reanudar",
};

export function PanelRalphs() {
  const ralphs = useRalphStore((s) => s.ralphs);
  const seleccionado = useRalphStore((s) => s.seleccionado);
  const seleccionar = useRalphStore((s) => s.seleccionar);
  const abrirLanzador = useRalphStore((s) => s.abrirLanzador);

  return (
    <div className="flex flex-row items-center gap-2">
      {ralphs.map((r) => {
        const activa = r.id === seleccionado;
        return (
          <Tooltip key={r.id} label={`${r.nombre} · ${ETIQUETA_ESTADO[r.estado]}`} side="top">
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

      <Tooltip label="Lanzar Ralph" side="top">
        <button
          type="button"
          onClick={abrirLanzador}
          className={cn(
            "flex h-11 w-11 items-center justify-center rounded-full border-2 border-dashed border-keni/60 bg-white text-keni shadow-sm transition-colors hover:bg-keni/10",
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
