import { UserCheck } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { cn } from "@/lib/utils";

// REPARTO ("la lista"): mostrar quién lleva una pieza es del piloto de ClaroSports; el resto
// de marcas no reparte por persona, así que nunca pinta este badge.
const MARCA_REPARTO = "claro-sports";

/**
 * Badge de SOLO LECTURA: muestra quién lleva una pieza ("la lista" de ClaroSports) sin
 * permitir coger/soltar (eso vive en la Lista). Pinta "Tuya" si la llevas tú o el nombre del
 * responsable. Solo aparece en `marca === "claro-sports"` y cuando hay alguien asignado
 * (`responsableId` no vacío); en cualquier otro caso NO renderiza nada.
 *
 * useContext directo (no useSesion): en tests no hay SesionProvider y el badge debe pintarse
 * igual aunque no sepamos quién mira (mismo criterio que VistaLista).
 */
export function BadgeResponsable({
  marca,
  responsableId,
  responsableNombre,
  className,
}: {
  marca: string;
  responsableId: string;
  responsableNombre: string;
  className?: string;
}) {
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const responsable = responsableNombre ?? "";
  // Gated por marca + asignación: ClaroSports y solo si la pieza está cogida por alguien.
  if (marca !== MARCA_REPARTO || !(responsableId ?? "")) return null;
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
