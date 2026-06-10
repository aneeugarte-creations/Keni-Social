// Barra de acciones de la selección (alinear/orden/duplicar/borrar). Presentacional: recibe la lista
// de acciones ya construida. Se monta en la franja superior del lienzo (arriba de la imagen, fuera
// de ella), no flota sobre la selección; por eso aquí no maneja posición.
//
// Cada icono lleva tooltip (con el atajo de teclado entre paréntesis cuando lo tiene). Usamos la
// variante FLOTANTE (portal) porque el tooltip CSS quedaría recortado por el overflow-x de la barra.

import type { Trash2 } from "lucide-react";

import { TooltipFlotante } from "@/components/ui/tooltip";

export type AccionLienzo = {
  icono: typeof Trash2;
  titulo: string;
  // Atajo de teclado (p. ej. "⌘D"): se muestra en el tooltip entre paréntesis.
  atajo?: string;
  onClick: () => void;
};

export function BarraAcciones({ acciones }: { acciones: AccionLienzo[] }) {
  return (
    <div className="flex max-w-full items-center gap-0.5 overflow-x-auto rounded-md border border-border bg-popover p-1 shadow-md">
      {acciones.map((a, i) => (
        <TooltipFlotante key={i} label={a.atajo ? `${a.titulo} (${a.atajo})` : a.titulo} side="bottom">
          <button onClick={a.onClick} className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
            <a.icono className="h-4 w-4" />
          </button>
        </TooltipFlotante>
      ))}
    </div>
  );
}
