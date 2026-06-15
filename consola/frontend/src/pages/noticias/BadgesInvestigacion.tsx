/**
 * Badges del PROCESO de Investigación visibles por historia (ADR 0011).
 *
 *  - `ChipMarca`: la marca de la historia como chip discreto; si la asignó el clasificador IA
 *    (`marca_clasificada_por_ia`), un mini-badge «IA» a su lado.
 *  - `BadgeVeredictoFuente`: el veredicto de VERIFICACIÓN de la fuente (`verificar_veredicto`):
 *    'no_verificado' = la fuente pasó la criba sin problemas (deja pasar a copy) → «Verificada»;
 *    'problema' = la criba encontró un problema de peso → «Problema en la fuente». Nada si vacío.
 *
 *  Línea visual calcada de los badges de Pipelines (`BadgeQaFuente`): discretos, sin saturar la
 *  tarjeta.
 */
import { OctagonAlert, ShieldCheck, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Historia } from "@/types";

/** Chip discreto de la MARCA de la historia + mini-badge «IA» si la asignó el clasificador. */
export function ChipMarca({ historia, className }: { historia: Historia; className?: string }) {
  const nombre = historia.marca_nombre || historia.marca;
  if (!nombre) return null;
  return (
    <span className={cn("inline-flex items-center gap-1", className)} data-testid="chip-marca">
      <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
        {nombre}
      </Badge>
      {historia.marca_clasificada_por_ia && (
        <Tooltip label="Marca asignada por IA" side="top">
          <Badge
            variant="outline"
            className="gap-0.5 border-violet-500/30 px-1 text-[10px] text-violet-600"
            data-testid="badge-marca-ia"
          >
            <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
            IA
          </Badge>
        </Tooltip>
      )}
    </span>
  );
}

/** Badge del VEREDICTO de verificación de la fuente (QA por historia, ADR 0011). Nada si vacío. */
export function BadgeVeredictoFuente({
  veredicto,
  className,
}: {
  veredicto?: string;
  className?: string;
}) {
  if (!veredicto) return null;
  if (veredicto === "problema") {
    return (
      <Tooltip label="Problema detectado en la fuente" side="top">
        <Badge
          variant="secondary"
          className={cn(
            "gap-1 border border-destructive/30 bg-destructive/10 text-destructive",
            className,
          )}
          data-testid="badge-veredicto-problema"
        >
          <OctagonAlert className="h-3 w-3" aria-hidden="true" />
          Problema en la fuente
        </Badge>
      </Tooltip>
    );
  }
  if (veredicto === "no_verificado") {
    return (
      <Tooltip label="Fuente verificada, sin problemas" side="top">
        <Badge variant="ok" className={cn("gap-1", className)} data-testid="badge-veredicto-verificada">
          <ShieldCheck className="h-3 w-3" aria-hidden="true" />
          Verificada
        </Badge>
      </Tooltip>
    );
  }
  return null;
}
