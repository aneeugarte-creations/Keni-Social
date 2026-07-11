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
  alinearMovil = "izquierda",
}: {
  children?: React.ReactNode;
  etiqueta?: string;
  /** Publicacion del panel de ajustes. Si se pasa, el "⋮" muestra la entrada «Ajustes». */
  ajustes?: React.ReactNode;
  ajustesTitulo?: string;
  /** Abre el panel ya desplegado al montar (deep-links, p. ej. `?horarios=1`). */
  ajustesAbiertoInicial?: boolean;
  /** Flanco al que se ancla el panel bajo `md` (en `md+` siempre a la derecha). Un "⋮"
   *  pegado al borde derecho de su barra (p. ej. la fila de chips de Métricas en móvil)
   *  debe anclar a la derecha para que el panel no desborde el viewport. */
  alinearMovil?: "izquierda" | "derecha";
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
          // El "⋮" vive en el flanco DERECHO de la barra (escritorio): el panel se ancla a su
          // borde derecho y crece hacia dentro para no salirse del viewport. En móvil el flanco
          // lo decide `alinearMovil`: a la izquierda cuando el "⋮" cae al inicio de su fila
          // (acciones de página), a la derecha cuando va pegado al borde derecho.
          className={cn(
            "absolute z-50 mt-1 min-w-44 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md",
            alinearMovil === "izquierda" ? "left-0 md:left-auto md:right-0" : "right-0",
          )}
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

/** Un comando dentro de `<MenuAcciones/>`. Con `descripcion` gana una segunda línea de
 *  contexto en muted (p. ej. el alcance de una descarga que ignora los filtros de pantalla). */
export function ItemMenu({
  children,
  onClick,
  icono: Icono,
  disabled,
  descripcion,
  className,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  icono?: LucideIcon;
  disabled?: boolean;
  descripcion?: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-start gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
    >
      {Icono && <Icono className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
      <span className="min-w-0 flex-1">
        <span className="block truncate">{children}</span>
        {descripcion && (
          <span className="mt-0.5 block text-xs text-muted-foreground">{descripcion}</span>
        )}
      </span>
    </button>
  );
}
