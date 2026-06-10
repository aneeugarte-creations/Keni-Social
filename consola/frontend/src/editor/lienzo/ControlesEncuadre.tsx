// Controles de ENCUADRE + zoom en una BARRA INFERIOR estilo Canva: franja delgada (~36 px) a lo
// ancho del área del lienzo, FUERA de la foto para no tapar el campo visual. Imán, rejilla
// (+ tamaño de celda), "dentro del marco" y "zonas seguras" son toggles INDEPENDIENTES; sus
// preferencias se guardan en localStorage en el componente padre. Presentacional: recibe el
// estado y los setters/handlers por props.
//
// Colocación (como Canva): a la IZQUIERDA los toggles de encuadre (en pantallas estrechas se
// pliegan en un menú "⋯"); a la DERECHA el bloque de zoom: slider compacto (md+), −/+, el botón
// del PORCENTAJE —que abre el menú de niveles (10–300 %, "Ajustar" y "100 %" = 1 px del documento
// : 1 px de pantalla)— y "ajustar a la pantalla". Todos los iconos llevan tooltip con su atajo.

import { Check, Frame, Grid3x3, Magnet, Maximize, Minus, MoreHorizontal, Plus, Shield } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import { useState } from "react";

import { TooltipFlotante } from "@/components/ui/tooltip";

import { useCerrarConEscape } from "../Telon";
import { CELDAS, ESCALA_MAX, ESCALA_MIN, PASOS_ZOOM } from "./lib";

