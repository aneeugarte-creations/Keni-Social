import * as React from "react";

import { cn } from "@/lib/utils";

/** Posición (px) donde abrir el menú. */
interface PosicionMenu {
  x: number;
  y: number;
}

/** Item del menú contextual. Click izquierdo dispara `onClick`. */
export interface ItemMenuContextual {
  /** Texto del item. */
  etiqueta: string;
  /** Icono lucide (opcional). */
  icono?: React.ComponentType<{ className?: string }>;
  /** Acción al hacer click. */
  onClick: () => void;
  /** Si está activo (chip a la izquierda). Útil para "Cambiar franja". */
  activo?: boolean;
  /** Si el item es destructivo (rojo). */
  destructivo?: boolean;
  /** Si el item está deshabilitado. */
  deshabilitado?: boolean;
}

/** Separador entre grupos de items. */
export interface SeparadorMenuContextual {
  separador: true;
}

export type EntradaMenuContextual = ItemMenuContextual | SeparadorMenuContextual;

function esSeparador(e: EntradaMenuContextual): e is SeparadorMenuContextual {
  return (e as SeparadorMenuContextual).separador === true;
}

/**
 * Menú contextual (right-click) reutilizable. El padre envuelve el área disparadora con
 * `<MenuContextualDisparador>` y pasa los items; el menú se renderiza en `position:
 * fixed` en la coordenada del click, se cierra al hacer click fuera o pulsar Escape.
 *
 * No añade dependencias: comparte patrón con `CuentaUsuario` (avatar dropdown).
 */
export function MenuContextual({
  children,
  items,
  disparador = "contextmenu",
}: {
  children: React.ReactNode;
  items: EntradaMenuContextual[];
  /**
   * Qué evento abre el menú. `contextmenu` (default) preserva el comportamiento histórico
   * de right-click; `click` lo dispara con left-click; `ambos` acepta cualquiera de los
   * dos. Útil cuando el chip debe responder al toque primario sin botón derecho.
   */
  disparador?: "contextmenu" | "click" | "ambos";
}) {
  const [pos, setPos] = React.useState<PosicionMenu | null>(null);
  const menuRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!pos) return;
    function alPulsarFuera(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setPos(null);
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") setPos(null);
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [pos]);

  function alAbrir(e: React.MouseEvent) {
    e.preventDefault();
    setPos({ x: e.clientX, y: e.clientY });
  }

  const usaContextMenu = disparador === "contextmenu" || disparador === "ambos";
  const usaClick = disparador === "click" || disparador === "ambos";

  return (
    <>
      <div
        onContextMenu={usaContextMenu ? alAbrir : undefined}
        onClick={usaClick ? alAbrir : undefined}
      >
        {children}
      </div>
      {pos && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="Acciones del turno"
          className="fixed z-50 min-w-[12rem] overflow-hidden rounded-md border border-border bg-popover py-1 text-popover-foreground shadow-md"
          style={{ left: pos.x, top: pos.y }}
        >
          {items.map((entrada, i) => {
            if (esSeparador(entrada)) {
              return (
                <div
                  key={`sep-${i}`}
                  className="my-1 border-t border-border"
                  aria-hidden="true"
                />
              );
            }
            const Icono = entrada.icono;
            return (
              <button
                key={`${entrada.etiqueta}-${i}`}
                type="button"
                role="menuitem"
                disabled={entrada.deshabilitado}
                onClick={() => {
                  setPos(null);
                  entrada.onClick();
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-sm transition-colors",
                  "hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50",
                  entrada.destructivo
                    ? "text-destructive hover:bg-destructive/10"
                    : "text-foreground",
                )}
              >
                {Icono && (
                  <Icono
                    className={cn(
                      "h-4 w-4 shrink-0",
                      entrada.destructivo ? "text-destructive" : "text-muted-foreground",
                    )}
                  />
                )}
                <span className="flex-1">{entrada.etiqueta}</span>
                {entrada.activo && <span className="text-xs text-muted-foreground">●</span>}
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}
