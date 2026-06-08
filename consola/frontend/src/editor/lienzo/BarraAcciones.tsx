// Barra de acciones flotante sobre la capa/selección (alinear/orden/duplicar/borrar). Presentacional:
// recibe la lista de acciones ya construida y el rect en pantalla que envuelve la selección.

import type { Trash2 } from "lucide-react";

export type AccionLienzo = { icono: typeof Trash2; titulo: string; onClick: () => void };

export function BarraAcciones({
  acciones,
  rectSel,
}: {
  acciones: AccionLienzo[];
  rectSel: { x: number; y: number; w: number };
}) {
  return (
    <div
      className="absolute z-10 flex items-center gap-0.5 rounded-md border border-border bg-popover p-1 shadow-md"
      style={{ left: Math.max(0, rectSel.x), top: Math.max(0, rectSel.y - 38) }}
    >
      {acciones.map((a, i) => (
        <button key={i} title={a.titulo} onClick={a.onClick} className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
          <a.icono className="h-4 w-4" />
        </button>
      ))}
    </div>
  );
}
