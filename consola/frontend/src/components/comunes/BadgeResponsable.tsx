import { UserCheck } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { cn } from "@/lib/utils";

/**
 * Badge de SOLO LECTURA: muestra quién lleva una pieza («la lista») sin permitir coger/soltar
 * (eso vive en el tablero de Cobertura). Pinta "Tuya" si la llevas tú o el nombre del
 * responsable. Aparece en CUALQUIER marca cuando hay alguien asignado (`responsableId` no
 * vacío); si la pieza está libre, NO renderiza nada. «La lista» (reparto PULL) es universal.
 *
 * useContext directo (no useSesion): en tests no hay SesionProvider y el badge debe pintarse
 * igual aunque no sepamos quién mira (mismo criterio que VistaLista).
 */
export function BadgeResponsable({
  responsableId,
  responsableNombre,
  className,
}: {
  responsableId: string;
  responsableNombre: string;
  className?: string;
}) {
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const responsable = responsableNombre ?? "";
  // Solo si la pieza está cogida por alguien (en cualquier marca: «la lista» es universal).
  if (!(responsableId ?? "")) return null;
  const esMia = Boolean(usuario && responsableId === usuario.id);
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 font-normal",
        esMia
          ? "border-primary/50 text-primary"
          : "border-violet-500/40 text-violet-700 dark:text-violet-300",
        className,
      )}
      title={esMia ? "Esta pieza la llevas tú" : `Esta pieza la lleva ${responsable}`}
    >
      <UserCheck className="h-3 w-3" />
      {esMia ? "Tuya" : responsable}
    </Badge>
  );
}
