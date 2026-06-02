import { NavLink, useLocation } from "react-router-dom";

import { pestanasDeRuta } from "@/components/layout/hub-tabs";
import { cn } from "@/lib/utils";

/**
 * Barra de pestañas in-page de un hub. En la nueva navegación por flujo, los hubs
 * (Investigación, Revisión, Analíticas, Parrilla) son UNA sola entrada en el
 * sidebar —para calmar la barra y no listar herramientas que se usan dentro de un
 * flujo, no sueltas—; su sub-navegación vive aquí, como pestañas horizontales
 * sobre el contenido. Se pinta sola cuando la ruta actual cae en un hub con 2+
 * pestañas; fuera de un hub (o en un hub de una sola hoja, p. ej. Activos) no
 * renderiza nada. Vive en el AppShell, encima del `<Outlet/>`.
 */
export function SubnavHub() {
  const { pathname } = useLocation();
  const pestanas = pestanasDeRuta(pathname);
  // Sin hub, o hub de una sola hoja: no hay nada que conmutar.
  if (!pestanas || pestanas.length < 2) return null;

  return (
    <nav
      aria-label="Sub-navegación de la sección"
      className="mb-6 flex flex-wrap items-center gap-1 border-b border-border"
    >
      {pestanas.map((pestana) => {
        const Icono = pestana.icono;
        return (
          <NavLink
            key={pestana.ruta}
            to={pestana.ruta}
            end={pestana.end}
            className={({ isActive }) =>
              cn(
                // `-mb-px` solapa el borde inferior de la barra para que la pestaña
                // activa "muerda" la línea (subrayado de acento continuo).
                "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm transition-colors",
                isActive
                  ? "border-foreground font-medium text-foreground"
                  : "border-transparent font-normal text-muted-foreground hover:border-border hover:text-foreground",
              )
            }
          >
            <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{pestana.etiqueta}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
