// Barra de acciones flotante sobre la capa/selección (alinear/orden/duplicar/borrar). Presentacional:
// recibe la lista de acciones ya construida y el rect en pantalla que envuelve la selección.

import type { Trash2 } from "lucide-react";

export type AccionLienzo = { icono: typeof Trash2; titulo: string; onClick: () => void };

// Alto aproximado de la barra (botones h-4 + padding) más una holgura, para colocarla pegada
// a la selección sin solaparla.
const ALTO_BARRA = 38;

export function BarraAcciones({
  acciones,
  rectSel,
}: {
  acciones: AccionLienzo[];
  rectSel: { x: number; y: number; w: number; h: number };
}) {
  // Por defecto va ARRIBA de la selección. Si no cabe (selección pegada al borde superior del
  // lienzo, donde la barra quedaría solapada por encima de la imagen), la VOLTEAMOS debajo.
  const arriba = rectSel.y - ALTO_BARRA;
  const top = arriba >= 0 ? arriba : rectSel.y + rectSel.h + 6;
  return (
    <div
      className="absolute z-10 flex items-center gap-0.5 rounded-md border border-border bg-popover p-1 shadow-md"
      style={{ left: Math.max(0, rectSel.x), top }}
    >
      {acciones.map((a, i) => (
        <button key={i} title={a.titulo} onClick={a.onClick} className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
          <a.icono className="h-4 w-4" />
        </button>
      ))}
    </div>
  );
}
