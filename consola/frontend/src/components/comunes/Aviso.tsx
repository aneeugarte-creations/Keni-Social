import { TriangleAlert } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Aviso (callout ámbar) canónico. Consume los tokens semánticos `--aviso-*` de
 * `index.css` (borde/superficie/texto) en lugar de repetir a mano el bloque
 * `border-amber-500/40 bg-amber-500/10 text-amber-700 dark:…` que estaba copiado
 * por toda la app. Un solo ámbar de aviso, con su par claro/oscuro ya resuelto.
 *
 * - `icono`: muestra el triángulo de atención (por defecto sí); ponlo a `false`
 *   para un aviso de solo texto.
 */
export function Aviso({
  children,
  icono = true,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { icono?: boolean }) {
  return (
    <div
      role="note"
      className={cn(
        "flex items-start gap-2 rounded-md border px-3 py-2 text-xs",
        "border-[hsl(var(--aviso-borde))] bg-[hsl(var(--aviso-superficie))] text-[hsl(var(--aviso-texto))]",
        className,
      )}
      {...props}
    >
      {icono && <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
      <div className="min-w-0">{children}</div>
    </div>
  );
}
