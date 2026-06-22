/**
 * Selector de REDES del dashboard de Métricas (cabecera, junto al de periodo).
 *
 * MULTI-SELECCIÓN: combina redes a antojo (Instagram + YouTube + …) o "Todas". Escribe en
 * `useVistaConfig` (`red` = CSV de ids, `null` = todas), que filtra TODA la página: cada
 * sub-sección incluye las redes en foco en su consulta y el backend (`?red=a,b`) las une.
 * Cada opción lleva un punto del color de su red (`coloresRed`) para anclar la lectura
 * cromática del resto de visualizaciones.
 */
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { nombreRed } from "@/lib/formato";
import { cn } from "@/lib/utils";

import { colorDe } from "./coloresRed";
import { useVistaConfig } from "./vistaConfig";

/** Redes en el orden de lectura del piloto (las más activas primero). */
const ORDEN_REDES = ["instagram", "youtube", "facebook", "tiktok", "x"];

/** Punto de color de una red (ancla cromática compartida con las gráficas). */
function PuntoRed({ red }: { red: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ backgroundColor: colorDe(red) }}
    />
  );
}

/** Etiqueta legible de la(s) red(es) en foco (o "Todas las redes") para portadas y nombres. */
export function etiquetaRed(red: string | null): string {
  const ids = red ? red.split(",").filter(Boolean) : [];
  if (ids.length === 0) return "Todas las redes";
  if (ids.length === 1) return nombreRed(ids[0]);
  if (ids.length === 2) return ids.map(nombreRed).join(" + ");
  return `${ids.length} redes`;
}

export function SelectorRed() {
  const red = useVistaConfig((s) => s.red);
  const toggleRed = useVistaConfig((s) => s.toggleRed);
  const setRedes = useVistaConfig((s) => s.setRedes);
  const seleccion = red ? red.split(",").filter(Boolean) : [];

  const [abierto, setAbierto] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!abierto) return;
    const alClicFuera = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false);
    };
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("mousedown", alClicFuera);
    document.addEventListener("keydown", alEscape);
    return () => {
      document.removeEventListener("mousedown", alClicFuera);
      document.removeEventListener("keydown", alEscape);
    };
  }, [abierto]);

  return (
    <div ref={ref} className="relative">
      <Button
        variant="outline"
        size="sm"
        className="h-8 w-full justify-between gap-2 text-xs sm:w-[180px]"
        aria-label="Redes"
        aria-haspopup="menu"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        <span className="flex items-center gap-1.5 truncate">
          {seleccion.length > 0 && (
            <span className="flex -space-x-1">
              {seleccion.slice(0, 3).map((r) => (
                <PuntoRed key={r} red={r} />
              ))}
            </span>
          )}
          <span className="truncate">{etiquetaRed(red)}</span>
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </Button>

      {abierto && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-[200px] rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
        >
          <button
            type="button"
            role="menuitemradio"
            aria-checked={seleccion.length === 0}
            className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-xs hover:bg-accent"
            onClick={() => setRedes([])}
          >
            <Check
              className={cn("h-3.5 w-3.5", seleccion.length === 0 ? "opacity-100" : "opacity-0")}
            />
            Todas las redes
          </button>
          <div role="separator" className="my-1 h-px bg-border" />
          {ORDEN_REDES.map((r) => {
            const activa = seleccion.includes(r);
            return (
              <button
                key={r}
                type="button"
                role="menuitemcheckbox"
                aria-checked={activa}
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-xs hover:bg-accent"
                onClick={() => toggleRed(r)}
              >
                <Check className={cn("h-3.5 w-3.5", activa ? "opacity-100" : "opacity-0")} />
                <PuntoRed red={r} />
                <span className="truncate">{nombreRed(r)}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
