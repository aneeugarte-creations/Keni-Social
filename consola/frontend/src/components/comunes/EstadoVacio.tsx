import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Estado vacío reutilizable: icono opcional, título, texto descriptivo y una
 * acción opcional (p. ej. un botón).
 */
export function EstadoVacio({
  icono: Icono,
  titulo,
  texto,
  accion,
  className,
}: {
  /** Icono opcional mostrado en gris (estilo sobrio, sin círculo tintado). */
  icono?: LucideIcon;
  titulo: string;
  texto?: string;
  /** Acción opcional (botón, enlace…) bajo el texto. */
  accion?: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        {Icono && <Icono className="h-6 w-6 text-muted-foreground" aria-hidden="true" />}
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">{titulo}</p>
          {texto && <p className="max-w-md text-sm text-muted-foreground">{texto}</p>}
        </div>
        {accion}
      </CardContent>
    </Card>
  );
}

/**
 * Variante "ligera" del estado vacío: solo texto centrado, sin tarjeta. Útil
 * dentro de paneles que ya viven en una Card (Fuentes, etc.).
 */
export function EstadoVacioTexto({
  texto,
  className,
}: {
  texto: string;
  className?: string;
}) {
  return (
    <p className={cn("py-12 text-center text-sm text-muted-foreground", className)}>{texto}</p>
  );
}
