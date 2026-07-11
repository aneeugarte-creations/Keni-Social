/**
 * Lienzo en vivo del editor de placa inline: el `<canvas>` (previa en vivo, arrastrable para
 * reencuadrar), el editor IN PLACE del titular superpuesto, y debajo la pista de uso + el contador
 * "Faltan X de N fotos". Es PRESENTACIONAL: toda la lógica (render, punteros, estado) vive en el
 * componente padre `EditorPlacaInline` y se pasa por props.
 */
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";

export interface LienzoPlacaProps {
  /** Ref al `<canvas>` (lo gobierna el padre: render + tamaño + capturas de puntero). */
  canvasRef: React.RefObject<HTMLCanvasElement>;
  /** Formato del lienzo (px) para el aspect-ratio del canvas. */
  lienzo: { w: number; h: number };
  /** ¿Las fuentes del documento están cargadas? (si no, muestra el spinner). */
  fuentesListas: boolean;
  /** ¿El hueco activo tiene foto? (cursor "move" vs "pointer"). */
  hayFotoActiva: boolean;
  onPointerDown: (e: React.PointerEvent<HTMLCanvasElement>) => void;
  onPointerMove: (e: React.PointerEvent<HTMLCanvasElement>) => void;
  onPointerUp: (e: React.PointerEvent<HTMLCanvasElement>) => void;
  /** Titular en vivo (copy-in), editable IN PLACE sobre el lienzo. */
  copyIn: string;
  onCopyInCambio?: (valor: string) => void;
  /** ¿Se está editando el titular in place? */
  editandoTitular: boolean;
  onTerminarTitular: () => void;
  /** Caja (px CSS) donde situar el editor del titular, o null si no aplica. */
  cajaTitular: { left: number; top: number; width: number; height: number } | null;
  /** ¿El collage tiene varios huecos? (cambia la pista y muestra el contador). */
  esCollage: boolean;
  /** ¿El titular es editable? (cambia la pista de uso). */
  titularEditable: boolean;
  /** Huecos sin foto (sobre el total). */
  faltan: number;
  /** Nº total de huecos del diseño. */
  nHuecos: number;
  /**
   * Capa(s) DOM superpuestas sobre el área EXACTA del canvas (el wrapper `relative` que ciñe el
   * lienzo): tratamiento "SIN LICENCIA" y badge de fuente. Se ancla a la foto, no a la tarjeta.
   */
  superpuesto?: React.ReactNode;
}

export function LienzoPlaca({
  canvasRef,
  lienzo,
  fuentesListas,
  hayFotoActiva,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  copyIn,
  onCopyInCambio,
  editandoTitular,
  onTerminarTitular,
  cajaTitular,
  esCollage,
  titularEditable,
  faltan,
  nHuecos,
  superpuesto,
}: LienzoPlacaProps) {
  return (
    <>
      {/* Lienzo en vivo: resolución real, escalado por CSS. Arrastrable para reencuadrar el hueco
          tocado; el titular es clicable y reescribible in place. */}
      <div className="flex justify-center rounded-xl border bg-muted/20 p-2">
        {!fuentesListas ? (
          <div className="flex h-56 items-center justify-center">
            <Spinner className="h-5 w-5 text-muted-foreground" />
          </div>
        ) : (
          <div className="relative inline-block">
            <canvas
              ref={canvasRef}
              className="block max-h-[22rem] w-auto rounded-md"
              style={{
                aspectRatio: `${lienzo.w} / ${lienzo.h}`,
                cursor: hayFotoActiva ? "move" : "pointer",
                touchAction: "none",
              }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            />
            {/* Tratamiento de stock anclado a la FOTO (el lienzo), no a la tarjeta. */}
            {superpuesto}
            {editandoTitular && cajaTitular && (
              <textarea
                autoFocus
                value={copyIn}
                onChange={(e) => onCopyInCambio?.(e.target.value)}
                onBlur={onTerminarTitular}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault();
                    onTerminarTitular();
                  }
                }}
                placeholder="Escribe el titular…"
                className="absolute resize-none overflow-hidden rounded-sm bg-black/55 p-1 text-center font-bold uppercase leading-tight text-white shadow-lg outline-none ring-2 ring-primary placeholder:text-white/60"
                style={{
                  left: cajaTitular.left,
                  top: cajaTitular.top,
                  width: cajaTitular.width,
                  height: cajaTitular.height,
                  fontSize: Math.max(11, cajaTitular.height * 0.16),
                }}
              />
            )}
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {esCollage
            ? "Toca un hueco para elegir su foto o arrastra para encuadrar"
            : titularEditable
              ? "Toca el titular para reescribirlo · toca la imagen para cambiar"
              : "Toca la imagen para añadir o cambiar la foto"}
        </p>
        {esCollage && (
          <Badge variant={faltan > 0 ? "aviso" : "ok"} className="shrink-0">
            {faltan > 0 ? `Faltan ${faltan} de ${nHuecos} fotos` : `${nHuecos} de ${nHuecos} fotos`}
          </Badge>
        )}
      </div>
    </>
  );
}
