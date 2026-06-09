// Barra de acciones de la selección (alinear/orden/duplicar/borrar). Presentacional: recibe la lista
// de acciones ya construida. Se monta en la franja superior del lienzo (arriba de la imagen, fuera
// de ella), no flota sobre la selección; por eso aquí no maneja posición.

import type { Trash2 } from "lucide-react";

export type AccionLienzo = { icono: typeof Trash2; titulo: string; onClick: () => void };

export function BarraAcciones({ acciones }: { acciones: AccionLienzo[] }) {
  return (
    <div className="flex max-w-full items-center gap-0.5 overflow-x-auto rounded-md border border-border bg-popover p-1 shadow-md">
      {acciones.map((a, i) => (
        <button key={i} title={a.titulo} onClick={a.onClick} className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
          <a.icono className="h-4 w-4" />
        </button>
      ))}
    </div>
  );
}
