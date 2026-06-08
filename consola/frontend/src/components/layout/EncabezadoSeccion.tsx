import { NavLink, useLocation } from "react-router-dom";

import { rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import { pestanasDeRuta } from "@/components/layout/hub-tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { cn } from "@/lib/utils";

/**
 * Barra de cabecera UNIFICADA de la sección, encima del `<Outlet/>`. Reemplaza al antiguo
 * `SubnavHub`: ahora SIEMPRE es la misma barra para todas las páginas (misma altura, ancho
 * y posición), con tres zonas:
 *   - PESTAÑAS (izquierda): si la ruta cae en un hub con 2+ pestañas, se pintan aquí.
 *   - Hueco de TÍTULO (izquierda): si es una página plana, su `<TituloPagina/>` se portaliza
 *     aquí con el formato de una pestaña activa. (Hub y título son excluyentes por diseño.)
 *   - Hueco de ACCIONES (derecha): el menú "⋯" o los controles que la página portalice.
 *
 * Los huecos los entrega el `AppShell` por contexto (refs `refInicio`/`refAcciones`). La barra
 * solo se pinta —y toma su borde inferior— cuando hay pestañas o un título montado; en una
 * página aún sin título ni pestañas queda colapsada (sin hueco visual).
 */
export function EncabezadoSeccion({
  refInicio,
  refAcciones,
  tituloPresente,
}: {
  refInicio: (el: HTMLElement | null) => void;
  refAcciones: (el: HTMLElement | null) => void;
  tituloPresente: boolean;
}) {
  const { pathname } = useLocation();
  const { marcaActiva } = useMarcaActiva();
  const pestanas = pestanasDeRuta(pathname)?.filter((p) =>
    rutaVisibleParaMarca(p.ruta, marcaActiva),
  );
  // Hub solo si quedan 2+ pestañas tras el gating por marca (si no, no hay nada que conmutar).
  const hayTabs = !!pestanas && pestanas.length >= 2;
  const visible = hayTabs || tituloPresente;

  return (
    <nav
      aria-label="Cabecera de sección"
      className={cn(
        "mb-6 flex min-h-9 flex-wrap items-center gap-1 border-border",
        visible ? "border-b" : "hidden",
      )}
    >
      {hayTabs &&
        pestanas.map((pestana) => {
          const Icono = pestana.icono;
          return (
            <NavLink
              key={pestana.ruta}
              to={pestana.ruta}
              end={pestana.end}
              className={({ isActive }) =>
                cn(
                  // `-mb-px` solapa el borde inferior de la barra para que la pestaña activa
                  // "muerda" la línea (subrayado de acento continuo).
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

      {/* Hueco del título de página plana (portal). Excluyente con las pestañas. */}
      <div ref={refInicio} className="flex items-center" />

      {/* Hueco de acciones, a la derecha (portal). */}
      <div ref={refAcciones} className="ml-auto flex items-center gap-2" />
    </nav>
  );
}
