/**
 * Badges del PROCESO de Investigación visibles por historia (ADR 0011).
 *
 *  - `ChipMarca`: la marca de la historia como chip discreto.
 *  - `BadgeVerificacionFuente`: la VERIFICACIÓN de la fuente (`verificacion_fuente`):
 *    'no_verificado' = la fuente pasó la verificación sin problemas (deja pasar a copy) → «Verificada»;
 *    'problema' = la verificación encontró un problema de peso → «Problema en la fuente». Nada si vacío.
 *
 *  Línea visual calcada de los badges de Pipelines (`BadgeVerificacionFuente`): discretos, sin saturar la
 *  tarjeta.
 */
import { AlertTriangle, OctagonAlert, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Historia } from "@/types";

/** Chip discreto de la MARCA de la historia. */
export function ChipMarca({ historia, className }: { historia: Historia; className?: string }) {
  const nombre = historia.marca_nombre || historia.marca;
  if (!nombre) return null;
  return (
    <span className={cn("inline-flex items-center gap-1", className)} data-testid="chip-marca">
      <Badge variant="outline" className="font-normal text-muted-foreground">
        {nombre}
      </Badge>
    </span>
  );
}

/** Badge de la VERIFICACIÓN de la fuente (verificación por historia, ADR 0011). Nada si vacío. */
export function BadgeVerificacionFuente({
  verificacion_fuente,
  className,
}: {
  verificacion_fuente?: string;
  className?: string;
}) {
  if (!verificacion_fuente) return null;
  if (verificacion_fuente === "rechazado") {
    return (
      <Tooltip label="Rechazada en la fuente (falsa o problema de peso)" side="top">
        <Badge
          variant="secondary"
          className={cn(
            "gap-1 border border-destructive/30 bg-destructive/10 text-destructive",
            className,
          )}
          data-testid="badge-verificacion-rechazada"
        >
          <OctagonAlert className="h-3 w-3" aria-hidden="true" />
          Rechazada en la fuente
        </Badge>
      </Tooltip>
    );
  }
  if (verificacion_fuente === "requiere_humano") {
    return (
      <Tooltip label="La IA no pudo verificarla; requiere revisión humana" side="top">
        <Badge
          variant="aviso"
          className={cn("gap-1", className)}
          data-testid="badge-verificacion-requiere-humano"
        >
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          Requiere revisión
        </Badge>
      </Tooltip>
    );
  }
  if (verificacion_fuente === "verificado") {
    return (
      <Tooltip label="Confirmada con fuentes fiables" side="top">
        <Badge variant="ok" className={cn("gap-1", className)} data-testid="badge-verificacion-verificada">
          <ShieldCheck className="h-3 w-3" aria-hidden="true" />
          Verificada
        </Badge>
      </Tooltip>
    );
  }
  return null;
}
