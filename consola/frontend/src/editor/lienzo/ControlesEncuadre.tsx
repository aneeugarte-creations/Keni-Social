// Controles de ENCUADRE + zoom (raíl vertical al lado del lienzo, FUERA de la foto para no tapar
// el campo visual). Imán, rejilla (+ tamaño de celda) y "dentro del marco" son toggles
// INDEPENDIENTES; sus preferencias se guardan en localStorage en el componente padre.
// Presentacional: recibe el estado y los setters/handlers por props.

import { Frame, Grid3x3, Magnet, Maximize, Minus, Plus } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";

import { CELDAS } from "./lib";

export function ControlesEncuadre({
  iman,
  setIman,
  grid,
  setGrid,
  tamCelda,
  setTamCelda,
  dentroMarco,
  setDentroMarco,
  escala,
  alejar,
  acercar,
  zoomReal,
  ajustarPantalla,
}: {
  iman: boolean;
  setIman: Dispatch<SetStateAction<boolean>>;
  grid: boolean;
  setGrid: Dispatch<SetStateAction<boolean>>;
  tamCelda: number;
  setTamCelda: (px: number) => void;
  dentroMarco: boolean;
  setDentroMarco: Dispatch<SetStateAction<boolean>>;
  escala: number;
  alejar: () => void;
  acercar: () => void;
  zoomReal: () => void;
  ajustarPantalla: () => void;
}) {
  return (
    <div className="flex shrink-0 flex-col items-center gap-0.5 self-center rounded-md border border-border bg-popover/90 p-0.5 shadow">
      <button
        title="Imán: ajustar a objetos, bordes y márgenes"
        onClick={() => setIman((v) => !v)}
        className={`rounded p-1 hover:bg-accent ${iman ? "bg-accent text-foreground" : "text-muted-foreground"}`}
      >
        <Magnet className="h-3.5 w-3.5" />
      </button>
      <button
        title="Rejilla y ajuste a rejilla"
        onClick={() => setGrid((g) => !g)}
        className={`rounded p-1 hover:bg-accent ${grid ? "bg-accent text-foreground" : "text-muted-foreground"}`}
      >
        <Grid3x3 className="h-3.5 w-3.5" />
      </button>
      {grid && (
        <select
          title="Tamaño de celda de la rejilla (px)"
          value={tamCelda}
          onChange={(e) => setTamCelda(Number(e.target.value))}
          className="rounded bg-transparent px-0.5 text-xs tabular-nums outline-none hover:bg-accent"
        >
          {CELDAS.map((c) => (
            <option key={c.px} value={c.px}>{c.etiqueta}px</option>
          ))}
        </select>
      )}
      <button
        title="Mantener las capas dentro del marco"
        onClick={() => setDentroMarco((v) => !v)}
        className={`rounded p-1 hover:bg-accent ${dentroMarco ? "bg-accent text-foreground" : "text-muted-foreground"}`}
      >
        <Frame className="h-3.5 w-3.5" />
      </button>
      <div className="my-0.5 h-px w-4 bg-border" />
      <button title="Alejar" onClick={alejar} className="rounded p-1 hover:bg-accent">
        <Minus className="h-3.5 w-3.5" />
      </button>
      <button title="100% (tamaño real, ⌘0 ajusta a pantalla)" onClick={zoomReal} className="rounded px-1 text-xs tabular-nums hover:bg-accent">
        {Math.round(escala * 100)}%
      </button>
      <button title="Acercar (⌘+)" onClick={acercar} className="rounded p-1 hover:bg-accent">
        <Plus className="h-3.5 w-3.5" />
      </button>
      <button title="Ajustar a la pantalla (⌘0)" onClick={ajustarPantalla} className="rounded p-1 hover:bg-accent">
        <Maximize className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
