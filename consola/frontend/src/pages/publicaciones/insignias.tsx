import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { iconoRed, metaEstado, nombreRed } from "./meta";

/** Badge coloreado según el estado de la publicación. */
export function BadgeEstado({ estado, className }: { estado: string; className?: string }) {
  const m = metaEstado(estado);
  return <Badge className={cn(m.clase, className)}>{m.nombre}</Badge>;
}

/** Etiqueta de red con su icono. */
export function EtiquetaRed({
  red,
  nombre,
  className,
}: {
  red: string;
  nombre?: string;
  className?: string;
}) {
  const Icono = iconoRed(red);
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm", className)}>
      <Icono className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      {nombre || nombreRed(red)}
    </span>
  );
}
