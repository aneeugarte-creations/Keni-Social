import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Spinner de carga canónico: el `Loader2` de lucide con la animación y el rol de
 * accesibilidad ya puestos, para que TODA la app pinte la espera igual en vez de
 * repetir `<Loader2 className="animate-spin" />` suelto.
 *
 * - Tamaño por `className` (por defecto `h-4 w-4`). HEREDA el color del contexto
 *   (`currentColor`, igual que el `Loader2` que reemplaza): dentro de un botón toma
 *   el color del botón; suelto, pásale `text-muted-foreground` para el gris estándar.
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
      className={cn("h-4 w-4 animate-spin", className)}
      {...props}
    />
  );
}
