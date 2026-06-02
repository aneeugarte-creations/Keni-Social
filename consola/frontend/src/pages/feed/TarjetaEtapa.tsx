/**
 * Badge de ETAPA IA de una pieza en el Feed de ideación (Flujo D, Fase 4).
 *
 * Pinta el estado de la cadena IA en vivo ("Generando copy / Generando arte / Lista para
 * revisar / Aprobada …"), con un punto que PULSA mientras la IA trabaja la pieza. La etapa
 * la deriva `etapaDePublicacion` (ver `etapa.ts`); cuando el Flujo C exponga la etapa real
 * por pieza, esta tarjeta no cambia: solo cambia la fuente del valor.
 */
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

import { META_ETAPA, type EtapaIa } from "./etapa";

export function BadgeEtapa({ etapa, className }: { etapa: EtapaIa; className?: string }) {
  const meta = META_ETAPA[etapa];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        meta.enCurso
          ? "bg-amber-500/15 text-amber-700 dark:text-amber-300"
          : etapa === "lista_para_revisar"
            ? "bg-sky-500/15 text-sky-700 dark:text-sky-300"
            : "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
        className,
      )}
      title={meta.enCurso ? "La IA aún está trabajando esta pieza" : undefined}
    >
      {meta.enCurso ? (
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
      ) : (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            etapa === "lista_para_revisar" ? "bg-sky-500" : "bg-emerald-500",
          )}
          aria-hidden="true"
        />
      )}
      {meta.etiqueta}
    </span>
  );
}
