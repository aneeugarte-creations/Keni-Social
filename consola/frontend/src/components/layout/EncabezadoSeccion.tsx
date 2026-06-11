import { NavLink, useLocation } from "react-router-dom";

import { rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import { pestanasDeRuta } from "@/components/layout/hub-tabs";
import { SelectorSeccion } from "@/components/layout/SelectorSeccion";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { cn } from "@/lib/utils";

/**
 * Cabecera de sección UNIFICADA, dentro de la barra superior (donde antes estaban los
 * breadcrumbs), a la izquierda del control de marca/filtros y las notificaciones. Tres zonas
 * contiguas:
 *   - SECCIÓN: si la ruta cae en un hub con 2+ pestañas, se pinta de DOS formas según el ancho:
 *       · ESCRITORIO (`md+`): la tira de pestañas horizontal de siempre (la activa muerde el
 *         borde inferior del header).
 *       · MÓVIL (`<md`): un DROPDOWN compacto (`SelectorSeccion`), que no ocupa una fila entera.
 *   - Hueco de TÍTULO: si es una página plana, su `<TituloPagina/>` se portaliza aquí.
 *     (Hub y título son excluyentes por diseño.)
 *   - Hueco de ACCIONES: el menú "⋮" (vertical) o los controles que la página portalice, JUNTO
 *     a la sección/título.
 *
 * Los huecos los entrega el `AppShell` por contexto (refs `refInicio`/`refAcciones`).
 * `refAcciones` es OPCIONAL: en las rutas del editor el AppShell coloca el hueco de acciones
 * en un carril CENTRADO de la barra (patrón Canva) en vez de junto al título; entonces esta
 * cabecera no pinta su hueco propio.
 */
export function EncabezadoSeccion({
  refInicio,
  refAcciones,
}: {
  refInicio: (el: HTMLElement | null) => void;
  refAcciones?: (el: HTMLElement | null) => void;
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
      {hayTabs && (
        <>
          {/* ESCRITORIO: tira de pestañas a altura completa; la activa muerde el borde del header. */}
          <div className="hidden h-full items-stretch md:flex">
            {pestanas.map((pestana) => {
              const Icono = pestana.icono;
              return (
                <NavLink
                  key={pestana.ruta}
                  to={pestana.ruta}
                  end={pestana.end}
                  className={({ isActive }) =>
                    cn(
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
          </div>

          {/* MÓVIL: el mismo conjunto de pestañas, como dropdown compacto. */}
          <div className="flex items-center md:hidden">
            <SelectorSeccion pestanas={pestanas} pathname={pathname} />
          </div>
        </>
      )}

      {/* Hueco del título de página plana (portal). Excluyente con la sección. `min-w-0`
          deja ENCOGER el hueco en móvil para que el `truncate` del título actúe (sin esto
          el control de marca de la derecha lo pisaba). */}
      <div ref={refInicio} className="flex min-w-0 items-center" />

      {/* Hueco de acciones, JUNTO a la sección/título (portal). En el editor no se pinta:
          el AppShell ofrece el carril centrado en su lugar. */}
      {refAcciones && <div ref={refAcciones} className="flex min-w-0 items-center" />}
    </nav>
  );
}
