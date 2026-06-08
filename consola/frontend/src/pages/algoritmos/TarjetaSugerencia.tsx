import { Check, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/Markdown";
import type { SugerenciaEditorial } from "@/types";

/** Tarjeta de una sugerencia editorial (digest diario). */
export function TarjetaSugerencia({
  sugerencia,
  onAplicar,
  onDescartar,
  ocupada,
}: {
  sugerencia: SugerenciaEditorial;
  onAplicar: (s: SugerenciaEditorial) => void;
  onDescartar: (s: SugerenciaEditorial) => void;
  ocupada: boolean;
}) {
  const esLimite = sugerencia.tipo === "limite";
  return (
    <li className="rounded-lg border border-border/60 p-3">
      <div className="flex flex-wrap items-center gap-1.5 pb-1">
        <Badge variant="outline">{sugerencia.plataforma_nombre || sugerencia.plataforma}</Badge>
        <Badge
          variant="outline"
          className={
            esLimite
              ? "border-violet-500/40 text-violet-700 dark:text-violet-300"
              : "border-sky-500/40 text-sky-700 dark:text-sky-300"
          }
        >
          {esLimite ? "Límite" : "Ficha editorial"}
        </Badge>
      </div>
      <p className="text-sm font-medium">{sugerencia.titulo}</p>
      {sugerencia.detalle && (
        <div className="pt-1">
          <Markdown className="text-xs text-muted-foreground">{sugerencia.detalle}</Markdown>
        </div>
      )}
      <div className="flex items-center justify-end gap-1 pt-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onAplicar(sugerencia)}
          disabled={ocupada}
          title={
            esLimite
              ? "Marcar como atendida (los límites se cambian en el código)"
              : "Añadir esta propuesta a la ficha editorial de la plataforma"
          }
        >
          <Check className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
          {esLimite ? "Atendida" : "Aplicar a la ficha"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onDescartar(sugerencia)}
          disabled={ocupada}
          title="Descartar"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
    </li>
  );
}
