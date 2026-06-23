/**
 * Selector de FORMATO del dashboard de Métricas (cabecera, junto al de red).
 *
 * MULTI-SELECCIÓN y DEPENDIENTE DE LA RED: las opciones son los formatos canónicos de la(s)
 * red(es) en foco (Instagram → Reel/Carrusel/Foto, YouTube → Vídeo, …). Escribe en
 * `useVistaConfig` (`formato` = CSV de ids canónicos, `null` = todos), que filtra las
 * secciones por pieza y recalcula los agregados derivables; el backend recibe `?formato=`.
 * Cuando cambia la red, poda los formatos elegidos que ya no apliquen.
 */
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { formatosDeRedes, nombreFormato } from "@/lib/formato";
import { cn } from "@/lib/utils";

import { useVistaConfig } from "./vistaConfig";

/** Etiqueta legible de el/los formato(s) en foco (o "Todos los formatos") para portadas y nombres. */
export function etiquetaFormato(formato: string | null): string {
  const ids = formato ? formato.split(",").filter(Boolean) : [];
  if (ids.length === 0) return "Todos los formatos";
  if (ids.length === 1) return nombreFormato(ids[0]);
  if (ids.length === 2) return ids.map(nombreFormato).join(" + ");
  return `${ids.length} formatos`;
}

export function SelectorFormato() {
  const red = useVistaConfig((s) => s.red);
  const formato = useVistaConfig((s) => s.formato);
  const toggleFormato = useVistaConfig((s) => s.toggleFormato);
  const setFormatos = useVistaConfig((s) => s.setFormatos);

  // Opciones disponibles según la red en foco; el resto del componente trabaja sobre ellas.
  const opciones = formatosDeRedes(red);
  const seleccion = formato ? formato.split(",").filter(Boolean) : [];

  // Si la red cambia y deja formatos elegidos fuera del universo disponible, los podamos
  // (no tendría sentido filtrar por "carrusel" cuando solo se mira YouTube).
  React.useEffect(() => {
    if (seleccion.length === 0) return;
    const validos = seleccion.filter((f) => opciones.includes(f as never));
    if (validos.length !== seleccion.length) setFormatos(validos);
    // Solo cuando cambian las opciones (derivadas de la red).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opciones.join(",")]);

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
        aria-label="Formatos"
        aria-haspopup="menu"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        <span className="truncate">{etiquetaFormato(formato)}</span>
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
            onClick={() => setFormatos([])}
          >
            <Check
              className={cn("h-3.5 w-3.5", seleccion.length === 0 ? "opacity-100" : "opacity-0")}
            />
            Todos los formatos
          </button>
          <div role="separator" className="my-1 h-px bg-border" />
          {opciones.map((f) => {
            const activa = seleccion.includes(f);
            return (
              <button
                key={f}
                type="button"
                role="menuitemcheckbox"
                aria-checked={activa}
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-xs hover:bg-accent"
                onClick={() => toggleFormato(f)}
              >
                <Check className={cn("h-3.5 w-3.5", activa ? "opacity-100" : "opacity-0")} />
                <span className="truncate">{nombreFormato(f)}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
