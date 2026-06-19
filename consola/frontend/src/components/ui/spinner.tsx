import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Spinner de carga canónico: el `Loader2` de lucide con la animación y el rol de
 * accesibilidad ya puestos, para que TODA la app pinte la espera igual en vez de
 * repetir `<Loader2 className="animate-spin" />` suelto.
 *
 * - Tamaño por `className` (por defecto `h-4 w-4`); hereda el color del contexto
 *   (gris `muted-foreground` por defecto). Para un botón: `<Spinner className="mr-2" />`.
 * - `label` alimenta el `aria-label` (texto para lector de pantalla).
 */
export function Spinner({
  className,
  label = "Cargando…",
  ...props
}: React.ComponentProps<typeof Loader2> & { label?: string }) {
  return (
    <Loader2
      role="status"
      aria-label={label}
      className={cn("h-4 w-4 animate-spin text-muted-foreground", className)}
      {...props}
    />
  );
}
