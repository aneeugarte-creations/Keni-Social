import { SlidersHorizontal, X } from "lucide-react";
import * as React from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";

/**
 * Panel lateral de AJUSTES de página, el reparto canónico de la cabecera:
 *   - ACCIONES (comandos puntuales) → menú "⋮" (`MenuAcciones`).
 *   - AJUSTES (configuración persistente de lo que la página gobierna) → ESTE panel.
 * Un botón de deslizadores en la barra (vía `<AccionesPagina/>`) abre un panel lateral
 * TEMPORAL por la derecha (overlay; cierra con Escape, clic fuera o la X). Los filtros
 * de vista efímeros (rango temporal, buscadores) NO van aquí: se quedan inline.
 */
export function AjustesPagina({
  titulo = "Ajustes",
  descripcion,
  etiqueta = "Ajustes de la página",
  abiertoInicial = false,
  children,
}: {
  titulo?: string;
  descripcion?: string;
  /** Etiqueta accesible del botón que abre el panel. */
  etiqueta?: string;
  /** Abre el panel ya desplegado (deep-links tipo `?ajustes=1`). */
  abiertoInicial?: boolean;
  children: React.ReactNode;
}) {
  const [abierto, setAbierto] = React.useState(abiertoInicial);

  React.useEffect(() => {
    if (!abierto) return;
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("keydown", alEscape);
    return () => document.removeEventListener("keydown", alEscape);
  }, [abierto]);

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-muted-foreground hover:text-foreground"
        aria-label={etiqueta}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        onClick={() => setAbierto(true)}
      >
        <SlidersHorizontal className="h-4 w-4" />
      </Button>
      {abierto &&
        createPortal(
          <div className="fixed inset-0 z-50">
            {/* Telón: cierra al clic fuera (el panel es temporal, no una página). */}
            <div
              className="absolute inset-0 bg-black/40"
              aria-hidden="true"
              onClick={() => setAbierto(false)}
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
                  {descripcion && (
                    <p className="text-xs text-muted-foreground">{descripcion}</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
                  aria-label="Cerrar ajustes"
                  onClick={() => setAbierto(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </header>
              <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">{children}</div>
            </aside>
          </div>,
          document.body,
        )}
    </>
  );
}
