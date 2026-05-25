import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { Card, CardContent } from "@/components/ui/card";

/**
 * Bloque sobrio para estados vacíos / de error / informativos: icono en gris
 * (sin círculo de color ni borde rojo), título y mensaje, con acción opcional.
 * Centrado en una tarjeta. Reemplaza el patrón ruidoso de círculo tintado.
 */
export function EstadoMensaje({
  icono: Icono,
  titulo,
  mensaje,
  accion,
  className,
}: {
  icono: LucideIcon;
  titulo: string;
  mensaje?: string;
  accion?: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <Icono className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">{titulo}</p>
          {mensaje && <p className="max-w-md text-sm text-muted-foreground">{mensaje}</p>}
        </div>
        {accion}
      </CardContent>
    </Card>
  );
}
