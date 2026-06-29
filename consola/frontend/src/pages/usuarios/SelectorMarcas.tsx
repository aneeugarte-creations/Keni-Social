import { Check, ChevronDown, Tag } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { type MarcaDisponible } from "@/types";

const ANCHO_PANEL = 240; // px (= w-60); se usa para alinear el panel por su borde derecho.

/**
 * Selector de marcas como CHECKLIST desplegable. El disparador muestra el CONTEO de marcas; el
 * panel, un checklist del catálogo. Se usa igual en la tabla del panel y en la subpágina de
 * detalle; al marcar/desmarcar llama `onChange` con el conjunto nuevo.
 *
 * El panel se PORTALIZA a `<body>` con posición fija (mismo patrón que `Tooltip`): así no
 * lo recorta el `overflow-auto` de la tabla. Se cierra al pulsar fuera, con Escape, o al hacer
 * scroll/resize (la posición quedaría obsoleta). En la tabla, el disparador frena la propagación
 * del clic para que abrir el selector no navegue a la fila.
 */
export function SelectorMarcas({
  marcas,
  catalogo,
  onChange,
  disabled,
  align = "start",
  className,
}: {
  /** Ids de marca seleccionados. */
  marcas: string[];
  /** Catálogo canónico (id + nombre). */
  catalogo: MarcaDisponible[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  /** Borde por el que se alinea el panel respecto al disparador. */
  align?: "start" | "end";
  className?: string;
}) {
  const [abierto, setAbierto] = React.useState(false);
  const [pos, setPos] = React.useState<{ left: number; top: number } | null>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const panelRef = React.useRef<HTMLDivElement>(null);

  const recalcular = React.useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const left = align === "end" ? r.right - ANCHO_PANEL : r.left;
    setPos({ left: Math.max(8, left), top: r.bottom + 4 });
  }, [align]);

  React.useEffect(() => {
    if (!abierto) return;
    recalcular();
    function alPulsarFuera(e: MouseEvent) {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setAbierto(false);
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    function alMover() {
      setAbierto(false); // la posición fija quedaría obsoleta al hacer scroll/resize.
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    window.addEventListener("scroll", alMover, true);
    window.addEventListener("resize", alMover);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
      window.removeEventListener("scroll", alMover, true);
      window.removeEventListener("resize", alMover);
    };
  }, [abierto, recalcular]);

  const seleccion = new Set(marcas);
  const n = marcas.length;
  const etiqueta = n === 0 ? "Sin marcas" : n === 1 ? "1 marca" : `${n} marcas`;

  const alternar = (id: string) => {
    const siguiente = new Set(seleccion);
    if (siguiente.has(id)) siguiente.delete(id);
    else siguiente.add(id);
    onChange([...siguiente]);
  };

  return (
    // stopPropagation: en la tabla la fila navega al detalle; abrir el selector no debe hacerlo.
    <div className={cn("inline-flex", className)} onClick={(e) => e.stopPropagation()}>
      <Button
        ref={triggerRef}
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        className="h-8 gap-1.5 font-normal"
        onClick={() => setAbierto((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={abierto}
      >
        <Tag className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        <span className={cn(n === 0 && "text-muted-foreground")}>{etiqueta}</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
      </Button>
      {abierto &&
        pos &&
        createPortal(
          <div
            ref={panelRef}
            role="listbox"
            aria-label="Marcas"
            style={{ left: pos.left, top: pos.top, width: ANCHO_PANEL }}
            className="fixed z-[100] max-h-72 overflow-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
          >
            {catalogo.length === 0 ? (
              <p className="px-2 py-1.5 text-sm text-muted-foreground">
                No hay catálogo de marcas.
              </p>
            ) : (
              catalogo.map((m) => {
                const activa = seleccion.has(m.id);
                return (
                  <button
                    key={m.id}
                    type="button"
                    role="option"
                    aria-selected={activa}
                    onClick={() => alternar(m.id)}
                    className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent focus:bg-accent focus:outline-none"
                  >
                    <span
                      className={cn(
                        "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                        activa
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-input",
                      )}
                      aria-hidden
                    >
                      {activa && <Check className="h-3 w-3" />}
                    </span>
                    <span className="truncate">{m.nombre}</span>
                  </button>
                );
              })
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
