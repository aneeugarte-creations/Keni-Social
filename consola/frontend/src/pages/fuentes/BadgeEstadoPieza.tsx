/**
 * Estado de la pieza auto-generada desde un volcado interno (clip de Claro Sports,
 * nota de Presidencia): generando el copy → lista en el feed → aún sin pieza. Mismo
 * vocabulario visual en todos los cajones de Fuentes.
 */
import { CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";

type EstadoPieza = "generando" | "lista" | "sin_pieza";

export function BadgeEstadoPieza({
  estado,
  tituloGenerando = "Redactando copy automático…",
}: {
  estado: EstadoPieza;
  tituloGenerando?: string;
}) {
  if (estado === "generando") {
    return (
      <Badge variant="aviso" className="gap-1" title={tituloGenerando}>
        <Spinner className="h-3 w-3" />
        Generando…
      </Badge>
    );
  }
  if (estado === "lista") {
    return (
      <Badge variant="ok" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        En el feed
      </Badge>
    );
  }
  return <Badge variant="secondary">Sin pieza</Badge>;
}
