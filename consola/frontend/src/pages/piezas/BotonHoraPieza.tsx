/**
 * Editor INLINE de la hora de una pieza programada, directamente sobre su píldora del
 * calendario: el texto de la hora es un botón que abre un popover anclado con un campo de
 * hora (CDMX) para personalizar el instante de ESE post sin abrir el editor completo ni el
 * diálogo de reprogramar. Conserva el DÍA; solo cambia HH:MM. El padre (`VistaCalendario`)
 * recibe la nueva hora "HH:MM" (CDMX) y la persiste con su mutación `reprogramar`.
 *
 * Para mover también el día están el atajo «Cambiar también el día…» (abre el diálogo de
 * reprogramar) y el arrastre entre columnas de la semana.
 */
import { CheckCircle2, Loader2 } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";

import { origenBajoDisparador, type PosicionMenu } from "@/components/comunes/menuPos";
import { Button } from "@/components/ui/button";
import { isoADatetimeLocal } from "@/lib/fecha";
import { cn } from "@/lib/utils";

import { formatearHoraOperativa } from "./meta";

const RE_HORA = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** "HH:mm" (24h CDMX) de un instante ISO, para sembrar el campo de hora. */
function horaCdmx(iso: string | null | undefined): string {
  return isoADatetimeLocal(iso).slice(11, 16);
}

export function BotonHoraPieza({
  iso,
  ocupado,
  onGuardar,
  onOtroDia,
  horaSugerida,
  className,
}: {
  /** Instante programado (UTC ISO) de la pieza. */
  iso: string | null | undefined;
  /** Mutación en vuelo: bloquea el guardado y muestra spinner. */
  ocupado: boolean;
  /** Persistir la nueva hora "HH:MM" (CDMX) conservando el día. */
  onGuardar: (hhmm: string) => void;
  /** Abrir el flujo de cambiar también el día (diálogo de reprogramar). */
  onOtroDia: () => void;
  /** Mejor hora ("HH:MM" CDMX) para esta red, o null si no hay sugerencia. */
  horaSugerida?: string | null;
  className?: string;
}) {
  const [abierto, setAbierto] = React.useState(false);
  const triggerRef = React.useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        disabled={ocupado}
        onClick={(e) => {
          // El click NO debe burbujear al chip (arrastre / menú): solo abre el editor de hora.
          e.stopPropagation();
          setAbierto(true);
        }}
        title="Cambiar la hora de este post"
        className={cn(
          "shrink-0 rounded tabular-nums underline decoration-dotted decoration-transparent underline-offset-2 transition-colors hover:decoration-current focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-60",
          className,
        )}
      >
        {formatearHoraOperativa(iso)}
      </button>
      {abierto &&
        createPortal(
          <PopoverHora
            anchor={triggerRef.current}
            horaInicial={horaCdmx(iso)}
            horaSugerida={horaSugerida}
            ocupado={ocupado}
            onGuardar={(hhmm) => {
              onGuardar(hhmm);
              setAbierto(false);
            }}
            onOtroDia={() => {
              setAbierto(false);
              onOtroDia();
            }}
            onCerrar={() => setAbierto(false)}
          />,
          document.body,
        )}
    </>
  );
}

/**
 * Popover anclado bajo la hora con un campo `time` (CDMX) + Guardar. Se posiciona en
 * `position: fixed` bajo el disparador (misma idiom que `MenuFlotante`), se reubica si
 * se sale del viewport y se cierra con click fuera o Escape.
 */
function PopoverHora({
  anchor,
  horaInicial,
  horaSugerida,
  ocupado,
  onGuardar,
  onOtroDia,
  onCerrar,
}: {
  anchor: HTMLElement | null;
  horaInicial: string;
  horaSugerida?: string | null;
  ocupado: boolean;
  onGuardar: (hhmm: string) => void;
  onOtroDia: () => void;
  onCerrar: () => void;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [hora, setHora] = React.useState(horaInicial);
  const [pos, setPos] = React.useState<PosicionMenu>(() =>
    anchor ? origenBajoDisparador(anchor.getBoundingClientRect()) : { x: 0, y: 0 },
  );

  // Cierra al hacer click fuera o pulsar Escape.
  React.useEffect(() => {
    function alPulsarFuera(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onCerrar();
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") onCerrar();
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [onCerrar]);

  // Tras montar, mide y desplaza el popover si se sale del viewport (borde derecho/inferior).
  React.useLayoutEffect(() => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const margen = 8;
    let { x, y } = pos;
    if (r.right > window.innerWidth - margen) {
      x = Math.max(margen, window.innerWidth - r.width - margen);
    }
    if (r.bottom > window.innerHeight - margen) {
      y = Math.max(margen, window.innerHeight - r.height - margen);
    }
    if (x !== pos.x || y !== pos.y) setPos({ x, y });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Enfoca el campo al abrir para teclear la hora sin ratón.
  React.useEffect(() => {
    ref.current?.querySelector<HTMLInputElement>("input")?.focus();
  }, []);

  const valida = RE_HORA.test(hora);
  // Solo ofrecemos la sugerencia si es una hora válida y distinta de la del campo.
  const sugerencia =
    horaSugerida && RE_HORA.test(horaSugerida) && horaSugerida !== hora ? horaSugerida : null;

  function guardar() {
    if (!valida || ocupado) return;
    onGuardar(hora);
  }

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Cambiar la hora del post"
      className="pointer-events-auto fixed z-50 w-60 rounded-md border border-border bg-popover p-3 text-popover-foreground shadow-md"
      style={{ left: pos.x, top: pos.y }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          guardar();
        }
      }}
    >
      <p className="mb-2 text-xs font-medium text-muted-foreground">Hora del post · CDMX</p>
      <div className="flex items-center gap-2">
        <input
          type="time"
          value={hora}
          onChange={(e) => setHora(e.target.value)}
          aria-label="Hora (CDMX)"
          className="h-9 flex-1 rounded-md border border-input bg-background px-2 text-sm tabular-nums focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <Button type="button" size="sm" onClick={guardar} disabled={ocupado || !valida}>
          {ocupado ? <Loader2 className="h-4 w-4 animate-spin" /> : "Guardar"}
        </Button>
      </div>
      {sugerencia && (
        <button
          type="button"
          onClick={() => onGuardar(sugerencia)}
          disabled={ocupado}
          aria-label={`Usar la mejor hora para publicar: ${sugerencia}`}
          className="mt-2 flex w-full items-center gap-2 rounded-md border bg-muted/30 px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-muted/50 disabled:opacity-60"
        >
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>
            Mejor hora:{" "}
            <strong className="font-semibold tabular-nums text-foreground">{sugerencia}</strong>
          </span>
        </button>
      )}
      <button
        type="button"
        onClick={onOtroDia}
        className="mt-2 text-xs text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline"
      >
        Cambiar también el día…
      </button>
    </div>
  );
}
