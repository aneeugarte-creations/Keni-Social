// Controles de ENCUADRE + zoom (raíl vertical al lado del lienzo, FUERA de la foto para no tapar
// el campo visual). Imán, rejilla (+ tamaño de celda) y "dentro del marco" son toggles
// INDEPENDIENTES; sus preferencias se guardan en localStorage en el componente padre.
// Presentacional: recibe el estado y los setters/handlers por props.
//
// El botón del PORCENTAJE abre un menú de niveles estilo Canva (10–300 %, "Ajustar" y "100 %" =
// 1 px del documento : 1 px de pantalla). Todos los iconos llevan tooltip con su atajo.

import { Check, Frame, Grid3x3, Magnet, Maximize, Minus, Plus } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useState } from "react";

import { TooltipFlotante } from "@/components/ui/tooltip";

import { useCerrarConEscape } from "../Telon";
import { CELDAS, PASOS_ZOOM } from "./lib";

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
  fijarEscala,
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
  // Fija la escala efectiva (px doc : px pantalla) a un nivel absoluto del menú (0.1 => 10 %).
  fijarEscala: (esc: number) => void;
}) {
  const [menuZoom, setMenuZoom] = useState(false);
  useCerrarConEscape(menuZoom, () => setMenuZoom(false));
  const pctActual = Math.round(escala * 100);

  // Fila del menú de zoom (texto a la izquierda, atajo/check a la derecha).
  const fila = (etiqueta: string, onClick: () => void, derecha?: ReactNode, activo = false) => (
    <button
      key={etiqueta}
      onClick={() => {
        onClick();
        setMenuZoom(false);
      }}
      className={`flex w-full items-center justify-between gap-3 rounded px-2 py-1 text-left text-xs tabular-nums hover:bg-accent ${
        activo ? "text-foreground" : "text-muted-foreground"
      }`}
    >
      <span>{etiqueta}</span>
      {derecha}
    </button>
  );

  return (
    <div className="relative flex shrink-0 flex-col items-center gap-0.5 self-center rounded-md border border-border bg-popover/90 p-0.5 shadow">
      <TooltipFlotante label="Imán: ajustar a objetos, bordes y márgenes" side="left">
        <button
          onClick={() => setIman((v) => !v)}
          aria-pressed={iman}
          className={`rounded p-1 hover:bg-accent ${iman ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Magnet className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>
      <TooltipFlotante label="Rejilla y ajuste a rejilla" side="left">
        <button
          onClick={() => setGrid((g) => !g)}
          aria-pressed={grid}
          className={`rounded p-1 hover:bg-accent ${grid ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Grid3x3 className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>
      {grid && (
        <select
          title="Tamaño de celda de la rejilla (px)"
          aria-label="Tamaño de celda de la rejilla (px)"
          value={tamCelda}
          onChange={(e) => setTamCelda(Number(e.target.value))}
          className="rounded bg-transparent px-0.5 text-xs tabular-nums outline-none hover:bg-accent"
        >
          {CELDAS.map((c) => (
            <option key={c.px} value={c.px}>{c.etiqueta}px</option>
          ))}
        </select>
      )}
      <TooltipFlotante label="Mantener las capas dentro del marco" side="left">
        <button
          onClick={() => setDentroMarco((v) => !v)}
          aria-pressed={dentroMarco}
          className={`rounded p-1 hover:bg-accent ${dentroMarco ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Frame className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>
      <div className="my-0.5 h-px w-4 bg-border" />
      <TooltipFlotante label="Alejar (⌘−)" side="left">
        <button onClick={alejar} className="rounded p-1 hover:bg-accent">
          <Minus className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>
      <TooltipFlotante label="Nivel de zoom" side="left">
        <button
          onClick={() => setMenuZoom((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={menuZoom}
          className={`rounded px-1 text-xs tabular-nums hover:bg-accent ${menuZoom ? "bg-accent" : ""}`}
        >
          {pctActual}%
        </button>
      </TooltipFlotante>
      <TooltipFlotante label="Acercar (⌘+)" side="left">
        <button onClick={acercar} className="rounded p-1 hover:bg-accent">
          <Plus className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>
      <TooltipFlotante label="Ajustar a la pantalla (⌘0)" side="left">
        <button onClick={ajustarPantalla} className="rounded p-1 hover:bg-accent">
          <Maximize className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>

      {menuZoom && (
        <>
          {/* Telón transparente: clic fuera cierra el menú. */}
          <div className="fixed inset-0 z-40" onClick={() => setMenuZoom(false)} />
          <div
            role="menu"
            aria-label="Nivel de zoom"
            className="absolute bottom-0 right-full z-50 mr-1.5 w-44 rounded-md border border-border bg-popover p-1 shadow-md"
          >
            {fila("Ajustar a la pantalla", ajustarPantalla, <kbd className="text-[10px] text-muted-foreground">⌘0</kbd>)}
            {fila("100 % (tamaño real)", zoomReal, <kbd className="text-[10px] text-muted-foreground">⇧0</kbd>)}
            <div className="my-1 h-px bg-border" />
            {PASOS_ZOOM.map((p) => {
              const pct = Math.round(p * 100);
              return fila(
                `${pct} %`,
                () => fijarEscala(p),
                pct === pctActual ? <Check className="h-3 w-3" /> : undefined,
                pct === pctActual,
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
