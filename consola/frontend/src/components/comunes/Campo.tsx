import * as React from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * Campo de formulario canónico: etiqueta (tipo frase) arriba, control en medio, y debajo
 * una sola línea de ayuda O de error. Anatomía idéntica en todos los formularios.
 *
 * El error va EN LÍNEA (texto rojo bajo el campo), no como toast; el rojo aquí es señal de
 * error. Marca el control con `aria-invalid` cuando pases `error` para que se lea su borde.
 */
export function Campo({
  etiqueta,
  htmlFor,
  ayuda,
  error,
  className,
  children,
}: {
  etiqueta: React.ReactNode;
  /** `id` del control que etiqueta (asocia label↔control y el mensaje de error). */
  htmlFor?: string;
  /** Texto de ayuda neutro bajo el campo. Lo tapa `error` si lo hay. */
  ayuda?: React.ReactNode;
  /** Mensaje de error de validación. Si está presente, se muestra en rojo en vez de `ayuda`. */
  error?: string | null;
  className?: string;
  children: React.ReactNode;
}) {
  const idError = error && htmlFor ? `${htmlFor}-error` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor}>{etiqueta}</Label>
      {children}
      {error ? (
        <p id={idError} className="text-xs text-destructive">
          {error}
        </p>
      ) : ayuda ? (
        <p className="text-xs text-muted-foreground">{ayuda}</p>
      ) : null}
    </div>
  );
}
