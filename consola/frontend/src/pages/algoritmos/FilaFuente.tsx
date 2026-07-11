import { CircleCheck, CircleX, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
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
  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Borrar la fuente "${fuente.nombre}"? Esta acción no se puede deshacer.`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        )
          onBorrar(fuente);
      },
      destructivo: true,
    },
  ];

  return (
    <FilaConAcciones
      como="li"
      kebab="nunca"
      realce
      acciones={acciones}
      className="rounded-xl border bg-card p-2.5 pr-10"
    >
      <div className="flex items-center justify-between gap-3 min-w-0 flex-1">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            {fuente.ultimo_error ? (
              <CircleX className="h-3.5 w-3.5 shrink-0 text-red-500" aria-hidden="true" />
            ) : (
              <CircleCheck className="h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden="true" />
            )}
            <p className="truncate text-sm font-medium">{fuente.nombre}</p>
            <Badge variant="outline">{fuente.plataforma_nombre || fuente.plataforma}</Badge>
            {fuente.tipo === "oficial" && <Badge variant="info">Oficial</Badge>}
          </div>
          {fuente.ultimo_error ? (
            <p className="truncate text-xs text-red-600 dark:text-red-400">{fuente.ultimo_error}</p>
          ) : (
            <p className="truncate text-xs text-muted-foreground">
              {fuente.ultimo_conteo} noticia(s)
              {fuente.ultima_actualizacion ? ` · ${fuente.ultima_actualizacion}` : ""}
            </p>
          )}
        </div>
        <Switch
          checked={fuente.activo}
          onCheckedChange={() => onToggle(fuente)}
          disabled={ocupada}
          aria-label={fuente.activo ? "Desactivar fuente" : "Activar fuente"}
        />
      </div>
    </FilaConAcciones>
  );
}
