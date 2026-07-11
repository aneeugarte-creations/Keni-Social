/**
 * Barra de reencuadre del hueco activo: arrastra la foto + zoom + "Centrar". Solo se renderiza
 * cuando el hueco activo tiene foto cargada.
 */
import { Crop, Move } from "lucide-react";

import { Button } from "@/components/ui/button";

export interface BarraReencuadreProps {
  /** ¿El collage tiene varios huecos? (muestra "Hueco X de N"). */
  esCollage: boolean;
  /** Índice (0-based) del hueco activo. */
  slotActivo: number;
  /** Nº total de huecos del diseño. */
  nHuecos: number;
  /** Reencuadre vigente del hueco activo (foco + zoom). */
  encActivo: { foco: number[]; zoom: number };
  /** Cambia el zoom del hueco activo. */
  onZoom: (valor: number) => void;
  /** Centra el hueco activo (foco [0.5,0.5], zoom 1). */
  onCentrar: () => void;
}

export function BarraReencuadre({
  esCollage,
  slotActivo,
  nHuecos,
  encActivo,
  onZoom,
  onCentrar,
}: BarraReencuadreProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
      {esCollage && (
        <span className="font-medium text-foreground">
          Hueco {slotActivo + 1} de {nHuecos}
        </span>
      )}
      <span className="flex items-center gap-1.5">
        <Move className="h-3.5 w-3.5" />
        Arrastra la foto
      </span>
      <span className="flex flex-1 items-center gap-2">
        <Crop className="h-3.5 w-3.5 shrink-0" />
        <input
          type="range"
          min={1}
          max={6}
          step={0.02}
          value={encActivo.zoom}
          onChange={(e) => onZoom(Number(e.target.value))}
          aria-label="Zoom de la foto"
          className="h-1.5 w-full min-w-[6rem] max-w-[16rem] cursor-pointer accent-primary"
        />
      </span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 px-2 text-xs"
        disabled={encActivo.foco[0] === 0.5 && encActivo.foco[1] === 0.5 && encActivo.zoom === 1}
        onClick={onCentrar}
      >
        Centrar
      </Button>
    </div>
  );
}
