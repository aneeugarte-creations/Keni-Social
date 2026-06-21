/**
 * Atribución por usuario: muestra "por <usuario>" de quien creó un
 * registro (publicación, entrada de historial, tarea, generación). El estado es
 * COMPARTIDO entre el equipo y cada registro lleva su autor.
 *
 * RETROCOMPATIBLE: los registros legados/anónimos (creados antes de la atribución, o
 * por el token de mantenimiento) no traen autor (`autor_nombre === ""`); se muestran
 * como "desconocido" sin romper nada. La lógica de etiqueta vive en `./atribucion` para
 * no romper el fast-refresh (y evita la colisión de nombre con `Autor.tsx` en FS
 * insensibles a mayúsculas).
 */
import { User } from "lucide-react";

import { cn } from "@/lib/utils";

import { AUTOR_DESCONOCIDO, etiquetaAutor } from "./atribucion";

export function Autor({
  nombre,
  className,
  conPrefijo = true,
}: {
  /** Nombre del autor (`autor_nombre`). "" / undefined => "desconocido". */
  nombre: string | null | undefined;
  className?: string;
  /** `true` (def.): "por <usuario>". `false`: solo el nombre (sin el "por", p. ej. en el feed). */
  conPrefijo?: boolean;
}) {
  const etiqueta = conPrefijo ? etiquetaAutor(nombre) : (nombre ?? "").trim() || AUTOR_DESCONOCIDO;
  return (
    <span
      className={cn("inline-flex items-center gap-1 text-muted-foreground", className)}
    >
      <User className="h-3.5 w-3.5" />
      {etiqueta}
    </span>
  );
}
