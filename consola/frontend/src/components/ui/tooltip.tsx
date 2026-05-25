/**
 * Tooltip ligero (CSS puro, sin dependencias).
 *
 * Pensado para botones de solo icono: envuelve el disparador y muestra una
 * etiqueta al pasar el ratón o al enfocar con teclado. Para accesibilidad se
 * aplica también `aria-label` al hijo (sin pisar uno existente).
 *
 * No usamos Radix Tooltip para no añadir otra dependencia pesada; este patrón
 * cubre el caso (etiqueta corta sobre un icono) con foco/hover y modo oscuro.
 */
import * as React from "react";

import { cn } from "@/lib/utils";

type Lado = "top" | "bottom" | "left" | "right";

const POSICION: Record<Lado, string> = {
  top: "bottom-full left-1/2 mb-1.5 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-1.5 -translate-x-1/2",
  left: "right-full top-1/2 mr-1.5 -translate-y-1/2",
  right: "left-full top-1/2 ml-1.5 -translate-y-1/2",
};

export interface TooltipProps {
  /** Texto a mostrar. Si está vacío, se renderiza el hijo sin envoltorio. */
  label: string;
  /** Lado donde aparece (por defecto arriba). */
  side?: Lado;
  children: React.ReactElement;
  className?: string;
}

/**
 * Envuelve un único elemento (normalmente un Button de icono) y le añade un
 * tooltip accesible. El hijo recibe `aria-label` si no tiene uno.
 */
export function Tooltip({ label, side = "top", children, className }: TooltipProps) {
  if (!label) return children;

  const hijo = React.isValidElement<{ "aria-label"?: string }>(children)
    ? React.cloneElement(children, {
        "aria-label": children.props["aria-label"] ?? label,
      })
    : children;

  return (
    <span className={cn("group/tooltip relative inline-flex", className)}>
      {hijo}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 text-xs font-medium text-popover-foreground opacity-0 shadow-md transition-opacity duration-150",
          "group-hover/tooltip:opacity-100 group-focus-within/tooltip:opacity-100",
          POSICION[side],
        )}
      >
        {label}
      </span>
    </span>
  );
}
