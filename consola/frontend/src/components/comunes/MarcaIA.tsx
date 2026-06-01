import { DollarSign, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export function MarcaIA({
  costo = false,
  className,
}: {
  costo?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn("inline-flex items-center gap-0.5", className)}
      title={costo ? "Usa IA con coste (genera imagen)" : "Usa IA"}
    >
      <Sparkles className="h-4 w-4" aria-hidden="true" />
      {costo && <DollarSign className="h-3 w-3" aria-hidden="true" />}
    </span>
  );
}
