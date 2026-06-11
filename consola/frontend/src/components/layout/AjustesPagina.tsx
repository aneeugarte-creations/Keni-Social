import { X } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";

/**
 * Panel lateral CONTROLADO de AJUSTES de página. El reparto canónico de la cabecera es: UN solo
 * menú "⋮" (`MenuAcciones`) que aloja TANTO las acciones puntuales COMO la entrada «Ajustes», y
 * ESTE panel temporal que esa entrada abre (overlay por la derecha; cierra con Escape, clic fuera
 * o la X). Ya no monta su propio botón en la barra: el disparador vive dentro del "⋮", para que la
 * barra superior quede limpia (solo pestañas + "⋮"). Lo abre/cierra quien lo monta (`MenuAcciones`)
 * vía `abierto`/`onCerrar`. Los filtros de vista efímeros (rango temporal, buscadores) NO van aquí.
 */
export function PanelAjustesLateral({
  titulo = "Ajustes",
  descripcion,
  abierto,
  onCerrar,
  children,
}: {
  titulo?: string;
  descripcion?: string;
  abierto: boolean;
  onCerrar: () => void;
  children: React.ReactNode;
}) {
  React.useEffect(() => {
    if (!abierto) return;
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCerrar();
    };
    document.addEventListener("keydown", alEscape);
    return () => document.removeEventListener("keydown", alEscape);
  }, [abierto, onCerrar]);

  if (!abierto) return null;
  return createPortal(
    <div className="fixed inset-0 z-50">
      {/* Telón: cierra al clic fuera (el panel es temporal, no una página). */}
      <div
        className="absolute inset-0 bg-black/40"
        aria-hidden="true"
        onClick={onCerrar}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-border bg-background shadow-xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0 space-y-0.5">
            <h2 className="text-sm font-semibold tracking-tight">{titulo}</h2>
            {descripcion && <p className="text-xs text-muted-foreground">{descripcion}</p>}
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
            aria-label="Cerrar ajustes"
            onClick={onCerrar}
          >
            <X className="h-4 w-4" />
          </Button>
        </header>
        {/* Capa BASE del panel: las áreas (secciones colapsables) se apilan PLANAS, cada una
            con su propio divisor superior (`border-t`); sin tarjetas ni cajas anidadas. */}
        <div className="flex-1 overflow-y-auto px-4 py-1">{children}</div>
      </aside>
    </div>,
    document.body,
  );
}
