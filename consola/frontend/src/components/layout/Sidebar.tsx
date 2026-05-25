import { Search } from "lucide-react";
import * as React from "react";
import { NavLink } from "react-router-dom";

import { Wordmark } from "@/components/layout/Wordmark";
import { NAVEGACION } from "@/components/layout/navegacion";
import { cn } from "@/lib/utils";

/** Buscador del sidebar estilo Vercel: input blanco con icono y atajo de teclado "F". */
function BuscadorSidebar() {
  const ref = React.useRef<HTMLInputElement>(null);

  // Atajo "F" para enfocar el buscador (se ignora si ya estas escribiendo).
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "f" && e.key !== "F") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      // En movil/escritorio hay dos instancias: enfoca solo la visible.
      if (!ref.current || ref.current.offsetParent === null) return;
      e.preventDefault();
      ref.current.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        ref={ref}
        type="text"
        placeholder="Buscar…"
        aria-label="Buscar"
        className="h-9 w-full rounded-md border border-border bg-card pl-9 pr-9 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
      <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
        F
      </kbd>
    </div>
  );
}

/**
 * Barra lateral fija con el wordmark, el buscador, los grupos de navegacion
 * (Trabajo / Ajustes) y un pie discreto. Resalta la ruta activa con fondo gris.
 */
export function Sidebar({ onNavegar }: { onNavegar?: () => void }) {
  return (
    <nav
      aria-label="Navegación principal"
      className="flex h-full w-64 flex-col border-r border-border bg-background"
    >
      <div className="flex h-14 items-center border-b border-border px-4">
        <Wordmark />
      </div>

      <div className="px-3 pt-3">
        <BuscadorSidebar />
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {NAVEGACION.map((grupo) => (
          <div key={grupo.etiqueta}>
            <p className="px-3 pb-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {grupo.etiqueta}
            </p>
            <ul className="space-y-0.5">
              {grupo.items.map((item) => {
                const Icono = item.icono;
                return (
                  <li key={item.ruta}>
                    <NavLink
                      to={item.ruta}
                      onClick={onNavegar}
                      title={item.descripcion}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                          isActive
                            ? "bg-accent font-medium text-foreground"
                            : "font-normal text-muted-foreground hover:bg-accent hover:text-foreground",
                        )
                      }
                    >
                      <Icono className="h-4 w-4 shrink-0" />
                      <span>{item.etiqueta}</span>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
        Herramienta local · 127.0.0.1
      </div>
    </nav>
  );
}