export function ControlesEncuadre({
  iman,
  setIman,
  grid,
  setGrid,
  tamCelda,
  setTamCelda,
  dentroMarco,
  setDentroMarco,
  zonas,
  setZonas,
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
  // Zonas seguras del formato: velo sobre las franjas que la UI de la plataforma tapa.
  zonas: boolean;
  setZonas: Dispatch<SetStateAction<boolean>>;
  escala: number;
  alejar: () => void;
  acercar: () => void;
  zoomReal: () => void;
  ajustarPantalla: () => void;
  // Fija la escala efectiva (px doc : px pantalla) a un nivel absoluto del menú (0.1 => 10 %).
  fijarEscala: (esc: number) => void;
}) {
  const [menuZoom, setMenuZoom] = useState(false);
  // Menú "⋯" (solo visible en pantallas estrechas): aloja los toggles de encuadre que no caben.
  const [menuMas, setMenuMas] = useState(false);
  useCerrarConEscape(menuZoom, () => setMenuZoom(false));
  useCerrarConEscape(menuMas, () => setMenuMas(false));
  const pctActual = Math.round(escala * 100);

  // Fila del menú de zoom, con el MISMO tratamiento visual en todas: texto a la izquierda y, a la
  // derecha, atajo (kbd, si lo hay) + check del nivel actual (reserva su hueco siempre, para que
  // las filas no bailen).
  const fila = (etiqueta: string, onClick: () => void, opts: { atajo?: string; activo?: boolean } = {}) => (
    <button
      key={etiqueta}
      onClick={() => {
        onClick();
        setMenuZoom(false);
      }}
      className={`flex w-full items-center justify-between gap-3 rounded px-2 py-1 text-left text-xs tabular-nums hover:bg-accent ${
        opts.activo ? "text-foreground" : "text-muted-foreground"
      }`}
    >
      <span>{etiqueta}</span>
      <span className="flex items-center gap-1">
        {opts.atajo && <kbd className="text-[10px] text-muted-foreground">{opts.atajo}</kbd>}
        <Check aria-hidden className={`h-3 w-3 ${opts.activo ? "" : "invisible"}`} />
      </span>
    </button>
  );

  // Toggles de ENCUADRE (mismos handlers, tooltips y aria de siempre). Un único fragmento que se
  // pinta o bien en la barra (sm+) o bien dentro del menú "⋯" (pantallas estrechas).
  const toggles = (
    <>
      <TooltipFlotante label="Imán: ajustar a objetos, bordes y márgenes" side="top">
        <button
          onClick={() => setIman((v) => !v)}
          aria-pressed={iman}
          className={`rounded p-1 hover:bg-accent ${iman ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Magnet className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>
      <TooltipFlotante label="Rejilla y ajuste a rejilla" side="top">
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
      <TooltipFlotante label="Mantener las capas dentro del marco" side="top">
        <button
          onClick={() => setDentroMarco((v) => !v)}
          aria-pressed={dentroMarco}
          className={`rounded p-1 hover:bg-accent ${dentroMarco ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Frame className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>
      <TooltipFlotante label="Zonas seguras: la interfaz de la red puede tapar lo sombreado" side="top">
        <button
          onClick={() => setZonas((v) => !v)}
          aria-pressed={zonas}
          className={`rounded p-1 hover:bg-accent ${zonas ? "bg-accent text-foreground" : "text-muted-foreground"}`}
        >
          <Shield className="h-3.5 w-3.5" />
        </button>
      </TooltipFlotante>
    </>
  );

  return (
    <div className="mt-1.5 flex h-9 w-full shrink-0 items-center justify-between gap-2 rounded-md border border-border bg-popover/90 px-1.5 shadow">
      {/* IZQUIERDA: toggles de encuadre, en línea (sm+). */}
      <div className="hidden min-w-0 items-center gap-0.5 sm:flex">{toggles}</div>

      {/* IZQUIERDA compacta (sm-): los toggles se pliegan en un menú "⋯". */}
      <div className="relative sm:hidden">
        <TooltipFlotante label="Opciones de encuadre" side="top">
          <button
            onClick={() => setMenuMas((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={menuMas}
            className={`rounded p-1 hover:bg-accent ${menuMas ? "bg-accent text-foreground" : "text-muted-foreground"}`}
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </button>
        </TooltipFlotante>
        {menuMas && (
          <>
            {/* Telón transparente: clic fuera cierra el menú. */}
            <div className="fixed inset-0 z-40" onClick={() => setMenuMas(false)} />
            <div
              role="menu"
              aria-label="Opciones de encuadre"
              className="absolute bottom-full left-0 z-50 mb-1.5 flex items-center gap-0.5 rounded-md border border-border bg-popover p-1 shadow-md"
            >
              {toggles}
            </div>
          </>
        )}
      </div>

      {/* DERECHA: bloque de zoom (slider compacto md+, −/%, +, ajustar). El menú de niveles se
          abre HACIA ARRIBA, anclado a este bloque. */}
      <div className="relative flex shrink-0 items-center gap-0.5">
        <input
          type="range"
          aria-label="Zoom"
          min={Math.round(ESCALA_MIN * 100)}
          max={Math.round(ESCALA_MAX * 100)}
          value={Math.max(Math.round(ESCALA_MIN * 100), Math.min(Math.round(ESCALA_MAX * 100), pctActual))}
          onChange={(e) => fijarEscala(Number(e.target.value) / 100)}
          className="mr-1 hidden h-1 w-24 cursor-pointer accent-primary md:block"
        />
        <TooltipFlotante label="Alejar (⌘−)" side="top">
          <button onClick={alejar} className="rounded p-1 hover:bg-accent">
            <Minus className="h-3.5 w-3.5" />
          </button>
        </TooltipFlotante>
        <TooltipFlotante label="Nivel de zoom" side="top">
          <button
            onClick={() => setMenuZoom((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={menuZoom}
            className={`min-w-11 rounded px-1 py-0.5 text-center text-xs tabular-nums hover:bg-accent ${menuZoom ? "bg-accent" : ""}`}
          >
            {pctActual}%
          </button>
        </TooltipFlotante>
        <TooltipFlotante label="Acercar (⌘+)" side="top">
          <button onClick={acercar} className="rounded p-1 hover:bg-accent">
            <Plus className="h-3.5 w-3.5" />
          </button>
        </TooltipFlotante>
        <TooltipFlotante label="Ajustar a la pantalla (⌘0 · ⌥⌘0)" side="top">
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
              className="absolute bottom-full right-0 z-50 mb-1.5 w-44 rounded-md border border-border bg-popover p-1 shadow-md"
            >
              {fila("Ajustar a la pantalla", ajustarPantalla, { atajo: "⌘0 · ⌥⌘0" })}
              {fila("100 % (tamaño real)", zoomReal, { atajo: "⇧0", activo: pctActual === 100 })}
              <div className="my-1 h-px bg-border" />
              {PASOS_ZOOM.map((p) => {
                const pct = Math.round(p * 100);
                return fila(`${pct} %`, () => fijarEscala(p), { activo: pct === pctActual });
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
