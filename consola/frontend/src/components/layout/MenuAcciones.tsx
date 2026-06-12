import { MoreVertical, SlidersHorizontal, type LucideIcon } from "lucide-react";
import * as React from "react";

import { PanelAjustesLateral } from "@/components/layout/AjustesPagina";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Menú de acciones "⋮" minimalista (sin dependencia de dropdown): un botón fantasma con tres
 * puntos VERTICALES que despliega un panel con los comandos de la página. Vive junto a las
 * pestañas, en la barra superior (vía `<AccionesPagina/>`). Cierra al hacer clic fuera, con
 * Escape o al elegir un comando. Para comandos puntuales; los controles que deban verse siempre
 * (un selector de rango, p. ej.) se portalizan sueltos, no aquí dentro.
 *
 * Los AJUSTES de la página también viven AQUÍ (slot `ajustes`): el "⋮" muestra una entrada
 * «Ajustes» arriba del todo que abre el panel lateral (`PanelAjustesLateral`). Así la barra
 * superior queda limpia —solo pestañas y "⋮"—, sin un botón de deslizadores aparte. Las acciones
 * (`children`) son opcionales: una página puede tener solo ajustes, solo acciones, o ambas.
 */
export function MenuAcciones({
  children,
  etiqueta = "Acciones",
  ajustes,
  ajustesTitulo,
  ajustesAbiertoInicial = false,
}: {
  children?: React.ReactNode;
  etiqueta?: string;
  /** Contenido del panel de ajustes. Si se pasa, el "⋮" muestra la entrada «Ajustes». */
  ajustes?: React.ReactNode;
  ajustesTitulo?: string;
  /** Abre el panel ya desplegado al montar (deep-links, p. ej. `?cadencia=1`). */
  ajustesAbiertoInicial?: boolean;
}) {
  const [abierto, setAbierto] = React.useState(false);
  const [ajustesAbierto, setAjustesAbierto] = React.useState(ajustesAbiertoInicial);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!abierto) return;
    const alClicFuera = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false);
    };
    const alEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAbierto(false);
    };
    document.addEventListener("mousedown", alClicFuera);
    document.addEventListener("keydown", alEscape);
    return () => {
      document.removeEventListener("mousedown", alClicFuera);
      document.removeEventListener("keydown", alEscape);
    };
  }, [abierto]);

  return (
    <div ref={ref} className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-muted-foreground hover:text-foreground"
        aria-label={etiqueta}
        aria-haspopup="menu"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        <MoreVertical className="h-4 w-4" />
      </Button>
      {abierto && (
        <div
          role="menu"
          className="absolute left-0 z-50 mt-1 min-w-44 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
          onClick={() => setAbierto(false)}
        >
          {ajustes && (
            <>
              <ItemMenu icono={SlidersHorizontal} onClick={() => setAjustesAbierto(true)}>
                Ajustes
              </ItemMenu>
              {children && <div role="separator" className="my-1 h-px bg-border" />}
            </>
          )}
          {children}
        </div>
      )}
      {ajustes && (
        <PanelAjustesLateral
          titulo={ajustesTitulo}
          abierto={ajustesAbierto}
          onCerrar={() => setAjustesAbierto(false)}
        >
          {ajustes}
        </PanelAjustesLateral>
      )}
    </div>
  );
}

/** Un comando dentro de `<MenuAcciones/>`. */
export function ItemMenu({
  children,
  onClick,
  icono: Icono,
  disabled,
  className,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  icono?: LucideIcon;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
    >
      {Icono && <Icono className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
      <span className="truncate">{children}</span>
    </button>
  );
}
