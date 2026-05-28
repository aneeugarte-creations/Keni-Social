import { NavLink } from "react-router-dom";
import { type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export interface ItemTabHub {
  /** Ruta absoluta del tab (NavLink la consume tal cual). */
  ruta: string;
  etiqueta: string;
  icono: LucideIcon;
  /**
   * Si es `true`, el tab solo se marca activo cuando la URL coincide
   * exactamente; útil para el tab "raíz" de un hub que comparte prefijo con
   * los demás (p.ej. `/agentes` vs `/agentes/actividad`).
   */
  end?: boolean;
}

/**
 * Pestañas reutilizables para los hubs de la consola (Investigación, Revisión,
 * Analíticas, Parrilla, Agentes). Imita visualmente `Tabs` de shadcn pero usa
 * `NavLink` para que el activo dependa de la URL — así las sub-rutas son
 * compartibles y un refresh recae en el mismo tab.
 */
export function TabsHub({
  items,
  etiquetaAria = "Pestañas de la sección",
}: {
  items: ItemTabHub[];
  etiquetaAria?: string;
}) {
  return (
    <nav aria-label={etiquetaAria} className="mb-4">
      <div className="inline-flex h-9 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground">
        {items.map(({ ruta, etiqueta, icono: Icono, end }) => (
          <NavLink
            key={ruta}
            to={ruta}
            end={end}
            className={({ isActive }) =>
              cn(
                "inline-flex items-center gap-1.5 rounded-sm px-3 py-1 text-sm font-medium transition-colors",
                isActive
                  ? "bg-background text-foreground shadow-sm"
                  : "hover:text-foreground",
              )
            }
          >
            <Icono className="h-4 w-4" aria-hidden="true" />
            {etiqueta}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
