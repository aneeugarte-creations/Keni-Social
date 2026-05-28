import { Activity, Bot } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

/**
 * Subnavegación de la sección Agentes. Coloca dos pestañas (`/agentes` y
 * `/agentes/actividad`) que dan acceso al catálogo y al monitor de runs
 * respectivamente. La presentación imita a `Tabs` de shadcn pero usa `NavLink`
 * para que el activo dependa de la URL, no de estado local.
 */
export function TabsAgentes() {
  return (
    <nav aria-label="Pestañas de Agentes" className="mb-4">
      <div className="inline-flex h-9 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground">
        <NavLink
          to="/agentes"
          end
          className={({ isActive }) =>
            cn(
              "inline-flex items-center gap-1.5 rounded-sm px-3 py-1 text-sm font-medium transition-colors",
              isActive ? "bg-background text-foreground shadow-sm" : "hover:text-foreground",
            )
          }
        >
          <Bot className="h-4 w-4" aria-hidden="true" />
          Agentes
        </NavLink>
        <NavLink
          to="/agentes/actividad"
          className={({ isActive }) =>
            cn(
              "inline-flex items-center gap-1.5 rounded-sm px-3 py-1 text-sm font-medium transition-colors",
              isActive ? "bg-background text-foreground shadow-sm" : "hover:text-foreground",
            )
          }
        >
          <Activity className="h-4 w-4" aria-hidden="true" />
          Actividad IA
        </NavLink>
      </div>
    </nav>
  );
}
