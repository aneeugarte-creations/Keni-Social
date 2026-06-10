import { NavLink, useLocation } from "react-router-dom";

import { rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import { pestanasDeRuta } from "@/components/layout/hub-tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { cn } from "@/lib/utils";

/**
 * Cabecera de sección UNIFICADA: ahora vive DENTRO de la barra superior (donde antes estaban
 * los breadcrumbs), a la izquierda de los switches de marca y las notificaciones. Es la misma
 * barra para todas las páginas, con tres zonas contiguas (todas a la izquierda):
 *   - PESTAÑAS: si la ruta cae en un hub con 2+ pestañas, se pintan aquí.
 *   - Hueco de TÍTULO: si es una página plana, su `<TituloPagina/>` se portaliza aquí con el
 *     formato de una pestaña activa. (Hub y título son excluyentes por diseño.)
 *   - Hueco de ACCIONES: el menú "⋮" (vertical) o los controles que la página portalice, JUNTO
 *     a las pestañas/título.
 *
 * Los huecos los entrega el `AppShell` por contexto (refs `refInicio`/`refAcciones`). Como
 * vive en el header (altura fija de la barra), las pestañas ocupan todo el alto y su subrayado
 * de acento "muerde" el borde inferior del header.
 */
export function EncabezadoSeccion({
  refInicio,
  refAcciones,
}: {
  refInicio: (el: HTMLElement | null) => void;
  refAcciones: (el: HTMLElement | null) => void;
}) {
  const { pathname } = useLocation();
  const { marcaActiva } = useMarcaActiva();
  const pestanas = pestanasDeRuta(pathname)?.filter((p) =>
    rutaVisibleParaMarca(p.ruta, marcaActiva),
  );
  // Hub solo si quedan 2+ pestañas tras el gating por marca (si no, no hay nada que conmutar).
  const hayTabs = !!pestanas && pestanas.length >= 2;

  return (
    <nav
      aria-label="Cabecera de sección"
      className="flex h-full min-w-0 items-stretch gap-1 self-stretch"
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
                  // `-mb-px` solapa el borde inferior del header para que la pestaña activa
                  // "muerda" la línea (subrayado de acento continuo con el borde de la barra).
                  "-mb-px flex items-center gap-2 border-b-2 px-3 text-sm transition-colors",
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

      {/* Hueco del título de página plana (portal). Excluyente con las pestañas. `items-stretch`
          para que el título (con su subrayado) ocupe todo el alto y muerda el borde como un tab. */}
      <div ref={refInicio} className="flex items-stretch" />

      {/* Hueco de acciones, JUNTO a las pestañas/título (portal). */}
      <div ref={refAcciones} className="flex items-center" />
    </nav>
  );
}
