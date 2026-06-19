// Conmutador segmentado de UNA opción activa (single-select), con PALABRAS. Estilo de la
// plataforma: contenedor con borde gris (outline) y el item activo resaltado sobre `muted`.
// Patrón toggle-button: cada item es un `<button>` con `aria-pressed`; no hay navegación por
// flechas (para eso son Tabs). Para alternar entre vistas hermanas, no para navegar.
import * as React from "react";

import { cn } from "@/lib/utils";

export interface OpcionToggle<V extends string> {
  valor: V;
  etiqueta: React.ReactNode;
  /** Texto accesible si la etiqueta no es un string (lo usa `aria-label`). */
  ariaLabel?: string;
}

export function ToggleGroup<V extends string>({
  valor,
  onCambio,
  opciones,
  className,
  ariaLabel,
}: {
  valor: V;
  onCambio: (v: V) => void;
  opciones: ReadonlyArray<OpcionToggle<V>>;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn("inline-flex rounded-md border p-0.5", className)}
    >
      {opciones.map((op) => {
        const activo = op.valor === valor;
        return (
          <button
            key={op.valor}
            type="button"
            aria-pressed={activo}
            aria-label={op.ariaLabel}
            onClick={() => onCambio(op.valor)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded px-3 py-1 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              activo
                ? "bg-muted text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {op.etiqueta}
          </button>
        );
      })}
    </div>
  );
}
