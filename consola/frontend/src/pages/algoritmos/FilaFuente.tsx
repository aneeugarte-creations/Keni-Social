import { CircleCheck, CircleX, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { FuenteAlgoritmo } from "@/types";

/** Fila de una fuente (salud + activar/borrar). */
export function FilaFuente({
  fuente,
  onToggle,
  onBorrar,
  ocupada,
}: {
  fuente: FuenteAlgoritmo;
  onToggle: (f: FuenteAlgoritmo) => void;
  onBorrar: (f: FuenteAlgoritmo) => void;
  ocupada: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-border/60 py-2 last:border-0">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          {fuente.ultimo_error ? (
            <CircleX className="h-3.5 w-3.5 shrink-0 text-rose-500" aria-hidden="true" />
          ) : (
            <CircleCheck className="h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden="true" />
          )}
          <p className="truncate text-sm font-medium">{fuente.nombre}</p>
          <Badge variant="outline">{fuente.plataforma_nombre || fuente.plataforma}</Badge>
          {fuente.tipo === "oficial" && (
            <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
              Oficial
            </Badge>
          )}
        </div>
        <p className="truncate text-xs text-muted-foreground">
          {fuente.ultimo_error
            ? fuente.ultimo_error
            : `${fuente.ultimo_conteo} noticia(s)${
                fuente.ultima_actualizacion ? ` · ${fuente.ultima_actualizacion}` : ""
              }`}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Switch
          checked={fuente.activo}
          onCheckedChange={() => onToggle(fuente)}
          disabled={ocupada}
          aria-label={fuente.activo ? "Desactivar fuente" : "Activar fuente"}
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onBorrar(fuente)}
          disabled={ocupada}
          aria-label="Borrar fuente"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </div>
    </li>
  );
}
